#
# o2pop.py
#
# Copyright (c) 2020-2021 MURATA Yasuhisa
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT
#

import asyncio
import ssl
import sys
import socket
import argparse

import pickle
import os
import base64
import json

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

try:
    import _client_secret_data as client_secret_data
except ImportError:
    import client_secret_data

__version__ = '1.0.2'

PROG = 'o2pop'

LOCAL_HOST = '127.0.0.1'
SCOPES = ['https://mail.google.com/']

REMOTE_POP_HOST = 'pop.gmail.com'
REMOTE_POP_PORT = 995
LOCAL_POP_PORT = 8110

REMOTE_SMTP_HOST = 'smtp.gmail.com'
REMOTE_SMTP_PORT = 465
LOCAL_SMTP_PORT = 8025

STORE_DIR = ''

CLIENT_ID = None
CLIENT_SECRET = None
CLIENT_CONFIG = None

EMAIL = None
IP_ADDR = None

BLOCK_SMTP = None

def print2(label, s):
    print(f'{label} {s}')

def get_token_file(user):
    return os.path.join(STORE_DIR, 'token-' + user + '.pickle')

def get_token(user):
    token_file = get_token_file(user)
    creds = None
    if os.path.exists(token_file):
        with open(token_file, 'rb') as token:
            creds = pickle.load(token)
            creds._client_id = CLIENT_ID
            creds._client_secret = CLIENT_SECRET

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_config(
                CLIENT_CONFIG, SCOPES)
            flow.client_config['client_id'] = CLIENT_ID
            flow.client_config['client_secret'] = CLIENT_SECRET
            creds = flow.run_local_server()
        with open(token_file, 'wb') as token:
            creds._client_id = '*'
            creds._client_secret = '*'
            pickle.dump(creds, token)
    return creds.token

async def pop_init(local_reader, local_writer, remote_reader, remote_writer, verbose=None):
    # <<< +OK ... ready
    if remote_reader.at_eof():
        return 1
    s = await remote_reader.readline()
    if verbose:
        print2("<<<", s)
    local_writer.write(s)
    await local_writer.drain()

    # USER name / QUIT / CAPA
    if local_reader.at_eof():
        return 1
    s = await local_reader.readline()
    if verbose:
        print2(">>>", s)

    cmd = s.lower().rstrip()
    if cmd != b'quit' and cmd != b'capa' and (not cmd.startswith(b'user ')):
        s = b'-ERR malformed command\r\n'
        if verbose:
            print2("<<!", s)
        local_writer.write(s)
        await local_writer.drain()

        # QUIT / CAPA / USER name
        if local_reader.at_eof():
            return 1
        s = await local_reader.readline()
        if verbose:
           print2(">>>", s)
        cmd = s.lower().rstrip()

    if cmd == b'capa':
        remote_writer.write(s)
        await remote_writer.drain()

        while not remote_reader.at_eof():
            s = await remote_reader.readline()
            if verbose:
                print2("<<<", s)
            if s.startswith(b'.'):
                break
        s = b'+OK Capability list follows\r\nUSER\r\nTOP\r\nUIDL\r\n.\r\n'
        if verbose:
            print2("<<!", s)
        local_writer.write(s)
        await local_writer.drain()

        # QUIT / USER name
        if local_reader.at_eof():
            return 1
        s = await local_reader.readline()
        if verbose:
            print2(">>>", s)
        cmd = s.lower().rstrip()

    if cmd.startswith(b'user '):
        t = s.split()
        if len(t) >= 2:
            user = t[1]
        else:
            user = b''
        if verbose: # debug
            print2('User:', user)

    if cmd == b'quit':
        remote_writer.write(s)
        await remote_writer.drain()
        if remote_reader.at_eof():
            return 1
        s = await remote_reader.readline()
        if verbose:
            print2("<<<", s)
        local_writer.write(s)
        await local_writer.drain()            
        return 1

    s = b'+OK send PASS\r\n'
    if verbose:
        print2("<<!", s)
    local_writer.write(s)
    await local_writer.drain()

    # PASS string
    if local_reader.at_eof():
        return 1
    s = await local_reader.readline()
    if verbose:
        print2(">>>", s)

    # AUTH
    if args.email:
        user = EMAIL
    token = get_token(user.decode()).encode()

    auth_string = b'user=%b\1auth=Bearer %b\1\1' % (user, token)
    s = b'AUTH XOAUTH2 %b\r\n' % base64.b64encode(auth_string)
    if verbose:
        print2("!>>", s)
    remote_writer.write(s)
    await remote_writer.drain()

    # OK: <<< +OK Welcome.
    # NG: <<< + eyJzdGF0d...
    if remote_reader.at_eof():
        return 1
    s = await remote_reader.readline()
    if verbose:
        print2("<<<", s)
    
    if not s.startswith(b'+OK'):
        s = b'-ERR Bad login\r\n'
        if verbose:
            print2("<<!", s)
        local_writer.write(s)
        await local_writer.drain()
        return 1

    local_writer.write(s)
    await local_writer.drain()

    return 0

async def pipe(reader, writer, label=None):
    if label is None:
        while not reader.at_eof():
            writer.write(await reader.read(2048))
    else:
        while not reader.at_eof():
            s = await reader.readline()
            print2(label, s)
            writer.write(s)

async def handle_pop(local_reader, local_writer):
    try:
        ctx = ssl.create_default_context()
        if args.ca_file:
            ctx.load_verify_locations(cafile=args.ca_file)

        if args.verbose:
            print("Connect to " + REMOTE_POP_HOST + ":" + str(REMOTE_POP_PORT))

        remote_writer = None
        remote_reader, remote_writer = await asyncio.open_connection(
            REMOTE_POP_HOST, REMOTE_POP_PORT, ssl=ctx)

        res = await pop_init(local_reader, local_writer, remote_reader, remote_writer, args.verbose)
        if res > 0:
            return

        (label1, label2) = (None, None)
        if args.verbose:
            (label1, label2) = ('>>>', '<<<')
        pipe1 = pipe(local_reader, remote_writer, label1)
        pipe2 = pipe(remote_reader, local_writer, label2)

        await asyncio.gather(pipe1, pipe2)

    except Exception as ex:
        print(sys.exc_info()[0].__name__ + ":", ex)
        local_writer.write(b'-ERR\r\n')
        await local_writer.drain()

    finally:
        if remote_writer:
            remote_writer.close()
        local_writer.close()

def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def to_cc_count(data, exclude=None):
    found = False
    h = []
    for s in data:
        if s == b'\r\n':
            break
        t = s.lower()
        if t.startswith(b'to:') or t.startswith(b'cc:'):
            found = True
        elif found:
            t0 = t[:1]
            if t0 != b' ' and t0 != b'\t':
                found = False    
        if found:
            h.append(t)

    to_cc = b''.join(h)
    count1 = to_cc.count(b'@')
    if exclude:
        count2 = to_cc.count(exclude)
        return count1 - count2
    else:
        return count1

def remove_agent_header(data):
    i = 0
    found = False
    index = []
    for s in data:
        if s == b'\r\n':
            break
        t = s.lower()
        if t.startswith(b'user-agent:') or t.startswith(b'x-mailer:'):
            found = True
        elif found:
            t0 = t[:1]
            if t0 != b' ' and t0 != b'\t':
                found = False
        if found:
            index.append(i)
        i += 1

    while index:
        data.pop(index.pop())

async def smtp_init(local_reader, local_writer, remote_reader, remote_writer, verbose=None):
    # <<< 220 ... Service ready
    if remote_reader.at_eof():
        return 1
    s = await remote_reader.readline()
    if verbose:
        print2("<<<", s)
    local_writer.write(s)
    await local_writer.drain()

    # EHLO / QUIT
    if local_reader.at_eof():
        return 1
    s = await local_reader.readline()
    if verbose:
        print2(">>>", s)

    cmd = s.lower().rstrip()
    if cmd == b'quit':
        remote_writer.write(s)
        await remote_writer.drain()
        if remote_reader.at_eof():
            return 1
        s = await remote_reader.readline()
        if verbose:
            print2("<<<", s)
        local_writer.write(s)
        await local_writer.drain()            
        return 1

    if cmd.startswith(b'ehlo '):
        s = b'EHLO [%b]\r\n' % IP_ADDR.encode()
        if verbose:
            print2("!>>", s)
        remote_writer.write(s)
        await remote_writer.drain()

        while True:
            if remote_reader.at_eof():
                return 1
            s = await remote_reader.readline()
            if verbose:
                print2("<<<", s)
            local_writer.write(s)
            await local_writer.drain()
            if s.startswith(b'250 '):
                break

    # MAIL FROM: / AUTH PLAIN / AUTH LOGIN / QUIT
    if local_reader.at_eof():
        return 1
    s = await local_reader.readline()
    if verbose:
       print2(">>>", s)

    mail_from_buff = ''
    cmd = s.lower().rstrip()
    if cmd == b'quit':
        remote_writer.write(s)
        await remote_writer.drain()
        if remote_reader.at_eof():
            return 1
        s = await remote_reader.readline()
        if verbose:
            print2("<<<", s)
        local_writer.write(s)
        await local_writer.drain()            
        return 1

    if cmd.startswith(b'mail '):
        mail_from_buff = s
        t = s.split(b':')
        if len(t) == 2:
            user = t[1].split()[0].strip(b'<>')
        else:
            user = b''
        if verbose: # debug
            print('User:', user)
    elif cmd.startswith(b'auth plain '):
        t = base64.b64decode(s[11:]).split(b'\0')
        if len(t) == 3:
            user = t[1]
        else:
            user = b''
        if verbose: # debug
            print('User:', user)
    elif cmd.startswith(b'auth plain'):
        s = b'334\r\n'
        if verbose:
            print2("<<!", s)
        local_writer.write(s)
        await local_writer.drain()            
        if local_reader.at_eof():
            return 1
        s = await local_reader.readline()
        if verbose:
            print2(">>>", s)
        t = base64.b64decode(s).split(b'\0')
        if len(t) == 3:
            user = t[1]
        else:
            user = b''
        if verbose: # debug
            print('User:', user)
    elif cmd.startswith(b'auth login'):
        s = b'334 VXNlcm5hbWU6\r\n' # 'Username:'
        if verbose:
            print2("<<!", s)
        local_writer.write(s)
        await local_writer.drain()            
        if local_reader.at_eof():
            return 1
        s = await local_reader.readline()
        if verbose:
            print2(">>>", s)
        user = base64.b64decode(s)
        if verbose: # debug
            print('User:', user)

        s = b'334 UGFzc3dvcmQ6\r\n' # 'Password:'
        if verbose:
            print2("<<!", s)
        local_writer.write(s)
        await local_writer.drain()            
        if local_reader.at_eof():
            return 1
        s = await local_reader.readline()
        if verbose:
            print2(">>>", s)

    # AUTH
    if args.email:
        user = EMAIL
    token = get_token(user.decode()).encode()

    auth_string = b'user=%b\1auth=Bearer %b\1\1' % (user, token)
    s = b'AUTH XOAUTH2 %b\r\n' % base64.b64encode(auth_string)
    if verbose:
        print2("!>>", s)
    remote_writer.write(s)
    await remote_writer.drain()

    # OK: <<< 235 2.7.0 Accepted
    # NG: <<< 334 eyJzdGF0d...
    if remote_reader.at_eof():
        return 1
    s = await remote_reader.readline()
    if verbose:
        print2("<<<", s)
    
    if not s.startswith(b'235'):
        s = b'535 Authentication failed\r\n'
        if verbose:
            print2("<<!", s)
        local_writer.write(s)
        await local_writer.drain()

        if mail_from_buff:
            return 1

        if local_reader.at_eof():
            return 1
        s = await local_reader.readline()
        if verbose:
            print2(">>>", s)

        s = b'535 Authentication failed\r\n'
        if verbose:
            print2("<<!", s)
        local_writer.write(s)
        await local_writer.drain()

        return 1

    # MAIL FROM:
    if mail_from_buff:
        if verbose:
            print2("!>>", mail_from_buff)
        remote_writer.write(mail_from_buff)
        await remote_writer.drain()
        if remote_reader.at_eof():
            return 1
        s = await remote_reader.readline()
        if verbose:
            print2("<<<", s)

    local_writer.write(s)
    await local_writer.drain()

    if not BLOCK_SMTP:
        return 0

    # RCPT TO: / DATA
    while True:
        if local_reader.at_eof():
            return 1
        s = await local_reader.readline()
        if verbose:
            print2(">>>", s)

        cmd = s.lower().rstrip()
        if cmd == b'data':
            break

        remote_writer.write(s)
        await remote_writer.drain()
        if remote_reader.at_eof():
            return 1
        s = await remote_reader.readline()
        if verbose:
            print2("<<<", s)

        local_writer.write(s)
        await local_writer.drain()

        if cmd.startswith(b'rcpt ') or cmd.startswith(b'mail '):
            if not s.startswith(b'250'):
                return 1
        else:
            return 1

    s = b'354 Start mail input; end with <CRLF>.<CRLF>\r\n'
    if verbose:
        print2("<<!", s)
    local_writer.write(s)
    await local_writer.drain()            

    data = []
    while True:
        if local_reader.at_eof():
            return 1
        s = await local_reader.readline()
        if verbose:
            print2(">>>", s)
        data.append(s)
        if s == b'.\r\n':
            break

    block_smtp = BLOCK_SMTP
    parent = block_smtp.parent
    to_cc_max = parent.to_cc_max
    to_cc_exclude = parent.to_cc_exclude.encode()
    err = False
    if to_cc_max > 0:
        if to_cc_exclude:
            count = to_cc_count(data, to_cc_exclude)
        else:
            count = to_cc_count(data)
        if count > to_cc_max:
            err = True
            s = b'452 Too many addresses in To and Cc fields\r\n'

    if not err and parent.send_delay > 0:
        block_smtp.cancel = False
        block_smtp.run()

        task = asyncio.create_task(asyncio.sleep(60))
        block_smtp.task = task
        try:
            await asyncio.wait_for(task, timeout=None)
        except asyncio.CancelledError:
            pass

        if block_smtp.cancel:
            err = True
            s = b'451 Requested action aborted\r\n'
    
    if err:
        if verbose:
            print2("<<!", s)
        local_writer.write(s)
        await local_writer.drain()            

        s = b'QUIT\r\n'
        if verbose:
            print2("!>>", s)
        remote_writer.write(s)
        await remote_writer.drain()
        if remote_reader.at_eof():
            return 1
        s = await remote_reader.readline()
        if verbose:
            print2("<<<", s)
        return 1

    if parent.remove_header:
        remove_agent_header(data)

    s = b'DATA\r\n'
    if verbose:
        print2("!>>", s)
    remote_writer.write(s)
    await remote_writer.drain()
    if remote_reader.at_eof():
        return 1
    s = await remote_reader.readline()
    if verbose:
        print2("<<<", s)

    for s in data:
        if verbose:
            print2("!>>", s)
        remote_writer.write(s)
        await remote_writer.drain()
    if remote_reader.at_eof():
        return 1
    s = await remote_reader.readline()
    if verbose:
        print2("<<<", s)
    local_writer.write(s)
    await local_writer.drain()

    # QUIT

    if local_reader.at_eof():
        return 1
    s = await local_reader.readline()
    if verbose:
        print2(">>>", s)
    cmd = s.lower().rstrip()

    err = False
    if cmd != b'quit':
        err = True
        s = b'QUIT\r\n'
        if verbose:
            print2("!>>", s)
    remote_writer.write(s)
    await remote_writer.drain()
    if remote_reader.at_eof():
        return 1
    s = await remote_reader.readline()
    if verbose:
        print2("<<<", s)
    if err:
        return 1
    local_writer.write(s)
    await local_writer.drain()
    return 1

async def handle_smtp(local_reader, local_writer):
    try:
        ctx = ssl.create_default_context()
        if args.ca_file:
            ctx.load_verify_locations(cafile=args.ca_file)

        if args.verbose:
            print("Connect to " + REMOTE_SMTP_HOST + ":" + str(REMOTE_SMTP_PORT))

        remote_writer = None
        remote_reader, remote_writer = await asyncio.open_connection(
            REMOTE_SMTP_HOST, REMOTE_SMTP_PORT, ssl=ctx)

        res = await smtp_init(local_reader, local_writer, remote_reader, remote_writer, args.verbose)
        if res > 0:
            return

        (label1, label2) = (None, None)
        if args.verbose:
            (label1, label2) = ('>>>', '<<<')
        pipe1 = pipe(local_reader, remote_writer, label1)
        pipe2 = pipe(remote_reader, local_writer, label2)

        await asyncio.gather(pipe1, pipe2)

    except Exception as ex:
        print(sys.exc_info()[0].__name__ + ":", ex)
        s = b'451 Requested action aborted\r\n'
        if args.verbose:
            print2("<<<", s)
        local_writer.write(s)
        await local_writer.drain()

    finally:
        if remote_writer:
            remote_writer.close()
        local_writer.close()

async def start_server(handle, host, port, name):
    server = await asyncio.start_server(handle, host, port)
    addr = server.sockets[0].getsockname()
    if args.verbose:
        print(f'Serving on {addr}: {name}')
    async with server:
        await server.serve_forever()

async def main(parent=None):
    loop = asyncio.get_running_loop()

    if not args.no_pop:
        pop_server = start_server(handle_pop, LOCAL_HOST, args.pop_port, 'pop')
    if not args.no_smtp:
        if args.verbose:
            print('local ip:', IP_ADDR)
        smtp_server = start_server(handle_smtp, LOCAL_HOST, args.smtp_port, 'smtp')
    
    if parent is None:
        if args.no_pop:
            await smtp_server
        elif args.no_smtp:
            await pop_server
        else:
            await asyncio.gather(pop_server, smtp_server)
    else:
        if args.no_pop:
            task = asyncio.create_task(smtp_server)
        elif args.no_smtp:
            task = asyncio.create_task(pop_server)
        else:
            task = asyncio.gather(smtp_server, pop_server)

        parent.loop = loop
        parent.task = task

        try:
            await asyncio.gather(task)
        except asyncio.CancelledError:
            pass

def task_cancel(loop, task):
    loop.call_soon_threadsafe(task.cancel)

def load_client_secret_file(path):
    if path:
        with open(path, 'r') as f:
            return json.load(f)
    else:
        return json.loads(base64.b64decode(client_secret_data.CLIENT_SECRET_DATA))

def get_id_secret(config):
    client_id = config['installed']['client_id']
    client_secret = config['installed']['client_secret'] 
    return (client_id, client_secret)

def run_main(coro):
    if args.verbose: # debug
        print('=== Start ===')
    asyncio.run(coro)
    if args.verbose: # debug
        print('=== Stop ===')

parser = argparse.ArgumentParser(prog=PROG)
parser.add_argument("--version", help="show version and exit",
    action="store_true")
parser.add_argument("-v", "--verbose", help="increase output verbosity",
    action="store_true")
parser.add_argument("--email", help="Your email address")

group = parser.add_mutually_exclusive_group()
group.add_argument("--no_smtp", help="disable smtp proxy", action="store_true")
group.add_argument("--no_pop", help="disable pop proxy", action="store_true")
parser.add_argument("--smtp_port", type=int, default=LOCAL_SMTP_PORT, help="smtp listen port (default: %(default)s)")
parser.add_argument("--pop_port", type=int, default=LOCAL_POP_PORT, help="pop listen port (default: %(default)s)")
parser.add_argument("--ca_file", help="CA file")
parser.add_argument("-f", "--client_secret_file", help="client secret file")

args = parser.parse_args()

if args.email:
    EMAIL = args.email.encode()
    if args.verbose:
        print("email:", args.email)

if not args.no_smtp:
    IP_ADDR = get_ip()

CLIENT_CONFIG = load_client_secret_file(args.client_secret_file)
CLIENT_ID, CLIENT_SECRET = get_id_secret(CLIENT_CONFIG)

if __name__ == '__main__':
    if args.version:
        print(PROG, __version__)
        sys.exit()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

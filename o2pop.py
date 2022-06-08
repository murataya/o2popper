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
from google.auth import transport

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

try:
    import _client_secret_data as client_secret_data
except ImportError:
    import client_secret_data

__version__ = '2.0.0'

PROG = 'o2pop'

LOCAL_HOST = '127.0.0.1'

SCOPES = ['https://mail.google.com/']
REMOTE_POP_HOST = 'pop.gmail.com'
REMOTE_POP_PORT = 995
REMOTE_SMTP_HOST = 'smtp.gmail.com'
REMOTE_SMTP_PORT = 465

REDIRECT_PORT = 8080

LOCAL_POP_PORT = 8110
LOCAL_SMTP_PORT = 8025

MS_MODE = 1

def print2(label, s):
    print(f'{label} {s}')

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
    if params.email:
        user = params.email
    token = params.get_token(user.decode()).encode()

    auth_string = b'user=%b\1auth=Bearer %b\1\1' % (user, token)

    if params.mode == MS_MODE:
        s = b'AUTH XOAUTH2\r\n'
        if verbose:
            print2("!>>", s)
        remote_writer.write(s)
        await remote_writer.drain()

        # <<< b'+ '
        if remote_reader.at_eof():
            return 1
        s = await remote_reader.readline()
        if verbose:
            print2("<<<", s)
        
        s = base64.b64encode(auth_string) + b'\r\n'
    else:
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
            print("Connect to " + params.remote_pop_host + ":" + str(params.remote_pop_port))

        remote_writer = None
        remote_reader, remote_writer = await asyncio.open_connection(
            params.remote_pop_host, params.remote_pop_port, ssl=ctx)

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

    t = b''.join(h).translate(bytes.maketrans(b',<>\r\n', b'     '))
    emails = []
    for s in t.split():
        if (b'@' in s) and (not b'"' in s) and (not b'\\' in s):
            emails.append(s)

    if exclude:
        for t in exclude.replace(b',', b' ').lower().split():
            r = []
            if t.find(b'@') > 0 and (not t.startswith(b'.')):
                for s in emails:
                    if s != t:
                        r.append(s)
            else:
                for s in emails:
                    if not s.endswith(t):
                        r.append(s)
            emails = r
    return len(emails)

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

async def smtp_init(local_reader, local_writer, remote_reader, remote_writer, start_tls_ctx=None, verbose=None):
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
        s = b'EHLO [%b]\r\n' % params.ip_addr.encode()
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
            if s[3:4] == b' ':
                break

    if start_tls_ctx:
        s = b'STARTTLS\r\n'
        if verbose:
            print2("!>>", s)
        remote_writer.write(s)
        await remote_writer.drain()

        if remote_reader.at_eof():
            return 1

        s = await remote_reader.readline()
        if verbose:
            print2("<<<", s)

        transport = remote_writer.transport
        protocol = transport.get_protocol()
        protocol._over_ssl = True
        loop = asyncio.get_event_loop()

        tls_transport = await loop.start_tls(transport, protocol, start_tls_ctx)
        remote_writer._transport = tls_transport
        remote_reader._transport = tls_transport

        if params.mode == MS_MODE:
            # EHLO
            s = b'EHLO [%b]\r\n' % params.ip_addr.encode()
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
                if s[3:4] == b' ':
                    break

    # MAIL FROM: / AUTH PLAIN / AUTH LOGIN / QUIT
    if local_reader.at_eof():
        return 1
    s = await local_reader.readline()
    if verbose:
       print2(">>>", s)

    mail_from_buff = b''
    env_from = b''

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
        t = s.split(b':', 1)
        if len(t) == 2:
            user = t[1].split()[0].strip(b'<>')
            env_from = user
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
    if params.email:
        user = params.email
    token = params.get_token(user.decode()).encode()

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

    parent = params.parent
    err = False

    if s.startswith(b'235'):
        # MAIL FROM:
        if mail_from_buff:
            s = mail_from_buff
            if parent.change_env_from: # Change Envelope-From
                env_from = user
                t = s.split(b':', 1)
                if len(t) == 2:
                    t1 = t[1].split(b' ', 1)
                    if len(t1) == 2:
                        s = b'MAIL FROM:<' + user + b'> ' + t1[1]
                    else:
                        s = b'MAIL FROM:<' + user + b'>\r\n'
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
                if s[3:4] == b' ':
                    break

            if not s.startswith(b'250'):
                err = True
        else:
            local_writer.write(s)
            await local_writer.drain()
    else:
        if s.startswith(b'334'):
            s = b'\r\n'
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
                if s[3:4] == b' ':
                    break

        s = b'535 Authentication failed\r\n'
        if verbose:
            print2("<<!", s)
        local_writer.write(s)
        await local_writer.drain()

        err = True

    if err:
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

    if not params.parent:
        return 0

    block_smtp = parent.block_smtp
    block_list_parsed = parent.block_list_parsed

    rcpt_count = 0

    # MAIL FROM: / RCPT TO: / DATA
    while True:
        if local_reader.at_eof():
            return 1
        s = await local_reader.readline()
        if verbose:
            print2(">>>", s)

        cmd = s.lower().rstrip()
        if cmd == b'data':
            break

        mail_or_rcpt = False
        if cmd.startswith(b'mail '):
            mail_or_rcpt = True
            t = s.split(b':', 1)
            if len(t) == 2:
                if parent.change_env_from: # Change Envelope-From
                    env_from = user
                    t1 = t[1].split(b' ', 1)
                    if len(t1) == 2:
                        s = b'MAIL FROM:<' + user + b'> ' + t1[1]
                    else:
                        s = b'MAIL FROM:<' + user + b'>\r\n'
                    if verbose:
                        print2("!>>", s)
                else:
                    env_from = t[1].split()[0].strip(b'<>')
        elif cmd.startswith(b'rcpt '):
            mail_or_rcpt = True
            rcpt_count += 1
            if block_list_parsed: # Check block list
                t = cmd.split(b':', 1)
                if len(t) == 2:
                    email = t[1].split()[0].strip(b'<>')
                else:
                    email = b''

                matched = False
                for t, is_email in block_list_parsed:
                    if is_email:
                        if t == email:
                            matched = True
                            break
                    else:
                        if email.endswith(t):
                            matched = True
                            break
                if matched:
                    err = True
                    s = b'452 Matched block list\r\n'
                    if verbose:
                        print2("<<!", s)
                    local_writer.write(s)
                    await local_writer.drain()
                    break

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
            if s[3:4] == b' ':
                break

        if mail_or_rcpt:
            if not s.startswith(b'250'):
                err = True
                break
        else:
            return 1

    if err:
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

    to_cc_max = parent.to_cc_max
    to_cc_exclude = parent.to_cc_exclude.encode()
    err = False
    if to_cc_max > 0:
        count = to_cc_count(data, to_cc_exclude)
        if count > to_cc_max:
            err = True
            s = b'452 Too many addresses in To and Cc fields\r\n'

    if not err and parent.send_delay > 0:
        parent.rcpt_count = rcpt_count
        parent.env_from = env_from.decode()

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
        
        if params.remote_smtp_port == 587:
            start_tls_ctx = ctx
            ctx = None
        else:
            start_tls_ctx = None

        if args.verbose:
            print("Connect to " + params.remote_smtp_host + ":" + str(params.remote_smtp_port))

        remote_writer = None
        remote_reader, remote_writer = await asyncio.open_connection(
            params.remote_smtp_host, params.remote_smtp_port, ssl=ctx)

        res = await smtp_init(local_reader, local_writer, remote_reader, remote_writer, start_tls_ctx=start_tls_ctx, verbose=args.verbose)
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
        pop_server = start_server(handle_pop, args.host_address, args.pop_port, 'pop')
    if not args.no_smtp:
        if args.verbose:
            print('local ip:', params.ip_addr)
        smtp_server = start_server(handle_smtp, args.host_address, args.smtp_port, 'smtp')
    
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

def run_main(coro):
    if args.verbose: # debug
        print('=== Start ===')
    asyncio.run(coro)
    if args.verbose: # debug
        print('=== Stop ===')

def parse_hostport(s, default_port=None):
    r = s.rsplit(":", 1)
    if len(r) == 1:
        port = default_port
    else:
        try:
            port = int(r[1])
        except ValueError:
            port = default_port
    return (r[0], port)

class Params:
    def __init__(self, path=None):
        self.parent = None
        self.store_dir = ''
        self.email = None
        self.ip_addr = None
        self.mode = None
        self.path = path
        self.reset()

    def reset(self, parent=None):
        if self.path:
            with open(self.path, 'r') as f:
                self.client_config = json.load(f)
        else:
            self.client_config = json.loads(base64.b64decode(client_secret_data.CLIENT_SECRET_DATA))

        config = self.client_config['installed']

        if parent and parent.client_id:
            self.client_id = config['client_id'] = parent.client_id
        else:
            self.client_id = config['client_id']
        
        if parent and parent.client_secret:
            self.client_secret = config['client_secret'] = parent.client_secret
        else:
            self.client_secret = config['client_secret']

        if '_scopes' in config:
            self.scopes = config['_scopes']
            if len(self.scopes) > 1:
                os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
                if self.scopes[1].startswith('https://outlook.office.com/'):
                    self.mode = MS_MODE
        else:
            self.scopes = SCOPES

        if '_pop_server' in config:
            self.remote_pop_host, self.remote_pop_port = parse_hostport(
                config['_pop_server'], REMOTE_POP_PORT)
        else:
            self.remote_pop_host, self.remote_pop_port = REMOTE_POP_HOST, REMOTE_POP_PORT

        if '_smtp_server' in config:
            self.remote_smtp_host, self.remote_smtp_port = parse_hostport(
                config['_smtp_server'], REMOTE_SMTP_PORT)
        else:
            self.remote_smtp_host, self.remote_smtp_port = REMOTE_SMTP_HOST, REMOTE_SMTP_PORT
        
        if '_redirect_port' in config:
            self.redirect_port = config['_redirect_port']
        else:
            self.redirect_port = REDIRECT_PORT

    def get_token_file(self, user):
        return os.path.join(self.store_dir, 'token-' + user + '.pickle')

    def get_token(self, user, login_hint=None):
        token_file = self.get_token_file(user)
        creds = None
        if os.path.exists(token_file):
            with open(token_file, 'rb') as token:
                creds = pickle.load(token)
                creds._client_id = self.client_id
                creds._client_secret = self.client_secret

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_config(
                    self.client_config, self.scopes)
                kwargs = {}
                if login_hint or (self.parent and self.parent.login_hint):
                    kwargs['login_hint'] = user
                if self.redirect_port != REDIRECT_PORT:
                    kwargs['port'] = self.redirect_port
                creds = flow.run_local_server(**kwargs)
            with open(token_file, 'wb') as token:
                creds._client_id = '*'
                creds._client_secret = '*'
                if self.mode == MS_MODE:
                    if 'offline_access' in creds._scopes:
                        creds._scopes.remove('offline_access')
                pickle.dump(creds, token)
        return creds.token

    def info(self):
        config = self.client_config['installed']
        s = (
            f"_scopes: {self.scopes}\n"
            f"_pop_server: {self.remote_pop_host}:{self.remote_pop_port}\n"
            f"_smtp_server: {self.remote_smtp_host}:{self.remote_smtp_port}\n"
            f"_redirect_port: {self.redirect_port}\n"
            "\n"
            f"auth_uri: {config['auth_uri']}\n"
            f"token_uri: {config['token_uri']}"
        )
        return s

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
parser.add_argument("--host_address", type=str, default=LOCAL_HOST, help="listener host address (default: %(default)s)")
parser.add_argument("--ca_file", help="CA file")
parser.add_argument("-f", "--client_secret_file", help="client secret file")

args = parser.parse_args()
params = Params(args.client_secret_file)

if args.email:
    params.email = args.email.encode()
    if args.verbose:
        print("email:", args.email)

if not args.no_smtp:
    params.ip_addr = get_ip()

if __name__ == '__main__':
    if args.version:
        print(PROG, __version__)
        sys.exit()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

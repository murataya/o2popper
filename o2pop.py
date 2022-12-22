#
# o2pop.py
#
# Copyright (c) 2020-2022 MURATA Yasuhisa
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT
#

import asyncio
import ssl
import sys
import socket
import argparse
import time

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

__version__ = '3.0.0'

PROG = 'o2pop'

LOCAL_HOST = '127.0.0.1'

SCOPES = ['https://mail.google.com/']
REMOTE_POP_HOST = 'pop.gmail.com'
REMOTE_POP_PORT = 995
REMOTE_IMAP_HOST = 'imap.gmail.com'
REMOTE_IMAP_PORT = 993
REMOTE_SMTP_HOST = 'smtp.gmail.com'
REMOTE_SMTP_PORT = 465

REDIRECT_PORT = 8080

LOCAL_POP_PORT = 8110
LOCAL_IMAP_PORT = 8143
LOCAL_SMTP_PORT = 8025

MS_MODE = 1

class Conn:
    count = -1
    lock = -1
    def __init__(self):
        self.reader = None
        self.writer = None
        if Conn.count < 99:
            Conn.count += 1
        else:
            Conn.count = 0
        self.count = Conn.count
    
    def print2(self, label, s):
        print(f'{label}[{self.count}] {s}')

async def pipe(reader, writer, direction, count):
    try:
        if args.verbose:
            if direction == 1:
                label = f'>>>[{count}]'
            else:
                label = f'<<<[{count}]'
            while not reader.at_eof():
                s = await reader.readline()
                print(f'{label} {s}')
                writer.write(s)
        else:
            while not reader.at_eof():
                writer.write(await reader.read(2048))
    except Exception as ex: # debug
        if args.verbose:
            print(f'[{count}] ({direction}) {sys.exc_info()[0].__name__}: {ex}')
    finally:
        writer.close()

async def handle_common(local_reader, local_writer, init_func):
    try:
        step = 0
        remote = Conn()
        count = remote.count

        remote_writer = None
        res = await init_func(local_reader, local_writer, remote)
        remote_reader, remote_writer = remote.reader, remote.writer
        if res > 0:
            return

        pipe1 = pipe(local_reader, remote_writer, 1, count)
        pipe2 = pipe(remote_reader, local_writer, 2, count)

        step = 1
        await asyncio.gather(pipe1, pipe2)

    except Exception as ex: # debug
        if args.verbose:
            print(f'[{count}] {sys.exc_info()[0].__name__}: {ex}')

    finally:
        if step == 0:
            if remote_writer:
                remote_writer.close()
            local_writer.close()
        if args.verbose: # debug
            if Conn.lock == -1:
                print(f'[{count}] Closed')
            elif Conn.lock == count:
                Conn.lock = -1
                print(f'[{count}] Closed - with unlock')
            else:
                print(f'[{count}] Closed - with lock by [{Conn.lock}]')
        else:
            if Conn.lock == count:
                Conn.lock = -1

async def pop_init(local_reader, local_writer, remote):
    verbose = args.verbose
    print2 = remote.print2

    # <<! +OK ... ready
    s = b'+OK POP ready\r\n'
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
    if cmd != b'quit' and cmd != b'capa' and (not cmd.startswith(b'user ')):
        s = b'-ERR malformed command\r\n'
        if verbose:
            print2("<<!", s)
        local_writer.write(s)
        await local_writer.drain()

        # retry: QUIT / CAPA / USER name
        if local_reader.at_eof():
            return 1
        s = await local_reader.readline()
        if verbose:
           print2(">>>", s)
        cmd = s.lower().rstrip()

    if cmd == b'capa':
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

    user = b''
    if cmd.startswith(b'user '):
        t = s.split()
        if len(t) >= 2:
            user = t[1]
        if verbose: # debug
            print(f'[{remote.count}] User: {user}')

    if cmd == b'quit':
        s = b'+OK Bye\r\n'
        if verbose:
            print2("<<!", s)
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

    while Conn.lock >= 0:
        if verbose:
            print(f'[{remote.count}] Locked by [{Conn.lock}]') # debug
        await asyncio.sleep(1)
    Conn.lock = remote.count

    user_d = user.decode()
    if user_d in args.user_params:
        params = args.user_params[user_d]
    else:
        params = params_main

    token = params.get_token(user_d).encode()

    # connect to remote server
    if verbose:
        print(f'[{remote.count}] Connect to {params.remote_pop_host}:{params.remote_pop_port}')

    ctx = ssl.create_default_context()
    if args.ca_file:
        ctx.load_verify_locations(cafile=args.ca_file)

    remote_reader, remote_writer = await asyncio.open_connection(
        params.remote_pop_host, params.remote_pop_port, ssl=ctx)
    remote.reader, remote.writer = remote_reader, remote_writer
 
    # <<< +OK ... ready
    if remote_reader.at_eof():
        return 1
    s = await remote_reader.readline()
    if verbose:
        print2("<<<", s)

    auth_string = b'user=%b\1auth=Bearer %b\1\1' % (user, token)
    auth_b64 = base64.b64encode(auth_string)

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
        
        s = auth_b64 + b'\r\n'
        if verbose:
            if args.verbose == 1:
                blen = '*{' + str(len(auth_b64)) + '}'
                t = b'%b\r\n' % blen.encode()
                print2("!>>", t)
            else:
                print2("!>>", s)
    else:
        s = b'AUTH XOAUTH2 %b\r\n' % auth_b64
        if verbose:
            if args.verbose == 1:
                blen = '*{' + str(len(auth_b64)) + '}'
                t = b'AUTH XOAUTH2 %b\r\n' % blen.encode()
                print2("!>>", t)
            else:
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
        s = b'-ERR Bad login\r\n'
        if verbose:
            print2("<<!", s)
        local_writer.write(s)
        await local_writer.drain()
        return 1

    local_writer.write(s)
    await local_writer.drain()

    Conn.lock = -1

    return 0

async def imap_init(local_reader, local_writer, remote):
    verbose = args.verbose
    print2 = remote.print2

    # <<! * OK ... ready
    s = b'* OK IMAP ready\r\n'
    if verbose:
        print2("<<!", s)
    local_writer.write(s)
    await local_writer.drain()

    # LOGOUT / CAPABILITY / LOGIN
    if local_reader.at_eof():
        return 1
    s = await local_reader.readline()
    if verbose:
        print2(">>>", s)

    t = s.split(maxsplit=2)
    if len(t) < 2:
        return 1
    tag = t[0]
    cmd = t[1].lower()
    if len(t) >= 3:
        opt = t[2]
    else:
        opt = b''

    if cmd != b'logout' and cmd != b'capability' and cmd != b'login':
        s = tag + b' BAD malformed command\r\n'
        if verbose:
            print2("<<!", s)
        local_writer.write(s)
        await local_writer.drain()

        # retry: LOGOUT / CAPABILITY / LOGIN
        if local_reader.at_eof():
            return 1
        s = await local_reader.readline()
        if verbose:
           print2(">>>", s)

        t = s.split(maxsplit=2)
        if len(t) < 2:
            return 1
        tag = t[0]
        cmd = t[1].lower()
        if len(t) >= 3:
            opt = t[2]
        else:
            opt = b''

    if cmd == b'capability':
        s = b'* CAPABILITY IMAP4rev1 IDLE NAMESPACE QUOTA CHILDREN\r\n' + tag + b' OK Completed\r\n'
        if verbose:
            print2("<<!", s)
        local_writer.write(s)
        await local_writer.drain()

        # LOGOUT / LOGIN
        if local_reader.at_eof():
            return 1
        s = await local_reader.readline()
        if verbose:
            print2(">>>", s)

        t = s.split(maxsplit=2)
        if len(t) < 2:
            return 1
        tag = t[0]
        cmd = t[1].lower()
        if len(t) >= 3:
            opt = t[2]
        else:
            opt = b''

    user = b''
    if cmd == b'login':
        t = opt.split()
        if len(t) >= 2:
            user = t[0].strip(b'"')
        if verbose: # debug
            print(f'[{remote.count}] User: {user}')

    if cmd == b'logout':
        s = b'* BYE LOGOUT Requested\r\n' + tag + b' OK Completed\r\n'
        if verbose:
            print2("<<!", s)
        local_writer.write(s)
        await local_writer.drain()
        return 1

    while Conn.lock >= 0:
        if verbose:
            print(f'[{remote.count}] Locked by [{Conn.lock}]') # debug
        await asyncio.sleep(1)
    Conn.lock = remote.count

    user_d = user.decode()
    if user_d in args.user_params:
        params = args.user_params[user_d]
    else:
        params = params_main

    token = params.get_token(user_d).encode()

    # connect to remote server
    if verbose:
        print(f'[{remote.count}] Connect to {params.remote_imap_host}:{params.remote_imap_port}')

    ctx = ssl.create_default_context()
    if args.ca_file:
        ctx.load_verify_locations(cafile=args.ca_file)

    remote_reader, remote_writer = await asyncio.open_connection(
        params.remote_imap_host, params.remote_imap_port, ssl=ctx)
    remote.reader, remote.writer = remote_reader, remote_writer
 
    # <<< * OK ... ready
    if remote_reader.at_eof():
        return 1
    s = await remote_reader.readline()
    if verbose:
        print2("<<<", s)

    auth_string = b'user=%b\1auth=Bearer %b\1\1' % (user, token)
    auth_b64 = base64.b64encode(auth_string)
    s = tag + b' AUTHENTICATE XOAUTH2 %b\r\n' % auth_b64

    if verbose:
        if args.verbose == 1:
            blen = '*{' + str(len(auth_b64)) + '}'
            t = tag + b' AUTHENTICATE XOAUTH2 %b\r\n' % blen.encode()
            print2("!>>", t)
        else:
            print2("!>>", s)

    remote_writer.write(s)
    await remote_writer.drain()

    # OK: <<< tag OK Success / tag OK AUTHENTICATE Completed.
    # NG: <<< + eyJzdGF0d... / tag NO AUTHENTICATE failed.
    while True:
        if remote_reader.at_eof():
            return 1
        s = await remote_reader.readline()
        if verbose:
            print2("<<<", s)
        if not s.startswith(b'*'):
            break
    
    if s.startswith(b'+'):
        s = b'\r\n'
        if verbose:
            print2("!>>", s)
        remote_writer.write(s)
        await remote_writer.drain()
        if remote_reader.at_eof():
            return 1
        s = await remote_reader.readline()
        if verbose:
            print2("<<<", s)

    if not s.startswith(tag + b' OK'):
        s = b'99 LOGOUT\r\n'
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
            if not s.startswith(b'*'):
                break

        s = tag + b' NO LOGIN failed\r\n'
        if verbose:
            print2("<<!", s)
        local_writer.write(s)
        await local_writer.drain()
        return 1

    s = tag + b' OK LOGIN completed\r\n'
    if verbose:
        print2("<<!", s)
    local_writer.write(s)
    await local_writer.drain()

    Conn.lock = -1

    # CAPABILITY after Auth
    if not verbose:
        return 0

    if local_reader.at_eof():
        return 1
    s = await local_reader.readline()
    print2(">>>", s)

    remote_writer.write(s)
    await remote_writer.drain()

    t = s.split(maxsplit=2)
    if len(t) >= 2:
        cmd = t[1].lower()
    else:
        cmd = b''

    while True:
        if remote_reader.at_eof():
            return 1
        s = await remote_reader.readline()
        print2("<<<", s)
        if s.startswith(b'*') and cmd == b'capability':
            t = s
            s = t.replace(b' COMPRESS=DEFLATE', b'', 1)
            print2("<<!", s)
        local_writer.write(s)
        await local_writer.drain()
        if not s.startswith(b'*'):
            break

    return 0

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

async def smtp_init(local_reader, local_writer, remote):
    verbose = args.verbose
    print2 = remote.print2

    # <<! 220 ... Service ready
    s = b'220 ESMTP ready\r\n'
    if verbose:
        print2("<<!", s)
    local_writer.write(s)
    await local_writer.drain()

    # QUIT / EHLO / HELO
    if local_reader.at_eof():
        return 1
    s = await local_reader.readline()
    if verbose:
        print2(">>>", s)

    cmd = s.lower().rstrip()
    if cmd != b'quit' and (not cmd.startswith(b'ehlo ')) and (not cmd.startswith(b'helo ')):
        s = b'502 Unrecognized command\r\n'
        if verbose:
            print2("<<!", s)
        local_writer.write(s)
        await local_writer.drain()

        # retry: QUIT / EHLO / HELO
        if local_reader.at_eof():
            return 1
        s = await local_reader.readline()
        if verbose:
           print2(">>>", s)
        cmd = s.lower().rstrip()

    if cmd == b'quit':
        s = b'221 Bye\r\n'
        if verbose:
            print2("<<!", s)
        local_writer.write(s)
        await local_writer.drain()
        return 1
    if cmd.startswith(b'ehlo '):
        s = b'250-localhost\r\n250-AUTH LOGIN PLAIN\r\n250 8BITMIME\r\n'
    elif cmd.startswith(b'helo '):
        s = b'250 Hello\r\n'
    else:
        return 1

    if verbose:
        print2("<<!", s)
    local_writer.write(s)
    await local_writer.drain()

    # QUIT / MAIL FROM: / AUTH PLAIN / AUTH LOGIN
    if local_reader.at_eof():
        return 1
    s = await local_reader.readline()
    if verbose:
       print2(">>>", s)

    cmd = s.lower().rstrip()
    if cmd == b'quit':
        s = b'221 Bye\r\n'
        if verbose:
            print2("<<!", s)
        local_writer.write(s)
        await local_writer.drain()
        return 1

    env_from = b''
    mail_cmd = b''

    if cmd.startswith(b'mail '):
        mail_cmd = s
        t = s.split(b':', 1)
        if len(t) == 2:
            user = t[1].split()[0].strip(b'<>')
            env_from = user
        else:
            user = b''
        if verbose: # debug
            print(f'[{remote.count}] User: {user}')
    elif cmd.startswith(b'auth plain '):
        t = base64.b64decode(s[11:]).split(b'\0')
        if len(t) == 3:
            user = t[1]
        else:
            user = b''
        if verbose: # debug
            print(f'[{remote.count}] User: {user}')
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
            print(f'[{remote.count}] User: {user}')
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
            print(f'[{remote.count}] User: {user}')

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
    else:
        return 1

    if not mail_cmd:
        s = b'235 Authentication Successful\r\n'
        if verbose:
            print2("<<!", s)
        local_writer.write(s)
        await local_writer.drain()

        # QUIT / MAIL FROM:
        if local_reader.at_eof():
            return 1
        s = await local_reader.readline()
        if verbose:
            print2(">>>", s)

        cmd = s.lower().rstrip()
        if cmd == b'quit':
            s = b'221 Bye\r\n'
            if verbose:
                print2("<<!", s)
            local_writer.write(s)
            await local_writer.drain()
            return 1

        if cmd.startswith(b'mail '):
            mail_cmd = s
        else:
            return 1

    s = b'250 OK\r\n'
    if verbose:
        print2("<<!", s)
    local_writer.write(s)
    await local_writer.drain()

    parent = params_main.parent

    block_list_parsed = False
    if parent:
        block_list_parsed = parent.block_list_parsed

    # QUIT / RCPT TO: / DATA
    rcpt_cmds = []
    while True:
        if local_reader.at_eof():
            return 1
        s = await local_reader.readline()
        if verbose:
            print2(">>>", s)

        cmd = s.lower().rstrip()
        if cmd == b'quit':
            s = b'221 Bye\r\n'
            if verbose:
                print2("<<!", s)
            local_writer.write(s)
            await local_writer.drain()
            return 1

        if cmd.startswith(b'rcpt '):
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
                    s = b'552 Matched block list\r\n'
                    if verbose:
                        print2("<<!", s)
                    local_writer.write(s)
                    await local_writer.drain()
                    return 1
            rcpt_cmds.append(s)
            s = b'250 OK\r\n'
            if verbose:
                print2("<<!", s)
            local_writer.write(s)
            await local_writer.drain()
        elif cmd == b'data':
            if rcpt_cmds:
                break
            s = b'503 RCPT first.\r\n'
            if verbose:
                print2("<<!", s)
            local_writer.write(s)
            await local_writer.drain()
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

    if parent:
        block_smtp = parent.block_smtp

        to_cc_max = parent.to_cc_max
        to_cc_exclude = parent.to_cc_exclude.encode()
        err = False
        if to_cc_max > 0:
            n = to_cc_count(data, to_cc_exclude)
            if n > to_cc_max:
                err = True
                s = b'552 Too many addresses in To and Cc fields\r\n'

        if not err and parent.send_delay > 0:
            parent.rcpt_count = len(rcpt_cmds)
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
                s = b'552 Requested action aborted\r\n'
        
        if err:
            if verbose:
                print2("<<!", s)
            local_writer.write(s)
            await local_writer.drain()
            return 1

        if parent.remove_header:
            remove_agent_header(data)

    while Conn.lock >= 0:
        if verbose:
            print(f'[{remote.count}] Locked by [{Conn.lock}]') # debug
        await asyncio.sleep(1)
    Conn.lock = remote.count

    user_d = user.decode()
    if user_d in args.user_params:
        params = args.user_params[user_d]
    else:
        params = params_main

    token = params.get_token(user_d).encode()

    # connect to remote server
    if verbose:
        print(f'[{remote.count}] Connect to {params.remote_smtp_host}:{params.remote_smtp_port}')

    ctx = ssl.create_default_context()
    if args.ca_file:
        ctx.load_verify_locations(cafile=args.ca_file)

    if params.remote_smtp_port == 587:
        start_tls_ctx = ctx
        ctx = None
    else:
        start_tls_ctx = None

    remote_reader, remote_writer = await asyncio.open_connection(
        params.remote_smtp_host, params.remote_smtp_port, ssl=ctx)
    remote.reader, remote.writer = remote_reader, remote_writer

    err = False
    err_msg = b''

    # <<< 220 ... Service ready
    if remote_reader.at_eof():
        return 1
    s = await remote_reader.readline()
    if verbose:
        print2("<<<", s)
    if not s.startswith(b'220'):
        local_writer.write(s)
        await local_writer.drain()
        return 1

    # EHLO
    s = b'EHLO [%b]\r\n' % params_main.ip_addr.encode()
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
    if not s.startswith(b'250'):
        err = True
        err_msg = b'552 EHLO command failed\r\n'

    if not err and start_tls_ctx:
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
        if not s.startswith(b'250'):
            err = True
            err_msg = b'552 STARTTLS command failed\r\n'

        if not err:
            transport = remote_writer.transport
            protocol = transport.get_protocol()
            protocol._over_ssl = True
            loop = asyncio.get_event_loop()

            tls_transport = await loop.start_tls(transport, protocol, start_tls_ctx)
            remote_writer._transport = tls_transport
            remote_reader._transport = tls_transport

        if not err and params.mode == MS_MODE:
            # EHLO after STARTTLS
            s = b'EHLO [%b]\r\n' % params_main.ip_addr.encode()
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
            if not s.startswith(b'250'):
                err = True
                err_msg = b'552 EHLO command failed\r\n'

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
        s = err_msg
        if verbose:
            print2("<<!", s)
        local_writer.write(s)
        await local_writer.drain()

        return 1

    auth_string = b'user=%b\1auth=Bearer %b\1\1' % (user, token)
    auth_b64 = base64.b64encode(auth_string)
    s = b'AUTH XOAUTH2 %b\r\n' % auth_b64

    if verbose:
        if args.verbose == 1:
            blen = '*{' + str(len(auth_b64)) + '}'
            t = b'AUTH XOAUTH2 %b\r\n' % blen.encode()
            print2("!>>", t)
        else:
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

    if s.startswith(b'235'):
        # MAIL FROM:
        s = mail_cmd
        if parent and parent.change_env_from: # Change Envelope-From
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
            if s[3:4] == b' ':
                break

        if not s.startswith(b'250'):
            err = True
            err_msg = b'552 MAIL command failed\r\n'
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
        err = True
        err_msg = b'552 Authentication failed\r\n'

    # RCPT TO:
    if not err:
        for s in rcpt_cmds:
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

            if not s.startswith(b'250'):
                err = True
                err_msg = b'552 RCPT command failed\r\n'
                break

    # DATA:
    if not err:
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
        if not s.startswith(b'354'):
            err = True
            err_msg = b'552 DATA command failed\r\n'

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
        s = err_msg
        if verbose:
            print2("<<!", s)
        local_writer.write(s)
        await local_writer.drain()

        return 1

    Conn.lock = -1

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

async def handle_pop(reader, writer):
    await handle_common(reader, writer, pop_init)

async def handle_imap(reader, writer):
    await handle_common(reader, writer, imap_init)

async def handle_smtp(reader, writer):
    await handle_common(reader, writer, smtp_init)

async def start_server(handle, host, port, name):
    server = await asyncio.start_server(handle, host, port)
    addr = server.sockets[0].getsockname()
    if args.verbose:
        print(f'Serving on {addr}: {name}')
    async with server:
        await server.serve_forever()

# coroutine for KeyboardInterrupt on Windows
async def wakeup():
    while True:
        await asyncio.sleep(1)

async def main(parent=None):
    Conn.lock = -1
    loop = asyncio.get_running_loop()
    aws = []
    if args.smtp:
        if args.verbose:
            print('local ip:', params_main.ip_addr)
        smtp_server = start_server(handle_smtp, LOCAL_HOST, args.smtp_port, 'smtp')
        aws.append(smtp_server)
    if args.pop:
        pop_server = start_server(handle_pop, LOCAL_HOST, args.pop_port, 'pop')
        aws.append(pop_server)
    if args.imap:
        imap_server = start_server(handle_imap, LOCAL_HOST, args.imap_port, 'imap')
        aws.append(imap_server)

    if parent is None:
        if sys.platform == 'win32':
            aws.append(wakeup()) # or loop.create_task(wakeup())
        await asyncio.gather(*aws)
    else:
        task = asyncio.gather(*aws)

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
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
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

        if '_smtp_server' in config:
            self.remote_smtp_host, self.remote_smtp_port = parse_hostport(
                config['_smtp_server'], REMOTE_SMTP_PORT)
        else:
            self.remote_smtp_host, self.remote_smtp_port = REMOTE_SMTP_HOST, REMOTE_SMTP_PORT

        if '_pop_server' in config:
            self.remote_pop_host, self.remote_pop_port = parse_hostport(
                config['_pop_server'], REMOTE_POP_PORT)
        else:
            self.remote_pop_host, self.remote_pop_port = REMOTE_POP_HOST, REMOTE_POP_PORT

        if '_imap_server' in config:
            self.remote_imap_host, self.remote_imap_port = parse_hostport(
                config['_imap_server'], REMOTE_IMAP_PORT)
        else:
            self.remote_imap_host, self.remote_imap_port = REMOTE_IMAP_HOST, REMOTE_IMAP_PORT
        
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
                if args.verbose: # debug
                    now = time.strftime('%Y-%m-%d %H:%M:%S')
                    print(f'--- Refresh token [{now}] {user} ---')
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
            f"_smtp_server: {self.remote_smtp_host}:{self.remote_smtp_port}\n"
            f"_pop_server: {self.remote_pop_host}:{self.remote_pop_port}\n"
            f"_imap_server: {self.remote_imap_host}:{self.remote_imap_port}\n"
            f"_redirect_port: {self.redirect_port}\n"
            "\n"
            f"auth_uri: {config['auth_uri']}\n"
            f"token_uri: {config['token_uri']}"
        )
        return s

def parse_map_list(map_list):
    user_params = {}
    file_params = {}
    for s in map_list:
        t = s.split(':', 2)
        if len(t) < 2:
            continue
        emails = t[0]
        secret_file = t[1]
        if secret_file not in file_params:
            file_params[secret_file] = Params(secret_file)
        for user in emails.split(','):
            if user:
                user_params[user] = file_params[secret_file]
    return user_params

def print_params():
    print(params_main.info())
    if not args.user_params:
        return
    params_users = {}
    for user, params in args.user_params.items():
        if params not in params_users:
            params_users[params] = [user]
        else:
            params_users[params].append(user)
    for params, users in params_users.items():
        print("\n[" + ", ".join(users) + "]:")
        print(params.info())

parser = argparse.ArgumentParser(prog=PROG, formatter_class=argparse.RawTextHelpFormatter)
parser.add_argument("--version", help="show version and exit", action="store_true")
parser.add_argument("-p", "--params", help="show parameters for OAuth2", action="store_true")
parser.add_argument("-v", "--verbose", metavar='LEVEL', nargs='?', type=int,
    const=1, default=0, help="increase output verbosity")
parser.add_argument("--email", help="Your email address")
parser.add_argument("--smtp", dest='smtp_port', metavar='PORT', nargs='?', type=int,
    const=LOCAL_SMTP_PORT, help="enable smtp proxy (default port: %(const)s)", )
parser.add_argument("--pop", dest='pop_port', metavar='PORT', nargs='?', type=int,
    const=LOCAL_POP_PORT, help="enable pop proxy (default port: %(const)s)", )
parser.add_argument("--imap", dest='imap_port', metavar='PORT', nargs='?', type=int,
    const=LOCAL_IMAP_PORT, help="enable imap proxy (default port: %(const)s)", )
parser.add_argument("--ca_file", help="CA file")
parser.add_argument("-f", "--secret_file", help="client secret file", dest='client_secret_file', metavar='SECRET_FILE')
parser.add_argument("-m", nargs='+', help="mapping email and client secret file\n(MAP syntax: EMAIL[,EMAIL2 ...]:SECRET_FILE)",
    dest='map_list', metavar='MAP')

args = parser.parse_args()

args.smtp = args.smtp_port is not None
args.pop = args.pop_port is not None
args.imap = args.imap_port is not None

if args.smtp_port is None:
    args.smtp_port = LOCAL_SMTP_PORT
if args.pop_port is None:
    args.pop_port = LOCAL_POP_PORT
if args.imap_port is None:
    args.imap_port = LOCAL_IMAP_PORT

params_main = Params(args.client_secret_file)

if args.map_list:
    args.user_params = parse_map_list(args.map_list)
else:
    args.user_params = {}

if args.email:
    params_main.email = args.email.encode()
    if args.verbose:
        print("email:", args.email)

if args.smtp:
    params_main.ip_addr = get_ip()

if __name__ == '__main__':
    if args.version:
        print(PROG, __version__)
        sys.exit()
    if args.params:
        print_params()
        sys.exit()
    if not (args.smtp or args.pop or args.imap):
        parser.print_help()
        sys.exit()
    try:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        if args.verbose: # debug
            print('--- KeyboardInterrupt ---')

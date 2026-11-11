#!/usr/bin/env python3
# -----------------------------------------------------------------------------
#  The Lapki Compiler Plugin
#
#  The fake lapki-compiler of the tests of the local compiler
#
#  Copyright (C) 2026 Alexey Fedoseev <aleksey@fedoseev.net>
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 3 of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public License
#  along with this program. If not, see https://www.gnu.org/licenses/
#
#  -----------------------------------------------------------------------------

"""The arguments of lapki-compiler, /main of the stub compiler and /kill.

FAKE_COMPILER: serve (by default), die - exit at the start, deaf - ignore
/kill, mute - never open the port, hang - never answer cgml."""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import conftest  # noqa: E402 pylint: disable=wrong-import-position

MODE = 'FAKE_COMPILER'
FOREVER = 3600
ARDUINO = {'id': 'ArduinoUno', 'compile': True, 'compilingSettings': [
    {'command': 'no-such-program-of-the-tests', 'flags': ['compile']}]}


def main():
    """Serve until /kill or a signal."""
    parser = argparse.ArgumentParser()
    parser.add_argument('--server-host')
    parser.add_argument('--server-port', type=int)
    parser.add_argument('--killable', action='store_true')
    for name in ('--build-directory', '--artifacts-directory', '--log-path',
                 '--access-token-path'):
        parser.add_argument(name)
    args = parser.parse_args()
    mode = os.environ.get(MODE, 'serve')
    with open('fake.json', 'w', encoding='utf-8') as f:
        json.dump({'pid': os.getpid(), 'argv': sys.argv[1:]}, f)
    print('fake compiler: ' + mode, flush=True)
    if mode == 'die':
        print('no platforms', flush=True)
        sys.exit(4)
    if mode == 'mute':
        time.sleep(FOREVER)

    def kill(sock):
        if args.killable and mode != 'deaf':
            os._exit(0)  # pylint: disable=protected-access
        sock.sendall(b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n')

    def start(handler):
        return conftest.Server(handler, port=args.server_port,
                               plain={'/kill': kill})
    stub = conftest.Compiler(start)
    stub.platforms[('ArduinoUno', '1.0')] = ARDUINO
    answer = (lambda peer: time.sleep(FOREVER)) if mode == 'hang' else \
        conftest.reply(conftest.machine('G0'))
    stub.replies.extend([answer] * 100)
    time.sleep(FOREVER)


if __name__ == '__main__':
    main()

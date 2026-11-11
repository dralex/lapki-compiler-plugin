# -----------------------------------------------------------------------------
#  The Lapki Compiler Plugin
#
#  The test helpers: the WebSocket test server and the stub compiler
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

"""The test helpers: a WebSocket server of the standard library."""

import base64
import hashlib
import os
import socket
import struct
import sys
import threading

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# pylint: disable=wrong-import-position
from lapki_build import websocket as ws  # noqa: E402

POLL = 0.05
WAIT = 10.0


class Peer:
    """The server side of one connection."""

    def __init__(self, sock, buffer=b''):
        self.sock = sock
        self.buffer = bytearray(buffer)
        self.masks = []         # the mask bit of every frame of the client
        self.pongs = []
        self.closes = []

    def _read(self, size):
        while len(self.buffer) < size:
            chunk = self.sock.recv(ws.CHUNK)
            if not chunk:
                raise EOFError
            self.buffer += chunk
        data = bytes(self.buffer[:size])
        del self.buffer[:size]
        return data

    def frame(self):
        """Return (fin, opcode, payload) of the next frame, unmasked."""
        first, second = self._read(2)
        size = second & ws.LENGTH
        if size == ws.LENGTH_16:
            size = struct.unpack('!H', self._read(2))[0]
        elif size == ws.LENGTH_64:
            size = struct.unpack('!Q', self._read(8))[0]
        masked = bool(second & ws.MASKED)
        self.masks.append(masked)
        key = self._read(ws.MASK_SIZE) if masked else b''
        payload = self._read(size)
        if masked:
            payload = ws._mask(key, payload)  # pylint: disable=protected-access
        return bool(first & ws.FIN), first & ws.OPCODE, payload

    def message(self):
        """The next text or binary message; None on the close of the client."""
        parts, first = [], None
        while True:
            fin, opcode, payload = self.frame()
            if opcode == ws.OP_CLOSE:
                self.closes.append(payload)
                self.send(ws.OP_CLOSE, payload[:2])
                return None
            if opcode == ws.OP_PONG:
                self.pongs.append(payload)
                continue
            if first is None:
                first = opcode
            parts.append(payload)
            if fin:
                data = b''.join(parts)
                return data if first == ws.OP_BINARY else data.decode('utf-8')

    def send(self, opcode, payload=b'', fin=True):
        """Send one frame, not masked."""
        if isinstance(payload, str):
            payload = payload.encode('utf-8')
        size = len(payload)
        first = (ws.FIN if fin else 0) | opcode
        if size <= ws.MAX_LENGTH_7:
            head = struct.pack('!BB', first, size)
        elif size <= ws.MAX_LENGTH_16:
            head = struct.pack('!BBH', first, ws.LENGTH_16, size)
        else:
            head = struct.pack('!BBQ', first, ws.LENGTH_64, size)
        self.sock.sendall(head + payload)

    def send_text(self, text):
        """Send a text message in one frame."""
        self.send(ws.OP_TEXT, text)

    def close(self, code=ws.CLOSE_NORMAL, reason=''):
        """Send the close frame."""
        self.send(ws.OP_CLOSE, struct.pack('!H', code) + reason.encode())


class Server:  # pylint: disable=too-many-instance-attributes,too-few-public-methods
    """A WebSocket server on a free port: handler(peer) for every connection.

    status and accept spoil the handshake for the tests of the client."""

    def __init__(self, handler, status='101 Switching Protocols', accept=None):
        self.handler = handler
        self.status = status
        self.accept = accept
        self.paths = []
        self.headers = []
        self.peers = []
        self.errors = []
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen()
        self.listener.settimeout(POLL)
        self.port = self.listener.getsockname()[1]
        self.url = 'ws://127.0.0.1:{}/main'.format(self.port)
        self.stopped = threading.Event()
        self.threads = [threading.Thread(target=self._serve, daemon=True)]
        self.threads[0].start()

    def _serve(self):
        while not self.stopped.is_set():
            try:
                sock, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            thread = threading.Thread(target=self._connection, args=(sock,),
                                      daemon=True)
            self.threads.append(thread)
            thread.start()

    def _connection(self, sock):
        sock.settimeout(WAIT)
        try:
            data = b''
            while b'\r\n\r\n' not in data:
                chunk = sock.recv(ws.CHUNK)
                if not chunk:
                    return
                data += chunk
            head, rest = data.split(b'\r\n\r\n', 1)
            lines = head.decode('latin-1').split('\r\n')
            self.paths.append(lines[0].split(' ')[1])
            headers = {}
            for line in lines[1:]:
                name, _, value = line.partition(':')
                headers[name.strip().lower()] = value.strip()
            self.headers.append(headers)
            key = headers.get('sec-websocket-key', '')
            accept = self.accept or base64.b64encode(hashlib.sha1(
                (key + ws.GUID).encode()).digest()).decode()
            sock.sendall(('HTTP/1.1 {}\r\nUpgrade: websocket\r\n'
                          'Connection: Upgrade\r\n'
                          'Sec-WebSocket-Accept: {}\r\n\r\n').format(
                              self.status, accept).encode())
            if not self.status.startswith('101'):
                return
            peer = Peer(sock, rest)
            self.peers.append(peer)
            self.handler(peer)
        except (EOFError, ConnectionError, socket.timeout):
            pass
        except Exception as e:  # pylint: disable=broad-except
            self.errors.append(e)
        finally:
            sock.close()

    def close(self):
        """Stop the server and wait for its connections."""
        self.stopped.set()
        self.listener.close()
        for thread in self.threads:
            thread.join(WAIT)


@pytest.fixture
def server():
    """server(handler, ...) starts a Server stopped after the test."""
    servers = []

    def start(handler, **options):
        servers.append(Server(handler, **options))
        return servers[-1]
    yield start
    for item in servers:
        item.close()


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    """No setting of the user leaks into a test."""
    for name in list(os.environ):
        if name.startswith('LAPKI_BUILD_'):
            monkeypatch.delenv(name)

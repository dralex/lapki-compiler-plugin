# -----------------------------------------------------------------------------
#  The Lapki Compiler Plugin
#
#  The WebSocket client (RFC 6455) over socket and ssl
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

"""The WebSocket client (RFC 6455): text and binary messages, no extensions."""

import base64
import hashlib
import os
import socket
import ssl
import struct
import time
from urllib.parse import urlsplit

MAX_MESSAGE = 64 * 1024 * 1024

# the opcodes
OP_CONTINUATION = 0x0
OP_TEXT = 0x1
OP_BINARY = 0x2
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA
CONTROL = 0x8           # the opcodes from it on are the control frames

# the frame header
FIN = 0x80
RSV = 0x70
OPCODE = 0x0F
MASKED = 0x80
LENGTH = 0x7F
LENGTH_16 = 126
LENGTH_64 = 127
MAX_LENGTH_7 = 125      # also the largest control payload
MAX_LENGTH_16 = 0xFFFF
MASK_SIZE = 4
KEY_SIZE = 16

# the close codes
CLOSE_NORMAL = 1000
CLOSE_PROTOCOL = 1002
CLOSE_DATA = 1007
CLOSE_ABNORMAL = 1006   # never sent: there was no close frame
CLOSE_TOO_BIG = 1009

GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
PORTS = {'ws': 80, 'wss': 443}
CHUNK = 64 * 1024
MAX_HANDSHAKE = 64 * 1024
CLOSE_WAIT = 1.0        # seconds to wait for the close frame of the server


class WebSocketError(Exception):
    """The connection failed."""


class ClosedError(WebSocketError):
    """The server closed the connection."""

    def __init__(self, code=CLOSE_ABNORMAL, reason=''):
        super().__init__('the server closed the connection ({}{})'.format(
            code, ': ' + reason if reason else ''))
        self.code = code
        self.reason = reason


def connect(url, timeout=None, max_size=MAX_MESSAGE):
    """Open a connection to a ws:// or wss:// URL."""
    parts = urlsplit(url)
    if parts.scheme not in PORTS or not parts.hostname:
        raise WebSocketError('not a WebSocket URL: {}'.format(url))
    try:
        port = parts.port or PORTS[parts.scheme]
    except ValueError as e:
        raise WebSocketError('bad port in {}'.format(url)) from e
    path = parts.path or '/'
    if parts.query:
        path += '?' + parts.query
    try:
        sock = socket.create_connection((parts.hostname, port), timeout)
    except OSError as e:
        raise WebSocketError('cannot connect to {}:{}: {}'.format(
            parts.hostname, port, _reason(e))) from e
    try:
        if parts.scheme == 'wss':
            context = ssl.create_default_context()
            sock = context.wrap_socket(sock, server_hostname=parts.hostname)
        host = parts.hostname if port == PORTS[parts.scheme] else \
            '{}:{}'.format(parts.hostname, port)
        rest = _handshake(sock, host, path)
        sock.settimeout(None)
    except (OSError, WebSocketError) as e:
        sock.close()
        if isinstance(e, WebSocketError):
            raise
        raise WebSocketError('handshake with {} failed: {}'.format(
            url, _reason(e))) from e
    return Connection(sock, max_size, rest)


def _reason(error):
    if isinstance(error, socket.timeout):
        return 'timeout'
    return error.strerror or str(error) or type(error).__name__


def _accept(key):
    digest = hashlib.sha1((key + GUID).encode('ascii')).digest()
    return base64.b64encode(digest).decode('ascii')


def _handshake(sock, host, path):
    key = base64.b64encode(os.urandom(KEY_SIZE)).decode('ascii')
    sock.sendall(('GET {} HTTP/1.1\r\n'
                  'Host: {}\r\n'
                  'Upgrade: websocket\r\n'
                  'Connection: Upgrade\r\n'
                  'Sec-WebSocket-Key: {}\r\n'
                  'Sec-WebSocket-Version: 13\r\n'
                  '\r\n').format(path, host, key).encode('ascii'))
    data = b''
    while b'\r\n\r\n' not in data:
        if len(data) > MAX_HANDSHAKE:
            raise WebSocketError('the handshake answer is too long')
        chunk = sock.recv(CHUNK)
        if not chunk:
            raise WebSocketError('the server closed the connection '
                                 'in the handshake')
        data += chunk
    head, rest = data.split(b'\r\n\r\n', 1)
    lines = head.decode('latin-1').split('\r\n')
    status = lines[0].split(' ', 2)
    if len(status) < 2 or status[1] != '101':
        raise WebSocketError('the server refused the WebSocket: {}'.format(
            lines[0]))
    headers = {}
    for line in lines[1:]:
        name, _, value = line.partition(':')
        headers[name.strip().lower()] = value.strip()
    if headers.get('upgrade', '').lower() != 'websocket' or \
            'upgrade' not in headers.get('connection', '').lower():
        raise WebSocketError('the server did not upgrade to WebSocket')
    if headers.get('sec-websocket-accept') != _accept(key):
        raise WebSocketError('bad Sec-WebSocket-Accept of the server')
    return rest


def _mask(key, data):
    if not data:
        return data
    size = len(data)
    pad = (key * (size // MASK_SIZE + 1))[:size]
    return (int.from_bytes(data, 'big') ^
            int.from_bytes(pad, 'big')).to_bytes(size, 'big')


class Connection:
    """A client connection: text messages out, text and binary messages in."""

    def __init__(self, sock, max_size=MAX_MESSAGE, buffer=b''):
        self._sock = sock
        self._max_size = max_size
        self._buffer = bytearray(buffer)
        self._deadline = None
        self._closing = False
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def send(self, text):
        """Send a text message."""
        self._send(OP_TEXT, text.encode('utf-8'))

    def receive(self, timeout=None):
        """Return the next data message: str for a text one, bytes else."""
        self._deadline = None if timeout is None else \
            time.monotonic() + timeout
        opcode, parts, size = None, [], 0
        while True:
            fin, code, payload = self._frame()
            if code >= CONTROL:
                self._control(code, payload)
                continue
            if code == OP_CONTINUATION:
                if opcode is None:
                    self._fail(CLOSE_PROTOCOL, 'a continuation without '
                               'a message')
            elif code in (OP_TEXT, OP_BINARY):
                if opcode is not None:
                    self._fail(CLOSE_PROTOCOL, 'a new message inside '
                               'a fragmented one')
                opcode = code
            else:
                self._fail(CLOSE_PROTOCOL, 'unknown opcode {}'.format(code))
            size += len(payload)
            if size > self._max_size:
                self._fail(CLOSE_TOO_BIG, 'the message is larger than '
                           '{} bytes'.format(self._max_size))
            parts.append(payload)
            if fin:
                break
        data = b''.join(parts)
        if opcode == OP_BINARY:
            return data
        try:
            return data.decode('utf-8')
        except UnicodeDecodeError:
            self._fail(CLOSE_DATA, 'the text message is not UTF-8')
        return None

    def close(self, code=CLOSE_NORMAL, reason=''):
        """Close the connection; again does nothing."""
        if self.closed or self._closing:
            return
        self._closing = True
        try:
            self._send(OP_CLOSE, struct.pack('!H', code) +
                       reason.encode('utf-8')[:MAX_LENGTH_7 - 2])
            self._deadline = time.monotonic() + CLOSE_WAIT
            while True:
                _, opcode, _ = self._frame()
                if opcode == OP_CLOSE:
                    break
        except WebSocketError:
            pass
        finally:
            self._shut()

    def _shut(self):
        self.closed = True
        try:
            self._sock.close()
        except OSError:
            pass

    def _fail(self, code, message):
        self.close(code, message)
        raise WebSocketError(message)

    def _send(self, opcode, payload):
        if self.closed:
            raise WebSocketError('the connection is closed')
        size = len(payload)
        if size <= MAX_LENGTH_7:
            head = struct.pack('!BB', FIN | opcode, MASKED | size)
        elif size <= MAX_LENGTH_16:
            head = struct.pack('!BBH', FIN | opcode, MASKED | LENGTH_16, size)
        else:
            head = struct.pack('!BBQ', FIN | opcode, MASKED | LENGTH_64, size)
        key = os.urandom(MASK_SIZE)
        try:
            self._sock.sendall(head + key + _mask(key, payload))
        except OSError as e:
            self._shut()
            raise WebSocketError('the connection is lost: {}'.format(
                _reason(e))) from e

    def _control(self, opcode, payload):
        if opcode == OP_PING:
            self._send(OP_PONG, payload)
        elif opcode == OP_CLOSE:
            code, reason = CLOSE_ABNORMAL, ''
            if len(payload) >= 2:
                code = struct.unpack('!H', payload[:2])[0]
                reason = payload[2:].decode('utf-8', 'replace')
            try:
                self._send(OP_CLOSE, payload[:2])
            except WebSocketError:
                pass
            self._shut()
            raise ClosedError(code, reason)
        elif opcode != OP_PONG:
            self._fail(CLOSE_PROTOCOL, 'unknown opcode {}'.format(opcode))

    def _frame(self):
        first, second = self._read(2)
        if first & RSV:
            self._fail(CLOSE_PROTOCOL, 'an extension bit without '
                       'an extension')
        if second & MASKED:
            self._fail(CLOSE_PROTOCOL, 'a masked frame of the server')
        fin, opcode, size = bool(first & FIN), first & OPCODE, second & LENGTH
        if opcode >= CONTROL and (not fin or size > MAX_LENGTH_7):
            self._fail(CLOSE_PROTOCOL, 'a broken control frame')
        if size == LENGTH_16:
            size = struct.unpack('!H', self._read(2))[0]
        elif size == LENGTH_64:
            size = struct.unpack('!Q', self._read(8))[0]
        if size > self._max_size:
            self._fail(CLOSE_TOO_BIG, 'the message is larger than '
                       '{} bytes'.format(self._max_size))
        return fin, opcode, self._read(size)

    def _read(self, size):
        while len(self._buffer) < size:
            if self.closed:
                raise ClosedError()
            if self._deadline is not None:
                left = self._deadline - time.monotonic()
                if left <= 0:
                    raise WebSocketError('timeout')
                self._sock.settimeout(left)
            else:
                self._sock.settimeout(None)
            try:
                chunk = self._sock.recv(max(CHUNK, size - len(self._buffer)))
            except socket.timeout as e:
                raise WebSocketError('timeout') from e
            except OSError as e:
                self._shut()
                raise WebSocketError('the connection is lost: {}'.format(
                    _reason(e))) from e
            if not chunk:
                self._shut()
                raise ClosedError()
            self._buffer += chunk
        data = bytes(self._buffer[:size])
        del self._buffer[:size]
        return data

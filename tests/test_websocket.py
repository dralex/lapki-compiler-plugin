# -----------------------------------------------------------------------------
#  The Lapki Compiler Plugin
#
#  The tests of the WebSocket client
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

"""The frames, the lengths, the fragments, ping, close and the handshake."""

# pylint: disable=missing-function-docstring

import socket
import threading

import pytest

from lapki_build import websocket as ws

TIMEOUT = 5.0
SHORT = 0.2


def echo(peer):
    """Answer every message with itself."""
    while True:
        data = peer.message()
        if data is None:
            return
        peer.send(ws.OP_BINARY if isinstance(data, bytes) else ws.OP_TEXT,
                  data)


@pytest.mark.parametrize('size', [0, 1, ws.MAX_LENGTH_7, ws.LENGTH_16,
                                  ws.MAX_LENGTH_16, ws.MAX_LENGTH_16 + 1,
                                  300 * 1024])
def test_lengths(server, size):
    srv = server(echo)
    text = ('лапки' * size)[:size]
    with ws.connect(srv.url, TIMEOUT) as connection:
        connection.send(text)
        assert connection.receive(TIMEOUT) == text
    assert all(srv.peers[0].masks)
    assert not srv.errors


def test_path_and_host(server):
    srv = server(echo)
    with ws.connect(srv.url + '?a=1', TIMEOUT):
        pass
    assert srv.paths == ['/main?a=1']
    assert srv.headers[0]['host'] == '127.0.0.1:{}'.format(srv.port)
    assert srv.headers[0]['sec-websocket-version'] == '13'


def test_binary(server):
    blob = bytes(range(256)) * 300

    def handler(peer):
        peer.send(ws.OP_BINARY, blob)
        peer.message()
    srv = server(handler)
    with ws.connect(srv.url, TIMEOUT) as connection:
        assert connection.receive(TIMEOUT) == blob


def test_fragments_and_ping(server):
    def handler(peer):
        peer.send(ws.OP_TEXT, 'one ', fin=False)
        peer.send(ws.OP_PING, 'are you there')
        peer.send(ws.OP_CONTINUATION, 'two ', fin=False)
        peer.send(ws.OP_PONG, 'unasked')
        peer.send(ws.OP_CONTINUATION, 'three')
        peer.message()
    srv = server(handler)
    with ws.connect(srv.url, TIMEOUT) as connection:
        assert connection.receive(TIMEOUT) == 'one two three'
    assert srv.peers[0].pongs == [b'are you there']


def test_close_by_server(server):
    def handler(peer):
        peer.close(ws.CLOSE_TOO_BIG, 'message too big')
        peer.frame()
    srv = server(handler)
    connection = ws.connect(srv.url, TIMEOUT)
    with pytest.raises(ws.ClosedError) as info:
        connection.receive(TIMEOUT)
    assert info.value.code == ws.CLOSE_TOO_BIG
    assert info.value.reason == 'message too big'
    assert connection.closed
    with pytest.raises(ws.WebSocketError):
        connection.send('after the close')


def test_lost_connection(server):
    srv = server(lambda peer: peer.sock.shutdown(socket.SHUT_RDWR))
    connection = ws.connect(srv.url, TIMEOUT)
    with pytest.raises(ws.ClosedError) as info:
        connection.receive(TIMEOUT)
    assert info.value.code == ws.CLOSE_ABNORMAL


def test_close_by_client(server):
    srv = server(echo)
    connection = ws.connect(srv.url, TIMEOUT)
    connection.close()
    connection.close()
    assert connection.closed
    srv.close()
    assert srv.peers[0].closes == [b'\x03\xe8']


def test_too_large(server):
    def handler(peer):
        peer.send_text('x' * 2000)
        peer.message()
    srv = server(handler)
    connection = ws.connect(srv.url, TIMEOUT, max_size=1000)
    with pytest.raises(ws.WebSocketError) as info:
        connection.receive(TIMEOUT)
    assert not isinstance(info.value, ws.ClosedError)
    assert connection.closed


def test_too_large_in_fragments(server):
    def handler(peer):
        peer.send(ws.OP_TEXT, 'x' * 600, fin=False)
        peer.send(ws.OP_CONTINUATION, 'x' * 600)
        peer.message()
    srv = server(handler)
    connection = ws.connect(srv.url, TIMEOUT, max_size=1000)
    with pytest.raises(ws.WebSocketError, match='larger'):
        connection.receive(TIMEOUT)


def test_timeout(server):
    release = threading.Event()

    def handler(peer):
        release.wait(TIMEOUT)
        peer.send_text('late')
        peer.message()
    srv = server(handler)
    with ws.connect(srv.url, TIMEOUT) as connection:
        with pytest.raises(ws.WebSocketError, match='timeout'):
            connection.receive(SHORT)
        release.set()
        assert connection.receive(TIMEOUT) == 'late'


def test_not_utf8(server):
    def handler(peer):
        peer.send(ws.OP_TEXT, b'\xff\xfe')
        peer.message()
    srv = server(handler)
    connection = ws.connect(srv.url, TIMEOUT)
    with pytest.raises(ws.WebSocketError, match='UTF-8'):
        connection.receive(TIMEOUT)


def test_bad_frames(server):
    def handler(peer):
        peer.send(ws.OP_CONTINUATION, 'nothing to continue')
        peer.message()
    srv = server(handler)
    connection = ws.connect(srv.url, TIMEOUT)
    with pytest.raises(ws.WebSocketError, match='continuation'):
        connection.receive(TIMEOUT)


def test_refused_upgrade(server):
    srv = server(echo, status='403 Forbidden')
    with pytest.raises(ws.WebSocketError, match='403'):
        ws.connect(srv.url, TIMEOUT)


def test_bad_accept(server):
    srv = server(echo, accept='bm90IHRoZSBhY2NlcHQ=')
    with pytest.raises(ws.WebSocketError, match='Accept'):
        ws.connect(srv.url, TIMEOUT)


def test_connection_refused():
    probe = socket.socket()
    probe.bind(('127.0.0.1', 0))
    port = probe.getsockname()[1]
    probe.close()
    with pytest.raises(ws.WebSocketError, match='cannot connect'):
        ws.connect('ws://127.0.0.1:{}/main'.format(port), TIMEOUT)


@pytest.mark.parametrize('url', ['http://localhost:8084/main', 'ws://',
                                 'localhost:8084', 'ws://host:port/'])
def test_bad_urls(url):
    with pytest.raises(ws.WebSocketError):
        ws.connect(url, TIMEOUT)

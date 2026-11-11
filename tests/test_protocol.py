# -----------------------------------------------------------------------------
#  The Lapki Compiler Plugin
#
#  The tests of the compiler protocol
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

"""The commands of /main and the reply shapes of lapki-compiler."""

# pylint: disable=missing-function-docstring

import json

import pytest

from conftest import HEX, INTERNAL, command, machine, rejected, reply
from lapki_build import protocol, websocket

TIMEOUT = 5.0


def test_reply_built():
    result = protocol.parse_reply(json.dumps(reply(machine('G0'))))
    assert result.result == protocol.OK
    built = result.machines['G0']
    assert built.result == protocol.OK
    assert built.commands == [protocol.Command(
        'arduino-cli compile --export-binaries -b arduino:avr:uno', 0, '', '')]
    assert built.binaries == [protocol.File('sketch.ino.hex', HEX)]
    assert [f.name for f in built.sources] == ['sketch.ino', 'sketch.h']
    assert isinstance(built.sources[0].content, str)


def test_reply_shapes():
    result = protocol.parse_reply(json.dumps(rejected('G0', 'нет сигнала')))
    assert result.result == protocol.NOTOK
    assert result.machines['G0'].commands[0].return_code == \
        protocol.VALIDATION
    assert result.machines['G0'].commands[0].stderr == 'нет сигнала'
    internal = protocol.parse_reply(json.dumps(INTERNAL))
    assert list(internal.machines) == [protocol.INTERNAL]
    assert internal.machines[''].commands[0].return_code == \
        protocol.INTERNAL_ERROR
    skipped = protocol.parse_reply('{"result": "OK", "state_machines": {}}')
    assert skipped.machines == {}


def test_reply_keeps_the_order():
    result = protocol.parse_reply(json.dumps(reply(machine('b'),
                                                   machine('a'))))
    assert list(result.machines) == ['b', 'a']


def test_null_fields():
    result = protocol.parse_reply(json.dumps(reply({
        'result': 'NOTOK', 'name': 'G0', 'binary': None, 'source': None,
        'commands': [{'command': 'x', 'return_code': None, 'stdout': None,
                      'stderr': None}]})))
    assert result.machines['G0'].commands == [
        protocol.Command('x', None, '', '')]


@pytest.mark.parametrize('text', [
    'Internal error!', '[]', '{"result": "OK"}',
    '{"result": "MAYBE", "state_machines": {}}',
    '{"result": "OK", "state_machines": {"G0": []}}',
    json.dumps(reply(dict(machine('G0'), binary=[{
        'filename': 'sketch', 'extension': 'hex',
        'fileContent': 'not base64!'}]))),
    json.dumps(reply(dict(machine('G0'), source=[{'extension': 'ino'}])))])
def test_bad_replies(text):
    with pytest.raises(protocol.ProtocolError):
        protocol.parse_reply(text)


def test_compile(compiler):
    compiler.replies.append(reply(machine('G0')))
    with websocket.connect(compiler.url, TIMEOUT) as connection:
        result = protocol.compile_cgml(connection, '<graphml/>', TIMEOUT)
    assert result.machines['G0'].result == protocol.OK
    assert compiler.received == [('cgml', '<graphml/>')]


def test_compile_too_large(compiler):
    compiler.replies.append(lambda peer: peer.close(websocket.CLOSE_TOO_BIG))
    with websocket.connect(compiler.url, TIMEOUT) as connection:
        with pytest.raises(protocol.ProtocolError, match='too large'):
            protocol.compile_cgml(connection, '<graphml/>', TIMEOUT)


def test_compile_closed(compiler):
    compiler.replies.append(lambda peer: peer.close(websocket.CLOSE_NORMAL))
    with websocket.connect(compiler.url, TIMEOUT) as connection:
        with pytest.raises(protocol.ProtocolError, match='without a reply'):
            protocol.compile_cgml(connection, '<graphml/>', TIMEOUT)


def test_compile_binary(compiler):
    compiler.replies.append(lambda peer: peer.send(websocket.OP_BINARY, b'x'))
    with websocket.connect(compiler.url, TIMEOUT) as connection:
        with pytest.raises(protocol.ProtocolError, match='binary'):
            protocol.compile_cgml(connection, '<graphml/>', TIMEOUT)


def test_platform(compiler):
    scheme = {'id': 'ArduinoUno', 'compile': True, 'compilingSettings': [
        {'command': 'arduino-cli', 'flags': ['compile']}]}
    compiler.platforms[('ArduinoUno', '1.0')] = scheme
    with websocket.connect(compiler.url, TIMEOUT) as connection:
        assert protocol.get_platform(connection, 'ArduinoUno', '1.0',
                                     TIMEOUT) == scheme
    with websocket.connect(compiler.url, TIMEOUT) as connection:
        assert protocol.get_platform(connection, 'Teapot', '1.0',
                                     TIMEOUT) is None
    assert compiler.received == [('get_platform_json', 'ArduinoUno', '1.0'),
                                 ('get_platform_json', 'Teapot', '1.0')]


def test_command_helper():
    assert command(1)['return_code'] == 1

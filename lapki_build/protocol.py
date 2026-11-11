# -----------------------------------------------------------------------------
#  The Lapki Compiler Plugin
#
#  The commands of the compiler route /main and its reply
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

"""The protocol of Lapki IDE: a command word, then its arguments, as texts."""

import base64
import binascii
import collections
import json

from . import websocket

ROUTE = '/main'
INTERNAL = ''           # the machine id of an internal error
OK = 'OK'
NOTOK = 'NOTOK'
VALIDATION = -1         # the return code of a rejected machine
INTERNAL_ERROR = -2

CGML = 'cgml'
GET_PLATFORM = 'get_platform_json'
PLATFORM_SCHEME = 'raw-platform-scheme'
EXCERPT = 80            # the characters of a bad reply quoted in an error

Reply = collections.namedtuple('Reply', 'result machines')
MachineResult = collections.namedtuple(
    'MachineResult', 'id result commands binaries sources')
Command = collections.namedtuple('Command',
                                 'command return_code stdout stderr')
File = collections.namedtuple('File', 'name content')


class ProtocolError(Exception):
    """The reply cannot be read, or the connection failed."""


def _receive(connection, timeout):
    try:
        return connection.receive(timeout)
    except websocket.ClosedError as e:
        if e.code == websocket.CLOSE_TOO_BIG:
            raise ProtocolError('the compiler refused the message as too '
                                'large ({})'.format(e.code)) from e
        raise ProtocolError('the compiler closed the connection without '
                            'a reply ({})'.format(e.code)) from e
    except websocket.WebSocketError as e:
        raise ProtocolError(str(e)) from e


def _send(connection, *texts):
    try:
        for text in texts:
            connection.send(text)
    except websocket.WebSocketError as e:
        raise ProtocolError(str(e)) from e


def compile_cgml(connection, xml, timeout=None):
    """Send cgml and the Lapki XML; return the Reply."""
    _send(connection, CGML, xml)
    text = _receive(connection, timeout)
    if not isinstance(text, str):
        raise ProtocolError('the compiler sent a binary reply')
    return parse_reply(text)


def get_platform(connection, platform, version, timeout=None):
    """The platform as a dict, or None when the compiler does not know it."""
    _send(connection, GET_PLATFORM, platform, version)
    if _receive(connection, timeout) != PLATFORM_SCHEME:
        return None     # the error text; the compiler closes the connection
    text = _receive(connection, timeout)
    try:
        scheme = json.loads(text)
    except (TypeError, ValueError) as e:
        raise ProtocolError('the platform is not JSON') from e
    if not isinstance(scheme, dict):
        raise ProtocolError('the platform is not a JSON object')
    return scheme


def _name(item):
    filename, extension = item['filename'], item.get('extension') or ''
    return '{}.{}'.format(filename, extension) if extension else filename


def _code(value):
    return None if value is None else int(value)


def _machine(machine_id, item):
    commands = [Command(c.get('command') or '', _code(c.get('return_code')),
                        c.get('stdout') or '', c.get('stderr') or '')
                for c in item.get('commands') or []]
    binaries = [File(_name(f), base64.b64decode(f['fileContent'],
                                                validate=True))
                for f in item.get('binary') or []]
    sources = [File(_name(f), f['fileContent'])
               for f in item.get('source') or []]
    return MachineResult(machine_id, item.get('result', NOTOK), commands,
                         binaries, sources)


def parse_reply(text):
    """The Reply of a JSON text."""
    try:
        data = json.loads(text)
    except ValueError as e:
        raise ProtocolError('the reply is not JSON: {}'.format(
            text[:EXCERPT])) from e
    if not isinstance(data, dict) or \
            not isinstance(data.get('state_machines'), dict) or \
            data.get('result') not in (OK, NOTOK):
        raise ProtocolError('not a reply of the compiler: {}'.format(
            text[:EXCERPT]))
    try:
        machines = collections.OrderedDict(
            (machine_id, _machine(machine_id, item))
            for machine_id, item in data['state_machines'].items())
    except (AttributeError, KeyError, TypeError, ValueError,
            binascii.Error) as e:
        raise ProtocolError('a broken machine in the reply: {}'.format(
            e)) from e
    return Reply(data['result'], machines)

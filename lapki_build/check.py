# -----------------------------------------------------------------------------
#  The Lapki Compiler Plugin
#
#  The check of a diagram before its build
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

"""What only a run can know: the ids, the size, the platform, the toolchain."""

import re
import shutil

from . import protocol, websocket
from .report import ERROR, WARNING, finding, meta_findings

MAX_SIZE = 256 * 1024   # --max-msg-size of the compiler by default
KIB = 1024
ID = re.compile(r'\w+')
CONNECT_TIMEOUT = 30.0


def _platform(url, document, timeout):
    """The platform of the compiler, None when unknown; ProtocolError."""
    try:
        with websocket.connect(url, CONNECT_TIMEOUT) as connection:
            return protocol.get_platform(connection, document.platform,
                                         document.platform_version, timeout)
    except websocket.WebSocketError as e:
        raise protocol.ProtocolError(str(e)) from e


def check(document, url, compiler, timeout=None):
    """The findings of Check; compiler is None for a remote one.

    Without url only the document is checked."""
    items = meta_findings(document)
    for machine in document.machines:
        if not ID.fullmatch(machine.id):
            items.append(finding(ERROR, 'lapki-id', 'the id must consist of '
                                 'letters, digits and _', machine.id))
    size = document.size()
    if size > MAX_SIZE:
        items.append(finding(WARNING, 'lapki-size', 'the diagram is {} KiB; '
                             'the compiler takes {} KiB by default'.format(
                                 (size + KIB - 1) // KIB, MAX_SIZE // KIB)))
    if document.missing_meta() or not url:
        return items
    try:
        platform = _platform(url, document, timeout)
    except protocol.ProtocolError as e:
        items.append(finding(ERROR, 'lapki-compiler', str(e)))
        return items
    if platform is None:
        items.append(finding(ERROR, 'lapki-platform',
                             'the compiler has no platform {} {}'.format(
                                 document.platform,
                                 document.platform_version)))
    elif not platform.get('compile'):
        items.append(finding(WARNING, 'lapki-platform', 'the platform {} is '
                             'not compiled'.format(document.platform)))
    elif compiler is not None:
        for step in platform.get('compilingSettings') or []:
            program = step.get('command') if isinstance(step, dict) else None
            if program and shutil.which(program) is None:
                items.append(finding(ERROR, 'lapki-toolchain', '{} of the '
                                     'platform {} is not on PATH'.format(
                                         program, document.platform)))
    return items

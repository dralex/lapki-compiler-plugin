# -----------------------------------------------------------------------------
#  The Lapki Compiler Plugin
#
#  The compiler of a run: the remote link or the local compiler
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

"""The URL of /main: the remote link as given, else the local compiler."""

import contextlib
import os
import shutil
from urllib.parse import urlsplit, urlunsplit

from .protocol import ROUTE

SCHEMES = ('ws', 'wss')


class ServerError(Exception):
    """No compiler: not found, not started, a bad link."""


def remote_url(link):
    """The URL of a link: host:port gets ws://, an absent path /main."""
    text = link.strip()
    if '://' not in text:
        text = 'ws://' + text
    parts = urlsplit(text)
    try:
        port = parts.port
    except ValueError as e:
        raise ServerError('bad port in the link {}'.format(link)) from e
    if parts.scheme not in SCHEMES or not parts.hostname or port is None:
        raise ServerError('the link {} is not ws://host:port[/path]'.format(
            link))
    path = parts.path if parts.path not in ('', '/') else ROUTE
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, ''))


def find_compiler(compiler):
    """The path of the compiler executable, or None."""
    if os.sep in compiler or (os.altsep and os.altsep in compiler):
        path = os.path.abspath(os.path.expanduser(compiler))
        return path if os.path.isfile(path) and os.access(path, os.X_OK) \
            else None
    return shutil.which(compiler)


@contextlib.contextmanager
def open_compiler(link, compiler, workdir, log=None):  # pylint: disable=unused-argument
    """The URL of /main for the block."""
    if link:
        url = remote_url(link)
        if log:
            log.write('lapki-build: the remote compiler {}\n'.format(url))
        yield url
        return
    raise ServerError('the local compiler {} is not supported yet: set the '
                      'remote link'.format(compiler))

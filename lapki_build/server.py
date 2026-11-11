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
import http.client
import os
import shutil
import socket
import subprocess
import time
from urllib.parse import urlsplit, urlunsplit

from .protocol import ROUTE

SCHEMES = ('ws', 'wss')
HOST = '127.0.0.1'
START_TIMEOUT = 30.0
KILL_TIMEOUT = 1.0
TERMINATE_TIMEOUT = 3.0
POLL = 0.1
TAIL = 2000             # the characters of the compiler output in an error
OUTPUT = 'compiler.out'


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


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((HOST, 0))
        return probe.getsockname()[1]


class LocalCompiler:
    """The installed compiler started for a run, as Lapki IDE starts it."""

    def __init__(self, executable, workdir, start_timeout=START_TIMEOUT):
        self.executable = executable
        self.workdir = os.path.abspath(workdir)
        self.start_timeout = start_timeout
        self.port = None
        self.url = None
        self.process = None
        self._output = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()

    def arguments(self):
        """The command line of the compiler."""
        def path(name):
            return os.path.join(self.workdir, name)
        return [self.executable, '--server-host=' + HOST,
                '--server-port={}'.format(self.port), '--killable',
                '--build-directory=' + path('build'),
                '--artifacts-directory=' + path('artifacts'),
                '--log-path=' + path('compiler.log'),
                '--access-token-path=' + path('tokens')]

    def tail(self):
        """The end of the compiler output."""
        try:
            with open(os.path.join(self.workdir, OUTPUT), 'rb') as f:
                text = f.read().decode('utf-8', 'replace')
        except OSError:
            return ''
        return text[-TAIL:].strip()

    def _failed(self, message):
        tail = self.tail()
        return ServerError(message + (':\n' + tail if tail else ''))

    def start(self):
        """Spawn the compiler on a free port and wait for the port."""
        try:
            # the compiler creates its token file, not the directory of it
            os.makedirs(self.workdir, exist_ok=True)
            self._output = open(os.path.join(self.workdir, OUTPUT), 'wb')  # pylint: disable=consider-using-with
            self.port = _free_port()
            self.process = subprocess.Popen(  # pylint: disable=consider-using-with
                self.arguments(), stdin=subprocess.DEVNULL,
                stdout=self._output, stderr=subprocess.STDOUT,
                cwd=self.workdir)
        except OSError as e:
            self.stop()
            raise ServerError('cannot start the compiler {}: {}'.format(
                self.executable, e.strerror or e)) from e
        deadline = time.monotonic() + self.start_timeout
        while True:
            code = self.process.poll()
            if code is not None:
                self.stop()
                raise self._failed('the compiler {} exited with the code '
                                   '{}'.format(self.executable, code))
            try:
                with socket.create_connection((HOST, self.port), POLL):
                    break
            except OSError:
                pass
            if time.monotonic() > deadline:
                self.stop()
                raise self._failed('the compiler {} did not open the port '
                                   'in {:g} s'.format(self.executable,
                                                      self.start_timeout))
            time.sleep(POLL)
        self.url = 'ws://{}:{}{}'.format(HOST, self.port, ROUTE)

    def _kill_request(self):
        connection = http.client.HTTPConnection(HOST, self.port,
                                                timeout=KILL_TIMEOUT)
        try:
            connection.request('GET', '/kill')
            connection.getresponse().read()
        except (OSError, http.client.HTTPException):
            pass    # the compiler exits without an answer
        finally:
            connection.close()

    def stop(self):
        """Ask /kill, then terminate, then kill; again does nothing."""
        process, self.process = self.process, None
        if process is not None and process.poll() is None:
            self._kill_request()
            try:
                process.wait(KILL_TIMEOUT)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(TERMINATE_TIMEOUT)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        if self._output is not None:
            self._output.close()
            self._output = None


@contextlib.contextmanager
def open_compiler(link, compiler, workdir, log=None):
    """The URL of /main for the block: the remote link when it is not empty,
    else the local compiler started for the block."""
    if link:
        url = remote_url(link)
        if log:
            log.write('lapki-build: the remote compiler {}\n'.format(url))
        yield url
        return
    executable = find_compiler(compiler)
    if executable is None:
        raise ServerError('the compiler {} is not found: install '
                          'lapki-compiler or set the remote link'.format(
                              compiler))
    with LocalCompiler(executable, workdir) as local:
        if log:
            log.write('lapki-build: the local compiler {} on {}:{}\n'.format(
                compiler, HOST, local.port))
            log.flush()
        yield local.url

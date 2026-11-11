# -----------------------------------------------------------------------------
#  The Lapki Compiler Plugin
#
#  The tests of the compiler of a run
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

"""The remote link and the local compiler: spawn, the port, /kill, SIGTERM."""

# pylint: disable=missing-function-docstring,unused-argument

import json
import os
import shutil
import signal
import subprocess
import sys
import time

import pytest

from conftest import ROOT, diagram
from lapki_build import cli, server

FAKE = os.path.join(ROOT, 'tests', 'fake_compiler.py')
WAIT = 10.0
POLL = 0.05

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='POSIX signals '
                                'and the script compiler')


@pytest.mark.parametrize('link, url', [
    ('ide.polyus-nt.ru:8084', 'ws://ide.polyus-nt.ru:8084/main'),
    ('ws://ide.polyus-nt.ru:8084', 'ws://ide.polyus-nt.ru:8084/main'),
    (' ws://h:1/ ', 'ws://h:1/main'),
    ('wss://h:443/lapki?x=1', 'wss://h:443/lapki?x=1')])
def test_remote_url(link, url):
    assert server.remote_url(link) == url


@pytest.mark.parametrize('link', ['http://h:1', 'h', 'ws://h', 'ws://h:x',
                                  'ws://:1'])
def test_bad_links(link):
    with pytest.raises(server.ServerError):
        server.remote_url(link)


def test_find_compiler(tmp_path):
    assert server.find_compiler(FAKE) == FAKE
    assert server.find_compiler('sh') == shutil.which('sh')
    assert server.find_compiler('no-such-compiler-of-the-tests') is None
    plain = tmp_path / 'plain'
    plain.write_text('')
    assert server.find_compiler(str(plain)) is None


def fake(workdir):
    with open(os.path.join(str(workdir), 'fake.json'), encoding='utf-8') as f:
        return json.load(f)


def gone(pid):
    deadline = time.monotonic() + WAIT
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(POLL)
    return False


def test_start_and_kill(tmp_path):
    workdir = tmp_path / 'work'
    with server.LocalCompiler(FAKE, str(workdir)) as local:
        assert local.url == 'ws://127.0.0.1:{}/main'.format(local.port)
        process = local.process
        argv = fake(workdir)['argv']
    assert process.returncode == 0          # /kill, not a signal
    assert argv == ['--server-host=127.0.0.1',
                    '--server-port={}'.format(local.port), '--killable',
                    '--build-directory=' + str(workdir / 'build'),
                    '--artifacts-directory=' + str(workdir / 'artifacts'),
                    '--log-path=' + str(workdir / 'compiler.log'),
                    '--access-token-path=' + str(workdir / 'tokens')]
    local.stop()


def test_dies(monkeypatch, tmp_path):
    monkeypatch.setenv('FAKE_COMPILER', 'die')
    with pytest.raises(server.ServerError, match='exited with the code 4'
                       '(.|\n)*no platforms'):
        server.LocalCompiler(FAKE, str(tmp_path)).start()


def test_deaf(monkeypatch, tmp_path):
    monkeypatch.setenv('FAKE_COMPILER', 'deaf')
    local = server.LocalCompiler(FAKE, str(tmp_path))
    local.start()
    process = local.process
    local.stop()
    assert process.returncode == -signal.SIGTERM


def test_mute(monkeypatch, tmp_path):
    monkeypatch.setenv('FAKE_COMPILER', 'mute')
    local = server.LocalCompiler(FAKE, str(tmp_path), start_timeout=0.5)
    with pytest.raises(server.ServerError, match='did not open the port'):
        local.start()
    assert gone(fake(tmp_path)['pid'])


def test_not_found(tmp_path):
    with pytest.raises(server.ServerError, match='not found'):
        with server.open_compiler('', 'no-such-compiler-of-the-tests',
                                  str(tmp_path)):
            pass


def test_build_local(binding, capsys, tmp_path):
    code = cli.main(['build', diagram('blinker'), '-o', str(tmp_path / 'out'),
                     '--compiler', FAKE, '--workdir', str(tmp_path / 'work')])
    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith('lapki-build: the local compiler {} on '
                          '127.0.0.1:'.format(FAKE))
    assert (tmp_path / 'out' / 'Blinker' / 'sketch.ino.hex').exists()
    assert gone(fake(tmp_path / 'work')['pid'])


def test_check_local_toolchain(binding, capsys, tmp_path):
    code = cli.main(['check', diagram('blinker'), '--compiler', FAKE,
                     '--workdir', str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert out.endswith('error: lapki-toolchain: no-such-program-of-the-tests'
                        ' of the platform ArduinoUno is not on PATH\n')


def test_check_local_not_found(binding, capsys, tmp_path):
    code = cli.main(['check', diagram('blinker'), '--compiler',
                     'no-such-compiler-of-the-tests'])
    assert code == 0
    assert 'error: lapki-compiler: the compiler no-such-compiler-of-the-' \
        'tests is not found' in capsys.readouterr().out


def test_sigterm(binding, tmp_path):
    env = dict(os.environ, FAKE_COMPILER='hang')
    env['PYTHONPATH'] = os.pathsep.join(
        [ROOT] + [p for p in env.get('PYTHONPATH', '').split(os.pathsep)
                  if p])
    workdir = tmp_path / 'work'
    with subprocess.Popen([sys.executable, '-B', '-m', 'lapki_build', 'code',
                           diagram('blinker'), '--compiler', FAKE,
                           '--workdir', str(workdir)], env=env,
                          stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE) as run:
        deadline = time.monotonic() + WAIT
        while not (workdir / 'fake.json').exists() and \
                time.monotonic() < deadline:
            time.sleep(POLL)
        # the request is sent once the compiler answers its port
        time.sleep(1.0)
        run.send_signal(signal.SIGTERM)
        run.communicate(timeout=WAIT)
    assert run.returncode == cli.EXIT_TERMINATED
    assert gone(fake(workdir)['pid'])

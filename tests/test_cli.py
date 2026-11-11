# -----------------------------------------------------------------------------
#  The Lapki Compiler Plugin
#
#  The tests of the command against the stub compiler
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

"""build, code and check with a remote compiler played by the stub."""

# pylint: disable=missing-function-docstring,unused-argument
# pylint: disable=too-many-arguments,too-many-positional-arguments

import json
import socket
import threading

import pytest

from conftest import (HEX, INTERNAL, command, diagram, machine, rejected,
                      reply)
from lapki_build import __version__, cli, websocket

ARDUINO = {'id': 'ArduinoUno', 'compile': True, 'compilingSettings': [
    {'command': 'arduino-cli', 'flags': ['compile']}]}


def run(capsys, *argv):
    code = cli.main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return code, out, err


def diagnostics(path):
    with open(str(path), encoding='utf-8') as f:
        return [(i['severity'], i['rule'], i.get('element')) for i in json.load(f)]


def free_port():
    probe = socket.socket()
    probe.bind(('127.0.0.1', 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


def test_build(binding, compiler, capsys, tmp_path):
    compiler.replies.append(reply(machine('G0')))
    old = tmp_path / 'out' / 'Blinker'
    old.mkdir(parents=True)
    (old / 'sketch.ino.elf').write_text('old')
    code, out, err = run(capsys, 'build', diagram('blinker'), '-o',
                         tmp_path / 'out', '--server', compiler.link,
                         '--diagnostics', tmp_path / 'd.json')
    assert (code, err) == (0, '')
    assert 'lapki-build: 1 state machine, ArduinoUno 1.0, ' in out
    assert '== Blinker (G0): OK\n' in out
    assert 'lapki-build: Blinker: sketch.ino, sketch.h, sketch.ino.hex\n' in out
    assert out.endswith('lapki-build: built 1 of 1 state machine\n')
    assert (old / 'sketch.ino.hex').read_bytes() == HEX
    assert not (old / 'sketch.ino.elf').exists()
    assert diagnostics(tmp_path / 'd.json') == []
    word, xml = compiler.received[0]
    assert word == 'cgml' and 'id/ led' in xml


def test_build_two_machines(binding, compiler, capsys, tmp_path):
    compiler.replies.append(reply(machine('G0'), machine('G1', [command(
        1, 'sketch.ino:3:1: error: oops')])))
    code, out, _ = run(capsys, 'build', diagram('two-machines'), '-o',
                       tmp_path, '--server', compiler.link, '--diagnostics',
                       tmp_path / 'd.json')
    assert code == 1
    assert 'built 1 of 2 state machines' in out
    assert 'error: lapki-build: arduino-cli: sketch.ino:3:1: error: oops' in out
    assert diagnostics(tmp_path / 'd.json') == [('error', 'lapki-build', 'G1')]
    assert (tmp_path / 'Beacon' / 'sketch.ino').exists()


@pytest.mark.parametrize('answer, rule', [
    (rejected('G0', 'нет сигнала'), 'lapki-validation'),
    (INTERNAL, 'lapki-internal')])
def test_build_refused(binding, compiler, capsys, tmp_path, answer, rule):
    compiler.replies.append(answer)
    code, _, _ = run(capsys, 'build', diagram('blinker'), '-o', tmp_path,
                     '--server', compiler.link, '--diagnostics',
                     tmp_path / 'd.json')
    assert code == 1
    assert [d[1] for d in diagnostics(tmp_path / 'd.json')] == [rule]


def test_build_skipped(binding, compiler, capsys, tmp_path):
    compiler.replies.append({'result': 'OK', 'state_machines': {}})
    code, out, _ = run(capsys, 'build', diagram('berloga'), '-o', tmp_path,
                       '--server', compiler.link, '--diagnostics',
                       tmp_path / 'd.json')
    assert code == 0
    assert 'not built, the platform BearlogaDefend-Autoborder' in out
    assert diagnostics(tmp_path / 'd.json') == [
        ('warning', 'lapki-skipped', 'G0')]


def test_no_meta(binding, compiler, capsys, tmp_path):
    code, out, _ = run(capsys, 'build', diagram('no-version'), '-o',
                       tmp_path, '--server', compiler.link, '--diagnostics',
                       tmp_path / 'd.json')
    assert code == 1
    assert out == 'error: lapki-meta: the diagram has no platformVersion\n'
    assert compiler.received == []


def test_code(binding, compiler, capsys):
    compiler.replies.append(reply(machine('G0')))
    code, out, _ = run(capsys, 'code', diagram('blinker'), '--server',
                       compiler.link)
    assert code == 0
    assert '== Blinker (G0): sketch.ino\n// the machine G0\n' in out
    compiler.replies.append(INTERNAL)
    code, out, _ = run(capsys, 'code', diagram('blinker'), '--server',
                       compiler.link)
    assert code == 1


def test_check(binding, compiler, capsys, tmp_path):
    compiler.platforms[('ArduinoUno', '1.0')] = ARDUINO
    code, _, _ = run(capsys, 'check', diagram('blinker'), '--server',
                     compiler.link, '--diagnostics', tmp_path / 'd.json')
    assert (code, diagnostics(tmp_path / 'd.json')) == (0, [])
    assert compiler.received == [('get_platform_json', 'ArduinoUno', '1.0')]


def test_check_findings(binding, compiler, capsys, tmp_path):
    compiler.platforms[('BearlogaDefend-Autoborder', '1.0')] = {
        'compile': False}
    code, out, _ = run(capsys, 'check', diagram('berloga'), '--server',
                       compiler.link, '--diagnostics', tmp_path / 'd.json')
    assert code == 0
    assert out.endswith('warning: lapki-platform: the platform '
                        'BearlogaDefend-Autoborder is not compiled\n')
    code, _, _ = run(capsys, 'check', diagram('ms1-button'), '--server',
                     compiler.link, '--diagnostics', tmp_path / 'd.json')
    assert code == 0
    assert diagnostics(tmp_path / 'd.json') == [
        ('error', 'lapki-platform', None)]
    code, out, _ = run(capsys, 'check', diagram('no-version'), '--server',
                       compiler.link)
    assert (code, out) == (0, 'error: lapki-meta: the diagram has no '
                           'platformVersion\n')


def test_check_no_compiler(binding, capsys, tmp_path):
    code, _, _ = run(capsys, 'check', diagram('blinker'), '--server',
                     '127.0.0.1:{}'.format(free_port()), '--diagnostics',
                     tmp_path / 'd.json')
    assert code == 0
    assert diagnostics(tmp_path / 'd.json') == [
        ('error', 'lapki-compiler', None)]


def test_no_compiler(binding, capsys, tmp_path):
    code, _, err = run(capsys, 'build', diagram('blinker'), '-o', tmp_path,
                       '--server', '127.0.0.1:{}'.format(free_port()))
    assert code == 3
    assert err.startswith('lapki-build: the compiler: cannot connect')


def test_too_large(binding, compiler, capsys, tmp_path):
    compiler.replies.append(lambda peer: peer.close(websocket.CLOSE_TOO_BIG))
    code, _, err = run(capsys, 'build', diagram('blinker'), '-o', tmp_path,
                       '--server', compiler.link)
    assert code == 3
    assert 'too large' in err


def test_timeout(binding, compiler, capsys, tmp_path):
    release = threading.Event()
    compiler.replies.append(lambda peer: release.wait(5))
    try:
        code, _, err = run(capsys, 'code', diagram('blinker'), '--server',
                           compiler.link, '--timeout', '0.3')
    finally:
        release.set()
    assert code == 3
    assert err == 'lapki-build: the compiler: timeout\n'


@pytest.mark.parametrize('argv', [
    ['build', 'missing.graphml', '-o', 'x', '--server', 'h:1'],
    ['build', diagram('blinker')],
    ['code', diagram('blinker'), '--timeout', '-1'],
    ['make', diagram('blinker')],
    [],
    ['--install-editor-plugin']])
def test_usage(capsys, argv):
    assert run(capsys, *argv)[0] == 2


def test_unreadable(capsys, tmp_path):
    bad = tmp_path / 'bad.graphml'
    bad.write_text('not a diagram')
    code, _, err = run(capsys, 'code', bad, '--server', 'h:1')
    assert code == 2
    assert err.startswith('lapki-build: {}: '.format(bad))


def test_bad_link(binding, capsys, tmp_path):
    code, _, err = run(capsys, 'code', diagram('blinker'), '--server',
                       'http://host:1')
    assert code == 3
    assert err.startswith('lapki-build: no compiler: the link')


def test_unwritable_outdir(binding, compiler, capsys, tmp_path):
    taken = tmp_path / 'file'
    taken.write_text('')
    code, _, err = run(capsys, 'build', diagram('blinker'), '-o', taken,
                       '--server', compiler.link)
    assert code == 2
    assert compiler.received == []
    assert err.startswith('lapki-build: {}'.format(taken))


def test_workdir_kept(binding, compiler, capsys, tmp_path):
    compiler.replies.append(reply(machine('G0')))
    run(capsys, 'code', diagram('blinker'), '--server', compiler.link,
        '--workdir', tmp_path / 'work')
    assert (tmp_path / 'work' / 'lapki.graphml').exists()


def test_version(capsys):
    code, out, _ = run(capsys, '--version')
    assert (code, out) == (0, 'lapki-build {}\n'.format(__version__))

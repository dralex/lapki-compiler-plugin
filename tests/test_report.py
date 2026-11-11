# -----------------------------------------------------------------------------
#  The Lapki Compiler Plugin
#
#  The tests of the results of a run
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

"""The files, the build log, the findings and the diagnostics file."""

# pylint: disable=missing-function-docstring

import io
import json
import os

import pytest

from conftest import HEX, INTERNAL, command, machine, rejected, reply
from lapki_build import protocol, report
from lapki_build.document import Document, Machine

STDERR = ('\x1b[93mIn file included from x.ino:2:0:\x1b[0m\n'
          '/tmp/lapki-compiler/2026-11-11/sketch/G0/sketch/sketch.ino:57:5: '
          "error: 'ghost' was not declared in this scope\n"
          'compilation terminated.\n')


def document(*machines, platform='ArduinoUno', version='1.0'):
    return Document([Machine(*m) for m in machines], platform, version,
                    '<graphml/>')


def parse(data):
    return protocol.parse_reply(json.dumps(data))


def test_write_files(tmp_path):
    doc = document(('G0', 'Мигалка 1'), ('G1', ''), ('G2', 'Мигалка 1'))
    old = tmp_path / 'G1'
    old.mkdir()
    (old / 'sketch.ino.with_bootloader.hex').write_text('old')
    (old / 'notes.txt').write_text('kept')
    written = report.write_files(parse(reply(
        machine('G0'), machine('G1'), machine('G2'))), doc, str(tmp_path))
    names = sorted(os.path.relpath(p, str(tmp_path)) for p in written)
    assert names == sorted([
        'Мигалка_1/sketch.ino', 'Мигалка_1/sketch.h', 'Мигалка_1/sketch.ino.hex',
        'G1/sketch.ino', 'G1/sketch.h', 'G1/sketch.ino.hex',
        'Мигалка_1-G2/sketch.ino', 'Мигалка_1-G2/sketch.h',
        'Мигалка_1-G2/sketch.ino.hex'])
    assert (tmp_path / 'G1' / 'sketch.ino.hex').read_bytes() == HEX
    assert (tmp_path / 'G1' / 'sketch.ino').read_text() == '// the machine G1\n'
    assert not (old / 'sketch.ino.with_bootloader.hex').exists()
    assert (old / 'notes.txt').exists()


def test_write_nothing_of_internal(tmp_path):
    assert not report.write_files(parse(INTERNAL), document(('G0', 'a')),
                                  str(tmp_path))
    assert os.listdir(str(tmp_path)) == []


def test_log():
    out = io.StringIO()
    doc = document(('G0', 'Blinker'), ('G1', 'Beacon'))
    report.print_log(parse(reply(machine('G0', [command(
        1, STDERR, 'Sketch uses 2182 bytes')]))), doc, out)
    text = out.getvalue()
    assert text.startswith('== Blinker (G0): NOTOK\n$ arduino-cli compile')
    assert 'return code 1\nSketch uses 2182 bytes\nIn file included' in text
    assert '\x1b' not in text
    assert text.endswith('== Beacon (G1): not built, the platform ArduinoUno '
                         'is not compiled\n')


def test_sources():
    out = io.StringIO()
    report.print_sources(parse(reply(machine('G0'))),
                         document(('G0', 'G0')), out)
    assert out.getvalue() == ('== G0: sketch.ino\n// the machine G0\n'
                              '== G0: sketch.h\n#pragma once\n')


def test_findings():
    doc = document(('G0', 'a'), ('G1', 'b'), ('G2', 'c'), ('G3', 'd'))
    found = report.findings(parse(reply(
        machine('G0'),
        machine('G1', [command(1, STDERR)]),
        rejected('G2', 'Во время парсинга схемы\nпроизошла ошибка')[
            'state_machines']['G2'])), doc)
    assert found == [
        {'severity': 'error', 'rule': 'lapki-build', 'element': 'G1',
         'message': "arduino-cli: sketch.ino:57:5: error: 'ghost' was not "
                    'declared in this scope'},
        {'severity': 'error', 'rule': 'lapki-validation', 'element': 'G2',
         'message': 'Во время парсинга схемы произошла ошибка'},
        {'severity': 'warning', 'rule': 'lapki-skipped', 'element': 'G3',
         'message': 'not built: the platform ArduinoUno is not compiled'}]


def test_findings_internal():
    assert report.findings(parse(INTERNAL), document(('G0', 'a'))) == [
        {'severity': 'error', 'rule': 'lapki-internal',
         'message': 'the compiler failed: Internal error!'}]


def test_findings_return_code_only():
    found = report.findings(parse(reply(machine('G0', [
        command(2, text='/usr/bin/make -C x')]))), document(('G0', 'a')))
    assert found[0]['message'] == 'make: return code 2'


@pytest.mark.parametrize('stderr, line', [
    ('', ''), ('\n  \n', ''), ('warning: a\nb.c:1: error: c\n', 'b.c:1: error: c'),
    ('first\nsecond\n', 'first')])
def test_first_error(stderr, line):
    assert report.first_error(stderr) == line


def test_meta_findings():
    assert report.meta_findings(document(('G0', 'a'), platform='',
                                         version='')) == [
        {'severity': 'error', 'rule': 'lapki-meta',
         'message': 'the diagram has no platform'},
        {'severity': 'error', 'rule': 'lapki-meta',
         'message': 'the diagram has no platformVersion'}]


def test_diagnostics_file(tmp_path):
    path = str(tmp_path / 'diagnostics.json')
    items = [report.finding('error', 'lapki-build', 'ошибка', 'G0')]
    report.write_diagnostics(path, items)
    with open(path, encoding='utf-8') as f:
        assert json.load(f) == items

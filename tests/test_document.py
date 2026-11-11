# -----------------------------------------------------------------------------
#  The Lapki Compiler Plugin
#
#  The tests of the document conversion
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

"""Cyberiada 1.0 to the Lapki dialect lapki-compiler reads."""

# pylint: disable=missing-function-docstring,unused-argument

import os

import pytest

from conftest import diagram
from lapki_build import document


def test_blinker(binding, tmp_path):
    doc = document.load(diagram('blinker'), str(tmp_path))
    assert doc.machines == [document.Machine('G0', 'Blinker')]
    assert (doc.platform, doc.platform_version) == ('ArduinoUno', '1.0')
    assert doc.missing_meta() == []
    # the Lapki component: the bare name, the id in the body
    assert '<data key="dName">CGML_COMPONENT</data>' in doc.xml
    assert 'id/ led' in doc.xml
    assert doc.path == os.path.join(str(tmp_path), document.LAPKI_FILE)
    with open(doc.path, encoding='utf-8') as f:
        assert f.read() == doc.xml
    assert doc.size() == len(doc.xml.encode('utf-8'))


def test_two_machines(binding, tmp_path):
    doc = document.load(diagram('two-machines'), str(tmp_path))
    assert doc.machines == [document.Machine('G0', 'Blinker'),
                            document.Machine('G1', 'Beacon')]
    assert doc.name('G1') == 'Beacon'
    assert doc.name('nobody') == 'nobody'


def test_missing_meta(binding, tmp_path):
    doc = document.load(diagram('no-version'), str(tmp_path))
    assert doc.platform_version == ''
    assert doc.missing_meta() == ['platformVersion']


def test_no_platform(binding, tmp_path):
    doc = document.load(diagram('no-platform'), str(tmp_path))
    assert doc.missing_meta() == ['platform', 'platformVersion']
    assert doc.xml == '' and doc.path is None
    assert doc.machines == [document.Machine('G0', 'Blinker')]


def test_unreadable(binding, tmp_path):
    bad = tmp_path / 'bad.graphml'
    bad.write_text('<graphml>no diagram')
    with pytest.raises(document.DocumentError):
        document.load(str(bad), str(tmp_path / 'work'))


def test_pure_python_has_no_lapki_writer(monkeypatch, tmp_path):
    pytest.importorskip('cyberiadaml_py.cml')
    monkeypatch.setenv(document.BACKEND, document.PURE_PYTHON)
    assert document.module().__name__ == 'cyberiadaml_py.cml'
    with pytest.raises(document.DocumentError, match='binding'):
        document.load(diagram('blinker'), str(tmp_path))

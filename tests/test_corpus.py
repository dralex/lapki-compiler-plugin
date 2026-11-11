# -----------------------------------------------------------------------------
#  The Lapki Compiler Plugin
#
#  The tests of the conversion against the view of lapki-compiler
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

"""The Lapki corpus of cyberiadaml-py: the document as is (lapki) or saved as
Cyberiada 1.0 by the binding (cyberiada), converted by the plugin and read by
the 1.x parser of lapki-compiler, gives the recorded view of the compiler
(tests/legacy/lapki-compiler-view.json), the spaces of the behaviour aside."""

# pylint: disable=missing-function-docstring,unused-argument

import json
import os
import re

import pytest

from conftest import BINDING, SIBLINGS
from lapki_build import document

LEGACY = os.path.join(SIBLINGS, 'cyberiadaml-py', 'tests')
CORPUS = os.path.join(LEGACY, 'examples', 'lapki')
VIEW = os.path.join(LEGACY, 'legacy', 'lapki-compiler-view.json')
VERTICES = ('initial_states', 'choices', 'finals', 'shallow_history',
            'deep_history')
PROPAGATE = 'the binding drops propagate of an entry behaviour'
KNOWN = {
    'js-demo-arduino-blinker': {'lapki': PROPAGATE, 'cyberiada': PROPAGATE},
    'js-demo-two-blinkers': {'lapki': PROPAGATE, 'cyberiada': PROPAGATE},
    'py-demo-two-blinkers': {'lapki': PROPAGATE, 'cyberiada': PROPAGATE},
    'lib-lapki-js': {'lapki': 'libcyberiadamlpp fails writing the Lapki '
                              'dialect of it',
                     'cyberiada': 'the same'},
    'js-demo-empty-state': {'cyberiada': 'the binding cannot write its '
                                         'empty comment as Cyberiada 1.0'},
}


def _names():
    try:
        with open(VIEW, encoding='utf-8') as f:
            return sorted(json.load(f))
    except OSError:
        return []


def _text(text):
    return re.sub(r'\s+', ' ', text or '').replace(' [', '[').strip()


def view(elements):
    """The fields lapki-compiler reads (cyberiadaml-py tests/legacy)."""
    out = {}
    for sm_id, sm in elements.state_machines.items():
        out[sm_id] = {
            'platform': sm.platform,
            'meta': dict(sm.meta.values),
            'name': sm.name,
            'states': {k: [v.name, _text(v.actions), v.parent]
                       for k, v in sm.states.items()},
            'transitions': {k: [v.source, v.target, _text(v.actions)]
                            for k, v in sm.transitions.items()},
            'vertices': {f: {k: v.parent for k, v in getattr(sm, f).items()}
                         for f in VERTICES},
            'components': {k: [v.id, v.type, dict(v.parameters)]
                           for k, v in sm.components.items()},
        }
    return out


def _recorded(name):
    with open(VIEW, encoding='utf-8') as f:
        data = json.load(f)[name]
    for sm in data.values():
        sm['states'] = {k: [v[0], _text(v[1]), v[2]]
                        for k, v in sm['states'].items()}
        sm['transitions'] = {k: [v[0], v[1], _text(v[2])]
                             for k, v in sm['transitions'].items()}
    return data


@pytest.mark.skipif(not BINDING or not _names(), reason='the binding and the '
                    'sibling cyberiadaml-py')
@pytest.mark.parametrize('name', _names())
@pytest.mark.parametrize('route', ['lapki', 'cyberiada'])
def test_view(tmp_path, name, route):
    parser = pytest.importorskip('cyberiadaml_py').CGMLParser
    import CyberiadaML  # pylint: disable=import-outside-toplevel
    reason = KNOWN.get(name, {}).get(route)
    if reason:
        pytest.xfail(reason)
    source = os.path.join(CORPUS, name + '.graphml')
    if route == 'cyberiada':
        doc = CyberiadaML.LocalDocument()
        doc.open(source, CyberiadaML.formatDetect)
        source = str(tmp_path / 'cyberiada.graphml')
        with open(source, 'w', encoding='utf-8') as f:
            f.write(doc.encode(CyberiadaML.formatCyberiada10))
    converted = document.load(source, str(tmp_path / 'work'))
    assert view(parser().parse_cgml(converted.xml)) == _recorded(name)

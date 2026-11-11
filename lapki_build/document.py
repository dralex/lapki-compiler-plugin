# -----------------------------------------------------------------------------
#  The Lapki Compiler Plugin
#
#  The diagram in the Lapki dialect of Cyberiada 1.0
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

"""The diagram converted by the CyberiadaML module into the Lapki dialect."""

import collections
import os

BACKEND = 'LAPKI_BUILD_BACKEND'
PURE_PYTHON = 'cml'
LAPKI_FILE = 'lapki.graphml'
META_KEYS = ('platform', 'platformVersion')

Machine = collections.namedtuple('Machine', 'id name')


class DocumentError(Exception):
    """The diagram cannot be read or converted."""


def module():
    """The CyberiadaML module: the binding, else cyberiadaml_py.cml."""
    if os.environ.get(BACKEND) != PURE_PYTHON:
        try:
            import CyberiadaML  # pylint: disable=import-outside-toplevel
            return CyberiadaML
        except ImportError:
            pass
    try:
        from cyberiadaml_py import cml  # pylint: disable=import-outside-toplevel
    except ImportError as e:
        raise DocumentError('no CyberiadaML module: install '
                            'libcyberiadamlpp-py') from e
    return cml


class Document:
    """The machines, the platform and the Lapki XML of a diagram."""

    def __init__(self, machines, platform, platform_version, xml,  # pylint: disable=too-many-arguments,too-many-positional-arguments
                 path=None):
        self.machines = list(machines)
        self.platform = platform
        self.platform_version = platform_version
        self.xml = xml
        self.path = path

    def missing_meta(self):
        """The absent keys of platform and platformVersion."""
        return [key for key, value in zip(
            META_KEYS, (self.platform, self.platform_version)) if not value]

    def name(self, machine_id):
        """The machine name, else its id."""
        for machine in self.machines:
            if machine.id == machine_id:
                return machine.name or machine_id
        return machine_id

    def size(self):
        """The size of the Lapki XML in bytes."""
        return len(self.xml.encode('utf-8'))


def _message(error):
    return str(error).strip() or type(error).__name__


def load(path, workdir):
    """Open the diagram, save it as formatLapki into workdir; a Document."""
    cyb = module()
    doc = cyb.LocalDocument()
    try:
        doc.open(path, cyb.formatDetect)
        machines = [Machine(sm.get_id(), sm.get_name())
                    for sm in doc.get_state_machines()]
        meta = doc.get_meta()
        platform, version = (meta.get_string(key) for key in META_KEYS)
    except Exception as e:  # pylint: disable=broad-except
        raise DocumentError(_message(e)) from e
    if not platform:
        # the binding writes no Lapki dialect without it: lapki-meta tells
        return Document(machines, platform, version, '')
    try:
        xml = doc.encode(cyb.formatLapki)
    except Exception as e:  # pylint: disable=broad-except
        if isinstance(e, getattr(cyb, 'NotImplementedException', ())):
            raise DocumentError('the Lapki dialect needs the CyberiadaML '
                                'binding (libcyberiadamlpp-py); {} has no '
                                'writer of it'.format(cyb.__name__)) from e
        raise DocumentError('cannot convert to the Lapki dialect: ' +
                            _message(e)) from e
    lapki = os.path.join(workdir, LAPKI_FILE)
    try:
        os.makedirs(workdir, exist_ok=True)
        with open(lapki, 'w', encoding='utf-8') as f:
            f.write(xml)
    except OSError as e:
        raise DocumentError('cannot write {}: {}'.format(
            lapki, e.strerror or e)) from e
    return Document(machines, platform, version, xml, lapki)

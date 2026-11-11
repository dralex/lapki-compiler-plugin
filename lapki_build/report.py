# -----------------------------------------------------------------------------
#  The Lapki Compiler Plugin
#
#  The results of a run: the files, the build log and the diagnostics
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

"""The files of the machines, the build log and the editor's diagnostics."""

import glob
import json
import os
import re

from .protocol import INTERNAL, OK, VALIDATION

SKETCH = 'sketch'
NOT_IN_NAME = re.compile(r'[^\w.-]')
ANSI = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')
# a path in a tool message: the build directory of the compiler is noise
PATH = re.compile(r'(?:[A-Za-z]:)?[\\/][^\s:]*[\\/]([^\\/\s:]+:)')

ERROR = 'error'
WARNING = 'warning'


def finding(severity, rule, message, element=None):
    """One entry of the diagnostics file."""
    item = {'severity': severity, 'rule': rule,
            'message': ' '.join(message.split())}
    if element is not None:
        item['element'] = element
    return item


def label(document, machine_id):
    """The machine for a person: 'Name (id)', the id, or the compiler."""
    if machine_id == INTERNAL:
        return 'the compiler'
    name = document.name(machine_id)
    return machine_id if name == machine_id else '{} ({})'.format(
        name, machine_id)


def ordered(reply, document):
    """The machine ids of the reply: the document order, then the rest."""
    known = [m.id for m in document.machines if m.id in reply.machines]
    return known + [i for i in reply.machines if i not in known]


def directories(reply, document):
    """The output directory name of every machine of the reply."""
    names, taken = {}, set()
    for machine_id in ordered(reply, document):
        if machine_id == INTERNAL:
            continue
        name = NOT_IN_NAME.sub('_', document.name(machine_id))
        if not name.strip('._') or name in taken:
            name = (name + '-' if name.strip('._') else '') + \
                NOT_IN_NAME.sub('_', machine_id)
        taken.add(name)
        names[machine_id] = name
    return names


def write_files(reply, document, outdir):
    """Write the sources and the firmware; return the written paths."""
    written = []
    for machine_id, name in directories(reply, document).items():
        machine = reply.machines[machine_id]
        files = machine.sources + machine.binaries
        if not files:
            continue
        folder = os.path.join(outdir, name)
        os.makedirs(folder, exist_ok=True)
        for old in glob.glob(os.path.join(glob.escape(folder),
                                          SKETCH + '.*')):
            os.remove(old)
        for item in files:
            path = os.path.join(folder, os.path.basename(item.name))
            if isinstance(item.content, bytes):
                with open(path, 'wb') as f:
                    f.write(item.content)
            else:
                with open(path, 'w', encoding='utf-8', newline='') as f:
                    f.write(item.content)
            written.append(path)
    return written


def _state(machine):
    return machine.result if machine.result else '-'


def print_log(reply, document, out):
    """The build log of every machine: its commands and their output."""
    for machine_id in ordered(reply, document):
        machine = reply.machines[machine_id]
        out.write('== {}: {}\n'.format(label(document, machine_id),
                                       _state(machine)))
        for command in machine.commands:
            out.write('$ {}\n'.format(command.command))
            out.write('return code {}\n'.format(command.return_code))
            for text in (command.stdout, command.stderr):
                text = ANSI.sub('', text)
                if text:
                    out.write(text if text.endswith('\n') else text + '\n')
    for machine in document.machines:
        if machine.id not in reply.machines and INTERNAL not in \
                reply.machines:
            out.write('== {}: not built, the platform {} is not '
                      'compiled\n'.format(label(document, machine.id),
                                          document.platform))


def print_sources(reply, document, out):
    """The sources of every machine."""
    for machine_id in ordered(reply, document):
        for item in reply.machines[machine_id].sources:
            out.write('== {}: {}\n'.format(label(document, machine_id),
                                           item.name))
            text = item.content
            out.write(text if text.endswith('\n') else text + '\n')


def first_error(stderr):
    """The first line holding 'error:', else the first line not empty."""
    lines = [line.strip() for line in ANSI.sub('', stderr).splitlines()
             if line.strip()]
    for line in lines:
        if 'error:' in line:
            return line
    return lines[0] if lines else ''


def _program(command):
    words = command.command.split()
    return os.path.basename(words[0]) if words else 'the command'


def findings(reply, document):
    """The diagnostics of a reply, a list of dict."""
    items = []
    for machine_id in ordered(reply, document):
        machine = reply.machines[machine_id]
        if machine_id == INTERNAL:
            reason = '; '.join(c.stderr.strip() for c in machine.commands
                               if c.stderr.strip()) or machine.result
            items.append(finding(ERROR, 'lapki-internal',
                                 'the compiler failed: ' + reason))
            continue
        failed = False
        for command in machine.commands:
            if command.return_code == VALIDATION:
                items.append(finding(ERROR, 'lapki-validation',
                                     command.stderr or 'rejected',
                                     machine_id))
                failed = True
            elif command.return_code:
                line = PATH.sub(r'\1', first_error(command.stderr))
                items.append(finding(
                    ERROR, 'lapki-build', '{}: {}'.format(
                        _program(command), line or 'return code {}'.format(
                            command.return_code)), machine_id))
                failed = True
        if machine.result != OK and not failed:
            items.append(finding(ERROR, 'lapki-build', 'not built: {}'.format(
                machine.result), machine_id))
    if INTERNAL not in reply.machines:
        for machine in document.machines:
            if machine.id not in reply.machines:
                items.append(finding(
                    WARNING, 'lapki-skipped', 'not built: the platform {} is '
                    'not compiled'.format(document.platform), machine.id))
    return items


def meta_findings(document):
    """The findings of the absent platform meta."""
    return [finding(ERROR, 'lapki-meta', 'the diagram has no ' +
                    ('platform' if key == 'platform' else 'platformVersion'))
            for key in document.missing_meta()]


def print_findings(items, out):
    """The findings, one a line."""
    for item in items:
        out.write('{}: {}: {}\n'.format(item['severity'], item['rule'],
                                        item['message']))


def write_diagnostics(path, items):
    """Write the diagnostics file of the editor."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
        f.write('\n')

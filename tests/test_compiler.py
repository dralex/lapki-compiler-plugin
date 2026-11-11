# -----------------------------------------------------------------------------
#  The Lapki Compiler Plugin
#
#  The tests against a real compiler, opt-in
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

"""build of the test diagrams by a real compiler, compared with tests/good:
the result, the files of every machine and the failed programs, never the
firmware. LAPKI_COMPILER_URL is a remote compiler, LAPKI_COMPILER an
installed one. Recording: python3 -B tests/test_compiler.py LINK."""

# pylint: disable=missing-function-docstring,unused-argument

import json
import os
import shutil
import sys
import tempfile

import pytest

from conftest import BINDING, GOOD, diagram
from lapki_build import cli

CASES = ['blinker', 'two-machines', 'ms1-button', 'berloga', 'rejected',
         'invalid-event', 'build-error', 'no-version']
# the programs a local compiler needs beside arduino-cli
NEEDS = {'ms1-button': 'arm-none-eabi-g++'}
TIMEOUT = '600'


def summary(name, compiler_options, workdir):
    """The exit code, the files and the findings of a build."""
    outdir = os.path.join(workdir, 'out')
    found = os.path.join(workdir, 'diagnostics.json')
    code = cli.main(['build', diagram(name), '-o', outdir, '--diagnostics',
                     found, '--timeout', TIMEOUT] + compiler_options)
    files = {}
    if os.path.isdir(outdir):
        for folder in sorted(os.listdir(outdir)):
            files[folder] = sorted(os.listdir(os.path.join(outdir, folder)))
    findings = []
    if os.path.exists(found):
        with open(found, encoding='utf-8') as f:
            for item in json.load(f):
                program = item['message'].split(':', 1)[0] \
                    if item['rule'] == 'lapki-build' else None
                findings.append([item['severity'], item['rule'],
                                 item.get('element'), program])
    return {'exit': code, 'files': files, 'findings': findings}


def good(name):
    with open(os.path.join(GOOD, name + '.json'), encoding='utf-8') as f:
        return json.load(f)


def compilers():
    if os.environ.get('LAPKI_COMPILER_URL'):
        yield 'remote', ['--server', os.environ['LAPKI_COMPILER_URL']]
    if os.environ.get('LAPKI_COMPILER'):
        yield 'local', ['--compiler', os.environ['LAPKI_COMPILER']]


@pytest.mark.parametrize('name', CASES)
def test_build(binding, capsys, tmp_path, name):
    runs = list(compilers())
    if not runs:
        pytest.skip('set LAPKI_COMPILER_URL or LAPKI_COMPILER')
    for mode, options in runs:
        if mode == 'local' and name in NEEDS and \
                shutil.which(NEEDS[name]) is None:
            continue
        workdir = tmp_path / mode
        workdir.mkdir()
        assert summary(name, options, str(workdir)) == good(name), mode
    capsys.readouterr()


def record(link):
    """Write tests/good from the compiler of the link."""
    if not BINDING:
        sys.exit('no CyberiadaML binding')
    os.makedirs(GOOD, exist_ok=True)
    for name in CASES:
        workdir = tempfile.mkdtemp()
        try:
            result = summary(name, ['--server', link], workdir)
        finally:
            shutil.rmtree(workdir)
        with open(os.path.join(GOOD, name + '.json'), 'w',
                  encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
            f.write('\n')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit('usage: python3 -B tests/test_compiler.py LINK')
    record(sys.argv[1])

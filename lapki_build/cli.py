# -----------------------------------------------------------------------------
#  The Lapki Compiler Plugin
#
#  The command lapki-build
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

"""The command: build, show the code, check a diagram with lapki-compiler."""

import argparse
import os
import shutil
import signal
import sys
import tempfile
import threading

from . import __version__
from . import check as checking
from . import document as documents
from . import protocol, report, server, websocket

PROG = 'lapki-build'
COMPILER = 'lapki-compiler'
TIMEOUT = 300
CONNECT_TIMEOUT = 30.0
KIB = 1024.0

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_COMPILER = 3
EXIT_TERMINATED = 128 + signal.SIGTERM


def _seconds(text):
    try:
        value = float(text)
    except ValueError as e:
        raise argparse.ArgumentTypeError('not a number: ' + text) from e
    if value < 0:
        raise argparse.ArgumentTypeError('negative: ' + text)
    return value


def _parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('input', metavar='INPUT', help='the diagram, '
                        'CyberiadaML-GraphML')
    common.add_argument('--diagnostics', metavar='FILE', help='write the '
                        'findings as the diagnostics file of the editor')
    group = common.add_argument_group('the compiler')
    group.add_argument('--server', metavar='LINK', default='', help='the '
                       'remote compiler: ws://host:port[/path], '
                       'wss://host:port[/path] or host:port; empty - the '
                       'local compiler')
    group.add_argument('--compiler', metavar='EXE', default=COMPILER,
                       help='the local compiler: a name on PATH or a path '
                       '(default: %(default)s)')
    group.add_argument('--workdir', metavar='DIR', help='the directory of '
                       'the converted diagram and of the local compiler '
                       '(default: a temporary one)')
    group.add_argument('--timeout', metavar='S', type=_seconds,
                       default=TIMEOUT, help='wait for the reply, seconds; '
                       '0 - no limit (default: %(default)s)')
    parser = argparse.ArgumentParser(
        prog=PROG, description='Build a CyberiadaML diagram with '
        'lapki-compiler: the sources and the firmware of its state machines.')
    parser.add_argument('--version', action='version',
                        version='%(prog)s ' + __version__)
    parser.add_argument('--install-editor-plugin', nargs='?', const='',
                        metavar='DIR', help='install the plugin of '
                        'CyberiadaPro into DIR or the user plugin folder')
    commands = parser.add_subparsers(dest='command', metavar='COMMAND')
    build = commands.add_parser('build', parents=[common], help='write the '
                                'sources and the firmware of every machine')
    build.add_argument('-o', '--outdir', metavar='OUTDIR', required=True,
                       help='the output directory, made when missing')
    commands.add_parser('code', parents=[common],
                        help='print the generated sources')
    commands.add_parser('check', parents=[common], help='check whether the '
                        'compiler can build the diagram')
    return parser


def _error(what, why):
    sys.stderr.write('{}: {}: {}\n'.format(PROG, what, why))


def _plural(count, word):
    return '{} {}{}'.format(count, word, '' if count == 1 else 's')


def _finish(options, items, out):
    report.print_findings(items, out)
    if options.diagnostics:
        try:
            report.write_diagnostics(options.diagnostics, items)
        except OSError as e:
            _error(options.diagnostics, e.strerror or e)
            return False
    return True


def _compile(url, document, timeout):
    try:
        with websocket.connect(url, CONNECT_TIMEOUT) as connection:
            return protocol.compile_cgml(connection, document.xml,
                                         timeout or None)
    except websocket.WebSocketError as e:
        raise protocol.ProtocolError(str(e)) from e


def _check(options, document, workdir, out):
    if document.missing_meta():
        _finish(options, checking.check(document, None, None), out)
        return EXIT_OK
    try:
        with server.open_compiler(options.server, options.compiler, workdir,
                                  out) as url:
            compiler = None if options.server else \
                server.find_compiler(options.compiler)
            items = checking.check(document, url, compiler,
                                   options.timeout or None)
    except server.ServerError as e:
        items = checking.check(document, None, None)
        items.append(report.finding(report.ERROR, 'lapki-compiler', str(e)))
    _finish(options, items, out)
    return EXIT_OK


def _built(options, document, reply, out):
    try:
        written = report.write_files(reply, document, options.outdir)
    except OSError as e:
        _error(options.outdir, e.strerror or e)
        return EXIT_USAGE
    report.print_log(reply, document, out)
    folders = {}
    for path in written:
        folders.setdefault(os.path.basename(os.path.dirname(path)),
                           []).append(os.path.basename(path))
    for folder, names in folders.items():
        out.write('{}: {}: {}\n'.format(PROG, folder, ', '.join(names)))
    built = sum(1 for m in document.machines if m.id in reply.machines and
                reply.machines[m.id].result == protocol.OK)
    out.write('{}: built {} of {}\n'.format(
        PROG, built, _plural(len(document.machines), 'state machine')))
    items = report.findings(reply, document)
    if not _finish(options, items, out):
        return EXIT_USAGE
    return EXIT_FAILED if any(i['severity'] == report.ERROR
                              for i in items) else EXIT_OK


def _code(options, document, reply, out):
    report.print_sources(reply, document, out)
    items = report.findings(reply, document)
    if not _finish(options, items, out):
        return EXIT_USAGE
    complete = protocol.INTERNAL not in reply.machines and \
        all(m.sources for m in reply.machines.values())
    return EXIT_OK if complete else EXIT_FAILED


def _run(options, workdir):  # pylint: disable=too-many-return-statements
    out = sys.stdout
    if not os.path.isfile(options.input):
        _error(options.input, 'no such file')
        return EXIT_USAGE
    try:
        document = documents.load(options.input, workdir)
    except documents.DocumentError as e:
        _error(options.input, e)
        return EXIT_USAGE
    if options.command == 'check':
        return _check(options, document, workdir, out)
    items = report.meta_findings(document)
    if items:
        return EXIT_USAGE if not _finish(options, items, out) else \
            EXIT_FAILED
    if options.command == 'build':
        try:
            os.makedirs(options.outdir, exist_ok=True)
        except OSError as e:
            _error(options.outdir, e.strerror or e)
            return EXIT_USAGE
    try:
        with server.open_compiler(options.server, options.compiler, workdir,
                                  out) as url:
            out.write('{}: {}, {} {}, {:.1f} KiB\n'.format(
                PROG, _plural(len(document.machines), 'state machine'),
                document.platform, document.platform_version,
                document.size() / KIB))
            out.flush()
            reply = _compile(url, document, options.timeout)
    except server.ServerError as e:
        _error('no compiler', e)
        return EXIT_COMPILER
    except protocol.ProtocolError as e:
        _error('the compiler', e)
        return EXIT_COMPILER
    if options.command == 'build':
        return _built(options, document, reply, out)
    return _code(options, document, reply, out)


def _terminated(signum, frame):
    # unwinds the run: a local compiler is stopped on the way out
    raise SystemExit(EXIT_TERMINATED)


def main(argv=None):
    """Run the command; return the exit code."""
    parser = _parser()
    try:
        options = parser.parse_args(argv)
    except SystemExit as e:
        return e.code
    if options.install_editor_plugin is not None:
        _error('--install-editor-plugin', 'not in this version')
        return EXIT_USAGE
    if not options.command:
        parser.print_usage(sys.stderr)
        return EXIT_USAGE
    previous = None
    if threading.current_thread() is threading.main_thread():
        previous = signal.signal(signal.SIGTERM, _terminated)
    workdir, temporary = options.workdir, not options.workdir
    if temporary:
        workdir = tempfile.mkdtemp(prefix=PROG + '-')
    try:
        return _run(options, workdir)
    finally:
        sys.stdout.flush()
        if temporary:
            shutil.rmtree(workdir, ignore_errors=True)
        if previous is not None:
            signal.signal(signal.SIGTERM, previous)

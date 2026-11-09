# The CyberiadaPro Plugin for Lapki Compiler

The plugin of the Cyberiada State Machine Editor (`CyberiadaPro`) that
builds the open diagram with `lapki-compiler`. The diagram goes to the
compiler, which generates the code for the diagram's platform (Arduino
Uno, the MS-TYuK and Cybermishka boards, ...) and builds the firmware. The
sources, the firmware, the build log and the failures come back into the
editor. The compiler is the installed one, started for every run on this
computer, or a remote server given by a link. The plugin is written in
pure Python 3 with the `CyberiadaML` module and runs as the command
`lapki-build` too.

The code is distributed under the Lesser GNU Public License (version 3), the
documentation -- under the GNU Free Documentation License (version 1.3).

## Documentation

The documentation is located in the `docs` directory and contains:

* The architecture - `ARCHITECTURE.md`: the run, the document, the local
  and the remote compiler, the protocol, the results, the editor plugin,
  the testing
* The interface specification - `API.md`: the command `lapki-build`, the
  plugin descriptor and the modules of the package `lapki_build`

## Requirements

* python3 (version 3.8+)
* the `CyberiadaML` module: libcyberiadamlpp-py (version 1.0.8+) or, when
  it is not installed, cyberiadaml-py (version 1.8+), its pure-Python
  interface
* lapki-compiler - installed on this computer (`lapki-compiler` on `PATH`
  or a path in the settings) with the toolchains of its platforms, or a
  remote server
* CyberiadaPro with the plugin conditions (`requires`, `when`) - for the
  editor plugin
* pytest - for the tests
* cmake (version 3.16+) - for the Debian package

## Usage

    lapki-build build blinker.graphml -o build
    lapki-build build blinker.graphml -o build --server ws://ide.polyus-nt.ru:8084
    lapki-build code blinker.graphml
    lapki-build check blinker.graphml --diagnostics findings.json

Without `--server` the command starts the installed compiler
(`--compiler`, `lapki-compiler` by default) on a free port and stops it at
the end. `build` writes the sources and the firmware of every state machine
into `<outdir>/<machine>/`; `code` prints the generated sources; `check`
asks the compiler whether it can build the diagram.

In the editor: Plugins > Lapki Compiler > Build, Show the code, Check; the
remote compiler and the local one are set in Settings...

## Tests

    python3 -B -m pytest -q tests

The tests need no compiler and no network: a local stub plays the
compiler. The runs against a real compiler are opt-in:
`LAPKI_COMPILER_URL=ws://ide.polyus-nt.ru:8084` for the remote one,
`LAPKI_COMPILER=<path>` for an installed one.

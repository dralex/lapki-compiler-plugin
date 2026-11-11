# The Lapki Compiler Plugin Architecture

Document version: 0.2 (2026-11-11)

The plugin brings `lapki-compiler` into `CyberiadaPro`: it sends the open
diagram to the compiler and gives the editor back what the compiler made -
the generated sources and the firmware of every state machine, the build
log and the failures. It does what the compiler panel of Lapki IDE
(`lapki-client`) does, as a plugin of the editor contract (`api` 1,
`CyberiadaHSM-Editor/docs/PLUGIN-API.md`): a child process with files in
and files out, no window of its own.

The plugin depends on the Python 3 standard library and the `CyberiadaML`
module only: no WebSocket package, no code of the compiler, no editor
library. The compiler is a WebSocket server; the plugin either starts the
installed one for the run or connects to a remote one by a link.

```
     CyberiadaPro                   lapki-build                  lapki-compiler
 +------------------+         +------------------+         +------------------+
 |                  | - run ->|                  | -spawn->|                  |
 |  plugin runner   |  input  |  build, code,    |  local  |  /main           |
 |                  |         |  check           | - cgml >|                  |
 |                  |<-files -|                  |  Lapki  |  code generator, |
 |                  |  stdout |                  |<-reply -|  toolchains      |
 |                  |  diagn. |                  |  JSON   |                  |
 +------------------+         +------------------+         +------------------+
```

## Usage requirements

| No | Requirement | Section |
|---|---|---|
| R1 | Build the open diagram from `CyberiadaPro`: the sources and the firmware of every state machine into a directory. | The results |
| R2 | Show the generated code without writing files. | The editor plugin |
| R3 | Check the diagram before a build: the compiler answers, knows the platform, has its toolchain. | The check |
| R4 | Use the installed compiler by default, started for a run and stopped after it; use a remote compiler when its link is given. Nothing leaves the computer without a link. | The compiler |
| R5 | Send the compiler the Lapki dialect it reads, made from the editor's Cyberiada 1.0 by the `CyberiadaML` module. | The document |
| R6 | Show the build log in the output tab and the failures as diagnostics on the state machines. | The results |
| R7 | Grey the actions out on a diagram without a platform: declare the conditions to the editor. | The editor plugin |
| R8 | Python 3.8+, the standard library and the `CyberiadaML` module only (its binding for the Lapki writer). | Code layout |
| R9 | Run as the command `lapki-build` too, for scripts and the tests. | The interface |

## The run

One run is one request: the plugin makes the Lapki document, gets a
compiler, sends the document, writes the reply and stops what it started.

```
 CyberiadaPro          lapki-build                       lapki-compiler
      |                     |                                  |
      |-- argv, input ----->|                                  |
      |                     |-- open, save as Lapki            |
      |                     |   (CyberiadaML)                  |
      |                     |-- spawn on a free port --------->|   local mode
      |                     |-- connect ws://.../main -------->|
      |                     |-- "cgml" ----------------------->|
      |                     |-- the Lapki XML ---------------->|
      |                     |                                  |-- generate,
      |                     |                                  |   build
      |                     |<--------------- the JSON reply --|
      |                     |-- GET /kill -------------------->|   local mode
      |<-- the build log ---|                                  |
      |<-- files, diagn. ---|                                  |
      |<-- the exit code ---|                                  |
```

The compiler answers once, when all the machines are built: the log comes
at the end, not while the build goes. The plugin waits for the reply up to
the timeout (`--timeout`, 300 s by default; the editor's limit of the
action is 600 s).

## The document

The editor gives the plugin the open document as CyberiadaML-GraphML 1.0
(`${input}`, unsaved edits included). `lapki-compiler` reads it with
`cyberiadaml-py` 1.x, which expects the Lapki dialect of Cyberiada 1.0:
the components are formal comments `CGML_COMPONENT` with the `id/`
parameter, and every machine carries the meta node. `libcyberiadaml`
writes this dialect (`formatLapki`), so the plugin converts and does not
build the XML itself:

```
 input.graphml  --open-->  CyberiadaML document  --save_as(formatLapki)-->  lapki.graphml
 (Cyberiada 1.0)            machines: id, name                               (sent as is)
                            meta: platform, platformVersion
```

The module is the binding of `libcyberiadamlpp-py` when it is installed,
else the pure-Python interface of `cyberiadaml-py`
(`cyberiadaml_py.cml`), as in `fa-dispatcher-py`. The pure-Python
interface reads the diagram but has no Lapki writer yet (`cyberiadaml-py`
1.8, `docs/CML.md`): with it the run stops with the document error, so a
build needs the binding. The document gives the
plugin the ids and the names of the machines (the reply is keyed by the
ids) and the platform with its version. The meta is the document's: all
its machines share the platform.

## The compiler

```
 --server LINK     -> remote: ws://host:port/main, the link as given
 (empty, absent)   -> local:  --compiler (lapki-compiler on PATH, or a path)
```

A link is `ws://host:port[/path]`, `wss://host:port[/path]` or
`host:port`; the path is `/main` when it is not given. Example:
`ws://ide.polyus-nt.ru:8084`. There is no default server: without a link
the diagram stays on the computer.

The local compiler lives for one run:

```
  find the compiler --> a free port --> spawn --> wait for the port --> the request
  (PATH or the path)    (bind port 0)             (30 s; the exit of        |
                                                   the child fails)         v
  the exit <-- kill <-- terminate, 3 s <-- GET /kill, 1 s <-------------- the end
                                                                    (done, error, SIGTERM)
```

The plugin makes `<workdir>` before the spawn: the compiler creates its
token file there but not the directory. The compiler opens the port after
loading its platforms. `/kill` exits the compiler without an HTTP answer:
a closed connection is the success.

It is started as Lapki IDE starts it (`ModuleManager.ts`):

    lapki-compiler --server-host=127.0.0.1 --server-port=<port> --killable
        --build-directory=<workdir>/build --artifacts-directory=<workdir>/artifacts
        --log-path=<workdir>/compiler.log --access-token-path=<workdir>/tokens

The platforms and the libraries are the compiler's own, beside its
module or its executable. `<workdir>` is the editor's run directory
(`${rundir}`), removed after the run; the output of the child goes to
`<workdir>/compiler.out`. A Cancel or a timeout of the editor sends
SIGTERM to the plugin, which stops the child before it exits. A compiler
that is not found fails the run with one line: install it or set the
remote link.

## The protocol

The plugin speaks the protocol of Lapki IDE: one WebSocket connection to
`/main`, a command word in a text frame, then its arguments in text
frames.

| Command | The plugin sends | The compiler answers |
|---|---|---|
| `cgml` | `cgml`, the Lapki XML | one JSON reply (below) |
| `get_platform_json` | `get_platform_json`, the platform id, the version | `raw-platform-scheme`, the platform JSON; an error text and a close for an unknown platform |

```
 { "result": "OK" | "NOTOK",
   "state_machines": {
     "<machine id>": { "result": "OK" | "NOTOK", "name": "<machine id>",
                       "commands": [ { "command": "...", "return_code": 0,
                                       "stdout": "...", "stderr": "..." } ],
                       "binary": [ { "filename": "sketch", "extension": "ino.hex",
                                     "fileContent": "<base64>" } ],
                       "source": [ { "filename": "sketch", "extension": "ino",
                                     "fileContent": "<text>" } ] } } }
```

* `name` is the machine id. An OK reply leaves the connection open.
* A machine the compiler rejects has the command `Валидация МС` with the
  return code -1 and the message in `stderr`; a missing `platformVersion`
  is such a rejection.
* An internal error (an unreadable diagram, an unknown platform, a
  program of the toolchain not found, a tool output not in UTF-8) is the
  machine `""` with the command `compiler job`, the return code -2 and
  `Internal error!`; the compiler closes the connection after it.
* A machine of a platform that is not compiled (`compile: false`, the
  Berloga platforms) is left out of the reply before any validation;
  with no machine left the reply is `{"result": "OK", "state_machines": {}}`.
* The compiler takes messages up to 256 KiB (`--max-msg-size`); a larger
  diagram closes the connection with the code 1009 and no reply.
* The id check of the compiler is broken (`CGML.py`: the pattern and the
  string are swapped): only an empty id is rejected, an id with the regular
  expression characters fails with -2. `lapki-id` is the plugin's own rule.
* The command of a reply is shown as the platform declares it, before the
  substitution of `{library_dir}`, `{base_dir}`, `{artifacts_dir}`.

`websocket.py` is a client of RFC 6455 on `socket` and `ssl`: the
handshake, masked frames, the 7, 16 and 64-bit lengths, fragmented
messages, ping and pong, the close codes. It has no extensions and no
server side.

## The results

```
 <outdir>/                     the output directory (Settings: next to the diagram)
   <machine>/                  the machine name, else its id; its sketch.* replaced
     sketch.ino                the sources: sketch.<main>, sketch.<header>
     sketch.h
     sketch.ino.hex            the firmware: <filename>.<extension> of the reply,
     sketch.ino.with_bootloader.hex   every file of it (AVR: .hex, .eep, .elf,
     ...                              .with_bootloader.hex, .with_bootloader.bin)
```

The build log goes to stdout, a block per machine: its commands with the
return codes, their stdout and stderr. The failures go to the diagnostics
file of the editor:

| Rule | Severity | Element | When |
|---|---|---|---|
| `lapki-meta` | error | - | the document has no `platform` or no `platformVersion` (an editor before the conditions) |
| `lapki-validation` | error | the machine | the compiler rejects the machine (-1) |
| `lapki-build` | error | the machine | a command of the build fails; the message is the first error line of its stderr |
| `lapki-internal` | error | - | the internal error of the compiler (-2) |
| `lapki-skipped` | warning | the machine | the machine is not in the reply: its platform is not compiled |
| `lapki-platform` | error, warning | - | Check: the platform is unknown to the compiler; not compiled |
| `lapki-toolchain` | error | - | Check, local: a program of the platform's build is not on `PATH` |
| `lapki-compiler` | error | - | Check: no compiler (not found, not started, no answer) |
| `lapki-id` | error | the machine | Check: the machine id is not of letters, digits and `_` |
| `lapki-size` | warning | - | Check: the Lapki XML is larger than 256 KiB |

| Exit code | `build` | `code` | `check` |
|---|---|---|---|
| 0 | every machine built | every machine has its sources | checked, findings or not |
| 1 | a machine failed or was rejected | a machine has no sources | - |
| 2 | a usage error | a usage error | a usage error |
| 3 | no compiler, a lost connection, a timeout, an unreadable reply | the same | - |

## The check

Check asks only what the run alone can know; the document conditions the
editor checks itself (The editor plugin).

```
 the document --> machine ids, the size of the Lapki XML
 the compiler --> it starts (local) and answers
              --> get_platform_json <platform> <version>: known? compile?
              --> local: every command of compilingSettings on PATH
```

The findings go to the Diagnostics tab; the check exits 0 with them. It
builds nothing.

## The editor plugin

`editor-plugin/` is the plugin of `CyberiadaPro`: a descriptor that runs
`python3 -m lapki_build`, no adapter. Its README is for the users of the
editor.

```
 Plugins                                    the toolbar
 +-----------------------------+            +--------------------+
 | Lapki Compiler            > |            | Lapki Compiler [>] |   [>] build
 +-----------------------------+            +--------------------+
   | Build                     |
   | Show the code             |
   | Check                     |
   |---------------------------|
   | Settings...               |
   +---------------------------+

 +--------------------------------------------------+
 | Lapki Compiler - Settings                    [x] |
 +--------------------------------------------------+
 | Remote compiler  [                             ] |
 | Local compiler   [lapki-compiler               ] |
 | Timeout, s       [300                          ] |
 | Output directory [~/diagrams/blinker-build][...] |
 |                                [Cancel]   [OK]   |
 +--------------------------------------------------+
```

| Action | Result | The command after `python3 -m lapki_build` |
|---|---|---|
| `build` - Build | `files` | `build ${input} -o ${outdir} --diagnostics ${diagnostics}` + the compiler options |
| `code` - Show the code | `log` | `code ${input} --diagnostics ${diagnostics}` + the compiler options |
| `check` - Check | `diagnostics` | `check ${input} --diagnostics ${diagnostics}` + the compiler options |

The compiler options are `[--server ${param:server}] --compiler
${param:compiler} --workdir ${rundir} --timeout ${param:timeout}`; the
server is passed only when it is set. The output directory is a
`document` parameter, asked at the first build of a document file
(`${document_dir}/${document_name}-build`); the others are kept per user.

Every action declares the document conditions of the editor
(`PLUGIN-API.md`, Conditions):

    "when": ["sm", "meta:platform", "meta:platformVersion"],
    "reason": "Set the platform and its version in the diagram (e.g. ArduinoUno 1.0)"

The editor greys the actions out on a diagram without them, with the
reason in the tooltip. The plugin never fills the meta. It declares no
`requires`: `programs` sees only `PATH`, not the remote link, so a
missing local compiler is told by the run. An editor before the
conditions ignores them; the run then reports `lapki-meta`.

## Code layout

```
 cli.py ------+--> document.py --> CyberiadaML module (the binding or cyberiadaml_py.cml)
              |
              +--> server.py ----> the lapki-compiler process (local mode)
              |
              +--> protocol.py --> websocket.py --> socket, ssl
              |
              +--> check.py -----> protocol.py, server.py
              |
              +--> report.py ----> <outdir>, stdout, diagnostics.json
```

| Path | Contents |
|---|---|
| `lapki_build/cli.py` | the command: `build`, `code`, `check`, `--install-editor-plugin` |
| `lapki_build/document.py` | the conversion to the Lapki dialect, the machines, the meta |
| `lapki_build/server.py` | the local compiler and the remote link |
| `lapki_build/protocol.py` | the commands of `/main`, the reply |
| `lapki_build/websocket.py` | the WebSocket client |
| `lapki_build/check.py` | the findings of Check |
| `lapki_build/report.py` | the files, the build log, the diagnostics |
| `lapki_build/plugin.py` | the installation of the editor plugin |
| `editor-plugin/` | `plugin.json`, `README.md`, `i18n/ru.json`, `icons/` |
| `tests/` | the tests, `diagrams/`, `good/` |

The package is `lapki_build`, not `compiler`: that is the package of
`lapki-compiler`, which may be installed into the same Python.

## Packaging

```
 editor-plugin/  --+--> cpack -G DEB ---> /usr/share/cyberiada-pro/plugins/lapki-compiler/
 lapki_build/    --+                      /usr/lib/python3/dist-packages/lapki_build/
                   |                      /usr/bin/lapki-build
                   |
                   +--> pip install ----> <prefix>/share/cyberiada-pro/plugins/lapki-compiler/
                                          <prefix>/.../site-packages/lapki_build/
                                          <prefix>/bin/lapki-build
                                                 |
                                                 | lapki-build --install-editor-plugin [DIR]
                                                 v
                                  <user folder>/lapki-compiler/   (argv[0] = <prefix>'s Python)
```

| Package | Needs |
|---|---|
| `python3-lapki-compiler-plugin` (deb, `all`) | `python3 (>= 3.8)`, `python3-libcyberiadamlpp (>= 1.1.0)`; enhances `cyberiada-pro` |
| `lapki-compiler-plugin` (wheel) | the binding installed apart (`cyberiadaml-py` 1.8 has no Lapki writer) |

`lapki-compiler` is not a dependency: it is installed apart (pip, the
Lapki IDE bundle), or a remote one is used. The packages are built and
tested with the editor's `packaging/build-toolchain.sh` like the other
plugins.

## Testing

| Layer | What | Needs |
|---|---|---|
| WebSocket | the frames, the lengths, the fragments, ping, close, 1009 | a stdlib test server |
| the document | the Lapki XML of the test diagrams; the corpus of `cyberiadaml-py`: Lapki -> Cyberiada 1.0 -> the plugin -> the fields `lapki-compiler` reads, as recorded (`tests/legacy/lapki-compiler-view.json`); the document error of the pure-Python interface | the binding and the sibling `cyberiadaml-py`, else skipped |
| the command | build, code, check against a stub compiler replaying the reply shapes of the compiler | - |
| the local compiler | spawn, the port, `/kill`, SIGTERM, a dead child | a fake `lapki-compiler` script |
| the editor | the descriptor; `--list-plugins`; a batch build against the stub; the actions refused with the reason on a course diagram and on a diagram without `platformVersion` | `CyberiadaPro` with the conditions (`CYBERIADA_PRO`), else skipped |
| the remote compiler | build, code, check of the test diagrams and of the Lapki sets: real firmware, the expected results in `tests/good` | `LAPKI_COMPILER_URL`, opt-in |
| the installed compiler | the same with a compiler installed from its sources | `LAPKI_COMPILER`, opt-in |

The test diagrams:

* `tests/diagrams/` - our own, small: an Arduino Uno blinker, an MS-TYuK
  button (`tjc-ms1-btn-a2`), two machines, a Berloga machine (skipped), no
  `platformVersion`, an unknown component type (-2), an unknown event of a
  component (-1), an undeclared component (the build fails).
* the Lapki sets of the project, used where they are, not copied (GPL-3):
  `cyberiadaml-compat-tests/fixtures/dialect/lapki` (21 Arduino Uno, 13
  MS-TYuK, ...) and `lapki-compiler/examples`; `LAPKI_EXAMPLES` points
  elsewhere.
* the course diagrams of `hsm-arduino-course/diagrams`: abstract, without
  a platform - the case the conditions refuse.

The expected results record the result of every machine, the names of the
files and the failed commands, never the contents of the firmware. They
are recorded from the remote compiler once and reviewed.

## Reuse

| Need | Reused | Not reused |
|---|---|---|
| the Lapki dialect | `formatLapki` of `libcyberiadaml` through the binding | the writer of `cyberiadaml_py.cml`: not there yet |
| the module choice | the binding, else `cyberiadaml_py.cml` (`fa-dispatcher-py/fad/reader.py`) | - |
| the local compiler | the arguments and `/kill` of Lapki IDE (`ModuleManager.ts`) | - |
| the plugin installation | `hsm_maker/plugin.py`, adapted | no package shared by the plugins |
| the stub server | the pattern of `cybersphere-hsm-maker/tests/conftest.py` | it is HTTP only |
| the compiler's view | `cyberiadaml-py/tests/legacy` | - |
| WebSocket | - | `websockets`: a new dependency of the deb and a wheel per Python of the Windows installer; `compiler/Client.py`: aiohttp |

## Known limits

* The compiler sends nothing until all the machines are built: no
  progress, the log at the end.
* A program of the toolchain that is not installed where the compiler
  runs fails the whole request with `Internal error!`, without the sources;
  Check names the missing program of a local compiler.
* The compiler waits for a command before it reads its output
  (`Compiler.py`): a command printing more than about 192 KiB to one
  stream hangs until the timeout, and the compiler never stops it.
* The compiler copies the platform libraries with `cp` it does not wait
  for (`os_commands/posix.py`): a loaded server may fail a build at random.
* The compiler needs Python 3.10 or 3.11 (`aiohttp` 3.8.4, `aiopath` 0.6).
* The firmware loses the subdirectories of the build: the reply keeps the
  base names only.
* All the machines of the document are built: the editor gives the plugin
  no chosen machine.
* A machine with an empty id is rejected by the compiler.
* A remote compiler keeps every build on its disk.
* On Windows the editor kills the plugin without SIGTERM: a local
  compiler outlives a Cancel there.
* The firmware is not uploaded: that is `lapki-flasher`.
* The conversion is the binding's: it drops `propagate` of an entry
  behaviour and fails on a few documents of the Lapki corpus
  (`tests/test_corpus.py`, the known cases).
* The Lapki files of the early IDE have no `platformVersion`: the run
  refuses them (`lapki-meta`), as the compiler would.

## Stages

| Stage | Contents |
|---|---|
| 1 | this document, `API.md`, the README |
| 2 | `websocket.py` and its tests |
| 3 | `document.py`, `protocol.py`, `report.py`, `cli.py` with a remote compiler; the stub |
| 4 | `server.py`: the local compiler |
| 5 | `editor-plugin/`, `plugin.py`, the editor tests |
| 6 | the packages: `pyproject.toml`, `CMakeLists.txt`, the deb |
| 7 | the editor side: `build-toolchain.sh`, the Windows installer, `PLUGIN-API.md` |

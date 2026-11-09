# The Lapki Compiler Plugin Interface Specification

Document version: 0.1 (2026-11-09)

The command `lapki-build`, the editor plugin descriptor and the modules
of the package `lapki_build`. The reasons are in `ARCHITECTURE.md`.

## Command lapki-build

    lapki-build build INPUT -o OUTDIR [--diagnostics FILE] [COMPILER OPTIONS]
    lapki-build code  INPUT [--diagnostics FILE] [COMPILER OPTIONS]
    lapki-build check INPUT [--diagnostics FILE] [COMPILER OPTIONS]
    lapki-build --install-editor-plugin [DIR]
    lapki-build --version

`python3 -m lapki_build` is the same command.

* `INPUT` - the diagram, CyberiadaML-GraphML 1.0 or another format the
  `CyberiadaML` module reads.
* `-o OUTDIR` - `build`: the output directory, made when missing.
* `--diagnostics FILE` - write the findings as the editor's diagnostics
  file (a JSON array, The diagnostics); without it they are only printed.

The compiler options:

* `--server LINK` - the remote compiler: `ws://host:port[/path]`,
  `wss://host:port[/path]` or `host:port`; the path is `/main` by default.
  Empty or absent: the local compiler.
* `--compiler EXE` - the local compiler: a name on `PATH` or a path;
  `lapki-compiler` by default.
* `--workdir DIR` - the directory of the converted document and of the
  local compiler's build, artifacts, log and output; a temporary directory
  removed at the exit by default.
* `--timeout S` - how long to wait for the reply, in seconds; 300 by
  default, 0 for no limit.

`build` writes `OUTDIR/<machine>/` per machine of the reply: the sources
and the firmware, after removing the `sketch.*` files there. `<machine>`
is the machine name with the characters other than letters, digits, `-`,
`_` and `.` replaced by `_`, else its id; a name taken twice gets `-<id>`.

stdout:

    lapki-build: the local compiler lapki-compiler on 127.0.0.1:50123
    lapki-build: 1 state machine, ArduinoUno 1.0, 12.3 KiB
    == Blinker (G0): OK
    $ arduino-cli compile --export-binaries -b arduino:avr:uno ...
    return code 0
    <stdout and stderr of the command>
    lapki-build: Blinker: sketch.ino, sketch.h, sketch.ino.hex, ...
    lapki-build: built 1 of 1 state machines

`code` prints `== <machine>: <file>` and the text of every source instead
of the commands; `check` prints its findings, one a line:
`error: lapki-platform: the compiler has no platform Foo 1.0`.

| Exit code | Meaning |
|---|---|
| 0 | `build`: every machine built; `code`: every machine has its sources; `check`: checked, with findings or not |
| 1 | `build`, `code`: a machine failed or was rejected, or the document is not buildable; the findings are written |
| 2 | a usage error: an unknown option, an unreadable `INPUT`, an unwritable `OUTDIR` |
| 3 | `build`, `code`: no compiler - not found, not started, the connection refused or lost, the timeout, an unreadable reply |

Errors are one line on stderr: `lapki-build: <what>: <why>`.

## The diagnostics

The file is the array of the editor (`PLUGIN-API.md`, The diagnostics
file): `{severity, message, rule, element?}`.

| Rule | Severity | Element | Message |
|---|---|---|---|
| `lapki-meta` | error | - | `the diagram has no platform` / `no platformVersion` |
| `lapki-validation` | error | the machine id | the compiler's message |
| `lapki-build` | error | the machine id | `<program>: <the first error line of stderr>`, else `<program>: return code <n>` |
| `lapki-internal` | error | - | `the compiler failed: <stderr>` |
| `lapki-skipped` | warning | the machine id | `not built: the platform <id> is not compiled` |
| `lapki-platform` | error | - | `the compiler has no platform <id> <version>` |
| `lapki-platform` | warning | - | `the platform <id> is not compiled` |
| `lapki-toolchain` | error | - | `<program> of the platform <id> is not on PATH` |
| `lapki-compiler` | error | - | the reason there is no compiler |
| `lapki-id` | error | the machine id | `the id must consist of letters, digits and _` |
| `lapki-size` | warning | - | `the diagram is <n> KiB; the compiler takes 256 KiB by default` |

The first error line of a stderr is its first line holding `error:`, else
its first line that is not empty.

## The editor plugin

`editor-plugin/plugin.json`, `api` 1, id `lapki-compiler`, name `Lapki
Compiler`, interpreter `python3`, `env` `{"PYTHONUTF8": "1"}`.

| Parameter | Type | Scope | Default | Label |
|---|---|---|---|---|
| `server` | `string` | `persistent` | empty | Remote compiler |
| `compiler` | `string` | `persistent` | `lapki-compiler` | Local compiler |
| `timeout` | `int` (0-3600) | `persistent` | 300 | Timeout, s |
| `outdir` | `dir`, `create` | `document` | `${document_dir}/${document_name}-build` | Output directory |

| Action | Label | Result | `exit_ok` | Timeout | Parameters |
|---|---|---|---|---|---|
| `build` | Build | `files`, `outdir: outdir`, toolbar | `[0, 1]` | 600 | all |
| `code` | Show the code | `log` | `[0, 1]` | 600 | `server`, `compiler`, `timeout` |
| `check` | Check | `diagnostics` | `[0]` | 120 | `server`, `compiler`, `timeout` |

Every action has

    "when": ["sm", "meta:platform", "meta:platformVersion"],
    "reason": "Set the platform and its version in the diagram (e.g. ArduinoUno 1.0)"

and no `requires`. The argv of `build`:

    ["-m", "lapki_build", "build", "${input}", "-o", "${outdir}",
     "--diagnostics", "${diagnostics}",
     {"if": "server", "argv": ["--server", "${param:server}"]},
     "--compiler", "${param:compiler}", "--workdir", "${rundir}",
     "--timeout", "${param:timeout}"]

`code` and `check` take the same without `-o ${outdir}`. The texts are
translated in `i18n/ru.json`.

## Package lapki_build

* `__version__` - the version of the package.

## Module websocket

The WebSocket client (RFC 6455) over `socket` and `ssl`.

* `connect(url, timeout=None, max_size=MAX_MESSAGE)` - open a connection to
  a `ws://` or `wss://` URL; return a `Connection`. `timeout` limits the
  connection and the handshake. Raises `WebSocketError`.
* `Connection.send(text)` - send a text message.
* `Connection.receive(timeout=None)` - the next data message: `str` for a
  text one, `bytes` for a binary one. Answers the pings on the way. Raises
  `ClosedError` when the server closes, `WebSocketError` on a timeout or a
  broken frame or a message over `max_size`.
* `Connection.close(code=1000, reason='')` - close the connection; also
  the exit of `with Connection`.
* `MAX_MESSAGE` - the largest message received, 64 MiB.

Exceptions:

* `WebSocketError` - the connection failed.
* `ClosedError(WebSocketError)` - the server closed the connection;
  `code` and `reason` of its close frame (`code` 1006 without one).

## Module protocol

The commands of `/main` and the reply of the compiler.

* `compile_cgml(connection, xml, timeout=None)` - send `cgml` and the
  Lapki XML; return the `Reply`. Raises `ProtocolError`.
* `get_platform(connection, platform, version, timeout=None)` - send
  `get_platform_json`; return the platform as a `dict`, or `None` when the
  compiler does not know it.
* `parse_reply(text)` - the `Reply` of a JSON text. Raises
  `ProtocolError` when it is not a reply.
* `ROUTE` - `/main`.
* `INTERNAL` - `''`, the machine id of an internal error.

Data:

* `Reply(result, machines)` - `result` is `'OK'` or `'NOTOK'`;
  `machines` maps the machine ids to `MachineResult`.
* `MachineResult(id, result, commands, binaries, sources)` - the lists of
  `Command` and `File`.
* `Command(command, return_code, stdout, stderr)` - `return_code` is an
  `int` or `None`; `-1` is the validation, `-2` an internal error.
* `File(name, content)` - `name` is `<filename>.<extension>`; `content` is
  `bytes` for the firmware (decoded from base64), `str` for a source.

Exceptions:

* `ProtocolError` - the reply cannot be read, or the connection failed
  (the `WebSocketError` as its cause).

## Module document

The diagram in the Lapki dialect.

* `load(path, workdir)` - open the diagram with the `CyberiadaML` module,
  save it as `formatLapki` into `workdir`; return a `Document`. Raises
  `DocumentError`.
* `Document.machines` - the list of `Machine(id, name)` in the document
  order.
* `Document.platform`, `Document.platform_version` - the meta values,
  `''` when absent.
* `Document.xml` - the Lapki XML text sent to the compiler.
* `Document.missing_meta()` - the absent keys of `platform` and
  `platformVersion`.
* `module()` - the `CyberiadaML` module in use: the binding, else
  `cyberiadaml_py.cml`; `LAPKI_BUILD_BACKEND=cml` chooses the second.

Exceptions:

* `DocumentError` - the diagram cannot be read or converted.

## Module server

The compiler of a run.

* `open_compiler(link, compiler, workdir, log)` - a context manager giving
  the URL of `/main`: the remote link when it is not empty, else a
  `LocalCompiler` started for the block. Raises `ServerError`.
* `remote_url(link)` - the URL of a link (`host:port` gets `ws://`, an
  absent path `/main`). Raises `ServerError` for a bad link.
* `find_compiler(compiler)` - the path of the executable, or `None`.
* `LocalCompiler(executable, workdir, start_timeout=START_TIMEOUT)` - the
  local compiler: `start()` spawns it on a free port and waits for the
  port, `stop()` asks `/kill`, then terminates and kills; `url`, `port`;
  a context manager. SIGTERM of the plugin stops it.
* `START_TIMEOUT` - 30 s.

Exceptions:

* `ServerError` - no compiler: not found, not started, a bad link; the
  message ends with the tail of the child's output when it exited.

## Module report

* `write_files(reply, document, outdir)` - write the sources and the
  firmware; return the written paths.
* `print_log(reply, document, out)` - the build log of every machine.
* `print_sources(reply, document, out)` - the sources of every machine.
* `findings(reply, document)` - the diagnostics of a reply, a list of
  `dict`.
* `write_diagnostics(path, items)` - write the diagnostics file.
* `first_error(stderr)` - the first error line of a command's stderr.

## Module check

* `check(document, url, compiler)` - the findings of Check: the ids, the
  size, the platform on the compiler, the toolchain of a local compiler
  (`compiler` is `None` for a remote one).

## Module plugin

* `source()` - the plugin directory of this installation: `editor-plugin/`
  of a source tree, else the data files of the prefix or of the user base.
* `user_folder(environ=None, system=None)` - the editor's user plugin
  folder.
* `install(target=None, executable=None)` - copy the plugin into `target`
  or the user folder as `lapki-compiler`, every command started by
  `executable` (the running Python by default). Raises `PluginError`.

## Module cli

* `main(argv=None)` - run the command; return the exit code.

# The Lapki Compiler plugin of CyberiadaPro

The plugin builds the open diagram with `lapki-compiler`: the sources and
the firmware of every state machine for the platform of the diagram
(Arduino Uno, the MS-TYuK and Cybermishka boards, ...). The installed
compiler runs on this computer for every build; when a remote compiler is
set, the diagram is sent to that server and nothing runs locally.

## Installation

* From the source tree, with the `CyberiadaML` binding (libcyberiadamlpp-py)
  importable by the Python that runs the command:

      python3 -m lapki_build --install-editor-plugin

  The plugin goes to the editor's user plugin folder and runs that Python,
  with the tree and the binding found as they were for the command
  (`PYTHONPATH`, `LD_LIBRARY_PATH`), so the editor needs no setting. Run the
  command again after moving the tree or the binding.
* By hand: copy this directory as `lapki-compiler` into the user plugin
  folder and set the interpreter `python3` in Preferences > Plugins to a
  Python that imports `lapki_build` and `CyberiadaML`.

| System | The user plugin folder |
|---|---|
| Linux | `~/.local/share/Cyberiada/CyberiadaPro/plugins/` |
| Windows | `%APPDATA%\Cyberiada\CyberiadaPro\plugins\` |
| macOS | `~/Library/Application Support/Cyberiada/CyberiadaPro/plugins/` |

Restart the editor: the Plugins menu gets Lapki Compiler, the toolbar its
Build button. A local build needs `lapki-compiler` (Python 3.10-3.11) with
the toolchains of its platforms: `arduino-cli` with `arduino:avr` for
Arduino, `arm-none-eabi-gcc` for the MS-TYuK boards.

## Use

```
 Plugins > Lapki Compiler > Build...         the files in the output directory
                            Show the code    the sources in the Output tab
                            Check            the findings in the Diagnostics tab
                            Settings...      remote compiler, local compiler, timeout
```

The actions need the platform and its version in the meta of the diagram
(`platform/ ArduinoUno`, `platformVersion/ 1.0`): an editor with the plugin
conditions greys them out on a diagram without them, on a finite automaton
and on an empty document, with the reason in the tooltip; an older one runs
them and gets a `lapki-meta` finding.

* **Build...** asks for the output directory at the first build of a
  diagram (`<diagram>-build` beside it, remembered per diagram) and writes
  `<machine>/sketch.ino`, `sketch.h` and the firmware (`sketch.ino.hex`,
  `.elf`, `.eep`, ...) of every state machine; the editor lists the new and
  the changed files. The build log of the compiler goes to the Output tab,
  the failures to the Diagnostics tab: a click selects the state machine.
* **Show the code** prints the generated sources without writing files.
* **Check** asks the compiler without building: it answers, it knows the
  platform, the programs of the build are on `PATH` (a local compiler), the
  ids of the machines and the size of the diagram suit it.
* The settings are asked once and kept: the remote compiler
  (`ws://ide.polyus-nt.ru:8084`, or empty for the local one), the local
  compiler (`lapki-compiler` on `PATH` or a path), how long to wait for it.

The compiler answers when all the machines are built: the log comes at the
end. Cancel stops the run and a local compiler it started. The exit codes:
0 every machine built, 1 a machine failed or the diagram is not buildable
(the findings tell why), 2 a usage error, 3 no compiler (the Output tab
shows the reason).

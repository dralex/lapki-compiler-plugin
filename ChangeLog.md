# lapki-compiler-plugin project changelog

## Version 0.1.0 (unreleased)

Added:
- the specification: the architecture (`docs/ARCHITECTURE.md`) and the
  interface (`docs/API.md`) of the plugin;
- the package `lapki_build` and the command `lapki-build` (`python3 -m
  lapki_build`): build, code and check of a diagram with a remote
  lapki-compiler or the installed one started for the run, the diagram
  converted to the Lapki dialect by libcyberiadamlpp-py 1.1;
- the RFC 6455 WebSocket client of the standard library;
- the editor plugin `lapki-compiler`: Build..., Show the code and Check,
  greyed out without the platform of the diagram, the Russian texts;
- `lapki-build --install-editor-plugin [DIR]`, the pip package and the
  Debian package `python3-lapki-compiler-plugin`.

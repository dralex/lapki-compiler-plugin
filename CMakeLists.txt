cmake_minimum_required(VERSION 3.16)

# the Debian package of the plugin, its command and its editor plugin;
# nothing is compiled
project(lapki-compiler-plugin VERSION 0.1.0 LANGUAGES NONE)

# the place of the pure Python packages on Debian
set(PYTHON_INSTALL_DIR "lib/python3/dist-packages" CACHE STRING
    "the directory of the lapki_build package under the prefix")
# the system plugin folder of CyberiadaPro
set(PLUGIN_INSTALL_DIR "share/cyberiada-pro/plugins/lapki-compiler")
set(DOC_INSTALL_DIR "share/doc/python3-lapki-compiler-plugin")
# the package directories do not follow the umask of the build
set(CMAKE_INSTALL_DEFAULT_DIRECTORY_PERMISSIONS OWNER_READ OWNER_WRITE OWNER_EXECUTE
    GROUP_READ GROUP_EXECUTE WORLD_READ WORLD_EXECUTE)

install(FILES ${CMAKE_CURRENT_SOURCE_DIR}/lapki_build/__init__.py
              ${CMAKE_CURRENT_SOURCE_DIR}/lapki_build/__main__.py
              ${CMAKE_CURRENT_SOURCE_DIR}/lapki_build/check.py
              ${CMAKE_CURRENT_SOURCE_DIR}/lapki_build/cli.py
              ${CMAKE_CURRENT_SOURCE_DIR}/lapki_build/document.py
              ${CMAKE_CURRENT_SOURCE_DIR}/lapki_build/plugin.py
              ${CMAKE_CURRENT_SOURCE_DIR}/lapki_build/protocol.py
              ${CMAKE_CURRENT_SOURCE_DIR}/lapki_build/report.py
              ${CMAKE_CURRENT_SOURCE_DIR}/lapki_build/server.py
              ${CMAKE_CURRENT_SOURCE_DIR}/lapki_build/websocket.py
        DESTINATION ${PYTHON_INSTALL_DIR}/lapki_build)

# the command, as the wheel's entry point makes it
file(WRITE ${CMAKE_CURRENT_BINARY_DIR}/lapki-build
     "#!/usr/bin/python3\nimport sys\nfrom lapki_build.cli import main\nsys.exit(main())\n")
install(PROGRAMS ${CMAKE_CURRENT_BINARY_DIR}/lapki-build DESTINATION bin)

install(FILES ${CMAKE_CURRENT_SOURCE_DIR}/editor-plugin/plugin.json
              ${CMAKE_CURRENT_SOURCE_DIR}/editor-plugin/README.md
        DESTINATION ${PLUGIN_INSTALL_DIR})
install(FILES ${CMAKE_CURRENT_SOURCE_DIR}/editor-plugin/i18n/ru.json
        DESTINATION ${PLUGIN_INSTALL_DIR}/i18n)
install(DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/editor-plugin/icons
        DESTINATION ${PLUGIN_INSTALL_DIR})

install(FILES ${CMAKE_CURRENT_SOURCE_DIR}/ChangeLog.md
              ${CMAKE_CURRENT_SOURCE_DIR}/README.md
              ${CMAKE_CURRENT_SOURCE_DIR}/LICENSE
              ${CMAKE_CURRENT_SOURCE_DIR}/docs/ARCHITECTURE.md
              ${CMAKE_CURRENT_SOURCE_DIR}/docs/API.md
        DESTINATION ${DOC_INSTALL_DIR})

# the machine-readable (DEP-5) copyright, where the Debian policy wants it
install(FILES ${CMAKE_CURRENT_SOURCE_DIR}/debian-copyright
        DESTINATION ${DOC_INSTALL_DIR} RENAME copyright)

# the tests need pytest; the conversions need the CyberiadaML binding in this
# Python (-DPython3_EXECUTABLE=... selects another one) and are skipped without
# it; a stub plays the compiler
find_package(Python3 3.8 COMPONENTS Interpreter)
if(Python3_FOUND)
  enable_testing()
  add_test(NAME pytest
           COMMAND ${Python3_EXECUTABLE} -B -m pytest -q -p no:cacheprovider tests
           WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR})
endif()

# optional per-release suffix (e.g. ubuntu2404) for the package version
set(DISTRO_TAG "" CACHE STRING "distribution suffix appended to the package version")
configure_file("${PROJECT_SOURCE_DIR}/LapkiCompilerPluginPackOptions.cmake.in"
               "${PROJECT_BINARY_DIR}/LapkiCompilerPluginPackOptions.cmake"
               @ONLY)
set(CPACK_PROJECT_CONFIG_FILE "${PROJECT_BINARY_DIR}/LapkiCompilerPluginPackOptions.cmake")

include(CPack)

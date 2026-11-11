# -----------------------------------------------------------------------------
#  The Lapki Compiler Plugin
#
#  The editor plugin of an installation copied into a plugin folder of the
#  editor, its commands bound to one Python (after hsm_maker/plugin.py of
#  cybersphere-hsm-maker, LGPL-3)
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

"""The editor plugin of an installation copied into a plugin folder of the
editor, its commands bound to one Python."""

import json
import os
import platform
import shutil
import site
import sys

PLUGIN_ID = 'lapki-compiler'
DESCRIPTOR = 'plugin.json'
SOURCE_TREE = 'editor-plugin'
# the data files of the packages, the system plugin folder of the editor
SHARE = ('share', 'cyberiada-pro', 'plugins', PLUGIN_ID)
# the AppDataLocation of the editor (its vendor and application) + plugins
EDITOR_FOLDER = ('Cyberiada', 'CyberiadaPro', 'plugins')
# what the binding of a prefix needs; the editor's env replaces them
KEPT = ('LD_LIBRARY_PATH',)


class PluginError(Exception):
    """No plugin to install, or the copy failed."""


def _tree():
    """The source tree holding the package."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def source():
    """The plugin directory of this installation: editor-plugin/ of a source
    tree, else the data files of the prefix or of the user base."""
    for path in (os.path.join(_tree(), SOURCE_TREE),
                 os.path.join(sys.prefix, *SHARE),
                 os.path.join(site.getuserbase(), *SHARE)):
        if os.path.isfile(os.path.join(path, DESCRIPTOR)):
            return path
    return None


def user_folder(environ=None, system=None):
    """The user plugin folder of the editor."""
    environ = os.environ if environ is None else environ
    system = system or platform.system()
    home = environ.get('HOME') or os.path.expanduser('~')
    if system == 'Windows':
        base = environ.get('APPDATA') or \
            os.path.join(home, 'AppData', 'Roaming')
    elif system == 'Darwin':
        base = os.path.join(home, 'Library', 'Application Support')
    else:
        base = environ.get('XDG_DATA_HOME') or \
            os.path.join(home, '.local', 'share')
    return os.path.join(base, *EDITOR_FOLDER)


def _ours(folder):
    try:
        with open(os.path.join(folder, DESCRIPTOR), encoding='utf-8') as file:
            return json.load(file).get('id') == PLUGIN_ID
    except (OSError, ValueError, AttributeError):
        return False


def pinned(descriptor, executable):
    """The descriptor whose commands start with the given Python instead of
    the interpreter the editor would look up."""
    if descriptor.pop('interpreter', None) is not None:
        for action in descriptor.get('actions', []):
            action['argv'] = [executable] + list(action.get('argv', []))
    return descriptor


def tree_environment(environ=None):
    """The env of a source tree plugin: the tree before the PYTHONPATH of
    this process, and its variables the binding of a prefix needs."""
    environ = os.environ if environ is None else environ
    paths = [_tree()] + [p for p in environ.get('PYTHONPATH', '').split(
        os.pathsep) if p and os.path.abspath(p) != _tree()]
    env = {'PYTHONPATH': os.pathsep.join(paths)}
    env.update((name, environ[name]) for name in KEPT if environ.get(name))
    return env


def install(target=None, executable=None):
    """Copy the plugin into target/lapki-compiler (the user plugin folder of
    the editor by default), replacing an earlier copy; return the directory."""
    origin = source()
    if origin is None:
        raise PluginError('the editor plugin is not found in this '
                          'installation')
    folder = os.path.join(target or user_folder(), PLUGIN_ID)
    if os.path.abspath(folder) == os.path.abspath(origin):
        raise PluginError('{} is the plugin itself'.format(folder))
    if os.path.lexists(folder) and not _ours(folder):
        raise PluginError('{} exists and is not the plugin {}'.format(
            folder, PLUGIN_ID))
    try:
        with open(os.path.join(origin, DESCRIPTOR), encoding='utf-8') as file:
            descriptor = pinned(json.load(file),
                                executable or sys.executable)
        if origin == os.path.join(_tree(), SOURCE_TREE):
            # a source tree is not installed: the package comes from it
            descriptor.setdefault('env', {}).update(tree_environment())
        if os.path.lexists(folder):
            shutil.rmtree(folder)
        shutil.copytree(origin, folder)
        with open(os.path.join(folder, DESCRIPTOR), 'w',
                  encoding='utf-8') as file:
            json.dump(descriptor, file, ensure_ascii=False, indent=2)
            file.write('\n')
    except (OSError, ValueError) as error:
        raise PluginError(str(error)) from error
    return folder

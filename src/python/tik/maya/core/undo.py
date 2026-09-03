#
# BSD 2-Clause License
#
# Copyright (c) 2024, Marcus Ottosson
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

# Derived from apiundo: https://github.com/mottosso/apiundo

"""Commit API edits to Maya's internal undo queue.

This is the Python half of tik's undo support; ``src/plugins/python/tik_undo.py``
is the plug-in half. See that file for why they are separate.

The plug-in is loaded by name out of ``MAYA_PLUG_IN_PATH``, which the generated
``.mod`` points at the plug-in area. That is what keeps Maya from asking the
user to approve a load from an untrusted location.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

from maya import cmds

PLUGIN_NAME = "tik_undo.py"

SHARED_NAME = "_tik_undo_shared"

_warned = False


def _shared():
    """The module both halves use to hand work to each other."""
    if SHARED_NAME not in sys.modules:
        module = types.ModuleType(SHARED_NAME)
        module.undo = None
        module.redo = None
        module.command = None
        sys.modules[SHARED_NAME] = module
    return sys.modules[SHARED_NAME]


def _command():
    """Name of the registered command, or None while the plug-in is unloaded.

    The plug-in publishes the name, so there is one source of truth for it.
    """
    command = getattr(_shared(), "command", None)
    if command and hasattr(cmds, command):
        return command
    return None


def _plugin_directory():
    """Find the plug-in area on disk, for the fallback load.

    Walks up from the ``tik`` package, which sits beside the plug-in area in
    both layouts::

        dev      <repo>/src/python/tik   ->  <repo>/src/plugins/python
        release  <module>/tik            ->  <module>/plugins/python
    """
    package_root = Path(__file__).resolve().parents[2]
    for ancestor in (package_root,) + tuple(package_root.parents)[:3]:
        candidate = ancestor / "plugins" / "python"
        if (candidate / PLUGIN_NAME).is_file():
            return candidate
    return None


def _install_from_disk():
    """Load the plug-in by absolute path, which Maya may ask to approve.

    Only reached when the tikworks module is not installed -- a raw checkout
    put on ``sys.path`` by hand, say. It warns rather than loading quietly,
    because an unnoticed fallback here is exactly the approval prompt this
    layout exists to avoid.
    """
    global _warned

    directory = _plugin_directory()
    if directory is None:
        raise RuntimeError(
            "%s is not on MAYA_PLUG_IN_PATH and could not be found on disk. "
            "Install the tikworks module to make undo available." % PLUGIN_NAME
        )

    if not _warned:
        _warned = True
        cmds.warning(
            "Loading %s from an untrusted location (%s) because it is not on "
            "MAYA_PLUG_IN_PATH. Install the tikworks module to avoid this."
            % (PLUGIN_NAME, directory)
        )

    cmds.loadPlugin(str(directory / PLUGIN_NAME), quiet=True)


def install():
    """Load the undo plug-in, preferring the deployed (trusted) location."""
    if _command():
        return

    try:
        cmds.loadPlugin(PLUGIN_NAME, quiet=True)
    except RuntimeError:
        pass

    if not _command():
        _install_from_disk()


def uninstall():
    """Unregister the plug-in."""
    # It may sit in the undo queue, and cannot be unloaded until that is flushed.
    cmds.flushUndo()
    cmds.unloadPlugin(PLUGIN_NAME)
    _shared().command = None


def commit(undo, redo=lambda: None):
    """Commit `undo` and `redo` to history.

    Args:
        undo: Call this function on next undo.
        redo: Like `undo`, for redo.
    """
    command = _command()
    if command is None:
        install()
        command = _command()

    state = _shared()

    # Precautionary measure. If this doesn't pass, odds are we've got a race
    # condition. NOTE: This assumes calls to `commit` can only be done from a
    # single thread, which should already be the case given that Maya's API is
    # not threadsafe.
    assert state.undo is None
    assert state.redo is None

    # Park them for the command to pick up when Maya calls it.
    state.undo = undo
    state.redo = redo

    # Let Maya know that something is undoable.
    getattr(cmds, command)()

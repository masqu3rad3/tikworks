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

This is the plug-in half of tik's undo support; ``tik.maya.core.undo`` is the
Python half. They are separate files because they need to live on separate
paths: a plug-in is trusted when Maya resolves it by name out of
``MAYA_PLUG_IN_PATH``, which the generated ``.mod`` points at this directory,
while ``commit()`` has to stay importable off ``PYTHONPATH``.

Neither half imports the other. They meet in a module parked in
``sys.modules`` under a name they both know, which is also how the plug-in
publishes the name of the command it registered.

This is a build-time helper: it exists while a rig is being constructed and
leaves nothing behind in the result. Nothing in a delivered rig depends on it.
"""

import sys
import types

from maya.api import OpenMaya as om

__version__ = "1.0.0"

# The command carries the version so two tikworks installs can coexist in one
# session without the older one answering for the newer.
COMMAND = "_tikUndo_%s" % __version__.replace(".", "_")

SHARED_NAME = "_tik_undo_shared"


def shared():
    """The module both halves use to hand work to each other."""
    if SHARED_NAME not in sys.modules:
        module = types.ModuleType(SHARED_NAME)
        module.undo = None
        module.redo = None
        module.command = None
        sys.modules[SHARED_NAME] = module
    return sys.modules[SHARED_NAME]


def maya_useNewAPI():
    """Plug-in boilerplate."""


class _TikUndo(om.MPxCommand):
    """Carries one pair of callables into the undo queue."""

    def doIt(self, args):
        state = shared()
        self.undo = state.undo
        self.redo = state.redo

        # Claim them, so a second commit cannot inherit this one's callables.
        state.undo = None
        state.redo = None

    def undoIt(self):
        self.undo()

    def redoIt(self):
        self.redo()

    def isUndoable(self):
        # Without this, undoIt and redoIt are never called.
        return True


def initializePlugin(plugin):
    """Plug-in boilerplate."""
    om.MFnPlugin(plugin).registerCommand(COMMAND, _TikUndo)
    shared().command = COMMAND


def uninitializePlugin(plugin):
    """Plug-in boilerplate."""
    om.MFnPlugin(plugin).deregisterCommand(COMMAND)
    shared().command = None

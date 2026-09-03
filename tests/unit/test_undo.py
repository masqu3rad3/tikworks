"""The undo plug-in and its deployment contract.

The plug-in must be loadable *by name* out of a directory declared on
``MAYA_PLUG_IN_PATH`` by the generated ``.mod``. Loading it by absolute path
is what makes Maya ask the user to approve an untrusted location, so the
by-name route is the behaviour under test here.
"""

import os
from pathlib import Path

import pytest
from maya import cmds

from tik.maya.core import undo

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_DIR = REPO_ROOT / "src" / "plugins" / "python"


@pytest.fixture
def deployed(monkeypatch):
    """Put the plug-in directory on MAYA_PLUG_IN_PATH, as the .mod does."""
    monkeypatch.setenv(
        "MAYA_PLUG_IN_PATH",
        os.pathsep.join([str(PLUGIN_DIR), os.environ.get("MAYA_PLUG_IN_PATH", "")]),
    )
    _unload()
    yield
    _unload()


def _unload():
    """Unload the plug-in and forget the registered command."""
    cmds.flushUndo()
    if cmds.pluginInfo(undo.PLUGIN_NAME, query=True, loaded=True):
        cmds.unloadPlugin(undo.PLUGIN_NAME)
    undo._shared().command = None


class TestDeployment:
    """The plug-in ships where the .mod says it does."""

    def test_plugin_lives_in_the_plugins_area(self):
        assert (PLUGIN_DIR / undo.PLUGIN_NAME).is_file()

    def test_plugin_is_not_inside_the_importable_package(self):
        """A plug-in is not an importable module; it must stay out of tik/."""
        package = REPO_ROOT / "src" / "python" / "tik"
        assert not list(package.rglob(undo.PLUGIN_NAME))

    def test_vendored_apiundo_is_retired(self):
        assert not (
            REPO_ROOT / "src" / "python" / "tik" / "vendor" / "apiundo"
        ).exists()


class TestInstall:
    """How the plug-in gets loaded."""

    def test_loads_by_name_from_the_plugin_path(self, deployed):
        undo.install()
        assert cmds.pluginInfo(undo.PLUGIN_NAME, query=True, loaded=True)

    def test_never_loads_by_absolute_path_when_deployed(self, deployed, monkeypatch):
        """The regression that matters: an absolute path re-triggers the dialog."""
        seen = []
        real = cmds.loadPlugin

        def spy(plugin, *args, **kwargs):
            seen.append(plugin)
            return real(plugin, *args, **kwargs)

        monkeypatch.setattr(cmds, "loadPlugin", spy)
        undo.install()
        assert seen == [undo.PLUGIN_NAME]

    def test_install_is_idempotent(self, deployed):
        undo.install()
        undo.install()
        assert cmds.pluginInfo(undo.PLUGIN_NAME, query=True, loaded=True)

    def test_raises_when_not_on_the_plugin_path(self, monkeypatch):
        """No fallback to an absolute path: that is the prompt the .mod avoids."""
        monkeypatch.setenv("MAYA_PLUG_IN_PATH", "")
        _unload()
        try:
            with pytest.raises(RuntimeError, match="MAYA_PLUG_IN_PATH"):
                undo.install()
            assert not cmds.pluginInfo(undo.PLUGIN_NAME, query=True, loaded=True)
        finally:
            _unload()


class TestCommit:
    """commit() puts the callables on Maya's undo queue."""

    def test_undo_and_redo_fire(self, deployed):
        cmds.file(new=True, force=True)
        calls = []
        cmds.undoInfo(state=True, infinity=True)
        cmds.undoInfo(openChunk=True)
        undo.commit(
            undo=lambda: calls.append("undo"), redo=lambda: calls.append("redo")
        )
        cmds.undoInfo(closeChunk=True)

        cmds.undo()
        assert calls == ["undo"]
        cmds.redo()
        assert calls == ["undo", "redo"]

    def test_commit_installs_on_first_use(self, deployed):
        cmds.undoInfo(openChunk=True)
        undo.commit(undo=lambda: None)
        cmds.undoInfo(closeChunk=True)
        assert cmds.pluginInfo(undo.PLUGIN_NAME, query=True, loaded=True)

    def test_apicommon_uses_the_new_commit(self):
        from tik.maya.core import apicommon

        assert apicommon.undocommit is undo.commit

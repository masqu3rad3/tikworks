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

    def test_falls_back_to_disk_when_not_on_the_plugin_path(self, monkeypatch):
        """A raw checkout with no module installed still works, but loudly."""
        monkeypatch.setenv("MAYA_PLUG_IN_PATH", "")
        monkeypatch.setattr(undo, "_warned", False)
        warnings = []
        monkeypatch.setattr(cmds, "warning", lambda msg: warnings.append(msg))
        _unload()
        try:
            undo.install()
            assert cmds.pluginInfo(undo.PLUGIN_NAME, query=True, loaded=True)
            assert warnings, "an untrusted-path load must warn"
        finally:
            _unload()

    def test_finds_the_plugin_directory(self):
        assert undo._plugin_directory() == PLUGIN_DIR


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


class TestPluginDirectoryLayouts:
    """The fallback has to find the plug-in area in both deployed shapes.

    The release layout cannot be exercised from a checkout, so the module is
    loaded out of a fabricated tree of each shape instead.
    """

    @staticmethod
    def _install_package(parent):
        """Write tik/maya/core/undo.py under `parent` and import it."""
        import importlib.util

        source = Path(undo.__file__)
        core = parent / "tik" / "maya" / "core"
        core.mkdir(parents=True)
        target = core / source.name
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

        spec = importlib.util.spec_from_file_location("_undo_layout_probe", target)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @staticmethod
    def _install_plugin_area(parent):
        """Write a plug-in area under `parent`."""
        plugins = parent / "plugins" / "python"
        plugins.mkdir(parents=True)
        (plugins / undo.PLUGIN_NAME).write_text("", encoding="utf-8")
        return plugins

    def test_release_layout(self, tmp_path):
        """<module>/tik beside <module>/plugins/python."""
        module = self._install_package(tmp_path)
        plugins = self._install_plugin_area(tmp_path)
        assert module._plugin_directory() == plugins

    def test_dev_layout(self, tmp_path):
        """<repo>/src/python/tik, with the area two levels up at src/."""
        src = tmp_path / "src"
        (src / "python").mkdir(parents=True)
        module = self._install_package(src / "python")
        plugins = self._install_plugin_area(src)
        assert module._plugin_directory() == plugins

    def test_returns_none_when_there_is_no_plugin_area(self, tmp_path):
        module = self._install_package(tmp_path)
        assert module._plugin_directory() is None

"""Guide authoring preferences, and the migration off QSettings."""

import pytest
from stub import StubScene

from tik.shared.ui.Qt import QtCore
from tik.trigger.ui.designer.window import GuideDesigner


@pytest.fixture
def designer(qapp):
    """A Designer over the Qt-only stub scene.

    Defined here rather than imported from test_guide_designer: importing a
    fixture across test modules reads as a redefinition to flake8, and this
    file needs no toy modules registered.
    """
    window = GuideDesigner(scene=StubScene())
    window.show()
    yield window
    window.close()


class TestMigration:
    """The two live QSettings keys move into the JSON store, once."""

    def test_migrates_auto_sync_false(self, qapp):
        from tik.trigger.config import prefs
        from tik.trigger.ui.designer.commands import migrate_designer_settings

        QtCore.QSettings("tikworks", "trigger").setValue("designer/auto_sync", False)
        migrate_designer_settings()
        assert prefs.guides.auto_sync is False

    def test_migrates_draw_on_create_false(self, qapp):
        from tik.trigger.config import prefs
        from tik.trigger.ui.designer.commands import migrate_designer_settings

        QtCore.QSettings("tikworks", "trigger").setValue(
            "designer/draw_on_create", False
        )
        migrate_designer_settings()
        assert prefs.guides.draw_on_create is False

    def test_normalises_qsettings_strings(self, qapp):
        from tik.trigger.config import prefs
        from tik.trigger.ui.designer.commands import migrate_designer_settings

        # QSettings hands back strings on some platforms.
        QtCore.QSettings("tikworks", "trigger").setValue("designer/auto_sync", "false")
        migrate_designer_settings()
        assert prefs.guides.auto_sync is False

    def test_runs_only_once(self, qapp):
        from tik.trigger.config import prefs
        from tik.trigger.ui.designer.commands import migrate_designer_settings

        QtCore.QSettings("tikworks", "trigger").setValue("designer/auto_sync", False)
        migrate_designer_settings()
        prefs.guides.auto_sync = True
        migrate_designer_settings()
        assert prefs.guides.auto_sync is True

    def test_no_qsettings_leaves_defaults(self, qapp):
        from tik.trigger.config import prefs
        from tik.trigger.ui.designer.commands import migrate_designer_settings

        QtCore.QSettings("tikworks", "trigger").remove("designer/auto_sync")
        QtCore.QSettings("tikworks", "trigger").remove("designer/draw_on_create")
        migrate_designer_settings()
        assert prefs.guides.auto_sync is True
        assert prefs.guides.draw_on_create is True

    def test_the_migration_is_recorded(self, qapp):
        from tik.trigger.config import prefs
        from tik.trigger.ui.designer.commands import migrate_designer_settings

        migrate_designer_settings()
        assert prefs.guides.migrated_from_qsettings is True

    @pytest.mark.parametrize(
        "raw,expected",
        [
            (None, True),
            (True, True),
            (False, False),
            ("true", True),
            ("false", False),
            ("0", False),
            ("", False),
            (0, False),
            (1, True),
        ],
    )
    def test_as_bool_normalises_every_shape(self, raw, expected):
        from tik.trigger.ui.designer.commands import _as_bool

        assert _as_bool(raw, True) is expected


class TestConfirmations:
    """The two destructive guide operations can be made silent."""

    def test_delete_all_asks_by_default(self, designer, monkeypatch):
        asked = []
        monkeypatch.setattr(
            type(designer),
            "_confirm_delete_all",
            lambda self: asked.append(1) or False,
        )
        designer.clear_guides()
        assert asked == [1]

    def test_delete_all_is_silent_when_disabled(self, designer, monkeypatch):
        from tik.trigger.config import prefs

        monkeypatch.setattr(prefs.guides, "confirm_delete_all", False)
        asked = []
        monkeypatch.setattr(
            type(designer),
            "_delete_all_dialog",
            lambda self: asked.append(1) or True,
        )
        designer.clear_guides()
        assert asked == []

    def test_declining_keeps_the_modules(self, designer, monkeypatch):
        monkeypatch.setattr(type(designer), "_delete_all_dialog", lambda self: False)
        cleared = []
        monkeypatch.setattr(designer.guides, "clear", lambda: cleared.append(1))
        designer.clear_guides()
        assert cleared == []

"""Tests for Trigger's preference pages."""

import pytest


class TestPagesRegistered:
    """The four pages exist, in order, with the expected fields."""

    def test_four_pages_in_order(self):
        from tik.trigger.config import prefs

        assert [page.name for page in prefs.pages()] == [
            "interface",
            "guides",
            "files",
            "tools",
        ]

    def test_every_field_declares_help(self):
        from tik.trigger.config import prefs

        missing = [
            f"{page.name}.{name}"
            for page in prefs.pages()
            for name, field in type(page).fields().items()
            if not field.help
        ]
        assert missing == []

    def test_no_duplicate_field_names_within_a_page(self):
        from tik.trigger.config import prefs

        for page in prefs.pages():
            names = list(type(page).fields())
            assert len(names) == len(set(names))


class TestDefaults:
    """Defaults match what the code did before it was configurable."""

    @pytest.mark.parametrize(
        "key,expected",
        [
            ("interface.restore_geometry", True),
            ("interface.restore_dock_layout", True),
            ("interface.log_open_on_error", True),
            ("interface.log_max_lines", 2000),
            ("interface.log_verbosity", "Info"),
            ("interface.graph_snap", True),
            ("interface.graph_show_grid", True),
            ("interface.graph_collapse_mode", "Everything"),
            ("guides.auto_sync", True),
            ("guides.draw_on_create", True),
            ("guides.confirm_delete_all", True),
            ("guides.confirm_reset_scene", True),
            ("files.remember_recent", True),
            ("files.max_recent", 8),
            ("files.remember_last_folder", True),
            ("files.default_folder", ""),
            ("files.autosave", False),
            ("files.autosave_interval", 300),
            ("files.confirm_unsaved_close", True),
            ("tools.external_editor", ""),
        ],
    )
    def test_default(self, key, expected):
        from tik.trigger.config import prefs

        page_name, _, field = key.partition(".")
        assert getattr(prefs.page(page_name), field) == expected


class TestLaziness:
    """Importing the package must not touch the disk."""

    def test_import_does_not_resolve_preferences(self):
        import tik.trigger.config as config

        fresh = config.LazyPreferences(config._build_preferences)
        assert repr(fresh) == "LazyPreferences(unloaded)"


class TestRejectedKeys:
    """Nothing that could change a rig may be declared as a preference."""

    @pytest.mark.parametrize(
        "banned",
        [
            "mirror_mapping",
            "side_suffixes",
            "center_prefix",
            "attribute_locking",
            "linear",
            "angular",
            "guide_size",
            "guide_radius",
        ],
    )
    def test_banned_field_name_absent(self, banned):
        from tik.trigger.config import prefs

        for page in prefs.pages():
            assert banned not in type(page).fields()


class TestEditorCommand:
    """The editor command reads the preference, from the UI layer."""

    def test_reads_the_preference(self, monkeypatch):
        from tik.trigger.config import prefs
        from tik.trigger.ui import prefs_access

        monkeypatch.setattr(prefs.tools, "external_editor", "code -g {path}")
        assert prefs_access.editor_command() == "code -g {path}"

    def test_empty_by_default(self, monkeypatch):
        from tik.trigger.config import prefs
        from tik.trigger.ui import prefs_access

        monkeypatch.setattr(prefs.tools, "external_editor", "")
        assert prefs_access.editor_command() == ""

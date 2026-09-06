"""Tests for the generic preferences dialog."""

import pytest


@pytest.fixture
def preferences(tmp_path):
    """A two-page Preferences on a throwaway store."""
    from tik.core.fields import BoolField, FieldGroup, IntField
    from tik.shared.prefs import Preferences, PrefPage, PrefStore

    class Alpha(PrefPage):
        name, label, order = "alpha", "Alpha", 10
        LOOK = FieldGroup("Look")
        enabled = BoolField(True, group=LOOK, help="Whether the log is shown.")
        count = IntField(3, min=1, max=10, group=LOOK, help="How many things.")

    class Beta(PrefPage):
        name, label, order = "beta", "Beta", 20
        SPEED = FieldGroup("Speed")
        turbo = BoolField(False, group=SPEED, help="Go faster.")

    return Preferences(PrefStore("demo", folder=tmp_path), [Alpha, Beta])


@pytest.fixture
def dialog(qapp, preferences):
    from tik.shared.ui.prefs_dialog import PrefsDialog

    return PrefsDialog(preferences)


class TestStructure:
    """The dialog builds itself from the registry."""

    def test_one_category_row_per_page(self, dialog):
        assert dialog.categories.count() == 2

    def test_category_labels_come_from_pages(self, dialog):
        labels = [dialog.categories.item(i).text() for i in range(2)]
        assert labels == ["Alpha", "Beta"]

    def test_first_page_is_selected(self, dialog):
        assert dialog.categories.currentRow() == 0

    def test_a_form_exists_per_page(self, dialog):
        assert set(dialog.forms) == {"alpha", "beta"}


class TestApply:
    """Apply writes, Cancel discards."""

    def test_apply_writes_the_file(self, dialog, preferences):
        preferences.alpha.count = 7
        dialog.apply_changes()
        assert preferences.store.read()["alpha.count"] == 7

    def test_apply_emits_changed_keys(self, dialog, preferences):
        seen = []
        dialog.applied.connect(seen.append)
        preferences.alpha.count = 7
        dialog.apply_changes()
        assert seen == [["alpha.count"]]

    def test_apply_twice_reports_nothing_the_second_time(self, dialog, preferences):
        seen = []
        dialog.applied.connect(seen.append)
        preferences.alpha.count = 7
        dialog.apply_changes()
        dialog.apply_changes()
        assert seen == [["alpha.count"], []]

    def test_reject_restores_the_opening_values(self, dialog, preferences):
        preferences.alpha.count = 7
        dialog.reject()
        assert preferences.alpha.count == 3

    def test_reject_does_not_write(self, dialog, preferences):
        preferences.alpha.count = 7
        dialog.reject()
        assert preferences.store.read() == {}

    def test_reject_after_apply_keeps_applied_values(self, dialog, preferences):
        preferences.alpha.count = 7
        dialog.apply_changes()
        preferences.alpha.count = 9
        dialog.reject()
        assert preferences.alpha.count == 7


class TestRestoreDefaults:
    """Restore Defaults acts on the selected page and stages like any edit."""

    def test_resets_the_current_page_only(self, dialog, preferences):
        preferences.alpha.count = 7
        preferences.beta.turbo = True
        dialog.categories.setCurrentRow(0)
        dialog.restore_defaults()
        assert preferences.alpha.count == 3
        assert preferences.beta.turbo is True

    def test_is_cancellable(self, dialog, preferences):
        preferences.alpha.count = 7
        dialog.apply_changes()
        dialog.restore_defaults()
        dialog.reject()
        assert preferences.alpha.count == 7

    def test_disabled_while_searching(self, dialog):
        dialog.search("log")
        assert not dialog.defaults_button.isEnabled()
        dialog.search("")
        assert dialog.defaults_button.isEnabled()


class TestSearch:
    """Search filters settings across every page."""

    def test_matches_a_label(self, dialog):
        dialog.search("count")
        assert dialog.forms["alpha"].isVisibleTo(dialog)
        assert not dialog.forms["beta"].isVisibleTo(dialog)

    def test_matches_help_text_not_just_labels(self, dialog):
        # "log" appears only in Alpha.enabled's help, never in a label.
        dialog.search("log")
        assert dialog.visible_matches() == ["alpha.enabled"]

    def test_is_case_insensitive(self, dialog):
        assert dialog.search("COUNT") == dialog.search("count")

    def test_empty_search_restores_single_page_view(self, dialog):
        dialog.search("count")
        dialog.search("")
        assert dialog.categories.isEnabled()
        assert dialog.forms["alpha"].isVisibleTo(dialog)
        assert not dialog.forms["beta"].isVisibleTo(dialog)

    def test_no_match_shows_the_empty_message(self, dialog):
        dialog.search("zzzznothing")
        assert dialog.empty_label.isVisibleTo(dialog)
        assert dialog.visible_matches() == []

    def test_search_does_not_change_values(self, dialog, preferences):
        dialog.search("count")
        dialog.search("")
        assert preferences.alpha.count == 3


class TestDefaultButton:
    """Enter accepts the dialog; it must never reset the page.

    Every button in a QDialog is autoDefault, so the first one added -- Restore
    Defaults -- otherwise claims Enter and the accent styling meant for OK.
    """

    def test_ok_is_the_default_button(self, dialog):
        assert dialog.ok_button.isDefault()

    def test_restore_defaults_is_not_default(self, dialog):
        assert not dialog.defaults_button.isDefault()
        assert not dialog.defaults_button.autoDefault()

    def test_cancel_and_apply_are_not_default(self, dialog):
        assert not dialog.cancel_button.autoDefault()
        assert not dialog.apply_button.autoDefault()

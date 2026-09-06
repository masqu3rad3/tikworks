"""The Tab search palette: filtering, recents and the keyboard.

``SearchPalette`` is reached today only in passing, through the pipeline and
designer tests that happen to open it -- which left its whole interaction model
uncovered: the recents list, arrow navigation over non-selectable headers, and
every key ``eventFilter`` handles. This drives the widget directly.
"""

from __future__ import annotations

import pytest

from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets
from tik.trigger.ui.palette import PaletteEntry, SearchPalette

ENTRIES = [
    PaletteEntry("weights", "Weights", "deform", ["skin"]),
    PaletteEntry("wrap", "Wrap", "deform"),
    PaletteEntry("import_asset", "Import Asset", "build", ["load", "reference"]),
    PaletteEntry("kinematics", "Kinematics", "build"),
    PaletteEntry("script", "Script", "utility"),
]


@pytest.fixture
def palette(qapp):
    widget = SearchPalette(ENTRIES)
    yield widget
    widget.hide()


def key_press(widget, key, modifiers=QtCore.Qt.NoModifier):
    """Send a real key press through the palette's event filter."""
    event = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, key, modifiers)
    QtWidgets.QApplication.sendEvent(widget.search, event)


class TestMatching:
    """``PaletteEntry.matches`` is what the filter line drives."""

    @pytest.mark.parametrize(
        "text", ["weights", "WEIGHTS", "  weights  ", "eigh", "skin", "deform"]
    )
    def test_key_label_keyword_and_category_all_match(self, text):
        assert ENTRIES[0].matches(text)

    def test_empty_text_matches_everything(self):
        assert all(entry.matches("") for entry in ENTRIES)

    def test_a_miss_is_a_miss(self):
        assert not ENTRIES[0].matches("nonesuch")


class TestFiltering:
    """What the list shows for a given search string."""

    def test_everything_is_listed_before_a_search(self, palette):
        assert set(palette.visible_keys()) == {entry.key for entry in ENTRIES}

    def test_typing_narrows_the_list(self, palette):
        palette.search.setText("wei")

        assert palette.visible_keys() == ["weights"]

    def test_a_keyword_finds_an_entry_its_label_does_not(self, palette):
        palette.search.setText("skin")

        assert palette.visible_keys() == ["weights"]

    def test_a_prefix_match_is_ranked_first(self, palette):
        """``Script`` starts with the text; ``Import Asset`` only contains it."""
        palette.search.setText("s")

        assert palette.visible_keys()[0] == "script"

    def test_no_match_empties_the_list(self, palette):
        palette.search.setText("nonesuch")

        assert palette.visible_keys() == []

    def test_entries_are_grouped_under_category_headers_when_unsearched(self, palette):
        """Headers are listed items too, but carry no key."""
        rows = [palette.list.item(row).text() for row in range(palette.list.count())]

        assert "DEFORM" in rows and "BUILD" in rows and "UTILITY" in rows

    def test_a_search_drops_the_headers(self, palette):
        palette.search.setText("e")
        rows = [palette.list.item(row).text() for row in range(palette.list.count())]

        assert not any(row.isupper() and " " not in row for row in rows if row)

    def test_the_first_selectable_row_is_highlighted(self, palette):
        assert palette.current_key() is not None

    def test_nothing_is_current_when_nothing_matches(self, palette):
        palette.search.setText("nonesuch")

        assert palette.current_key() is None


class TestChoosing:
    """Picking an entry emits it and remembers it."""

    def test_choosing_emits_the_key(self, palette):
        seen: list = []
        palette.chosen.connect(lambda key, as_child: seen.append((key, as_child)))
        palette.search.setText("wei")

        palette._choose(False)

        assert seen == [("weights", False)]

    def test_shift_enter_asks_for_a_child(self, palette):
        seen: list = []
        palette.chosen.connect(lambda key, as_child: seen.append((key, as_child)))
        palette.search.setText("wei")

        key_press(palette, QtCore.Qt.Key_Return, QtCore.Qt.ShiftModifier)

        assert seen == [("weights", True)]

    def test_enter_adds_after(self, palette):
        seen: list = []
        palette.chosen.connect(lambda key, as_child: seen.append((key, as_child)))
        palette.search.setText("wei")

        key_press(palette, QtCore.Qt.Key_Enter)

        assert seen == [("weights", False)]

    def test_choosing_hides_the_palette(self, palette):
        palette.show()
        palette.search.setText("wei")

        palette._choose(False)

        assert not palette.isVisible()

    def test_choosing_nothing_emits_nothing(self, palette):
        seen: list = []
        palette.chosen.connect(lambda key, as_child: seen.append(key))
        palette.search.setText("nonesuch")

        palette._choose(False)

        assert seen == []


class TestRecents:
    """Recently chosen entries lead the unsearched list."""

    def test_a_choice_is_remembered(self, palette):
        palette.search.setText("wei")
        palette._choose(False)

        assert palette.recent == ["weights"]

    def test_the_newest_choice_leads(self, palette):
        for text in ("wei", "kinem"):
            palette.search.setText(text)
            palette._choose(False)

        assert palette.recent == ["kinematics", "weights"]

    def test_choosing_the_same_entry_twice_does_not_duplicate_it(self, palette):
        for _ in range(2):
            palette.search.setText("wei")
            palette._choose(False)

        assert palette.recent == ["weights"]

    def test_re_choosing_moves_it_back_to_the_front(self, palette):
        for text in ("wei", "kinem", "wei"):
            palette.search.setText(text)
            palette._choose(False)

        assert palette.recent == ["weights", "kinematics"]

    def test_the_list_is_capped(self, palette):
        palette.recent = [f"stale{index}" for index in range(SearchPalette.MAX_RECENT)]
        palette.search.setText("wei")

        palette._choose(False)

        assert len(palette.recent) == SearchPalette.MAX_RECENT
        assert palette.recent[0] == "weights"

    def test_recents_lead_the_unsearched_list(self, palette):
        palette.search.setText("script")
        palette._choose(False)

        palette.popup(QtCore.QPoint(0, 0))

        assert palette.visible_keys()[0] == "script"

    def test_a_recent_entry_is_listed_under_a_recent_header(self, palette):
        palette.search.setText("script")
        palette._choose(False)

        palette.popup(QtCore.QPoint(0, 0))
        rows = [palette.list.item(row).text() for row in range(palette.list.count())]

        assert rows[0] == "RECENT"

    def test_a_recent_entry_still_appears_once_only(self, palette):
        palette.search.setText("script")
        palette._choose(False)

        palette.popup(QtCore.QPoint(0, 0))

        assert palette.visible_keys().count("script") == 1

    def test_the_other_entries_stay_grouped_below(self, palette):
        palette.search.setText("script")
        palette._choose(False)

        palette.popup(QtCore.QPoint(0, 0))

        assert set(palette.visible_keys()) == {entry.key for entry in ENTRIES}


class TestKeyboardNavigation:
    """Arrows move the highlight and step over the category headers."""

    def test_down_moves_to_the_next_entry(self, palette):
        palette.search.setText("w")
        first = palette.current_key()

        key_press(palette, QtCore.Qt.Key_Down)

        assert palette.current_key() != first

    def test_up_moves_back(self, palette):
        palette.search.setText("w")
        first = palette.current_key()
        key_press(palette, QtCore.Qt.Key_Down)

        key_press(palette, QtCore.Qt.Key_Up)

        assert palette.current_key() == first

    def test_down_wraps_around(self, palette):
        palette.search.setText("w")
        first = palette.current_key()

        for _ in range(len(palette.visible_keys())):
            key_press(palette, QtCore.Qt.Key_Down)

        assert palette.current_key() == first

    def test_up_from_the_top_wraps_to_the_bottom(self, palette):
        palette.search.setText("w")

        key_press(palette, QtCore.Qt.Key_Up)

        assert palette.current_key() == palette.visible_keys()[-1]

    def test_navigation_never_lands_on_a_header(self, palette):
        """Headers are rows too; the highlight has to skip them."""
        for _ in range(palette.list.count() + 2):
            key_press(palette, QtCore.Qt.Key_Down)
            assert palette.current_key() is not None

    def test_navigating_an_empty_list_is_harmless(self, palette):
        palette.search.setText("nonesuch")

        key_press(palette, QtCore.Qt.Key_Down)

        assert palette.current_key() is None


class TestDismissal:
    """Escape closes without choosing."""

    def test_escape_hides_the_palette(self, palette):
        palette.show()

        key_press(palette, QtCore.Qt.Key_Escape)

        assert not palette.isVisible()

    def test_escape_reports_the_dismissal(self, palette):
        seen: list = []
        palette.dismissed.connect(lambda: seen.append(True))

        key_press(palette, QtCore.Qt.Key_Escape)

        assert seen == [True]

    def test_escape_chooses_nothing(self, palette):
        seen: list = []
        palette.chosen.connect(lambda key, as_child: seen.append(key))

        key_press(palette, QtCore.Qt.Key_Escape)

        assert seen == []

    def test_an_unhandled_key_is_not_eaten_by_the_filter(self, palette):
        """Only Enter/arrows/Escape are the palette's; the rest are the edit's."""
        palette.show()
        chosen: list = []
        dismissed: list = []
        palette.chosen.connect(lambda key, as_child: chosen.append(key))
        palette.dismissed.connect(lambda: dismissed.append(True))

        key_press(palette, QtCore.Qt.Key_A)

        assert palette.isVisible()
        assert chosen == [] and dismissed == []


class TestPopup:
    """``popup`` is the entry point the Tab shortcut calls."""

    def test_it_clears_the_previous_search(self, palette):
        palette.search.setText("wei")

        palette.popup(QtCore.QPoint(10, 20))

        assert palette.search.text() == ""

    def test_it_shows_everything_again(self, palette):
        palette.search.setText("wei")

        palette.popup(QtCore.QPoint(10, 20))

        assert set(palette.visible_keys()) == {entry.key for entry in ENTRIES}

    def test_it_moves_to_the_requested_point(self, palette):
        palette.popup(QtCore.QPoint(10, 20))

        assert palette.pos() == QtCore.QPoint(10, 20)

    def test_it_shows_the_widget(self, palette):
        palette.popup(QtCore.QPoint(10, 20))

        assert palette.isVisible()


def test_an_icon_provider_is_used_when_given(qapp):
    """The designer passes module art; without one the palette draws initials."""
    calls: list = []

    def provider(entry, size):
        calls.append((entry.key, size))
        return QtGui.QIcon()

    SearchPalette(ENTRIES, icon_provider=provider)

    assert {key for key, _ in calls} == {entry.key for entry in ENTRIES}
    assert {size for _, size in calls} == {18}

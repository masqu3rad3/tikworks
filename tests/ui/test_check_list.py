"""The tick list a ``ListField(choices_from=..., filterable=True)`` renders.

The widget is action-agnostic on purpose: it only ever sees ``(label, value)``
pairs, so the same list serves kinematics today and anything with dozens of
options tomorrow.
"""

from tik.shared.ui.check_list import CheckListEditor
from tik.shared.ui.Qt import QtCore

OPTIONS = [
    ("spine", "id_spine"),
    ("L_arm", "id_larm"),
    ("R_arm", "id_rarm"),
    ("L_wing", "id_lwing"),
]


def _editor(filterable=True, options=None, value=None):
    editor = CheckListEditor(lambda: list(options or OPTIONS), filterable=filterable)
    editor.set_value(value or [])
    return editor


def _rows(editor):
    return [editor.list.item(row) for row in range(editor.list.count())]


def _labels(editor):
    return [item.text() for item in _rows(editor)]


def _shown(editor):
    return [item.text() for item in _rows(editor) if not item.isHidden()]


def _tick(editor, label, state=True):
    for item in _rows(editor):
        if item.text() == label:
            item.setCheckState(QtCore.Qt.Checked if state else QtCore.Qt.Unchecked)
            return
    raise AssertionError(f"no row named {label!r}")


# --- the plain list is untouched ---------------------------------------------


def test_a_plain_check_list_has_no_filter_furniture(qapp):
    """A short picker stays exactly the bare list it always was."""
    editor = _editor(filterable=False)
    assert editor.filter_bar is None
    assert editor.only_selected_box is None
    assert _labels(editor) == ["spine", "L_arm", "R_arm", "L_wing"]


# --- filtering ----------------------------------------------------------------


def test_typing_hides_the_rows_that_do_not_match(qapp):
    editor = _editor()
    editor.filter_bar.set_text("L_")
    assert _shown(editor) == ["L_arm", "L_wing"]


def test_filtering_hides_rows_rather_than_rebuilding_them(qapp):
    """Ticks and scroll survive typing, so the list never jumps under you."""
    editor = _editor(value=["id_spine"])
    editor.filter_bar.set_text("L_")
    assert editor.value() == ["id_spine"]
    editor.filter_bar.set_text("")
    assert _shown(editor) == ["spine", "L_arm", "R_arm", "L_wing"]
    assert editor.value() == ["id_spine"]


def test_a_committed_keyword_keeps_filtering(qapp):
    editor = _editor()
    editor.filter_bar.set_text("wing")
    editor.filter_bar.commit()
    assert _shown(editor) == ["L_wing"]


# --- show only selected --------------------------------------------------------


def test_only_selected_hides_the_unticked_rows(qapp):
    editor = _editor(value=["id_spine", "id_larm"])
    editor.set_only_selected(True)
    assert _shown(editor) == ["spine", "L_arm"]


def test_an_active_filter_reveals_unticked_rows(qapp):
    """Otherwise adding a module means untick the box, find it, tick it back."""
    editor = _editor(value=["id_spine"])
    editor.set_only_selected(True)
    editor.filter_bar.set_text("wing")
    assert _shown(editor) == ["L_wing"]


def test_unticking_while_only_selected_leaves_the_row_in_place(qapp):
    """A row must not vanish out from under the cursor that just clicked it."""
    editor = _editor(value=["id_spine", "id_larm"])
    editor.set_only_selected(True)
    _tick(editor, "spine", False)
    assert _shown(editor) == ["spine", "L_arm"]
    assert editor.value() == ["id_larm"]


def test_the_next_read_drops_the_row_it_kept(qapp):
    editor = _editor(value=["id_spine", "id_larm"])
    editor.set_only_selected(True)
    _tick(editor, "spine", False)
    editor.set_value(editor.value())
    assert _shown(editor) == ["L_arm"]


def test_toggling_only_selected_reports_itself(qapp):
    editor = _editor()
    seen = []
    editor.onlySelectedChanged.connect(seen.append)
    editor.only_selected_box.setChecked(True)
    assert seen == [True]
    assert editor.only_selected is True


def test_setting_only_selected_does_not_report_itself(qapp):
    """The form pushes the stored value in; that is not the user changing it."""
    editor = _editor()
    seen = []
    editor.onlySelectedChanged.connect(seen.append)
    editor.set_only_selected(True)
    assert seen == []


def test_the_list_is_marked_while_only_selected_is_on(qapp):
    """The theme paints an accent, so a short list is never a mystery."""
    editor = _editor()
    assert editor.list.property("onlySelected") is False
    editor.set_only_selected(True)
    assert editor.list.property("onlySelected") is True


# --- the context menu ----------------------------------------------------------


def test_the_menu_offers_the_declared_entries(qapp):
    editor = _editor()
    labels = [action.text() for action in editor.context_menu().actions()]
    assert "Select All" in labels
    assert "Select None" in labels
    assert "Invert Selection" in labels


def test_select_all_ticks_every_option_filter_or_not(qapp):
    """Deliberate: the menu acts on the list, not on what happens to show."""
    editor = _editor()
    editor.filter_bar.set_text("L_")
    editor.select_all()
    assert editor.value() == ["id_spine", "id_larm", "id_rarm", "id_lwing"]


def test_select_none_unticks_everything(qapp):
    editor = _editor(value=["id_spine", "id_larm"])
    editor.select_none()
    assert editor.value() == []


def test_invert_selection_flips_every_tick(qapp):
    editor = _editor(value=["id_spine", "id_lwing"])
    editor.invert_selection()
    assert editor.value() == ["id_larm", "id_rarm"]


def test_the_menu_reports_one_change_not_one_per_row(qapp):
    editor = _editor()
    seen = []
    editor.valueChanged.connect(seen.append)
    editor.select_all()
    assert len(seen) == 1


# --- sorting -------------------------------------------------------------------


def test_sorting_a_to_z_reorders_the_rows(qapp):
    editor = _editor()
    editor.set_sort_mode("az")
    assert _labels(editor) == ["L_arm", "L_wing", "R_arm", "spine"]


def test_sorting_z_to_a_reorders_the_rows(qapp):
    editor = _editor()
    editor.set_sort_mode("za")
    assert _labels(editor) == ["spine", "R_arm", "L_wing", "L_arm"]


def test_document_order_restores_the_session_ordering(qapp):
    editor = _editor()
    editor.set_sort_mode("az")
    editor.set_sort_mode("document")
    assert _labels(editor) == ["spine", "L_arm", "R_arm", "L_wing"]


def test_sorting_never_touches_the_stored_order(qapp):
    """Flipping to A-Z must not dirty the session it is only looking at."""
    editor = _editor(value=["id_lwing", "id_spine"])
    seen = []
    editor.valueChanged.connect(seen.append)
    editor.set_sort_mode("az")
    assert seen == []
    assert editor.value() == ["id_lwing", "id_spine"]


def test_ticking_under_a_sort_still_writes_document_order(qapp):
    """The rows are alphabetical; what lands in the .tr is the session order."""
    editor = _editor()
    editor.set_sort_mode("az")
    _tick(editor, "L_wing")
    _tick(editor, "spine")
    assert editor.value() == ["id_spine", "id_lwing"]


def test_sorting_survives_a_reread(qapp):
    editor = _editor()
    editor.set_sort_mode("az")
    editor.set_value(["id_spine"])
    assert _labels(editor) == ["L_arm", "L_wing", "R_arm", "spine"]


# --- the count -----------------------------------------------------------------


def test_the_count_reports_selected_of_total(qapp):
    editor = _editor(value=["id_spine", "id_larm"])
    assert editor.count_label.text() == "2 of 4"


def test_the_count_reports_how_many_are_shown_while_filtering(qapp):
    editor = _editor(value=["id_spine"])
    editor.filter_bar.set_text("L_")
    assert editor.count_label.text() == "1 of 4 · 2 shown"


# --- values nobody offers any more ---------------------------------------------


def test_a_missing_value_is_kept_ticked_and_marked(qapp):
    editor = _editor(value=["id_spine", "gone"])
    marked = [item for item in _rows(editor) if "missing" in item.text()]
    assert len(marked) == 1
    assert marked[0].checkState() == QtCore.Qt.Checked
    assert editor.value() == ["id_spine", "gone"]


def test_a_missing_value_shows_under_only_selected(qapp):
    editor = _editor(value=["gone"])
    editor.set_only_selected(True)
    assert _shown(editor) == ["gone (missing)"]


# --- the theme -----------------------------------------------------------------


def test_the_theme_dresses_every_part_of_the_list(qapp):
    """The object names the widget sets are the ones the theme paints."""
    from tik.shared.ui import theme

    qss = theme.stylesheet()
    for name in (
        "#CheckList",
        "#CheckListHeader",
        "#CheckListOnlySelected",
        "#CheckListCount",
    ):
        assert name in qss, f"{name} is unstyled"


def test_the_theme_paints_the_only_selected_state(qapp):
    """Nothing else tells a short list it is hiding rows."""
    from tik.shared.ui import theme

    assert '#CheckList[onlySelected="true"]' in theme.stylesheet()

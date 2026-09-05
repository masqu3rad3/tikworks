"""The Designer reports reconcile results in its status strip."""

from tik.trigger.core.reconcile import GuideDiff, ModuleDiff
from tik.trigger.ui.designer.window import diff_summary


def test_status_text_for_a_clean_diff():
    assert diff_summary(GuideDiff()) == ""


def test_status_text_counts_not_drawn_modules():
    diff = GuideDiff(modules={"a": ModuleDiff("a", absent=True)})
    assert diff_summary(diff) == "1 not drawn"


def test_status_text_counts_out_of_date_modules():
    diff = GuideDiff(modules={"a": ModuleDiff("a", missing=[("root", 0)])})
    assert diff_summary(diff) == "1 out of date"


def test_status_text_counts_orphans():
    assert diff_summary(GuideDiff(orphans=["ghost_guide"])) == "1 orphan guide(s)"


def test_status_text_counts_duplicates():
    diff = GuideDiff(duplicates=["copy1_guide", "copy2_guide"])
    assert diff_summary(diff) == "2 duplicate guide(s)"


def test_status_text_combines_them():
    diff = GuideDiff(
        modules={
            "a": ModuleDiff("a", absent=True),
            "b": ModuleDiff("b", missing=[("root", 0)]),
            "c": ModuleDiff("c", drifted=[("root", 0)]),
        },
        orphans=["g"],
        duplicates=["d"],
    )
    assert diff_summary(diff) == (
        "1 out of date · 1 not drawn · 1 moved · 1 orphan guide(s) · "
        "1 duplicate guide(s)"
    )


def test_pose_drift_is_reported_as_moved_not_as_a_redraw():
    """Drift is Sync's business. The status bar names both directions now --
    the action bar carries no counts at all -- but it must never call a
    moved guide something that needs redrawing."""
    diff = GuideDiff(modules={"a": ModuleDiff("a", drifted=[("root", 0)])})
    assert diff_summary(diff) == "1 moved"

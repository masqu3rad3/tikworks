"""The Designer reports reconcile results in its status strip."""

from tik.trigger.core.reconcile import GuideDiff, ModuleDiff
from tik.trigger.ui.designer.window import diff_summary


def test_status_text_for_a_clean_diff():
    assert diff_summary(GuideDiff()) == ""


def test_status_text_counts_stale_modules():
    diff = GuideDiff(modules={"a": ModuleDiff("a", absent=True)})
    assert diff_summary(diff) == "1 module(s) need redraw"


def test_status_text_counts_orphans():
    assert diff_summary(GuideDiff(orphans=["ghost_guide"])) == "1 orphan guide(s)"


def test_status_text_counts_duplicates():
    diff = GuideDiff(duplicates=["copy1_guide", "copy2_guide"])
    assert diff_summary(diff) == "2 duplicate guide(s)"


def test_status_text_combines_them():
    diff = GuideDiff(
        modules={"a": ModuleDiff("a", absent=True)},
        orphans=["g"],
        duplicates=["d"],
    )
    assert diff_summary(diff) == (
        "1 module(s) need redraw · 1 orphan guide(s) · 1 duplicate guide(s)"
    )


def test_pose_drift_alone_is_not_reported_as_needing_redraw():
    """Drift is capture's job; reporting it as a redraw would be a lie."""
    diff = GuideDiff(modules={"a": ModuleDiff("a", drifted=[("root", 0)])})
    assert diff_summary(diff) == ""

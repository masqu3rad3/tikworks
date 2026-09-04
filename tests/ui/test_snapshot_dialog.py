"""The dialog that says what a snapshot can and cannot bring back."""

import pytest
from stub import StubScene

from tik.trigger.core.guide_document import GuideDocument, ModuleEntry
from tik.trigger.core.scene_recovery import RecoveredModule, RecoveryReport
from tik.trigger.session import Session
from tik.trigger.ui.designer import GuideDesigner
from tik.trigger.ui.designer.snapshot_dialog import SnapshotDialog


def report(complete=2, partial=0):
    modules = [
        RecoveredModule(f"c{index}", f"mod{index}", "fkchain", True, 4)
        for index in range(complete)
    ] + [
        RecoveredModule(f"p{index}", f"old{index}", "fkchain", False, 4)
        for index in range(partial)
    ]
    return RecoveryReport(modules=modules, guide_count=4 * len(modules))


def test_a_fully_recovered_scene_still_admits_the_graph_is_lost(qapp):
    """``scene_recovery`` never restores positions/collapse/scene-groups, for
    any module -- a complete-breadcrumb scene is not exempt, so the losses
    block must stay up even when every module recovered its name and settings.
    """
    dialog = SnapshotDialog(report(complete=2))
    assert "2 modules" in dialog.found_label.text()
    assert not dialog.losses_group.isHidden()
    text = dialog.losses_label.text().lower()
    assert "graph" in text
    assert "scene-nodes" in text
    # nothing partial here: no per-module settings/connections loss to report
    assert "settings" not in text
    dialog.deleteLater()


def test_an_older_scene_lists_what_it_cannot_recover(qapp):
    """Old files arrive forever; the dialog must degrade honestly."""
    dialog = SnapshotDialog(report(complete=1, partial=2))
    text = dialog.losses_label.text()
    assert "2" in text
    assert "settings" in text.lower()
    assert "connections" in text.lower()
    dialog.deleteLater()


def test_an_empty_scene_has_nothing_to_admit_losing(qapp):
    """No modules found means no graph to have laid out either."""
    dialog = SnapshotDialog(RecoveryReport())
    assert dialog.losses_group.isHidden()
    dialog.deleteLater()


def test_an_empty_scene_cannot_be_confirmed(qapp):
    dialog = SnapshotDialog(RecoveryReport())
    assert not dialog.confirm_button.isEnabled()
    dialog.deleteLater()


# ---------------------------------------------------------------- the command
#
# The three tests above cover the widget. What actually matters to a rigger is
# what the *command* does with the answer: a rejected dialog must not touch the
# session, and an accepted one must replace its modules -- exactly what the
# dialog exists to gate.


def _recovered_document():
    entry = ModuleEntry(
        instance_id="new-id", module_type="fkchain", name="arm", side="L"
    )
    document = GuideDocument(modules=[entry])
    found = RecoveryReport(
        modules=[RecoveredModule("new-id", "L_arm", "fkchain", True, 4)],
        guide_count=4,
    )
    return document, found


@pytest.fixture
def wired_designer(qapp):
    """A designer whose ``StubScene`` is wired back to a real ``Session``,
    the way production wires ``GuideScene(session=self)`` (session.py:313)."""
    session = Session()
    original = ModuleEntry(
        instance_id="old-id", module_type="fkchain", name="spine", side="C"
    )
    session.document.guides = GuideDocument(modules=[original])

    scene = StubScene()
    scene.session = session
    document, found = _recovered_document()
    scene.snapshot_from_scene = lambda: (document, found)

    designer = GuideDesigner(scene=scene)
    yield designer, session, document
    designer.close()


def test_a_rejected_dialog_leaves_the_session_untouched(wired_designer, monkeypatch):
    designer, session, _document = wired_designer
    before = list(session.document.guides.modules)
    monkeypatch.setattr(SnapshotDialog, "exec", lambda self: SnapshotDialog.Rejected)
    designer.snapshot_guides()
    assert session.document.guides.modules == before
    assert [entry.instance_id for entry in session.document.guides.modules] == [
        "old-id"
    ]


def test_an_accepted_dialog_replaces_the_session_modules(wired_designer, monkeypatch):
    designer, session, document = wired_designer
    monkeypatch.setattr(SnapshotDialog, "exec", lambda self: SnapshotDialog.Accepted)
    designer.snapshot_guides()
    assert session.document.guides is document
    assert [entry.instance_id for entry in session.document.guides.modules] == [
        "new-id"
    ]

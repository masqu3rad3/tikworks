"""The Guide Designer keeps up with edits made in the pipeline pane.

Adding or removing a reference changes which modules exist, and that edit
happens in the other pane entirely. Nothing in Maya fires for it, so the
Designer has to be told -- otherwise the modules only turn up after some
unrelated act (Draw All, a scene event) happens to trigger a rebuild.
"""

import pytest
from toy_modules import ToyChain, ToyRoot

from tik.shared.ui.Qt import QtWidgets
from tik.trigger.core import clear_registries, register_module, registry
from tik.trigger.core.document import Document
from tik.trigger.core.guide_document import GuideDocument, GuideRecord, ModuleEntry
from tik.trigger.session import Session
from tik.trigger.ui.session_view import DESIGNER_TAB, SessionView


@pytest.fixture(autouse=True)
def _registered():
    clear_registries()
    register_module("toy_root")(ToyRoot)
    register_module("toy_chain")(ToyChain)
    from tik.trigger.actions.kinematics.kinematics import Kinematics
    from tik.trigger.actions.reference.reference import Reference

    registry.ensure_registered(Kinematics)
    registry.ensure_registered(Reference)
    yield
    clear_registries()


class FakeDesigner(QtWidgets.QWidget):
    """Counts rebuilds, so a test can say when the Designer was told."""

    def __init__(self, scene):
        super().__init__()
        self.guides = scene
        self.refreshed = 0
        self.drifted = 0

    def refresh(self):
        self.refreshed += 1

    def refresh_drift(self):
        self.drifted += 1

    def teardown(self):
        pass


def _base(tmp_path):
    document = Document()
    entry = ModuleEntry(
        instance_id="bbb", module_type="toy_root", name="body", side="C"
    )
    entry.guides = [GuideRecord(role="root", position=(0.0, 0.0, 0.0))]
    document.guides = GuideDocument(modules=[entry])
    path = tmp_path / "base.tr"
    document.save(path)
    return path


def _view(qapp, tmp_path):
    session = Session()
    session.file_path = tmp_path / "hero.tr"
    made = {}

    def _factory(scene):
        made["designer"] = FakeDesigner(scene)
        return made["designer"]

    view = SessionView(session, designer_factory=_factory)
    view.ensure_designer()
    return view, made["designer"]


def test_adding_a_reference_refreshes_the_designer(qapp, tmp_path):
    base = _base(tmp_path)
    view, designer = _view(qapp, tmp_path)
    before = designer.refreshed

    view.session.add("reference", file=str(base))
    view.refresh()

    assert view.session.document.guides.modules, "the link should have landed"
    assert designer.refreshed > before, "the Designer was never told"


def test_removing_a_reference_refreshes_the_designer(qapp, tmp_path):
    base = _base(tmp_path)
    view, designer = _view(qapp, tmp_path)
    handle = view.session.add("reference", file=str(base))
    view.refresh()
    before = designer.refreshed

    view.session.remove(handle.path)
    view.refresh()

    assert view.session.document.guides.modules == []
    assert designer.refreshed > before


def test_switching_to_the_designer_rebuilds_it(qapp, tmp_path):
    """Not just the drift indicators: which modules exist may have changed."""
    base = _base(tmp_path)
    view, designer = _view(qapp, tmp_path)
    view.session.add("reference", file=str(base))
    before = designer.refreshed

    view.sub_tabs.setCurrentIndex(DESIGNER_TAB)

    assert designer.refreshed > before

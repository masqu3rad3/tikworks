"""What the Designer says about borrowed modules and local overrides."""

import pytest
from stub import StubScene
from toy_modules import ToyChain, ToyRoot

from tik.shared.ui import feedback
from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets
from tik.trigger.core import clear_registries, register_module
from tik.trigger.ui.designer import GuideDesigner
from tik.trigger.ui.designer.delegates import (
    DisabledRole,
    DrawStateRole,
    GuideStateDelegate,
    OriginRole,
    OverrideRole,
)


@pytest.fixture(autouse=True)
def _registered():
    clear_registries()
    register_module("toy_root")(ToyRoot)
    register_module("toy_chain")(ToyChain)
    yield
    clear_registries()


@pytest.fixture
def designer(qapp):
    window = GuideDesigner(scene=StubScene())
    window.show()
    yield window
    window.close()


def _row(designer, key):
    """The tree item whose first column reads ``key``."""
    for index in range(designer.tree.topLevelItemCount()):
        found = _find(designer.tree.topLevelItem(index), key)
        if found is not None:
            return found
    return None


def _find(item, key):
    if item.text(0) == key:
        return item
    for index in range(item.childCount()):
        found = _find(item.child(index), key)
        if found is not None:
            return found
    return None


# ------------------------------------------------------------- tree roles
def test_a_local_module_carries_no_origin(designer):
    designer.guides.add("toy_root", name="spine")
    designer.refresh()
    row = _row(designer, "spine")
    assert row is not None
    assert row.data(0, OriginRole) is None
    assert row.data(0, OverrideRole) == 0
    assert row.data(0, DisabledRole) is False


def test_a_referenced_module_names_its_file(designer):
    handle = designer.guides.add("toy_root", name="arm")
    designer.guides.borrow(handle.instance_id, file="baseRig.tr")
    designer.refresh()
    assert _row(designer, "arm").data(0, OriginRole) == "baseRig.tr"


def test_an_overridden_module_carries_a_count(designer):
    handle = designer.guides.add("toy_root", name="wing")
    # upstream calls it "arm"; here it is "wing" -- one override
    designer.guides.borrow(handle.instance_id, source={"name": "arm"})
    designer.refresh()
    assert _row(designer, "wing").data(0, OverrideRole) == 1


def test_matching_the_source_leaves_no_override(designer):
    """The self-cleaning property, visible in the tree."""
    handle = designer.guides.add("toy_root", name="arm")
    designer.guides.borrow(handle.instance_id, source={"name": "arm"})
    designer.refresh()
    row = _row(designer, "arm")
    assert row.data(0, OriginRole) is not None
    assert row.data(0, OverrideRole) == 0


def test_a_disabled_module_is_marked(designer):
    handle = designer.guides.add("toy_root", name="arm")
    designer.guides.borrow(handle.instance_id)
    designer.guides.disable(handle.instance_id)
    designer.refresh()
    assert _row(designer, "arm").data(0, DisabledRole) is True


def test_draw_state_and_override_are_independent(designer):
    """A borrowed module can be not-drawn *and* overridden at once."""
    handle = designer.guides.add("toy_root", name="wing")
    designer.guides.borrow(handle.instance_id, source={"name": "arm"})
    designer.refresh()
    row = _row(designer, "wing")
    assert row.data(0, DrawStateRole) is not None
    assert row.data(0, OverrideRole) == 1


def test_the_tooltip_says_both_things(designer):
    handle = designer.guides.add("toy_root", name="wing")
    designer.guides.borrow(handle.instance_id, file="baseRig.tr", source={"name": "a"})
    designer.refresh()
    tip = _row(designer, "wing").toolTip(0)
    assert "baseRig.tr" in tip and "override" in tip.lower()


# ---------------------------------------------------------------- painting
def _paint(roles=None):
    """Render one row with the given roles; give back every pixel's colour."""
    tree = QtWidgets.QTreeWidget()
    tree.setColumnCount(1)
    item = QtWidgets.QTreeWidgetItem(["L_arm"])
    for role, value in (roles or {}).items():
        item.setData(0, role, value)
    tree.addTopLevelItem(item)
    delegate = GuideStateDelegate()

    image = QtGui.QImage(220, 20, QtGui.QImage.Format_ARGB32)
    image.fill(QtGui.QColor("#151515"))
    painter = QtGui.QPainter(image)
    option = QtWidgets.QStyleOptionViewItem()
    option.rect = QtCore.QRect(0, 0, 220, 20)
    try:
        delegate.paint(painter, option, tree.model().index(0, 0))
    finally:
        painter.end()
    pixels = {image.pixelColor(x, y).name() for x in range(220) for y in range(20)}
    tree.deleteLater()
    return pixels


def test_an_override_paints_its_ink(qapp):
    from tik.trigger.ui.designer.delegates import OVERRIDE_INK

    assert OVERRIDE_INK.lower() in _paint({OverrideRole: 2})


def test_no_override_paints_no_ink(qapp):
    from tik.trigger.ui.designer.delegates import OVERRIDE_INK

    assert OVERRIDE_INK.lower() not in _paint()


def test_an_origin_paints_a_chip(qapp):
    from tik.trigger.ui.designer.delegates import ORIGIN_INK

    assert ORIGIN_INK.lower() in _paint({OriginRole: "baseRig.tr"})


def test_painting_an_unmarked_row_still_works(qapp):
    """The delegate must survive rows that carry none of the new roles."""
    assert _paint()


# ------------------------------------------------------- properties strip
def _select(designer, handle):
    """Show one module in the properties panel."""
    designer._set_current(designer.guides.get(handle.instance_id))


def test_a_local_module_shows_no_reference_strip(designer):
    handle = designer.guides.add("toy_root", name="spine")
    designer.refresh()
    _select(designer, handle)
    assert designer.reference_strip.isVisibleTo(designer.properties) is False


def test_a_referenced_module_names_its_source(designer):
    handle = designer.guides.add("toy_root", name="arm")
    designer.guides.borrow(handle.instance_id, file="baseRig.tr")
    designer.refresh()
    _select(designer, handle)
    assert designer.reference_strip.isVisibleTo(designer.properties) is True
    assert "baseRig.tr" in designer.reference_label.text()


def test_the_strip_counts_the_overrides(designer):
    handle = designer.guides.add("toy_root", name="wing")
    designer.guides.borrow(handle.instance_id, source={"name": "arm"})
    designer.refresh()
    _select(designer, handle)
    assert "1" in designer.reference_label.text()
    assert designer.revert_button.isEnabled()


def test_revert_is_disabled_without_overrides(designer):
    handle = designer.guides.add("toy_root", name="arm")
    designer.guides.borrow(handle.instance_id, source={"name": "arm"})
    designer.refresh()
    _select(designer, handle)
    assert not designer.revert_button.isEnabled()


def test_reverting_restores_what_upstream_says(designer):
    handle = designer.guides.add("toy_root", name="wing")
    designer.guides.borrow(handle.instance_id, source={"name": "arm"})
    designer.refresh()
    _select(designer, handle)

    answered = []
    feedback.set_handler(
        lambda kind, title, text, details, buttons: answered.append(title) or "Revert"
    )
    try:
        designer.revert_module()
    finally:
        feedback.set_handler(None)

    assert answered, "reverting discards local work; it has to ask"
    entry = designer.guides.document.module(handle.instance_id)
    assert entry.name == "arm"


def test_a_cancelled_revert_changes_nothing(designer):
    handle = designer.guides.add("toy_root", name="wing")
    designer.guides.borrow(handle.instance_id, source={"name": "arm"})
    designer.refresh()
    _select(designer, handle)

    feedback.set_handler(lambda *_args: "Cancel")
    try:
        designer.revert_module()
    finally:
        feedback.set_handler(None)
    assert designer.guides.document.module(handle.instance_id).name == "wing"


def test_the_enabled_toggle_leaves_a_module_out(designer):
    handle = designer.guides.add("toy_root", name="arm")
    designer.guides.borrow(handle.instance_id)
    designer.refresh()
    _select(designer, handle)
    assert designer.enabled_box.isChecked()

    designer.set_module_enabled(False)
    assert designer.guides.document.module(handle.instance_id).enabled is False


# ------------------------------------------------------- link and unlink
class FakeSession:
    """Only the two verbs the designer's gestures call."""

    def __init__(self, guides):
        self.document = _Doc(guides)
        self.linked: list = []
        self.unlinked: list = []
        self.raises: Exception = None

    def link_modules(self, file_path, version="latest"):
        if self.raises is not None:
            raise self.raises
        self.linked.append((file_path, version))
        return object()

    def unlink_modules(self, ref_id, bake=False):
        self.unlinked.append((ref_id, bake))


class _Doc:
    def __init__(self, guides):
        self.guides = guides


@pytest.fixture
def linked(designer):
    """A designer whose scene reports a session, with one borrowed module."""
    handle = designer.guides.add("toy_root", name="arm")
    designer.guides.borrow(handle.instance_id, ref_id="r1", file="baseRig.tr")
    designer.guides.session = FakeSession(designer.guides.document)
    designer.refresh()
    return designer, handle


def test_reference_modules_links_what_the_browser_returns(designer):
    designer.file_browser = lambda mode, extensions, current: "/rigs/base.tr"
    designer.guides.session = FakeSession(designer.guides.document)
    designer.reference_modules()
    assert designer.guides.session.linked == [("/rigs/base.tr", "latest")]


def test_a_cancelled_browse_links_nothing(designer):
    designer.file_browser = lambda mode, extensions, current: ""
    designer.guides.session = FakeSession(designer.guides.document)
    designer.reference_modules()
    assert designer.guides.session.linked == []


def test_linking_an_already_linked_file_is_reported_not_raised(designer):
    from tik.trigger.core.exceptions import SessionError

    designer.file_browser = lambda mode, extensions, current: "/rigs/base.tr"
    session = FakeSession(designer.guides.document)
    session.raises = SessionError("'base.tr' is already linked to this session.")
    designer.guides._session = session
    designer.reference_modules()  # must not raise into Qt
    assert session.linked == []


def test_unlink_bakes_when_asked(linked):
    designer, _handle = linked
    feedback.set_handler(lambda *_args: "Bake in")
    try:
        designer.unlink_reference("r1")
    finally:
        feedback.set_handler(None)
    assert designer.guides.session.unlinked == [("r1", True)]


def test_unlink_discards_when_asked(linked):
    designer, _handle = linked
    feedback.set_handler(lambda *_args: "Discard")
    try:
        designer.unlink_reference("r1")
    finally:
        feedback.set_handler(None)
    assert designer.guides.session.unlinked == [("r1", False)]


def test_a_cancelled_unlink_does_nothing(linked):
    designer, _handle = linked
    feedback.set_handler(lambda *_args: "Cancel")
    try:
        designer.unlink_reference("r1")
    finally:
        feedback.set_handler(None)
    assert designer.guides.session.unlinked == []


def test_unlinking_offers_bake_before_discard(linked):
    """Discarding authored overrides must never be the default button."""
    designer, _handle = linked
    seen = {}

    def _handler(kind, title, text, details, buttons):
        seen["buttons"] = list(buttons)
        return "Cancel"

    feedback.set_handler(_handler)
    try:
        designer.unlink_reference("r1")
    finally:
        feedback.set_handler(None)
    assert seen["buttons"][0] == "Bake in"
    assert seen["buttons"].index("Discard") > 0

"""What the Designer says about borrowed modules and local overrides."""

import pytest
from stub import StubScene
from toy_modules import ToyChain, ToyRoot

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

"""The Designer's Labels toggle.

A view operation, not a preference read at draw time: ``trigger/guides`` may
not import the preferences packages, so Draw always writes labels on and this
button turns them off afterwards. A preference can never change what Draw
renders -- it only decides where the button starts.
"""

import pytest
from stub import StubScene
from toy_modules import ToyChain, ToyRoot

from tik.trigger.core import clear_registries, register_module
from tik.trigger.ui.designer import GuideDesigner
from tik.trigger.ui.designer.action_bar import DesignerActionBar


@pytest.fixture(autouse=True)
def _registered():
    clear_registries()
    register_module("toy_root")(ToyRoot)
    register_module("toy_chain")(ToyChain)
    yield
    clear_registries()


def test_the_bar_has_a_labels_toggle(qapp):
    bar = DesignerActionBar()
    assert bar.labels_check.text() == "Labels"
    assert bar.labels_check.isChecked()


def test_toggling_emits_its_state(qapp):
    bar = DesignerActionBar()
    seen = []
    bar.labels_toggled.connect(seen.append)
    bar.labels_check.setChecked(False)
    assert seen == [False]


def test_set_labels_does_not_re_emit(qapp):
    """Restoring the saved state must not read as a user toggle."""
    bar = DesignerActionBar()
    seen = []
    bar.labels_toggled.connect(seen.append)
    bar.set_labels(False)
    assert seen == []
    assert not bar.labels_check.isChecked()


def test_the_toggle_sits_in_the_scene_group(qapp):
    """Labels change the scene, so the bar places it before the stretch that
    separates the -> SCENE group from the -> SESSION one."""
    bar = DesignerActionBar()
    layout = bar.layout()
    order = [layout.itemAt(index).widget() for index in range(layout.count())]
    assert order.index(bar.labels_check) < order.index(bar.sync_button)


def test_the_designer_pushes_the_toggle_to_the_scene(qapp):
    """The bar emits; the Designer acts. The bar itself knows no scene."""
    window = GuideDesigner(scene=StubScene())
    try:
        window.action_bar.labels_check.setChecked(False)
        assert window.guides.labels_visible is False
        window.action_bar.labels_check.setChecked(True)
        assert window.guides.labels_visible is True
    finally:
        window.close()

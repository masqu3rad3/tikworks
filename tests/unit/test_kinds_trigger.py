"""The kind vocabulary a VCS provider maps, and how a field declares one."""

from tik.core.fields import FileField
from tik.trigger.core import kinds


def test_declared_kind_wins_over_extensions():
    assert kinds.kind_for([".mb"], declared="rig") == "rig"


def test_extensions_map_in_declared_order():
    assert kinds.kind_for([".tr"]) == kinds.SESSION
    assert kinds.kind_for([".trg"]) == kinds.GUIDES
    assert kinds.kind_for([".py"]) == kinds.SCRIPT
    # .mb is both a model and a rig; a bare field is more likely a model
    assert kinds.kind_for([".ma", ".mb", ".fbx"]) == kinds.MODEL
    assert kinds.kind_for([".mb"]) == kinds.MODEL


def test_unknown_extensions_are_a_generic_file():
    assert kinds.kind_for([".json"]) == kinds.FILE
    assert kinds.kind_for([]) == kinds.FILE


def test_file_field_carries_its_kind_into_the_schema():
    field = FileField("", extensions=[".mb"], kind="rig")
    field.name = "scene"
    assert field.kind == "rig"
    assert field.to_schema()["kind"] == "rig"
    plain = FileField("", extensions=[".py"])
    plain.name = "file_path"
    assert plain.kind == ""
    assert plain.to_schema()["kind"] == ""

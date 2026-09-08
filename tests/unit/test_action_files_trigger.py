"""What an action declares it needs (dependencies) and writes (products)."""

from pathlib import Path

from tik.trigger.core import Action, ActionContext, FileField, StringField
from tik.trigger.core.publish_set import Artifact


class Uses(Action):
    script = FileField("", extensions=[".py"], kind="script")
    folder = FileField("", mode="dir")
    name = StringField("")


class Writes(Uses):
    def products(self, ctx):
        return [Artifact("weights", ctx.resolve("weights/arm.json"))]


def test_file_fields_exclude_directories():
    assert list(Uses.file_fields()) == ["script"]


def test_dependencies_are_the_resolved_non_empty_file_fields(tmp_path):
    ctx = ActionContext(base_dir=str(tmp_path))
    assert Uses({"script": ""}).dependencies(ctx) == []
    assert Uses({"script": "scripts/a.py"}).dependencies(ctx) == [
        tmp_path / "scripts" / "a.py"
    ]


def test_products_default_to_nothing_and_subclasses_are_detected(tmp_path):
    ctx = ActionContext(base_dir=str(tmp_path))
    assert Uses().products(ctx) == []
    assert Uses.has_products() is False
    assert Writes.has_products() is True
    (product,) = Writes().products(ctx)
    assert product.kind == "weights" and product.path == Path(
        tmp_path, "weights/arm.json"
    )


def test_save_from_scene_is_gone():
    assert not hasattr(Action, "save_from_scene")

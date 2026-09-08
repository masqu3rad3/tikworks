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


def test_a_script_depends_on_its_whole_folder(tmp_path):
    """A script may import a sibling nothing in the document names.

    The runner puts ``<session>/scripts`` on the module path, so the import
    works in the rigger's session; the publish has to carry the folder or it
    would only work there.
    """
    from tik.trigger.actions.script.script import Script

    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for name in ("mark.py", "helper.py", "notes.txt"):
        (scripts / name).write_text("x", encoding="utf-8")
    ctx = ActionContext(base_dir=str(tmp_path))
    assert Script({"code": "pass"}).dependencies(ctx) == []
    assert Script({"file_path": "scripts/mark.py"}).dependencies(ctx) == [
        scripts / "mark.py",
        scripts / "helper.py",
    ]
    # a file field pointing nowhere brings nothing along
    assert Script({"file_path": "gone/mark.py"}).dependencies(ctx) == [
        tmp_path / "gone" / "mark.py"
    ]

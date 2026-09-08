"""The publish set: what a session needs, and bundles that never copy twice."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import tik.trigger as trigger
from tik.trigger.core import (
    Action,
    Document,
    FileField,
    get_action,
    kinds,
    register_action,
    unregister_action,
)
from tik.trigger.core.document import ActionNode
from tik.trigger.core.guide_document import ModuleReference
from tik.trigger.core.publish_set import (
    MANIFEST,
    STORE_DIR,
    Artifact,
    PublishSet,
    Store,
    clean,
    collect_dependencies,
    is_external,
    write_bundle,
)


@pytest.fixture(autouse=True, scope="module")
def _plugins():
    trigger.load_plugins()


def _script(name, file_path):
    return ActionNode(name=name, type="script", settings={"file_path": file_path})


class _WithSibling(Action):
    """A toy action whose script imports a sibling no field names."""

    file_path = FileField("", extensions=[".py"])

    def dependencies(self, ctx):
        found = super().dependencies(ctx)
        if self.file_path:
            found.append(ctx.resolve("scripts/helper.py"))
        return found

    def run(self, ctx):  # pragma: no cover - never executed
        return None


@pytest.fixture
def sibling_action():
    register_action("sibling_script")(_WithSibling)
    yield
    unregister_action("sibling_script")


def _session(folder: Path, name="hero", scripts=("a.py",)):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "scripts").mkdir(exist_ok=True)
    document = Document()
    for script in scripts:
        (folder / "scripts" / script).write_text(f"# {script}\n", encoding="utf-8")
        document.actions.append(_script(Path(script).stem, f"scripts/{script}"))
    document.save(folder / f"{name}.tr")
    return document


def test_is_external_means_outside_the_session_folder(tmp_path):
    assert is_external(tmp_path / "work" / "a.py", tmp_path / "work") is False
    assert is_external(tmp_path / "lib" / "a.py", tmp_path / "work") is True


def test_dependencies_come_from_file_fields_of_enabled_actions(tmp_path):
    document = _session(tmp_path / "work", scripts=("a.py", "b.py"))
    document.actions[1].enabled = False
    found = collect_dependencies(document, tmp_path / "work")
    # b is disabled, so it never owns a dependency -- but it still travels, as
    # a sibling of a's script that a is free to import
    assert [(dep.owner, dep.original, dep.external) for dep in found] == [
        ("a", "scripts/a.py", False),
        ("a", "scripts/b.py", False),
    ]
    assert found[0].path == tmp_path / "work" / "scripts" / "a.py"


def test_dependencies_recurse_through_references(tmp_path):
    _session(tmp_path / "base", name="base", scripts=("base.py",))
    hero = _session(tmp_path / "work", scripts=("a.py",))
    hero.actions.append(
        ActionNode(name="ref", type="reference", settings={"file": "../base/base.tr"})
    )
    hero.guides.references.append(
        ModuleReference(ref_id="r1", file="../base/base.tr", version="pinned")
    )
    found = collect_dependencies(hero, tmp_path / "work")
    owners = [(dep.owner, dep.path.name) for dep in found]
    assert ("a", "a.py") in owners
    assert ("ref", "base.tr") in owners
    assert ("ref/base", "base.py") in owners
    assert ("guides/r1", "base.tr") in owners
    # the same referenced file through two links is listed once per link,
    # but its own dependencies are walked once
    assert owners.count(("ref/base", "base.py")) == 1


def test_collect_builds_the_core_artifacts(tmp_path):
    document = _session(tmp_path / "work")
    rig = tmp_path / "work" / "hero_rig.mb"
    rig.write_bytes(b"rig")
    publish_set = PublishSet.collect(
        tmp_path / "work" / "hero.tr",
        document,
        rig=rig,
        products=[Artifact("weights", tmp_path / "work" / "w.json")],
    )
    assert publish_set.name == "hero"
    assert [item.kind for item in publish_set.artifacts] == [
        kinds.SESSION,
        kinds.RIG,
        "weights",
    ]
    assert [dep.original for dep in publish_set.dependencies] == ["scripts/a.py"]


def test_store_keeps_one_copy_per_content(tmp_path):
    store = Store(tmp_path / STORE_DIR)
    one = tmp_path / "one.py"
    two = tmp_path / "two.py"
    one.write_text("same", encoding="utf-8")
    two.write_text("same", encoding="utf-8")
    first = store.put(one)
    second = store.put(two)
    assert first.exists() and first.name.endswith("_one.py")
    assert second.name.endswith("_two.py")
    assert store.hash_file(one) == store.hash_file(two)
    assert store.put(one) == first
    assert len(store.files()) == 2


def test_hash_cache_is_keyed_by_size_and_mtime(tmp_path):
    store = Store(tmp_path / STORE_DIR)
    target = tmp_path / "f.txt"
    target.write_text("abc", encoding="utf-8")
    first = store.hash_file(target)
    index = json.loads((store.root / "index.json").read_text(encoding="utf-8"))
    assert list(index.values())[0]["hash"] == first
    target.write_text("abd", encoding="utf-8")
    os.utime(target, (1, 1))
    assert store.hash_file(target) != first


def test_bundle_rewrites_paths_and_reopens_on_its_own(tmp_path):
    document = _session(tmp_path / "work")
    rig = tmp_path / "work" / "hero_rig.mb"
    rig.write_bytes(b"rig")
    publish_set = PublishSet.collect(tmp_path / "work" / "hero.tr", document, rig=rig)
    target = tmp_path / "out" / "hero_v001"
    write_bundle(publish_set, target)
    bundled = Document.load(target / "hero.tr")
    value = bundled.actions[0].settings["file_path"]
    assert value.startswith(f"../{STORE_DIR}/") and value.endswith("_a.py")
    assert (target / value).resolve().exists()
    assert (target / "hero_rig.mb").read_bytes() == b"rig"
    manifest = json.loads((target / MANIFEST).read_text(encoding="utf-8"))
    assert manifest["session"] == "hero.tr"
    assert manifest["dependencies"][0]["owner"] == "a"
    assert manifest["dependencies"][0]["store"] == value


def test_second_bundle_reuses_unchanged_content(tmp_path):
    document = _session(tmp_path / "work")
    publish_set = PublishSet.collect(tmp_path / "work" / "hero.tr", document)
    write_bundle(publish_set, tmp_path / "out" / "hero_v001")
    write_bundle(publish_set, tmp_path / "out" / "hero_v002")
    store = Store(tmp_path / "out" / STORE_DIR)
    assert len(store.files()) == 1
    (tmp_path / "work" / "scripts" / "a.py").write_text("# changed\n", encoding="utf-8")
    write_bundle(publish_set, tmp_path / "out" / "hero_v003")
    assert len(store.files()) == 2


def test_external_paths_are_left_alone_and_flagged(tmp_path):
    library = tmp_path / "lib" / "model.mb"
    library.parent.mkdir()
    library.write_bytes(b"model")
    document = _session(tmp_path / "work", scripts=())
    document.actions.append(
        ActionNode(
            name="model",
            type="import_asset",
            settings={"file_path": str(library).replace("\\", "/")},
        )
    )
    publish_set = PublishSet.collect(tmp_path / "work" / "hero.tr", document)
    target = tmp_path / "out" / "hero_v001"
    write_bundle(publish_set, target)
    bundled = Document.load(target / "hero.tr")
    assert Path(bundled.actions[0].settings["file_path"]) == library
    manifest = json.loads((target / MANIFEST).read_text(encoding="utf-8"))
    assert manifest["dependencies"][0]["external"] is True
    assert Store(tmp_path / "out" / STORE_DIR).files() == []


def test_referenced_sessions_are_bundled_recursively(tmp_path):
    _session(tmp_path / "base", name="base", scripts=("base.py",))
    hero = _session(tmp_path / "work", scripts=())
    hero.actions.append(
        ActionNode(
            name="ref",
            type="reference",
            settings={"file": "../base/base.tr", "version": "latest"},
        )
    )
    publish_set = PublishSet.collect(tmp_path / "work" / "hero.tr", hero)
    target = tmp_path / "out" / "hero_v001"
    write_bundle(publish_set, target)
    bundled = Document.load(target / "hero.tr")
    ref = bundled.actions[0].settings
    assert ref["version"] == "pinned"
    nested_path = (target / ref["file"]).resolve()
    assert nested_path.parent == (tmp_path / "out" / STORE_DIR).resolve()
    nested = Document.load(nested_path)
    inner = nested.actions[0].settings["file_path"]
    assert "/" not in inner and inner.endswith("_base.py")
    assert (nested_path.parent / inner).exists()


def test_manifest_store_values_are_relative_to_the_bundle(tmp_path):
    _session(tmp_path / "base", name="base", scripts=("base.py",))
    hero = _session(tmp_path / "work", scripts=("a.py",))
    hero.actions.append(
        ActionNode(name="ref", type="reference", settings={"file": "../base/base.tr"})
    )
    publish_set = PublishSet.collect(tmp_path / "work" / "hero.tr", hero)
    target = tmp_path / "out" / "hero_v001"
    write_bundle(publish_set, target)
    manifest = json.loads((target / MANIFEST).read_text(encoding="utf-8"))
    stored = {
        entry["owner"]: entry["store"]
        for entry in manifest["dependencies"]
        if not entry["external"]
    }
    assert set(stored) == {"a", "ref", "ref/base"}
    for value in stored.values():
        assert (target / value).resolve().exists()
    # every store file the bundle needs is named by that one manifest
    assert clean(tmp_path / "out" / STORE_DIR, [target]) == []


def test_non_field_dependencies_are_copied_into_the_bundle(tmp_path, sibling_action):
    folder = tmp_path / "work"
    document = _session(folder, scripts=("a.py",))
    (folder / "scripts" / "helper.py").write_text("# helper\n", encoding="utf-8")
    document.actions[0].type = "sibling_script"
    publish_set = PublishSet.collect(folder / "hero.tr", document)
    assert [dep.original for dep in publish_set.dependencies] == [
        "scripts/a.py",
        "scripts/helper.py",
    ]
    target = tmp_path / "out" / "hero_v001"
    write_bundle(publish_set, target)
    # the sibling keeps its name and its place; only the field goes to the store
    assert (target / "scripts" / "helper.py").read_text(
        encoding="utf-8"
    ) == "# helper\n"
    bundled = Document.load(target / "hero.tr")
    assert bundled.actions[0].settings["file_path"].startswith(f"../{STORE_DIR}/")
    manifest = json.loads((target / MANIFEST).read_text(encoding="utf-8"))
    extra = next(
        entry
        for entry in manifest["dependencies"]
        if entry["original"] == "scripts/helper.py"
    )
    assert extra["owner"] == "a"
    assert extra["store"] == "scripts/helper.py"
    assert extra["external"] is False


def test_reference_overrides_are_rewritten_into_the_store(tmp_path):
    base = tmp_path / "base"
    _session(base, name="base", scripts=("base.py",))
    (base / "scripts" / "other.py").write_text("# other\n", encoding="utf-8")
    hero = _session(tmp_path / "work", scripts=())
    hero.actions.append(
        ActionNode(
            name="ref",
            type="reference",
            settings={
                "file": "../base/base.tr",
                "overrides": {"base": {"settings": {"file_path": "scripts/other.py"}}},
            },
        )
    )
    publish_set = PublishSet.collect(tmp_path / "work" / "hero.tr", hero)
    target = tmp_path / "out" / "hero_v001"
    write_bundle(publish_set, target)
    settings = Document.load(target / "hero.tr").actions[0].settings
    # an override is resolved against the referenced session, which now lives
    # in the store: the value has to be relative to the store root
    store_root = (target / settings["file"]).resolve().parent
    override = settings["overrides"]["base"]["settings"]["file_path"]
    assert "/" not in override and override.endswith("_other.py")
    assert (store_root / override).exists()


def test_an_override_pins_the_alias_the_file_it_swaps_in_gives(tmp_path):
    """The override decides the file, so it has to decide the alias too.

    The nested document pins ``import_as`` from the file *it* names; an
    override that swaps the file would otherwise leave the published copy
    importing the base session's name for the hero session's script.
    """
    base = tmp_path / "base"
    _session(base, name="base", scripts=("base.py",))
    (base / "scripts" / "other.py").write_text("# other\n", encoding="utf-8")
    hero = _session(tmp_path / "work", scripts=())
    hero.actions.append(
        ActionNode(
            name="ref",
            type="reference",
            settings={
                "file": "../base/base.tr",
                "overrides": {"base": {"settings": {"file_path": "scripts/other.py"}}},
            },
        )
    )
    publish_set = PublishSet.collect(tmp_path / "work" / "hero.tr", hero)
    target = tmp_path / "out" / "hero_v001"
    write_bundle(publish_set, target)
    settings = Document.load(target / "hero.tr").actions[0].settings
    override = settings["overrides"]["base"]["settings"]
    assert override["import_as"] == "other"
    # the nested document keeps its own alias; only the override moved
    nested = Document.load((target / settings["file"]).resolve())
    assert nested.actions[0].settings["import_as"] == "base"


def test_clean_removes_only_unreferenced_store_files(tmp_path):
    document = _session(tmp_path / "work")
    publish_set = PublishSet.collect(tmp_path / "work" / "hero.tr", document)
    write_bundle(publish_set, tmp_path / "out" / "hero_v001")
    store = Store(tmp_path / "out" / STORE_DIR)
    orphan = store.put_bytes(b"orphan", "orphan.txt")
    removed = clean(store.root, [tmp_path / "out" / "hero_v001"])
    assert removed == [orphan]
    assert len(store.files()) == 1


# ------------------------------------------------------------------- pins
def test_an_action_pins_nothing_by_default():
    assert Action.pin_settings({"file_path": "scripts/a.py"}) == {}


def test_the_script_action_pins_the_alias_its_file_name_gave_it():
    script = get_action("script")
    assert script.pin_settings({"file_path": "scripts/a.py"}) == {"import_as": "a"}
    # nothing to pin: the alias is already written down, or there is no file
    assert script.pin_settings({"file_path": "scripts/a.py", "import_as": "lib"}) == {}
    assert script.pin_settings({"code": "pass"}) == {}


def test_a_bundled_script_keeps_the_alias_its_original_name_gave_it(tmp_path):
    document = _session(tmp_path / "work")
    publish_set = PublishSet.collect(tmp_path / "work" / "hero.tr", document)
    target = tmp_path / "out" / "hero_v001"
    write_bundle(publish_set, target)
    settings = Document.load(target / "hero.tr").actions[0].settings
    # the store renamed the file to its hash; the alias must not follow it
    assert settings["file_path"].startswith(f"../{STORE_DIR}/")
    assert settings["import_as"] == "a"

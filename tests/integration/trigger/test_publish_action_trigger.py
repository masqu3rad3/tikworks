"""Build & Publish with the generic publish action writes a self-contained bundle."""

import json

import pytest
from maya import cmds

import tik.trigger as trigger
from tik.trigger.core.exceptions import SessionError
from tik.trigger.core.publish_set import MANIFEST, STORE_DIR, Store
from tik.trigger.guides.format import GuideFile
from tik.trigger.guides.snapshot import snapshot

MARK = "import maya.cmds as cmds\ncmds.createNode('transform', name='{name}')"


def _session(tmp_path):
    work = tmp_path / "work"
    (work / "scripts").mkdir(parents=True)
    (work / "scripts" / "mark.py").write_text(
        "import maya.cmds as cmds\n\n\ndef make():\n"
        "    cmds.createNode('transform', name='from_file')\n",
        encoding="utf-8",
    )
    rig = trigger.Session()
    rig.save(work / "hero.tr")
    rig.add("script", "lib", file_path="scripts/mark.py", code="mark.make()")
    rig.add("script", "inline", code=MARK.format(name="inline"))
    body = rig.guides.add("base", side="C", name="body")
    # the default after_build deletes the guide joints, which is exactly the
    # case the published .trg has to survive
    rig.add("kinematics", "skeleton", modules=[body.instance_id])
    rig.publish.add("publish", "out", folder="publish")
    rig.save()
    return rig


def test_build_and_publish_writes_a_bundle_that_rebuilds_alone(tmp_path):
    rig = _session(tmp_path)
    rig.build(publish=True)
    bundle = tmp_path / "work" / "publish" / "hero_v001"
    assert (bundle / "hero.tr").exists()
    assert (bundle / "hero_rig.mb").exists()
    # the build deleted the guide joints; the .trg comes from the document
    assert GuideFile.load(bundle / "hero.trg").records
    manifest = json.loads((bundle / MANIFEST).read_text(encoding="utf-8"))
    assert [item["kind"] for item in manifest["artifacts"]] == [
        "session",
        "guides",
        "rig",
    ]
    assert manifest["dependencies"][0]["original"] == "scripts/mark.py"
    assert not (tmp_path / "work" / "_publish_tmp").exists()
    # it drew the guides to export them, then put the scene back as it was
    assert not snapshot()

    # the published session builds on its own, from the store
    again = trigger.Session.open(str(bundle / "hero.tr"))
    again.build()
    assert cmds.objExists("from_file") and cmds.objExists("inline")


def test_second_publish_reuses_the_store(tmp_path):
    rig = _session(tmp_path)
    rig.build(publish=True)
    rig.build(publish=True)
    assert (tmp_path / "work" / "publish" / "hero_v002").exists()
    assert len(Store(tmp_path / "work" / "publish" / STORE_DIR).files()) == 1


def test_a_partial_build_still_refuses_to_publish(tmp_path):
    rig = _session(tmp_path)
    with pytest.raises(SessionError):
        rig.build(until="lib", publish=True)


def test_a_failing_delivery_keeps_the_temporaries(tmp_path, monkeypatch):
    from tik.trigger.actions.publish.publish import Publish
    from tik.trigger.core.exceptions import ActionExecutionError

    rig = _session(tmp_path)
    monkeypatch.setattr(Publish, "deliver", lambda self, s, c: 1 / 0)
    with pytest.raises(ActionExecutionError):
        rig.build(publish=True)
    assert (tmp_path / "work" / "_publish_tmp" / "hero_rig.mb").exists()

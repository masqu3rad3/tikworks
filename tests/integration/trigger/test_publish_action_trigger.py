"""Build & Publish with the generic publish action writes a self-contained bundle."""

import json

import pytest
from maya import cmds

import tik.trigger as trigger
from tik.trigger.core.exceptions import SessionError
from tik.trigger.core.publish_set import MANIFEST, STORE_DIR, Store

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
    rig.publish.add("publish", "out", folder="publish")
    rig.save()
    return rig


def test_build_and_publish_writes_a_bundle_that_rebuilds_alone(tmp_path):
    rig = _session(tmp_path)
    rig.build(publish=True)
    bundle = tmp_path / "work" / "publish" / "hero_v001"
    assert (bundle / "hero.tr").exists()
    assert (bundle / "hero_rig.mb").exists()
    assert (bundle / "hero.trg").exists()
    manifest = json.loads((bundle / MANIFEST).read_text(encoding="utf-8"))
    assert [item["kind"] for item in manifest["artifacts"]] == [
        "session",
        "guides",
        "rig",
    ]
    assert manifest["dependencies"][0]["original"] == "scripts/mark.py"
    assert not (tmp_path / "work" / "_publish_tmp").exists()

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

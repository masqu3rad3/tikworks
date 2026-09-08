"""PublishAction without Maya: fields, validation, and the folder delivery."""

import pytest

import tik.trigger as trigger
from tik.trigger.core import ActionContext, registry
from tik.trigger.core.publish_set import STORE_DIR, PublishSet
from tik.trigger.session import Session


@pytest.fixture(autouse=True, scope="module")
def _plugins():
    trigger.load_plugins()


def test_publish_is_registered_in_the_publish_scope():
    cls = registry.get_action("publish")
    assert cls.scope == "publish" and cls.category == "finish"
    assert "folder" in cls.fields() and "include_guides" in cls.fields()
    assert cls().include_guides is True and cls().include_products is True
    assert cls().folder == "publish"


def test_validate_needs_a_saved_session(tmp_path):
    cls = registry.get_action("publish")
    problems = cls().validate(ActionContext(session=None, base_dir=str(tmp_path)))
    assert problems == ["publish: save the session first"]
    session = Session()
    assert cls().validate(ActionContext(session=session, base_dir=str(tmp_path))) == [
        "publish: save the session first"
    ]
    session.save(tmp_path / "hero.tr")
    assert cls().validate(ActionContext(session=session, base_dir=str(tmp_path))) == []


def test_deliver_writes_a_versioned_bundle_beside_a_store(tmp_path):
    cls = registry.get_action("publish")
    session = Session()
    session.save(tmp_path / "hero.tr")
    publish_set = PublishSet.collect(session.file_path, session.document)
    ctx = ActionContext(session=session, base_dir=str(tmp_path))
    action = cls({"folder": "out"})
    action.deliver(publish_set, ctx)
    action.deliver(publish_set, ctx)
    assert (tmp_path / "out" / "hero_v001" / "hero.tr").exists()
    assert (tmp_path / "out" / "hero_v002" / "manifest.json").exists()
    assert (tmp_path / "out" / STORE_DIR).is_dir()
    assert action.summary() == "out"


def test_deliver_is_abstract_on_the_base():
    from tik.trigger.actions.publish.publish import PublishAction

    with pytest.raises(NotImplementedError):
        PublishAction().deliver(None, ActionContext())


def test_collect_hands_deliver_a_copy_of_the_document(tmp_path):
    """``deliver`` is third-party code; it must not reach the open session."""
    cls = registry.get_action("publish")
    session = Session()
    session.save(tmp_path / "hero.tr")
    session.add("script", "lib", code="pass")
    ctx = ActionContext(session=session, base_dir=str(tmp_path))
    publish_set = cls().collect(ctx)
    assert publish_set.document is not session.document
    publish_set.document.actions[0].settings["code"] = "changed"
    publish_set.document.actions.append(publish_set.document.actions[0].copy())
    assert session.document.actions[0].settings["code"] == "pass"
    assert len(session.document.actions) == 1

"""A session holds two views of one document: Session and Guide Designer."""

import pytest
from test_pipeline_ui import _stub_designer

from tik.trigger.session import Session
from tik.trigger.ui.session_view import DESIGNER_TAB, SESSION_TAB, SessionView


@pytest.fixture
def view(qapp):
    widget = SessionView(Session(), designer_factory=_stub_designer)
    widget.show()
    yield widget
    widget.teardown()
    widget.close()


def test_a_session_has_two_sub_tabs(view):
    titles = [view.sub_tabs.tabText(index) for index in range(view.sub_tabs.count())]
    assert titles == ["Session", "Guide Designer"]
    assert view.sub_tabs.currentIndex() == SESSION_TAB


def test_the_designer_is_not_built_until_its_tab_is_opened(view):
    assert view.designer is None
    view.sub_tabs.setCurrentIndex(DESIGNER_TAB)
    assert view.designer is not None


def test_the_designer_is_built_once(view):
    view.sub_tabs.setCurrentIndex(DESIGNER_TAB)
    first = view.designer
    view.sub_tabs.setCurrentIndex(SESSION_TAB)
    view.sub_tabs.setCurrentIndex(DESIGNER_TAB)
    assert view.designer is first


def test_the_pipeline_lives_on_the_session_tab(view):
    """Both pipeline trees -- build and publish -- sit on the Session tab."""
    found = view.sub_tabs.widget(SESSION_TAB).findChildren(type(view.tree))
    assert set(found) == {view.tree, view.publish_tree}


def test_switching_sub_tabs_reports_which_one(view):
    seen = []
    view.sub_tab_changed.connect(seen.append)
    view.sub_tabs.setCurrentIndex(DESIGNER_TAB)
    assert seen == [DESIGNER_TAB]


def test_teardown_releases_the_designer(view):
    view.sub_tabs.setCurrentIndex(DESIGNER_TAB)
    designer = view.designer
    view.teardown()
    assert designer._torn_down is True


def test_the_designer_edits_the_sessions_guides(qapp):
    """The Designer must not build a GuideScene of its own.

    An unbound one would show nothing and edit a document no session ever sees
    -- which is what happened, because the UI tests used to hand the double
    straight to the Designer and so never ran the real wiring.
    """
    seen = {}

    def factory(scene=None):
        seen["scene"] = scene
        return _stub_designer(scene)

    session = Session()
    view = SessionView(session, designer_factory=factory)
    view.sub_tabs.setCurrentIndex(DESIGNER_TAB)
    assert seen["scene"] is session.guides
    assert view.designer.guides is session.guides
    view.teardown()

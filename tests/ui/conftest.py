"""Qt UI tests run without Maya: ``TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen``."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from tik.shared.ui.Qt import QtWidgets
except Exception:  # noqa: BLE001 - Qt unavailable in this interpreter
    QtWidgets = None


def pytest_collection_modifyitems(config, items):
    if QtWidgets is None or not os.environ.get("TIK_TESTS_NO_MAYA"):
        skip = pytest.mark.skip(reason="UI tests need Qt and TIK_TESTS_NO_MAYA=1")
        for item in items:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def qapp():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


@pytest.fixture(autouse=True)
def stub_session_guides(monkeypatch):
    """Give every ``Session`` a ``StubScene`` for its guides.

    Maya standalone cannot host a QApplication, so these tests run without Maya
    and ``GuideScene`` is unimportable here. Injecting the double through
    ``Session.guides`` -- rather than handing it straight to the Designer --
    keeps the production wiring under test: the Designer really does get its
    scene from the session it belongs to.
    """
    if QtWidgets is None:
        yield
        return
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    from stub import StubScene
    from tik.trigger.session import Session

    scenes: dict = {}

    def guides(self):
        return scenes.setdefault(id(self), StubScene())

    monkeypatch.setattr(Session, "guides", property(guides))
    yield

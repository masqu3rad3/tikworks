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


@pytest.fixture(scope="session", autouse=True)
def _qsettings_sandbox(tmp_path_factory):
    """Keep ``QSettings("tikworks", "trigger")`` off the developer's real machine.

    That is the same org/app the running Trigger tool persists its designer
    preferences under (spec 3.2). Left alone, ``tests/ui`` writes for real --
    to the Windows registry here, an ini file under ``~/.config`` elsewhere --
    and a UI test run has been observed to flip the *live* app's default
    ``auto_sync`` setting. ``qapp`` below requests this fixture explicitly
    (rather than relying on autouse-ordering) so the redirect is in place
    before anything constructs a ``QSettings`` object.

    ``setDefaultFormat(IniFormat)`` + ``setPath(IniFormat, ...)`` alone is not
    enough: every call site in this codebase uses the two-arg convenience
    constructor ``QSettings(organization, application)``, which Qt documents
    as equivalent to ``QSettings(NativeFormat, UserScope, organization,
    application)`` -- it ignores ``setDefaultFormat()`` outright, and
    ``NativeFormat`` (the Windows registry, a macOS plist) ignores
    ``setPath()`` too, since neither backend is path-based. So the two-arg
    constructor itself is intercepted below and rerouted to the redirected
    ``IniFormat`` store, with no change to production code.
    """
    if QtWidgets is None:
        yield None
        return
    from tik.shared.ui.Qt import QtCore

    directory = tmp_path_factory.mktemp("qsettings")
    real_qsettings = QtCore.QSettings
    real_qsettings.setDefaultFormat(real_qsettings.IniFormat)
    real_qsettings.setPath(real_qsettings.IniFormat, real_qsettings.UserScope, str(directory))

    class _SandboxedQSettings(real_qsettings):
        def __init__(self, *args, **kwargs):
            if len(args) == 2 and not kwargs and all(isinstance(a, str) for a in args):
                organization, application = args
                super().__init__(real_qsettings.IniFormat, real_qsettings.UserScope, organization, application)
            else:
                super().__init__(*args, **kwargs)

    QtCore.QSettings = _SandboxedQSettings
    try:
        yield directory
    finally:
        QtCore.QSettings = real_qsettings


@pytest.fixture(scope="session")
def qapp(_qsettings_sandbox):
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

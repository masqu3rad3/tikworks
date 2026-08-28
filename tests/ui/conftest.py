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

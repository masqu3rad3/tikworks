"""Layering rules for tikworks packages.

tik.core < tik.maya < tik.trigger. ``tik.trigger.core`` and
``tik.trigger.session`` must stay DCC-agnostic (no Maya, no Qt).
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "python" / "tik"

QT = ("PySide2", "PySide6", "tik.vendor.Qt", "tik.shared.ui")

FORBIDDEN = {
    "core": ("maya", "tik.maya", "tik.trigger", "tik.shared") + QT,
    "maya": ("tik.trigger", "tik.shared") + QT,
    "trigger/core": ("maya", "tik.maya") + QT,
    "trigger/session": ("maya", "tik.maya") + QT,
}


def _imports(py_file: Path):
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module


def _violations(package: str, forbidden):
    found = []
    for py_file in (SRC / package).rglob("*.py"):
        for name in _imports(py_file):
            if any(name == bad or name.startswith(bad + ".") for bad in forbidden):
                found.append(f"{py_file.relative_to(SRC)} imports {name}")
    return found


# Packages still carrying DCC imports; the trigger core rebuild (Plan B) removes
# them. strict=True makes the test fail loudly once they are clean so the mark
# gets removed.
_KNOWN_DEBT = {"trigger/core", "trigger/session"}


@pytest.mark.parametrize(
    "package,forbidden",
    [
        pytest.param(
            package,
            forbidden,
            marks=pytest.mark.xfail(strict=True, reason="cleaned in Plan B")
            if package in _KNOWN_DEBT
            else (),
        )
        for package, forbidden in FORBIDDEN.items()
    ],
)
def test_no_forbidden_imports(package, forbidden):
    if not (SRC / package).exists():
        pytest.skip(f"{package} not present")
    assert _violations(package, forbidden) == []

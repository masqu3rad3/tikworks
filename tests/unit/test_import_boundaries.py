"""Layering rules for tikworks packages.

tik.core < tik.maya < tik.trigger. ``tik.trigger.core`` must stay pure
Python (no Maya, no Qt); everything else in tik.trigger may use tik.maya.
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
    # ``tik.trigger.config`` builds a settings singleton at import time that
    # writes a file into the process's working directory. Importing it at
    # module level in the UI made ``tik.trigger.ui.show()`` fail under Maya
    # with a permission error; the UI reads settings lazily instead.
    "trigger/ui": ("tik.trigger.config",),
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


@pytest.mark.parametrize("package,forbidden", FORBIDDEN.items())
def test_no_forbidden_imports(package, forbidden):
    if not (SRC / package).exists():
        pytest.skip(f"{package} not present")
    assert _violations(package, forbidden) == []

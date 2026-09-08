"""Layering rules for tikworks packages.

tik.core < tik.maya < tik.trigger. ``tik.trigger.core`` must stay pure
Python (no Maya, no Qt); everything else in tik.trigger may use tik.maya.
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "python" / "tik"

QT = ("PySide2", "PySide6", "tik.vendor.Qt", "tik.shared.ui")

#: A user preference must never be able to change a rig. The build path is
#: therefore forbidden from importing the preferences packages at all, which
#: is a stronger and cheaper guarantee than reviewing every read site.
#: Only ``tik/trigger/ui`` may read preferences.
PREFS = ("tik.trigger.config", "tik.shared.prefs")

#: The VCS package integrates from outside the repository, so nothing on the
#: build path -- core, modules, systems, maya, guides, anim -- may reach it.
#: Only the UI and the publish actions do.
VCS = ("tik.trigger.vcs",)

FORBIDDEN = {
    "core": ("maya", "tik.maya", "tik.trigger", "tik.shared") + QT,
    "maya": ("tik.trigger", "tik.shared") + QT,
    # ``tik.trigger.actions`` too: core/guide_reference.py writes its own
    # cycle check rather than reusing the reference action's, because an
    # action package sits above core and importing one would invert the layer.
    "trigger/core": ("maya", "tik.maya", "tik.trigger.actions") + QT + PREFS + VCS,
    "trigger/modules": PREFS + VCS,
    "trigger/systems": PREFS + VCS,
    "trigger/maya": PREFS + VCS,
    "trigger/actions": PREFS,
    "trigger/guides": PREFS + VCS,
    #: An animator tool reads the rig, never the session. Everything a switch
    #: needs is already on the built nodes -- the pivotPreset enum, the trg_*
    #: tags -- so this costs nothing, and it keeps the rigger's application and
    #: the animator's tools from entangling whatever either grows into.
    "trigger/anim": (
        "tik.trigger.session",
        "tik.trigger.core.document",
        "tik.trigger.core.guide_document",
        "tik.trigger.guides",
        "tik.trigger.ui",
    )
    + PREFS
    + VCS,
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


def test_only_the_publish_action_package_may_import_vcs():
    """Build actions never see the VCS; the publish base does not either."""
    offenders = []
    for py_file in (SRC / "trigger" / "actions").rglob("*.py"):
        if py_file.parent.name == "publish":
            continue
        for name in _imports(py_file):
            if name == "tik.trigger.vcs" or name.startswith("tik.trigger.vcs."):
                offenders.append(str(py_file.relative_to(SRC)))
    assert offenders == []


def test_vcs_never_reads_preferences_and_nothing_imports_tik_manager4():
    assert _violations("trigger/vcs", PREFS) == []
    assert _violations("", ("tik_manager4",)) == []

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


def _imports_vcs(py_file: Path) -> bool:
    return any(
        name == "tik.trigger.vcs" or name.startswith("tik.trigger.vcs.")
        for name in _imports(py_file)
    )


def test_only_the_publish_action_package_may_import_vcs():
    """Build actions never see the VCS; the publish base does not either.

    The ``publish`` folder is exempt as a package so a subclass shipped as a
    plugin can talk to a provider -- but the base and the generic action in
    ``publish.py`` publish to a plain folder, and must stay VCS-free.
    """
    offenders = []
    for py_file in (SRC / "trigger" / "actions").rglob("*.py"):
        if py_file.parent.name == "publish":
            continue
        if _imports_vcs(py_file):
            offenders.append(str(py_file.relative_to(SRC)))
    assert offenders == []
    base = SRC / "trigger" / "actions" / "publish" / "publish.py"
    assert base.exists()
    assert not _imports_vcs(base)


def test_vcs_never_reads_preferences_and_nothing_imports_tik_manager4():
    assert _violations("trigger/vcs", PREFS) == []
    assert _violations("", ("tik_manager4",)) == []


#: Grouping never changes the rig. The build path is therefore forbidden from
#: naming the group object or touching the document's group list at all --
#: a stronger and cheaper guarantee than reviewing every read site, and the
#: same trick the preferences rule above uses.
#:
#: ``trigger/guides`` is deliberately absent: the guide layer is not the build
#: path. It owns the document's rendering and the ``.trg``, which is exactly
#: where the group operations and the ``.trg`` section have to live. What must
#: stay blind is the code that turns guides into a rig.
GROUP_BLIND = ("trigger/maya", "trigger/modules", "trigger/systems")


def _group_reads(py_file: Path):
    """Names and attributes that would let this file see a module group.

    ``.module_groups`` rather than ``.groups`` on purpose: ``rig.groups`` is
    the four per-module rig groups and is all over the build path, so a bare
    ``groups`` could not be told apart from it. The distinct name is what
    makes this check possible at all.
    """
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "module_groups":
            yield f"line {node.lineno}: reads .module_groups"
        elif isinstance(node, ast.Name) and node.id == "ModuleGroup":
            yield f"line {node.lineno}: names ModuleGroup"
        elif isinstance(node, ast.Attribute) and node.attr in (
            "module_group",
            "group_of",
        ):
            yield f"line {node.lineno}: calls .{node.attr}()"


@pytest.mark.parametrize("package", GROUP_BLIND)
def test_the_build_path_cannot_see_module_groups(package):
    found = [
        f"{py_file.relative_to(SRC)} {problem}"
        for py_file in (SRC / package).rglob("*.py")
        for problem in _group_reads(py_file)
    ]
    assert found == []


def test_the_group_guard_would_catch_a_violation(tmp_path):
    """The guard is only worth having if it fails on the thing it forbids."""
    offender = tmp_path / "offender.py"
    offender.write_text("def build(doc):\n    return doc.module_groups\n")
    assert list(_group_reads(offender)) == ["line 2: reads .module_groups"]

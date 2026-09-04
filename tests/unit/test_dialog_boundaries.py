"""One dialog surface for the whole repo.

``shared/ui/feedback.py`` is where a tikworks tool asks the user something.
A raw ``QMessageBox`` anywhere else is how twelve dialogs ended up with
twelve different ideas about parenting, wording and cancellation -- and how
a headless test run ends up hanging on a modal nobody can click.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "python" / "tik"

DIALOGS = {"QMessageBox", "QFileDialog", "QInputDialog", "QErrorMessage"}

#: The surface itself, and vendored Qt.py which is not ours to police.
ALLOWED = {Path("shared/ui/feedback.py"), Path("vendor")}


def _is_allowed(py_file: Path) -> bool:
    relative = py_file.relative_to(SRC)
    return any(
        relative == allowed or allowed in relative.parents for allowed in ALLOWED
    )


def _dialog_names(py_file: Path):
    """Every ``QMessageBox``-style name the file actually references.

    Parsed rather than grepped so a mention in a docstring or a comment --
    like the one at the top of this file -- is not a violation.
    """
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in DIALOGS:
            yield node.attr
        elif isinstance(node, ast.Name) and node.id in DIALOGS:
            yield node.id


def test_dialogs_only_come_from_the_shared_feedback_module():
    violations = [
        f"{py_file.relative_to(SRC)} uses {name}"
        for py_file in SRC.rglob("*.py")
        if not _is_allowed(py_file)
        for name in sorted(set(_dialog_names(py_file)))
    ]
    assert violations == []

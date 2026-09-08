"""The integrator's guide compiles, and quotes the shipped FolderProvider verbatim."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "trigger" / "integrating-version-control.md"
FOLDER = ROOT / "src" / "python" / "tik" / "trigger" / "vcs" / "folder.py"


def _blocks():
    text = GUIDE.read_text(encoding="utf-8")
    return re.findall(r"```python\n(.*?)```", text, flags=re.S)


def test_the_guide_exists_and_covers_every_section():
    text = GUIDE.read_text(encoding="utf-8")
    for heading in (
        "## 1. What Trigger asks of a version control system",
        "## 2. Getting your code loaded",
        "## 3. The provider contract",
        "## 4. Kinds",
        "## 5. Writing a publish action",
        "## 6. Making an action publishable",
        "## 7. A complete minimal provider",
        "## 8. The tik_manager4 integration",
    ):
        assert heading in text, heading


def test_every_python_block_compiles():
    blocks = _blocks()
    assert len(blocks) >= 6
    for index, block in enumerate(blocks):
        compile(block, f"<guide block {index}>", "exec")


def test_the_folder_provider_is_quoted_verbatim():
    shipped = FOLDER.read_text(encoding="utf-8").strip()
    assert any(block.strip() == shipped for block in _blocks())

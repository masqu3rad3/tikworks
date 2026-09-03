"""The generated .mod files declare where Maya may load plug-ins from.

Maya trusts a plug-in resolved out of MAYA_PLUG_IN_PATH; anything loaded by
absolute path from elsewhere makes it ask the user for approval. The module
file is what puts our plug-in area on that path, for dev and release alike.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_DIR = REPO_ROOT / "package"


@pytest.fixture(scope="module")
def package():
    """Import package/package.py, which is a script rather than a module."""
    sys.path.insert(0, str(PACKAGE_DIR))
    try:
        spec = importlib.util.spec_from_file_location(
            "tikworks_package", PACKAGE_DIR / "package.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.path.remove(str(PACKAGE_DIR))


class TestDevMod:
    def test_declares_the_plugin_area(self, package):
        content = "".join(package._generate_dev_mod(["2026"]))
        assert "MAYA_PLUG_IN_PATH +:= src/plugins/python" in content

    def test_declares_the_plugin_area_once_per_block(self, package):
        blocks = "".join(package._generate_dev_mod(["2025", "2026"])).count("+ MAYAVERSION")
        plugin_lines = "".join(package._generate_dev_mod(["2025", "2026"])).count(
            "MAYA_PLUG_IN_PATH +:= src/plugins/python"
        )
        assert plugin_lines == blocks

    def test_still_declares_the_python_path(self, package):
        content = "".join(package._generate_dev_mod(["2026"]))
        assert "PYTHONPATH +:= src/python" in content


class TestReleaseMod:
    def test_declares_the_plugin_area(self, package):
        content = "".join(package._generate_release_mod())
        assert "MAYA_PLUG_IN_PATH +:= plugins/python" in content

    def test_declares_the_plugin_area_once_per_block(self, package):
        content = "".join(package._generate_release_mod())
        assert content.count("MAYA_PLUG_IN_PATH +:= plugins/python") == content.count(
            "+ MAYAVERSION"
        )


class TestDevDropInstaller:
    """The drag & drop dev installer writes its own .mod."""

    def test_declares_the_plugin_area(self):
        source = (REPO_ROOT / "src" / "dev_drop_setup.py").read_text(encoding="utf-8")
        assert "MAYA_PLUG_IN_PATH +:= src/plugins/python" in source

    def test_points_python_path_at_the_package_root(self):
        source = (REPO_ROOT / "src" / "dev_drop_setup.py").read_text(encoding="utf-8")
        assert "PYTHONPATH +:= src/python" in source

"""Package management for tikworks."""

import platform
import argparse
import sys
import os
import shutil
import subprocess
import time
from pathlib import Path

import inject_utils

LOG = sys.stdout.write

PACKAGE_ROOT = Path(__file__).parent
REPO_ROOT = PACKAGE_ROOT.parent

DEFINITIONS_FILE = PACKAGE_ROOT / "definitions.json"

BLUEPRINT_PATH = REPO_ROOT / "_blueprint" / "plugin_template"

VERSION_FILE = REPO_ROOT / "VERSION"
ROOT_CMAKELISTS = REPO_ROOT / "CMakeLists.txt"

OS = platform.system().lower()

VERSION = ""
with open(VERSION_FILE.as_posix(), "r") as version_file:
    VERSION = version_file.read().strip()

DEFINITIONS = {}
if DEFINITIONS_FILE.exists():
    import json
    DEFINITIONS = json.load(open(DEFINITIONS_FILE))


def add_plugin_to_cmakelists(plugin_name: str):
    """Add a subdirectory to the root CMakeLists.txt."""
    inject_utils.add_plugin(plugin_name, ROOT_CMAKELISTS, BLUEPRINT_PATH, REPO_ROOT / "src")


def _download_devkit_linux(download_link, devkit_path):
    """Download the devkit for Linux."""
    try:
        subprocess.check_call(["curl", "-L", download_link, "-o", f"{devkit_path / 'devkitBase.tar.gz'}"])
        LOG(f"Extracting devkit...\n")
        subprocess.check_call(["tar", "-xzf", f"{devkit_path / 'devkitBase.tar.gz'}", "-C", devkit_path])
        (devkit_path / "devkitBase.tar.gz").unlink()
        LOG(f"Devkit downloaded and extracted successfully.\n")
    except subprocess.CalledProcessError as e:
        LOG(f"Failed to download or extract devkit. Error: {e}\n")


def _download_devkit_mac(download_link, devkit_path):
    """Download the devkit for Mac."""
    try:
        subprocess.check_call(["curl", "-L", download_link, "-o", f"{devkit_path / 'devkitBase.zip'}"])
        LOG(f"Extracting devkit...\n")
        subprocess.check_call(["unzip", f"{(devkit_path / 'devkitBase.zip').resolve()}", "-d", devkit_path])
        (devkit_path / "devkitBase.zip").unlink()
        LOG(f"Devkit downloaded and extracted successfully.\n")
    except subprocess.CalledProcessError as e:
        LOG(f"Failed to download or extract devkit. Error: {e}\n")


def _download_devkit_win(download_link, devkit_path):
    """Download the devkit for Windows."""
    try:
        subprocess.check_call(["curl", "-L", download_link, "-o", f"{devkit_path / 'devkitBase.zip'}"])
        LOG(f"Extracting devkit...\n")
        subprocess.check_call([
            "powershell", "-Command",
            f"Expand-Archive -LiteralPath '{(devkit_path / 'devkitBase.zip').resolve()}' -DestinationPath '{devkit_path.resolve()}' -Force"
        ])
        (devkit_path / "devkitBase.zip").unlink()
        LOG(f"Devkit downloaded and extracted successfully.\n")
    except subprocess.CalledProcessError as e:
        LOG(f"Failed to download or extract devkit. Error: {e}\n")


def validate_local_devkits(maya_version=None):
    """Validate the local devkits."""
    if not DEFINITIONS.get("target_maya_versions"):
        LOG("No target Maya versions defined. Skipping devkit validation.\n")
        return

    target_maya_versions = [maya_version] if maya_version else DEFINITIONS["target_maya_versions"]
    local_devkits = REPO_ROOT / DEFINITIONS.get("local_devkits_relative_path", "../maya_devkit")
    local_devkits.mkdir(parents=True, exist_ok=True)

    for version in target_maya_versions:
        devkit_path = local_devkits / version
        if not (devkit_path / "devkitBase").exists():
            LOG(f"Devkit for Maya {version} not found at {devkit_path}. Attempting to download.\n")
            devkit_path.mkdir(parents=True, exist_ok=True)
            download_link = DEFINITIONS.get(f"{OS}_devkits", {}).get(version)
            if download_link:
                LOG(f"Downloading devkit for Maya {version}...\n")
                if OS == "linux":
                    _download_devkit_linux(download_link, devkit_path)
                elif OS == "darwin":
                    _download_devkit_mac(download_link, devkit_path)
                elif OS == "windows":
                    _download_devkit_win(download_link, devkit_path)
        else:
            LOG(f"Devkit for Maya {version} found at {devkit_path.resolve()}.\n")


def build_plugins(maya_version, build_type="Debug", continue_on_error=False):
    """Build the C++ plugins using CMake."""
    build_dir = REPO_ROOT / "build"
    if build_dir.exists():
        shutil.rmtree(build_dir.as_posix())

    devkit_root = DEFINITIONS.get("local_devkits_relative_path", "../maya_devkit")
    devkit_path = REPO_ROOT / devkit_root / maya_version / "devkitBase"

    try:
        cmake_args = [
            "-S", str(REPO_ROOT),
            "-B", str(build_dir),
            f"-DCMAKE_BUILD_TYPE={build_type}",
            f"-DMAYA_VERSION={maya_version}",
        ]
        if devkit_path.exists():
            cmake_args.append(f"-DMAYA_DEVKIT_ROOT={devkit_path}")

        subprocess.check_call(["cmake"] + cmake_args)
        subprocess.check_call(["cmake", "--build", str(build_dir), "--config", build_type])
        LOG("Plugins built successfully.\n")
        return build_dir
    except subprocess.CalledProcessError as e:
        if continue_on_error:
            LOG(f"Failed to build plugins. Error: {e}\n")
        else:
            raise RuntimeError(f"Failed to build plugins. Error: {e}") from e


def dev_deploy(version=None):
    """Deploy the plugin(s) for Maya version(s) for development."""
    extensions = {
        "windows": ".mll",
        "linux": ".so",
        "darwin": ".bundle"
    }

    # Determine which versions to deploy
    target_versions = DEFINITIONS.get("target_maya_versions", ["2024", "2025", "2026"])
    deploy_versions = [version] if version else target_versions

    # If there are C++ plugins, build them
    src_plugins_cpp = REPO_ROOT / "src" / "plugins" / "cpp"
    has_cpp_plugins = src_plugins_cpp.exists() and any(src_plugins_cpp.iterdir())

    deploy_root_path = REPO_ROOT / "_dev_deploy"
    plugins_path = deploy_root_path / "plugins"
    plugins_path.mkdir(parents=True, exist_ok=True)

    if has_cpp_plugins:
        # Only validate devkits if there are C++ plugins to build
        validate_local_devkits(version)
        for maya_version in deploy_versions:
            LOG(f"Building C++ plugins for Maya {maya_version}...\n")
            build_dir = build_plugins(maya_version, build_type="Release")
            plugin_path = plugins_path / f"{OS}-{maya_version}"
            plugin_path.mkdir(exist_ok=True)
            collected_plugins = build_dir.rglob(f"*{extensions[OS]}")
            for item in collected_plugins:
                shutil.copy(item, plugin_path / item.name)
                LOG(f"Copied {item.name} to deploy folder.\n")
            time.sleep(0.5)  # Small delay between builds to avoid file locks
    else:
        LOG("No C++ plugins found. Skipping plugin build.\n")

    # Copy Python plugins if they exist
    src_python_plugins_path = REPO_ROOT / "src" / "plugins" / "python"
    if src_python_plugins_path.exists():
        dev_python_plugins_path = deploy_root_path / "plugins" / "python"
        if dev_python_plugins_path.exists():
            shutil.rmtree(dev_python_plugins_path.as_posix())
        shutil.copytree(src_python_plugins_path, dev_python_plugins_path)
        LOG(f"Copied python plugins to dev deploy folder.\n")

    # Generate .mod file for development
    user_maya_folder = Path(_get_home_dir()) / "Documents" / "maya"
    if user_maya_folder.exists():
        modules_file_path = user_maya_folder / "modules" / f"{DEFINITIONS.get('project_slug', 'tikworks')}_dev.mod"
        modules_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(modules_file_path, "w") as mod_file:
            mod_file.writelines(_generate_dev_mod(deploy_versions))
        LOG(f"Generated dev .mod file at {modules_file_path.resolve()}.\n")


def release(version=None):
    """Make a deployable release package."""
    extensions = {
        "windows": ".mll",
        "linux": ".so",
        "darwin": ".bundle"
    }

    deploy_root_path = REPO_ROOT / "release"
    modules_path = deploy_root_path / "modules"
    deploy_path = modules_path / DEFINITIONS.get("project_slug", "tikworks")
    plugins_path = deploy_path / "plugins"
    plugins_path.mkdir(parents=True, exist_ok=True)

    # If there are C++ plugins, build them for all target versions
    src_plugins_cpp = REPO_ROOT / "src" / "plugins" / "cpp"
    has_cpp_plugins = src_plugins_cpp.exists() and any(src_plugins_cpp.iterdir())
    target_versions = [version] if version else DEFINITIONS.get("target_maya_versions", [])

    if has_cpp_plugins:
        validate_local_devkits()
        for maya_version in target_versions:
            build_dir = build_plugins(maya_version, build_type="Release")
            plugin_path = plugins_path / f"{OS}-{maya_version}"
            plugin_path.mkdir(exist_ok=True)
            collected_plugins = build_dir.rglob(f"*{extensions[OS]}")
            for item in collected_plugins:
                shutil.copy(item, plugin_path / item.name)
                LOG(f"Copied {item.name} to release folder.\n")

    # Copy Python tools/API if they exist
    src_tik_path = REPO_ROOT / "src" / "python" / "tik"
    if src_tik_path.exists():
        release_tik_path = deploy_path / "tik"
        if release_tik_path.exists():
            shutil.rmtree(release_tik_path.as_posix())
        shutil.copytree(src_tik_path, release_tik_path)
        LOG(f"Copied tik package to release folder.\n")

    # Copy Python plugins if they exist
    src_python_plugins_path = REPO_ROOT / "src" / "plugins" / "python"
    if src_python_plugins_path.exists():
        release_python_plugins_path = deploy_path / "plugins" / "python"
        if release_python_plugins_path.exists():
            shutil.rmtree(release_python_plugins_path.as_posix())
        shutil.copytree(src_python_plugins_path, release_python_plugins_path)
        LOG(f"Copied python plugins to release folder.\n")

    # Generate .mod file
    mod_file_path = modules_path / f"{DEFINITIONS.get('project_slug', 'tikworks')}.mod"
    with open(mod_file_path, "w") as mod_file:
        mod_file.writelines(_generate_release_mod())
    LOG(f"Generated .mod file at {mod_file_path.resolve()}.\n")

    # Save drag and drop installer
    _save_drag_and_drop_me_script(deploy_root_path / "dragAndDropMe.py")

    LOG(f"Release package created at {deploy_root_path.resolve()}.\n")


def generate_release_mod_file(dest_dir: Path):
    """Write the release .mod file to dest_dir/<project_slug>.mod."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    mod_file_path = dest_dir / f"{DEFINITIONS.get('project_slug', 'tikworks')}.mod"
    with open(mod_file_path, "w") as mod_file:
        mod_file.writelines(_generate_release_mod())
    LOG(f"Generated .mod file at {mod_file_path.resolve()}.\n")


def _generate_release_mod():
    """Generate the content for the release .mod file."""
    project_slug = DEFINITIONS.get("project_slug", "tikworks")
    target_versions = DEFINITIONS.get("target_maya_versions", ["2024", "2025", "2026"])

    for _platform, _scode in {"windows": "win64", "linux": "linux", "darwin": "mac"}.items():
        for maya_version in target_versions:
            yield f"+ MAYAVERSION:{maya_version} PLATFORM:{_scode} {project_slug} {VERSION} {project_slug}\n"
            yield f"MAYA_PLUG_IN_PATH +:= plugins\\{_platform}-{maya_version}\n"
            yield f"PYTHONPATH +:= tik\n"
            yield "\n"


def _generate_dev_mod(versions):
    """Generate the content for the development .mod file.

    Args:
        versions: A single version string, a list of version strings, or None (uses all targets).
    """
    project_slug = DEFINITIONS.get("project_slug", "tikworks")
    target_versions = DEFINITIONS.get("target_maya_versions", ["2024", "2025", "2026"])

    if versions is None:
        deploy_versions = target_versions
    elif isinstance(versions, str):
        deploy_versions = [versions]
    else:
        deploy_versions = versions

    for _platform, _scode in {"windows": "win64", "linux": "linux", "darwin": "mac"}.items():
        for maya_version in deploy_versions:
            yield f"+ MAYAVERSION:{maya_version} PLATFORM:{_scode} {project_slug} {VERSION} {REPO_ROOT.as_posix()}\n"
            yield f"MAYA_PLUG_IN_PATH +:= _dev_deploy/plugins/{_platform}-{maya_version}\n"
            yield f"PYTHONPATH +:= src/python\n"
            yield "\n"


def _save_drag_and_drop_me_script(path_to_save):
    """Generate the drag and drop script for easy installation."""
    project_name = DEFINITIONS.get("project_name", "tikworks")
    content = f'''"""Drag & Drop installer for {project_name}."""
from pathlib import Path
import platform
import sys
import shutil

# confirm the maya python interpreter
CONFIRMED = False
try:
    from maya import cmds
    CONFIRMED = True
except ImportError:
    CONFIRMED = False


def onMayaDroppedPythonFile(*args, **kwargs):
    if sys.version_info.major < 3:
        cmds.confirmDialog(
            title='ERROR:',
            message="{project_name} requires Python version 3 and higher. Current Maya Python interpreter is not compatible. \\n\\nAborting.",
            button=['OK'],
            defaultButton='OK'
        )
        return
    _add_module()


def _add_module():
    source_modules = Path(__file__).parent / "modules"
    user_maya_dir = Path(cmds.internalVar(uad=True))
    destination_modules = user_maya_dir / "modules"
    destination_modules.mkdir(parents=True, exist_ok=True)

    for item in source_modules.iterdir():
        destination_item = destination_modules / item.name
        if item.is_dir():
            for sub_item in item.rglob("*"):
                relative_path = sub_item.relative_to(item)
                target_path = destination_item / relative_path
                if sub_item.is_dir():
                    target_path.mkdir(parents=True, exist_ok=True)
                else:
                    shutil.copy2(sub_item, target_path)
        else:
            shutil.copy2(item, destination_item)

    cmds.confirmDialog(
        title="{project_name}",
        message="{project_name} installed. Please restart Maya to load the tools."
    )
'''
    with open(path_to_save, "w") as f:
        f.write(content)
    LOG(f"Generated drag and drop installer script at {path_to_save.resolve()}.\n")


def _get_home_dir():
    """Get the user home directory."""
    if OS == "windows":
        return os.path.normpath(os.getenv("USERPROFILE"))
    return os.path.normpath(os.getenv("HOME"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Package management script for tikworks.")
    parser.add_argument("--add-plugin", type=str, help="Add a new C++ plugin to CMakeLists.txt")
    parser.add_argument("--validate-local-devkits", action="store_true",
                        help="Validate local devkits. Downloads from definitions.json if missing.")
    parser.add_argument("--build", type=str, help="Build plugins for given Maya version.")
    parser.add_argument("--dev", nargs="?", const=None, type=str, default=argparse.SUPPRESS,
                        help="Build and dev-deploy for given Maya version.")
    parser.add_argument("--release", action="store_true", help="Create release package.")
    parser.add_argument("--generate-release-mod", type=str, metavar="DEST_DIR",
                        help="Generate .mod file into the given directory.")

    args = parser.parse_args()

    if args.add_plugin:
        add_plugin_to_cmakelists(args.add_plugin)

    if args.validate_local_devkits:
        validate_local_devkits()

    if args.build:
        build_plugins(args.build)

    if args.release:
        release()

    if args.generate_release_mod:
        generate_release_mod_file(Path(args.generate_release_mod))

    if hasattr(args, "dev"):
        dev_deploy(args.dev)

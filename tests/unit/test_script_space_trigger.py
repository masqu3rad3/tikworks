"""ScriptSpace: the per-run module namespace script actions share."""

import sys
from pathlib import Path

import pytest

from tik.trigger.maya.scripts import ScriptError, ScriptSpace

_OURS = ("gen_rig", "cfx_utils", "hero", "trigger_build", "keep_me")


@pytest.fixture(autouse=True)
def _clean_modules():
    before_path = list(sys.path)
    yield
    for name in list(sys.modules):
        if name.startswith(_OURS):
            sys.modules.pop(name, None)
    sys.path[:] = before_path


def _write(folder: Path, name: str, body: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(body, encoding="utf-8")
    return path


def test_enter_registers_the_build_module_and_exit_drops_it():
    with ScriptSpace() as space:
        assert sys.modules["trigger_build"] is space.module
    assert "trigger_build" not in sys.modules


def test_load_registers_an_alias_and_files_can_import_each_other(tmp_path):
    scripts = tmp_path / "scripts"
    gen = _write(
        scripts, "general_rig_utils_v001.py", "def hello():\n    return 'gen'\n"
    )
    cfx = _write(
        scripts,
        "cfx_utils_v001.py",
        "import gen_rig\n\ndef hello():\n    return 'cfx+' + gen_rig.hello()\n",
    )
    with ScriptSpace() as space:
        space.add_path(scripts)
        space.load(gen, "gen_rig")
        space.load(cfx, "cfx_utils")
        assert sys.modules["gen_rig"].__name__ == "gen_rig"
        assert sys.modules["cfx_utils"].hello() == "cfx+gen"
        namespace = space.globals(ctx="CTX")
        assert namespace["cfx_utils"] is sys.modules["cfx_utils"]
        assert namespace["ctx"] == "CTX"
        assert namespace["__name__"] == "trigger_build"
        assert str(scripts) in sys.path
    assert "gen_rig" not in sys.modules and "cfx_utils" not in sys.modules
    assert str(scripts) not in sys.path


def test_a_failing_file_is_unregistered(tmp_path):
    bad = _write(tmp_path, "hero_v001.py", "raise RuntimeError('boom')\n")
    with ScriptSpace() as space:
        with pytest.raises(RuntimeError):
            space.load(bad, "hero")
        assert "hero" not in sys.modules
        assert "hero" not in space.aliases


def test_kept_aliases_survive_and_the_next_run_replaces_them(tmp_path):
    first = _write(tmp_path / "a", "keep_me_v001.py", "VALUE = 1\n")
    second = _write(tmp_path / "b", "keep_me_v002.py", "VALUE = 2\n")
    with ScriptSpace() as space:
        space.add_path(first.parent)
        space.load(first, "keep_me")
        space.keep("keep_me")
    assert sys.modules["keep_me"].VALUE == 1
    assert sys.modules["trigger_build"].keep_me.VALUE == 1
    assert sys.modules["trigger_build"].ctx is None
    assert str(first.parent) in sys.path
    with ScriptSpace() as space:
        assert "keep_me" not in sys.modules  # torn down on enter
        assert str(first.parent) not in sys.path
        space.load(second, "keep_me")
    # not kept this time: gone after the run
    assert "keep_me" not in sys.modules
    assert "trigger_build" not in sys.modules


def test_reserved_names_are_refused():
    with ScriptSpace() as space:
        assert space.is_reserved("sys")
        assert not space.is_reserved("gen_rig")
        with pytest.raises(ScriptError):
            space.load(Path("whatever.py"), "sys")


def test_import_error_hint_names_the_missing_alias(tmp_path):
    scripts = tmp_path / "scripts"
    cfx = _write(scripts, "cfx_utils_v001.py", "import gen_rig\n")
    with ScriptSpace() as space:
        space.add_path(scripts)
        with pytest.raises(ImportError) as info:
            space.load(cfx, "cfx_utils")
        hint = space.hint_for(info.value)
        assert "gen_rig is not loaded yet" in hint
        # a name that does exist on disk gets no hint: it is a real import error
        _write(scripts, "gen_rig_v001.py", "import nothing_here\n")
        with pytest.raises(ImportError) as info:
            space.load(cfx, "cfx_utils")
        assert space.hint_for(info.value) == ""


def test_create_script_file_writes_a_versioned_stub(tmp_path):
    from tik.trigger.actions.script.script import create_script_file

    first = create_script_file(tmp_path, "claw setup")
    assert first == tmp_path / "scripts" / "claw_setup_v001.py"
    text = first.read_text(encoding="utf-8")
    assert "claw_setup" in text and "def build(ctx)" in text
    assert "$" not in text
    second = create_script_file(tmp_path, "claw_setup")
    assert second.name == "claw_setup_v002.py"
    with pytest.raises(ValueError):
        create_script_file(tmp_path, "9lives")


def test_editor_command_reads_settings_lazily_and_tolerates_failure(monkeypatch):
    import types

    from tik.trigger.actions.script.script import editor_command

    # the settings store can be unreadable or unwritable (Maya's cwd): the
    # editor falls back to the OS default rather than breaking the tool
    monkeypatch.setitem(sys.modules, "tik.trigger.config", None)
    assert editor_command() == ""
    fake = types.ModuleType("tik.trigger.config")
    fake.trigger_settings = types.SimpleNamespace(
        get=lambda key, default=None: "code --goto {path}"
    )
    monkeypatch.setitem(sys.modules, "tik.trigger.config", fake)
    assert editor_command() == "code --goto {path}"


def test_open_external_uses_the_configured_command(monkeypatch, tmp_path):
    from tik.shared import io

    launched = []
    monkeypatch.setattr(
        io.subprocess, "Popen", lambda args, **kw: launched.append(args)
    )
    target = tmp_path / "a.py"
    target.write_text("", encoding="utf-8")
    io.open_external(target, command="code --goto {path}")
    assert launched == [["code", "--goto", str(target)]]
    io.open_external(target, command="subl")
    assert launched[-1] == ["subl", str(target)]

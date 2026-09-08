"""External plugins: a folder on TRIGGER_PLUGIN_PATH registers like a built-in."""

from __future__ import annotations

import sys
import textwrap

import pytest

from tik.trigger.core import discovery, registry

ACTION = """
from tik.trigger.core import Action, StringField, register_action


@register_action("{name}", category="utility")
class Plugin(Action):
    label = "External"
    note = StringField("")

    def run(self, ctx):
        return None
"""


@pytest.fixture(autouse=True)
def _sandbox(monkeypatch):
    actions = dict(registry._ACTIONS)
    modules = list(sys.modules)
    discovery.clear_plugin_paths()
    monkeypatch.delenv(discovery.PLUGIN_PATH_VAR, raising=False)
    try:
        yield
    finally:
        registry._ACTIONS.clear()
        registry._ACTIONS.update(actions)
        for name in list(sys.modules):
            if name not in modules and name.startswith("ext_"):
                del sys.modules[name]
        discovery.clear_plugin_paths()


def _plugin(root, name, source=ACTION):
    folder = root / name
    folder.mkdir(parents=True)
    (folder / f"{name}.py").write_text(
        textwrap.dedent(source.format(name=name)), encoding="utf-8"
    )
    return folder


def test_env_var_paths_are_discovered(tmp_path, monkeypatch):
    _plugin(tmp_path, "ext_alpha")
    monkeypatch.setenv(discovery.PLUGIN_PATH_VAR, str(tmp_path))
    assert tmp_path in discovery.plugin_paths()
    imported = discovery.discover_external(discovery.plugin_paths())
    assert imported == ["ext_alpha.ext_alpha"]
    assert registry.is_action_registered("ext_alpha")


def test_add_plugin_path_is_deduplicated_and_skips_missing(tmp_path):
    discovery.add_plugin_path(tmp_path)
    discovery.add_plugin_path(str(tmp_path))
    discovery.add_plugin_path(tmp_path / "nope")
    assert discovery.plugin_paths() == [tmp_path]


def test_a_broken_plugin_does_not_stop_the_others(tmp_path):
    _plugin(tmp_path, "ext_bad", source="import nothing_of_the_sort\n")
    _plugin(tmp_path, "ext_good")
    discovery.add_plugin_path(tmp_path)
    imported = discovery.discover_external(discovery.plugin_paths())
    assert imported == ["ext_good.ext_good"]
    assert registry.is_action_registered("ext_good")


def test_load_plugins_walks_external_paths(tmp_path):
    import tik.trigger as trigger

    _plugin(tmp_path, "ext_loaded")
    trigger.add_plugin_path(tmp_path)
    trigger.load_plugins()
    assert registry.is_action_registered("ext_loaded")

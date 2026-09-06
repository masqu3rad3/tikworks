"""Folder-based plugin discovery: ``tik.trigger.core.discovery``.

``discover`` is what turns ``<package>/<name>/<name>.py`` folders into
registered modules and actions, and ``defaults.json`` beside one is the
documented way a studio re-points a module's field defaults without touching
its Python. Both were reached only indirectly through ``load_plugins()``
before, which meant the failure paths and the whole ``defaults.json``
mechanism went unexercised.
"""

from __future__ import annotations

import sys
import textwrap

import pytest

from tik.core.fields import FieldValidationError
from tik.trigger.core import registry
from tik.trigger.core.discovery import discover
from tik.trigger.core.exceptions import NotFoundError

MODULE_SOURCE = """
from tik.trigger.core import GuideLayout, FloatField, IntField, Module, register_module


@register_module("{type_name}")
class {class_name}(Module):
    label = "Discovered"
    sided = False
    guides = GuideLayout("root")
    outputs = ("root",)
    controls = ("root",)

    segments = IntField(2, min=1, max=9)
    length = FloatField(1.0)

    def draw_guides(self, guides):
        guides.joint("root", (0, 0, 0))

    def build(self, rig):
        rig.controller("root")
"""


@pytest.fixture(autouse=True)
def _registry_sandbox():
    """Give each test the live registries back exactly as it found them.

    ``@register_module`` refuses a name that is already taken, so without this
    a second test reusing a plugin name sees its import fail rather than its
    ``defaults.json`` applied.
    """
    modules = dict(registry._MODULES)
    actions = dict(registry._ACTIONS)
    try:
        yield
    finally:
        registry._MODULES.clear()
        registry._MODULES.update(modules)
        registry._ACTIONS.clear()
        registry._ACTIONS.update(actions)


@pytest.fixture
def plugin_root(tmp_path, monkeypatch):
    """An importable throwaway package that ``discover`` can be pointed at.

    Yields a ``make(folder, source=..., defaults=...)`` helper. The package is
    dropped from ``sys.path`` and ``sys.modules`` afterwards so one test's
    plugins cannot leak into the next.
    """
    package = tmp_path / "toyplugins"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))

    def make(folder: str, source: str | None = None, defaults: str | None = None):
        directory = package / folder
        directory.mkdir()
        (directory / "__init__.py").write_text("", encoding="utf-8")
        if source is not None:
            (directory / f"{folder}.py").write_text(
                textwrap.dedent(source), encoding="utf-8"
            )
        if defaults is not None:
            (directory / "defaults.json").write_text(defaults, encoding="utf-8")
        return directory

    try:
        yield make
    finally:
        for name in list(sys.modules):
            if name == "toyplugins" or name.startswith("toyplugins."):
                sys.modules.pop(name, None)


def _discover(make, folder, **kwargs):
    """Build one plugin folder and discover the package that holds it."""
    make(folder, **kwargs)
    return discover("toyplugins", [str(sys.modules["toyplugins"].__path__[0])])


@pytest.fixture(autouse=True)
def _import_package(plugin_root):
    """``discover`` walks a path, so the package has to be importable first."""
    import importlib

    importlib.import_module("toyplugins")


class TestWhatGetsImported:
    """Which folders ``discover`` picks up, and which it walks past."""

    def test_a_well_formed_folder_is_imported_and_registered(self, plugin_root):
        imported = _discover(
            plugin_root,
            "widget",
            source=MODULE_SOURCE.format(type_name="widget", class_name="Widget"),
        )

        assert imported == ["toyplugins.widget.widget"]
        assert registry.get_module("widget").label == "Discovered"

    def test_a_folder_without_its_named_file_is_skipped(self, plugin_root):
        """``foo/bar.py`` is not a plugin -- only ``foo/foo.py`` is."""
        assert _discover(plugin_root, "hollow") == []

    def test_an_underscored_folder_is_skipped(self, plugin_root):
        assert (
            _discover(
                plugin_root,
                "_private",
                source=MODULE_SOURCE.format(type_name="private", class_name="Private"),
            )
            == []
        )

    def test_a_loose_file_is_not_a_plugin(self, plugin_root, tmp_path):
        (tmp_path / "toyplugins" / "stray.py").write_text("", encoding="utf-8")

        assert _discover(plugin_root, "empty") == []

    def test_a_plugin_that_raises_on_import_does_not_stop_the_others(
        self, plugin_root, caplog
    ):
        """One bad plugin must not cost the rigger every other one."""
        plugin_root("broken", source="raise RuntimeError('boom')")
        imported = _discover(
            plugin_root,
            "healthy",
            source=MODULE_SOURCE.format(type_name="healthy", class_name="Healthy"),
        )

        assert imported == ["toyplugins.healthy.healthy"]
        assert "Failed to import toyplugins.broken.broken" in caplog.text
        assert "boom" in caplog.text

    def test_discovery_is_alphabetical(self, plugin_root):
        for name in ("charlie", "alpha", "bravo"):
            plugin_root(
                name,
                source=MODULE_SOURCE.format(
                    type_name=name, class_name=name.capitalize()
                ),
            )

        imported = discover("toyplugins", [str(sys.modules["toyplugins"].__path__[0])])

        assert imported == [
            "toyplugins.alpha.alpha",
            "toyplugins.bravo.bravo",
            "toyplugins.charlie.charlie",
        ]


class TestDefaultsJson:
    """``defaults.json`` overrides field *defaults*, and nothing else."""

    def _fields(self, plugin_root, defaults, type_name="tuned"):
        _discover(
            plugin_root,
            type_name,
            source=MODULE_SOURCE.format(
                type_name=type_name, class_name=type_name.capitalize()
            ),
            defaults=defaults,
        )
        return registry.get_module(type_name).fields()

    def test_a_declared_field_takes_the_new_default(self, plugin_root):
        fields = self._fields(plugin_root, '{"segments": 5}')

        assert fields["segments"].default == 5

    def test_an_untouched_field_keeps_its_python_default(self, plugin_root):
        fields = self._fields(plugin_root, '{"segments": 5}')

        assert fields["length"].default == 1.0

    def test_a_float_default_is_coerced_to_the_field_type(self, plugin_root):
        """``FloatField`` takes a JSON int and stores it as a float."""
        fields = self._fields(plugin_root, '{"length": 3}')

        assert fields["length"].default == 3.0
        assert isinstance(fields["length"].default, float)

    def test_a_wrongly_typed_value_is_rejected(self, plugin_root):
        """A default is validated, not merely stored -- a bad one is loud."""
        with pytest.raises(FieldValidationError, match="must be a number"):
            self._fields(plugin_root, '{"segments": "4"}')

    def test_a_value_outside_the_field_range_is_rejected(self, plugin_root):
        with pytest.raises(FieldValidationError, match="must be <= 9"):
            self._fields(plugin_root, '{"segments": 99}')

    def test_an_unknown_key_is_warned_about_and_ignored(self, plugin_root, caplog):
        fields = self._fields(plugin_root, '{"segments": 3, "nonesuch": 7}')

        assert fields["segments"].default == 3
        assert "unknown default 'nonesuch'" in caplog.text

    def test_malformed_json_is_reported_and_the_module_still_loads(
        self, plugin_root, caplog
    ):
        """A typo in defaults.json must not take the module down with it."""
        fields = self._fields(plugin_root, "{not json")

        assert fields["segments"].default == 2
        assert "Invalid defaults.json" in caplog.text

    def test_no_defaults_file_is_the_normal_case(self, plugin_root):
        _discover(
            plugin_root,
            "plain",
            source=MODULE_SOURCE.format(type_name="plain", class_name="Plain"),
        )

        assert registry.get_module("plain").fields()["segments"].default == 2


def test_rediscovery_re_registers_after_the_registries_are_cleared(plugin_root):
    """Import caching means the decorators do not run twice -- discover re-registers.

    This is the path ``clear_registries()`` followed by ``load_plugins()``
    takes, which is how the tool reloads plugins in a live Maya session.
    """
    path = [str(sys.modules["toyplugins"].__path__[0])]
    _discover(
        plugin_root,
        "recycled",
        source=MODULE_SOURCE.format(type_name="recycled", class_name="Recycled"),
    )
    registry.clear_registries()
    with pytest.raises(NotFoundError):
        registry.get_module("recycled")

    discover("toyplugins", path)

    assert registry.get_module("recycled").label == "Discovered"

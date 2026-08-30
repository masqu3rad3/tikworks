"""``GuideHandle``: one module instance, as the UI and TDs see it.

A handle is a view onto a ``ModuleInstance`` plus the scene that owns it.
It holds no Maya of its own — every write goes back through the scene — so
it works against any scene implementation.
"""

from __future__ import annotations

from typing import Optional

from tik.core.side import Side
from tik.trigger.core import registry
from tik.trigger.core.exceptions import GuideError
from tik.trigger.core.manifest import instance_key
from tik.trigger.core.schemas import ModuleInstance, ParentRef


def mirror_source(source: str, side: str, target_side: str) -> str:
    """``L_arm.hand`` -> ``R_arm.hand`` when mirroring; center/scene sources unchanged."""
    key, dot, output = source.rpartition(".")
    if dot and key.startswith(f"{side}_"):
        return f"{target_side}_{key[2:]}{dot}{output}"
    return source


class GuideHandle:
    """One module instance in the scene; settings are attributes."""

    def __init__(self, guides: "GuideScene", instance: ModuleInstance) -> None:
        object.__setattr__(self, "_guides", guides)
        object.__setattr__(self, "_instance", instance)

    def _refresh(self) -> ModuleInstance:
        found = self._guides._snapshot().get(self._instance.instance_id)
        if found is None:
            raise GuideError(f"Guides for '{self._instance.name}' no longer exist.")
        object.__setattr__(self, "_instance", found)
        return found

    def _touch(self) -> ModuleInstance:
        """After a write: drop the cache and re-read this instance."""
        self._guides.invalidate()
        return self._refresh()

    @property
    def instance(self) -> ModuleInstance:
        return self._refresh()

    @property
    def instance_id(self) -> str:
        return self._instance.instance_id

    @property
    def name(self) -> str:
        return self._instance.name

    @name.setter
    def name(self, value: str) -> None:
        value = (value or "").strip()
        if not value:
            raise GuideError("A module needs a name.")
        key = instance_key(value, self.side.value)
        taken = self._guides.by_key(key)
        if taken is not None and taken.instance_id != self.instance_id:
            raise GuideError(f"A module named '{key}' already exists.")
        if key in self._guides.layout.get("scene_nodes", {}):
            raise GuideError(f"'{key}' is already a scene-nodes group.")
        old_key = self.key
        self._guides.rename_instance(self.instance_id, value)
        self._touch()
        self._guides._rename_key(old_key, self.key)

    @property
    def module_type(self) -> str:
        return self._instance.module_type

    @property
    def side(self) -> Side:
        return Side.from_value(self._instance.side)

    @property
    def module_class(self) -> type:
        return registry.get_module(self._instance.module_type)

    @property
    def root(self):
        return self._guides.guide_node(self.instance_id, self.module_class.guides.root)

    @property
    def parent(self) -> Optional["GuideHandle"]:
        instance = self._refresh()
        if instance.parent is None:
            return None
        return self._guides.get(instance.parent.instance_id)

    @property
    def settings(self) -> dict:
        module = self.module_class(settings=self._refresh().settings)
        return module.values()

    def __getattr__(self, item: str) -> Any:
        if item.startswith("_"):
            raise AttributeError(item)
        fields = self.module_class.fields()
        if item not in fields:
            raise AttributeError(f"'{self._instance.module_type}' has no property '{item}'.")
        return self.settings[item]

    def __setattr__(self, item: str, value: Any) -> None:
        if isinstance(getattr(type(self), item, None), property):
            object.__setattr__(self, item, value)
            return
        fields = self.module_class.fields()
        if item not in fields:
            raise AttributeError(f"'{self._instance.module_type}' has no property '{item}'.")
        settings = self.settings
        settings[item] = fields[item].validate(value)
        self._guides.write_settings(self.instance_id, settings)
        self._touch()

    def set(self, **settings) -> "GuideHandle":
        for key, value in settings.items():
            setattr(self, key, value)
        return self

    @property
    def key(self) -> str:
        return self._refresh().key

    @property
    def inputs(self) -> dict:
        """``{input name: source}`` (explicit connections only)."""
        return dict(self._refresh().inputs)

    @property
    def input_names(self) -> list[str]:
        return self.module_class.input_names(self.settings)

    @property
    def outputs(self) -> tuple:
        return self.module_class.output_names(self.settings)

    def set_input(self, input_name: str, source: Optional[str]) -> None:
        if self.module_class.get_input(input_name, self.settings) is None:
            raise GuideError(f"'{self.module_type}' has no input '{input_name}'.")
        inputs = self.inputs
        if source:
            inputs[input_name] = source
        else:
            inputs.pop(input_name, None)
        self._guides.set_inputs(self.instance_id, inputs)
        self._touch()

    def select(self) -> None:
        self._guides.select_guides(self.instance_id)

    def __repr__(self) -> str:
        return f"<Guides {self.name} ({self.module_type} {self.side.value})>"



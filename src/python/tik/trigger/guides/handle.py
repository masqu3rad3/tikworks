"""``GuideHandle``: one module instance, as the UI and TDs see it.

A handle is a view onto a ``ModuleEntry`` in the guide document plus the scene
that owns it. It holds nothing itself -- every read goes to the document and
every write goes back through the scene -- so a handle stays valid across a
regenerate, and stays valid when the guide joints are deleted.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from tik.core.side import Side
from tik.trigger.core import registry
from tik.trigger.core.exceptions import GuideError
from tik.trigger.core.manifest import instance_key

if TYPE_CHECKING:
    from .scene import GuideScene


def mirror_source(source: str, side: str, target_side: str) -> str:
    """Mirror ``L_arm.hand`` to ``R_arm.hand``; center and scene sources unchanged."""
    key, dot, output = source.rpartition(".")
    if dot and key.startswith(f"{side}_"):
        return f"{target_side}_{key[2:]}{dot}{output}"
    return source


class GuideHandle:
    """One module instance in the scene; settings are attributes."""

    def __init__(self, guides: "GuideScene", instance_id: str) -> None:
        object.__setattr__(self, "_guides", guides)
        object.__setattr__(self, "_instance_id", instance_id)

    # ---------------------------------------------------------- identity
    @property
    def entry(self):
        """This module's document entry.

        Raises when the module has been removed -- note that deleting its guide
        joints does *not* remove it: the joints are a rendering.
        """
        found = self._guides.document.module(self._instance_id)
        if found is None:
            raise GuideError(
                f"Module '{self._instance_id}' is no longer in the document."
            )
        return found

    @property
    def instance_id(self) -> str:
        """The uuid that identifies this module in the document."""
        return self._instance_id

    @property
    def name(self) -> str:
        """The module's name (without its side)."""
        return self.entry.name

    @name.setter
    def name(self, value: str) -> None:
        value = (value or "").strip()
        if not value:
            raise GuideError("A module needs a name.")
        key = instance_key(value, self.side.value)
        taken = self._guides.by_key(key)
        if taken is not None and taken.instance_id != self.instance_id:
            raise GuideError(f"A module named '{key}' already exists.")
        if self._guides.scene_groups().get(key) is not None:
            raise GuideError(f"'{key}' is already a scene-nodes group.")
        self._guides.rename_instance(self.instance_id, value)

    @property
    def module_type(self) -> str:
        """The registered module type."""
        return self.entry.module_type

    @property
    def side(self) -> Side:
        """The module's side."""
        return Side.from_value(self.entry.side)

    @property
    def key(self) -> str:
        """Display key: ``name`` for center modules, ``<side>_<name>`` otherwise."""
        return self.entry.key

    @property
    def module_class(self) -> type:
        """The ``Module`` subclass registered for this type."""
        return registry.get_module(self.entry.module_type)

    def __repr__(self) -> str:
        entry = self._guides.document.module(self._instance_id)
        if entry is None:
            return f"<GuideHandle {self._instance_id} (removed)>"
        return f"<GuideHandle {entry.name} ({entry.module_type} {entry.side})>"

    # ------------------------------------------------------------- scene
    @property
    def instance(self):
        """The build-time ``ModuleInstance`` for this module (poses from the scene)."""
        found = self._guides.find_instances([self._instance_id])
        if not found:
            raise GuideError(f"Module '{self.name}' has no guides in the scene.")
        return found[0]

    @property
    def root(self):
        """This module's root guide joint, or None when it is not rendered."""
        return self._guides.guide_nodes(self._instance_id).get(
            (self.module_class.guides.root, 0)
        )

    @property
    def parent(self) -> Optional["GuideHandle"]:
        """The module feeding this one's primary input."""
        primary = self.module_class.primary_input()
        source = self.entry.inputs.get(primary.name) if primary else None
        if not source or "." not in source:
            return None
        return self._guides.get(source.rpartition(".")[0])

    def select(self) -> None:
        """Select this module's guide joints."""
        self._guides.select_guides(self._instance_id)

    # ---------------------------------------------------------- settings
    @property
    def settings(self) -> dict:
        """The module's settings with defaults filled in."""
        module = self.module_class(settings=self.entry.settings)
        return module.values()

    def __getattr__(self, item: str) -> Any:
        if item.startswith("_"):
            raise AttributeError(item)
        # A property that raises AttributeError lands here, and treating it as a
        # settings lookup would re-enter this method forever. Re-raise instead,
        # so the real failure is what surfaces.
        if isinstance(getattr(type(self), item, None), property):
            raise AttributeError(
                f"'{type(self).__name__}.{item}' failed; the module may be gone."
            )
        fields = self.module_class.fields()
        if item not in fields:
            raise AttributeError(f"'{self.module_type}' has no property '{item}'.")
        return self.settings[item]

    def __setattr__(self, item: str, value: Any) -> None:
        if isinstance(getattr(type(self), item, None), property):
            object.__setattr__(self, item, value)
            return
        fields = self.module_class.fields()
        if item not in fields:
            raise AttributeError(f"'{self.module_type}' has no property '{item}'.")
        settings = self.settings
        settings[item] = fields[item].validate(value)
        self._guides.write_settings(self.instance_id, settings)

    def set(self, **settings) -> "GuideHandle":
        """Assign several settings at once; returns the handle for chaining."""
        for key, value in settings.items():
            setattr(self, key, value)
        return self

    # ------------------------------------------------------------ inputs
    @property
    def inputs(self) -> dict:
        """``{input name: source}``; a source is ``"<key>.<output>"`` or a node."""
        return self._guides.inputs_as_keys(self.entry)

    @property
    def input_names(self) -> list[str]:
        """Declared inputs plus the space inputs the settings add."""
        return self.module_class.input_names(self.settings)

    @property
    def outputs(self) -> tuple:
        """The output names this module exposes with its settings."""
        return self.module_class.output_names(self.settings)

    def set_input(self, input_name: str, source: Optional[str]) -> None:
        """Point ``input_name`` at ``source`` (``key.output`` or node); None clears."""
        if self.module_class.get_input(input_name, self.settings) is None:
            raise GuideError(f"'{self.module_type}' has no input '{input_name}'.")
        self._guides.set_input(self.instance_id, input_name, source)

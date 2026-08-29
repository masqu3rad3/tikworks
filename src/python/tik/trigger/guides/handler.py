"""``Guides``: author module guides in the live scene and exchange ``.trg`` files."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from tik.core.side import Side
from tik.trigger.core import registry
from tik.trigger.core.builder import Builder
from tik.trigger.core.events import EventBus
from tik.trigger.core.exceptions import GuideError
from tik.trigger.core.schemas import GuidePose, ModuleInstance, ParentRef

from .format import GuideFile, GuideInstance, legacy_type, make_record


def _mirror_source(source: str, side: str, target_side: str) -> str:
    """``L_arm.hand`` -> ``R_arm.hand`` when mirroring; center/scene sources unchanged."""
    key, dot, output = source.rpartition(".")
    if dot and key.startswith(f"{side}_"):
        return f"{target_side}_{key[2:]}{dot}{output}"
    return source


class GuideHandle:
    """One module instance in the scene; settings are attributes."""

    def __init__(self, guides: "Guides", instance: ModuleInstance) -> None:
        object.__setattr__(self, "_guides", guides)
        object.__setattr__(self, "_instance", instance)

    def _refresh(self) -> ModuleInstance:
        found = self._guides.backend.find_instances([self._instance.instance_id])
        if not found:
            raise GuideError(f"Guides for '{self._instance.name}' no longer exist.")
        object.__setattr__(self, "_instance", found[0])
        return found[0]

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
        self._guides.backend.rename_instance(self.instance_id, value)
        self._refresh()

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
        return self._guides.backend.guide_node(self.instance_id, self.module_class.guides.root)

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
        self._guides.backend.write_settings(self.instance_id, settings)
        self._refresh()

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
        return self.module_class.input_names()

    @property
    def outputs(self) -> tuple:
        return self.module_class.output_names(self.settings)

    def set_input(self, input_name: str, source: Optional[str]) -> None:
        if self.module_class.get_input(input_name) is None:
            raise GuideError(f"'{self.module_type}' has no input '{input_name}'.")
        inputs = self.inputs
        if source:
            inputs[input_name] = source
        else:
            inputs.pop(input_name, None)
        self._guides.backend.set_inputs(self.instance_id, inputs)
        self._refresh()

    def select(self) -> None:
        self._guides.backend.select_guides(self.instance_id)

    def __repr__(self) -> str:
        return f"<Guides {self.name} ({self.module_type} {self.side.value})>"


class Guides:
    """Author guides in the scene; import/export ``.trg``; test build."""

    def __init__(self, backend=None, events: Optional[EventBus] = None) -> None:
        if backend is None:
            import tik.trigger as trigger

            backend = trigger.maya_backend()
        self.backend = backend
        self.events = events or EventBus()

    # ----------------------------------------------------------- listing
    def instances(self) -> list[GuideHandle]:
        return [GuideHandle(self, item) for item in self.backend.find_instances()]

    def roots(self) -> list[GuideHandle]:
        return [handle for handle in self.instances() if handle.instance.parent is None]

    def get(self, instance_id: str) -> Optional[GuideHandle]:
        found = self.backend.find_instances([instance_id])
        return GuideHandle(self, found[0]) if found else None

    def find(self, name: str, side: Optional[str] = None) -> Optional[GuideHandle]:
        for handle in self.instances():
            if handle.name == name and (side is None or handle.side == Side.from_value(side)):
                return handle
        return None

    def __getitem__(self, name: str) -> GuideHandle:
        handle = self.find(name)
        if handle is None:
            raise GuideError(f"No guides named '{name}'.")
        return handle

    def clear(self) -> None:
        for handle in self.instances():
            self.backend.delete_guides(handle.instance_id)

    # ---------------------------------------------------------- authoring
    def add(
        self,
        module_type: str,
        side: str = "C",
        name: Optional[str] = None,
        parent: Optional[GuideHandle | ParentRef] = None,
        inputs: Optional[dict] = None,
        **settings,
    ) -> GuideHandle:
        """Draw a module's guides. ``parent`` also hangs the joints under that guide and
        pre-fills the primary input; ``inputs`` sets connections explicitly without any
        scene parenting (what the Guide Designer does)."""
        module_cls = registry.get_module(module_type)
        module = module_cls(name=name, side=side, settings=settings)
        parent_ref = parent
        if isinstance(parent, GuideHandle):
            parent_ref = ParentRef(parent.instance_id, parent.module_class.guides.root)
        instance = self.backend.create_guides(module, parent=parent_ref, inputs=inputs)
        return GuideHandle(self, instance)

    def remove(self, handle: GuideHandle) -> None:
        self.backend.delete_guides(handle.instance_id)

    # -------------------------------------------------------- connections
    def by_key(self, key: str) -> Optional[GuideHandle]:
        return next((handle for handle in self.instances() if handle.key == key), None)

    def connect(self, target: str, source: str) -> None:
        """``connect("L_arm.root", "body.root")`` or ``connect("tail.space", "some_jnt")``."""
        key, _dot, input_name = target.rpartition(".")
        handle = self.by_key(key)
        if handle is None or not input_name:
            raise GuideError(f"No module input '{target}'.")
        source_key, _d, output = source.rpartition(".")
        producer = self.by_key(source_key) if source_key else None
        if producer is not None and output not in producer.outputs:
            raise GuideError(f"'{source_key}' has no output '{output}' (has {list(producer.outputs)}).")
        handle.set_input(input_name, source)

    def disconnect(self, target: str) -> None:
        key, _dot, input_name = target.rpartition(".")
        handle = self.by_key(key)
        if handle is None:
            raise GuideError(f"No module input '{target}'.")
        handle.set_input(input_name, None)

    def connections(self) -> list[dict]:
        found = []
        for handle in self.instances():
            for input_name, source in handle.inputs.items():
                found.append({"input": f"{handle.key}.{input_name}", "source": source})
        return found

    def reparent(self, handle: GuideHandle, parent: Optional[GuideHandle | ParentRef]) -> None:
        """Hang ``handle`` under ``parent`` (its root guide) or back at the top level."""
        parent_ref = parent
        if isinstance(parent, GuideHandle):
            parent_ref = ParentRef(parent.instance_id, parent.module_class.guides.root)
        self.backend.reparent_guides(handle.instance_id, parent_ref)

    def mirror(self, handle: GuideHandle) -> GuideHandle:
        """Create (or update) the opposite-side copy of ``handle``."""
        instance = handle.instance
        if handle.side is Side.CENTER:
            raise GuideError("Center guides cannot be mirrored.")
        target_side = handle.side.mirror
        existing = self.find(instance.name, target_side.value)
        poses = [
            GuidePose(pose.role, pose.index,
                      (-pose.position[0], pose.position[1], pose.position[2]),
                      (pose.rotation[0], -pose.rotation[1], -pose.rotation[2]))
            for pose in instance.guides
        ]
        if existing is not None:
            existing_instance = existing.instance
            existing_instance.guides = poses
            self.backend.apply_guide_poses(existing_instance)
            self.backend.write_settings(existing.instance_id, instance.settings)
            self.backend.set_inputs(
                existing.instance_id,
                {name: _mirror_source(source, handle.side.value, target_side.value) for name, source in instance.inputs.items()},
            )
            return existing
        module = handle.module_class(name=instance.name, side=target_side, settings=instance.settings)
        mirrored_inputs = {name: _mirror_source(source, handle.side.value, target_side.value) for name, source in instance.inputs.items()}
        created = self.backend.create_guides(module, parent=instance.parent, poses=poses, attach=instance.attach, inputs=mirrored_inputs)
        return GuideHandle(self, created)

    # ------------------------------------------------------------- build
    def test_build(self, *handles: GuideHandle, rig_name: str = "test") -> Any:
        scope = [handle.instance_id for handle in handles] or "scene"
        return Builder(self.backend, self.events).build(scope=scope, rig_name=rig_name, afterlife="keep")

    # ------------------------------------------------------------ files
    def export(self, file_path, *handles: GuideHandle) -> Path:
        wanted = {handle.instance_id for handle in handles} or None
        records = self.backend.export_guide_records(wanted)
        keys = {handle.key for handle in (handles or self.instances())}
        connections = [item for item in self.connections() if item["input"].split(".")[0] in keys]
        return GuideFile(records, connections).save(file_path)

    def import_(self, file_path, reset: bool = False) -> list[GuideHandle]:
        guide_file = GuideFile.load(file_path)
        instances = guide_file.instances()
        if guide_file.unknown:
            self.events.log(f"Guide file has unknown module types: {guide_file.unknown}", level="warning")
        if reset:
            self.clear()
        created = self.backend.import_guide_instances(instances)
        return [GuideHandle(self, item) for item in created]

    load = import_

    def __repr__(self) -> str:
        return f"Guides({len(self.instances())} instances)"

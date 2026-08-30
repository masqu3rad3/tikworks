"""``Guides``: author module guides in the live scene and exchange ``.trg`` files."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from tik.core.side import Side
from tik.trigger.core import registry
from tik.trigger.core.builder import Builder
from tik.trigger.core.events import EventBus
from tik.trigger.core.exceptions import GuideError
from tik.trigger.core.manifest import instance_key
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
        self._guides.backend.rename_instance(self.instance_id, value)
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
        return self.module_class.input_names()

    @property
    def outputs(self) -> tuple:
        return self.module_class.output_names(self.settings)

    @property
    def spaces(self) -> dict:
        """``{space name: [sources]}``."""
        return {key: list(value) for key, value in self._refresh().spaces.items()}

    def set_space(self, name: str, sources) -> None:
        """Replace the source list for one declared space."""
        if self.module_class.get_space(name) is None:
            raise GuideError(f"'{self.module_type}' has no space '{name}'.")
        spaces = self.spaces
        sources = [item for item in (sources or []) if item]
        if sources:
            spaces[name] = sources
        else:
            spaces.pop(name, None)
        self._guides.backend.set_spaces(self.instance_id, spaces)
        self._touch()

    def set_input(self, input_name: str, source: Optional[str]) -> None:
        if self.module_class.get_input(input_name) is None:
            raise GuideError(f"'{self.module_type}' has no input '{input_name}'.")
        inputs = self.inputs
        if source:
            inputs[input_name] = source
        else:
            inputs.pop(input_name, None)
        self._guides.backend.set_inputs(self.instance_id, inputs)
        self._touch()

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
        self._cache: Optional[dict[str, ModuleInstance]] = None

    # ----------------------------------------------------------- caching
    def _snapshot(self) -> dict[str, ModuleInstance]:
        """One scene scan, reused by every handle until something changes."""
        if self._cache is None:
            self._cache = {item.instance_id: item for item in self.backend.find_instances()}
        return self._cache

    def invalidate(self) -> None:
        """Forget the cached scene snapshot.

        Every write through this API does it for you; call it yourself after
        editing guides directly in Maya (moving joints, undo, deleting).
        """
        self._cache = None

    # ----------------------------------------------------------- listing
    def instances(self) -> list[GuideHandle]:
        return [GuideHandle(self, item) for item in self._snapshot().values()]

    def roots(self) -> list[GuideHandle]:
        return [handle for handle in self.instances() if handle.instance.parent is None]

    def get(self, instance_id: str) -> Optional[GuideHandle]:
        found = self._snapshot().get(instance_id)
        return GuideHandle(self, found) if found else None

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
        self.invalidate()

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
        module.name = self.unique_name(module.name, module.side.value)
        parent_ref = parent
        if isinstance(parent, GuideHandle):
            parent_ref = ParentRef(parent.instance_id, parent.module_class.guides.root)
        instance = self.backend.create_guides(module, parent=parent_ref, inputs=inputs)
        self.invalidate()
        return GuideHandle(self, instance)

    def unique_name(self, name: str, side: str) -> str:
        """``arm`` -> ``arm``, ``arm1``, ``arm2``... until ``<side>_<name>`` is free."""
        taken = {handle.key for handle in self.instances()} | set(self.layout.get("scene_nodes", {}))
        base = name.rstrip("0123456789") or name
        candidate, index = name, 1
        while instance_key(candidate, side) in taken:
            candidate = f"{base}{index}"
            index += 1
        return candidate

    def remove(self, handle: GuideHandle) -> None:
        key = handle.key
        self.backend.delete_guides(handle.instance_id)
        self.invalidate()
        self._forget_key(key)

    # ------------------------------------------------------------ layout
    @property
    def layout(self) -> dict:
        """Designer state stored with the guides: scene-node groups, node positions, collapse modes.

        ``{"scene_nodes": {group: [node, ...]}, "positions": {key: [x, y]}, "collapse": {key: 0|1|2}}``
        """
        reader = getattr(self.backend, "read_layout", None)
        return dict(reader() if reader else {})

    def set_layout(self, layout: dict) -> None:
        writer = getattr(self.backend, "write_layout", None)
        if writer is not None:
            writer(dict(layout))

    def update_layout(self, **sections) -> dict:
        """Replace whole sections (``positions=``, ``scene_nodes=``, ``collapse=``)."""
        layout = self.layout
        for name, value in sections.items():
            layout[name] = value
        self.set_layout(layout)
        return layout

    def _rename_key(self, old: str, new: str) -> None:
        layout = self.layout
        changed = False
        for section in ("positions", "collapse"):
            table = layout.get(section, {})
            if old in table:
                table[new] = table.pop(old)
                changed = True
        if changed:
            self.set_layout(layout)

    def _forget_key(self, key: str) -> None:
        layout = self.layout
        changed = False
        for section in ("positions", "collapse"):
            if key in layout.get(section, {}):
                del layout[section][key]
                changed = True
        if changed:
            self.set_layout(layout)

    # ------------------------------------------------------ scene nodes
    def scene_groups(self) -> dict[str, list[str]]:
        """``{group name: [scene node, ...]}`` — arbitrary Maya nodes modules connect to."""
        return {name: list(nodes) for name, nodes in self.layout.get("scene_nodes", {}).items()}

    def add_scene_group(self, name: str = "", nodes: Optional[list[str]] = None) -> str:
        groups = self.scene_groups()
        taken = set(groups) | {handle.key for handle in self.instances()}
        if not name:
            index = 1
            while f"sceneNodes{index}" in taken:
                index += 1
            name = f"sceneNodes{index}"
        elif name in taken:
            raise GuideError(f"'{name}' is already used.")
        groups[name] = list(nodes or [])
        self.update_layout(scene_nodes=groups)
        return name

    def set_scene_group(self, name: str, nodes: list[str]) -> None:
        groups = self.scene_groups()
        if name not in groups:
            raise GuideError(f"No scene-nodes group '{name}'.")
        removed = set(groups[name]) - set(nodes)
        groups[name] = [node for node in nodes if node]
        self.update_layout(scene_nodes=groups)
        for item in self.connections():
            if item["source"] in removed and not self.scene_node_group(item["source"]):
                self.disconnect(item["input"])

    def rename_scene_group(self, old: str, new: str) -> None:
        new = (new or "").strip()
        groups = self.scene_groups()
        if old not in groups:
            raise GuideError(f"No scene-nodes group '{old}'.")
        if not new or new == old:
            return
        if new in groups or self.by_key(new) is not None:
            raise GuideError(f"'{new}' is already used.")
        groups[new] = groups.pop(old)
        self.update_layout(scene_nodes=groups)
        self._rename_key(old, new)

    def remove_scene_group(self, name: str) -> None:
        groups = self.scene_groups()
        nodes = set(groups.pop(name, []))
        self.update_layout(scene_nodes=groups)
        for item in self.connections():
            if item["source"] in nodes and not self.scene_node_group(item["source"]):
                self.disconnect(item["input"])
        self._forget_key(name)

    def scene_node_group(self, node: str) -> Optional[str]:
        """The group that lists scene node ``node`` (first match)."""
        for name, nodes in self.scene_groups().items():
            if node in nodes:
                return name
        return None

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

    def set_spaces(self, handle, spaces: dict) -> None:
        """Replace every space source list on ``handle``."""
        for name, sources in spaces.items():
            handle.set_space(name, sources)

    def disconnect(self, target: str) -> None:
        key, _dot, input_name = target.rpartition(".")
        handle = self.by_key(key)
        if handle is None:
            raise GuideError(f"No module input '{target}'.")
        handle.set_input(input_name, None)

    def connections(self) -> list[dict]:
        """Every wire in the graph: inputs, plus spaces tagged ``kind``.

        A space is a connection too, so it travels in the same list. Entries
        without a ``kind`` are inputs, which keeps older ``.trg`` files valid.
        """
        found = []
        for handle in self.instances():
            for input_name, source in handle.inputs.items():
                found.append({"input": f"{handle.key}.{input_name}", "source": source})
            for space_name, sources in handle.spaces.items():
                for source in sources:
                    found.append({
                        "input": f"{handle.key}.{space_name}",
                        "source": source,
                        "kind": "space",
                    })
        return found

    def reparent(self, handle: GuideHandle, parent: Optional[GuideHandle | ParentRef]) -> None:
        """Hang ``handle`` under ``parent`` (its root guide) or back at the top level."""
        parent_ref = parent
        if isinstance(parent, GuideHandle):
            parent_ref = ParentRef(parent.instance_id, parent.module_class.guides.root)
        self.backend.reparent_guides(handle.instance_id, parent_ref)
        self.invalidate()

    def mirror(self, handle: GuideHandle) -> GuideHandle:
        """Create (or update) the opposite-side copy of ``handle``."""
        self.invalidate()  # poses may have been edited by hand
        instance = handle.instance
        if handle.side is Side.CENTER:
            raise GuideError("Center guides cannot be mirrored.")
        target_side = handle.side.mirror
        existing = self.find(instance.name, target_side.value)
        poses = [
            # Mirroring is conjugation by the world-YZ reflection, which maps
            # each euler factor onto the same axis: Rx keeps its angle, Ry and Rz
            # negate. Conjugation distributes over the product, so this is exact
            # in any rotation order - provided the order travels with it.
            GuidePose(pose.role, pose.index,
                      (-pose.position[0], pose.position[1], pose.position[2]),
                      (pose.rotation[0], -pose.rotation[1], -pose.rotation[2]),
                      pose.rotate_order)
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
            self.backend.set_spaces(
                existing.instance_id,
                {
                    name: [
                        _mirror_source(source, handle.side.value, target_side.value)
                        for source in sources
                    ]
                    for name, sources in instance.spaces.items()
                },
            )
            self.invalidate()
            return existing
        module = handle.module_class(name=instance.name, side=target_side, settings=instance.settings)
        mirrored_inputs = {name: _mirror_source(source, handle.side.value, target_side.value) for name, source in instance.inputs.items()}
        created = self.backend.create_guides(module, parent=instance.parent, poses=poses, attach=instance.attach, inputs=mirrored_inputs)
        if instance.spaces:
            self.backend.set_spaces(
                created.instance_id,
                {
                    name: [
                        _mirror_source(source, handle.side.value, target_side.value)
                        for source in sources
                    ]
                    for name, sources in instance.spaces.items()
                },
            )
        self.invalidate()
        return GuideHandle(self, created)

    def duplicate(self, handle: GuideHandle, name: Optional[str] = None) -> GuideHandle:
        """Copy a module: same type/side/settings/inputs/poses, a unique name (``arm`` -> ``arm1``)."""
        self.invalidate()
        instance = handle.instance
        module = handle.module_class(name=name or instance.name, side=instance.side, settings=instance.settings)
        module.name = self.unique_name(module.name, module.side.value)
        created = self.backend.create_guides(module, poses=list(instance.guides), attach=instance.attach, inputs=dict(instance.inputs))
        self.invalidate()
        layout = self.layout
        collapse = layout.get("collapse", {})
        if handle.key in collapse:
            collapse[module.key] = collapse[handle.key]
            self.update_layout(collapse=collapse)
        return GuideHandle(self, created)

    # ------------------------------------------------------------- build
    def test_build(self, *handles: GuideHandle, rig_name: str = "test") -> Any:
        scope = [handle.instance_id for handle in handles] or "scene"
        self.invalidate()  # guides may have been moved by hand since the last read
        try:
            return Builder(self.backend, self.events).build(scope=scope, rig_name=rig_name, afterlife="keep")
        finally:
            self.invalidate()

    # ------------------------------------------------------------ files
    def export(self, file_path, *handles: GuideHandle) -> Path:
        wanted = {handle.instance_id for handle in handles} or None
        self.invalidate()  # export the joints as they are now
        records = self.backend.export_guide_records(wanted)
        keys = {handle.key for handle in (handles or self.instances())}
        connections = [item for item in self.connections() if item["input"].split(".")[0] in keys]
        layout = self.layout
        sources = {item["source"] for item in connections}
        groups = {name: nodes for name, nodes in layout.get("scene_nodes", {}).items()
                  if not handles or set(nodes) & sources}
        wanted = keys | set(groups)
        designer = {
            "scene_nodes": groups,
            "positions": {key: value for key, value in layout.get("positions", {}).items() if key in wanted},
            "collapse": {key: value for key, value in layout.get("collapse", {}).items() if key in wanted},
        }
        designer = {name: value for name, value in designer.items() if value}
        return GuideFile(records, connections, designer=designer).save(file_path)

    def import_(self, file_path, reset: bool = False) -> list[GuideHandle]:
        guide_file = GuideFile.load(file_path)
        instances = guide_file.instances()
        if guide_file.unknown:
            self.events.log(f"Guide file has unknown module types: {guide_file.unknown}", level="warning")
        if reset:
            self.clear()
            self.set_layout({})
        created = self.backend.import_guide_instances(instances)
        self.invalidate()
        if guide_file.designer:
            layout = {} if reset else self.layout
            for section in ("scene_nodes", "positions", "collapse"):
                merged = dict(layout.get(section, {}))
                merged.update(guide_file.designer.get(section, {}))
                if merged:
                    layout[section] = merged
            self.set_layout(layout)
        return [GuideHandle(self, item) for item in created]

    load = import_

    def __repr__(self) -> str:
        return f"Guides({len(self.instances())} instances)"

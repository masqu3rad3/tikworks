"""``GuideScene``: the guides in the current Maya scene.

Authoring, settings, connections, layout and ``.trg`` exchange, in one place.
The joint-level primitives it is built on live in :mod:`.nodes`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import tik.maya as tm
from maya import cmds
from tik.core.side import Side
from tik.maya import attribute
from tik.trigger.core import registry
from tik.trigger.core.events import EventBus
from tik.trigger.core.exceptions import GuideError
from tik.trigger.core.manifest import instance_key
from tik.trigger.core.schemas import GuidePose, ModuleInstance, ParentRef
from tik.trigger.maya import tags
from tik.trigger.maya.rig import GuideDraft

from . import nodes
from .format import GuideFile, GuideInstance, make_record
from .handle import GuideHandle, mirror_source
from .nodes import INPUTS


class GuideScene:
    """The guides in the current Maya scene: author, connect, import/export, test build."""

    def __init__(self, events: Optional[EventBus] = None) -> None:
        self.events = events or EventBus()
        self._cache: Optional[dict[str, ModuleInstance]] = None


    # ------------------------------------------------------- scene access
    def find_instances(self, scope: Any = "scene") -> list[ModuleInstance]:
        return nodes.find_instances(scope)

    def guide_node(self, instance_id: str, role: str, index: int = 0):
        return nodes.guide_node(instance_id, role, index)

    def guide_nodes(self, instance_id: str) -> dict:
        return nodes.guide_nodes(instance_id)

    def select_guides(self, instance_id: str) -> None:
        nodes.select_guides(instance_id)

    def scene_node(self, name: str):
        """The Maya node called ``name``, or None (used to validate sources)."""
        return nodes.scene_node(name)

    def selected_guide(self) -> Optional[ParentRef]:
        return nodes.selected_guide()

    def selected_node_name(self) -> str:
        return nodes.selected_node_name()

    def selected_node_names(self) -> list[str]:
        return nodes.selected_node_names()

    def select_nodes(self, items) -> None:
        nodes.select_nodes(items)

    def make_observer(self, callback):
        from tik.trigger.maya.observer import SceneObserver

        return SceneObserver(callback)

    # ---------------------------------------------------------- authoring
    def create_guides(self, module, parent=None, poses=None, inputs=None) -> ModuleInstance:
        """Draw a module's guides and tag them; returns the scene instance."""
        if nodes.guide_nodes(module.instance_id):
            raise GuideError(f"GuideLayout for instance {module.instance_id} already exist.")
        parent_node = None
        if parent is not None:
            parent_node = nodes.guide_node(parent.instance_id, parent.role, parent.index)
        with nodes.undo_chunk(f"Trigger guides: {module.name}"):
            draft = GuideDraft(module, nodes.holder(), parent_node)
            module.draw_guides(draft)
            if draft.root is None:
                raise GuideError(f"'{module.module_type}' drew no guides.")
            self._write_root_meta(draft.root, module)
            if poses:
                nodes.apply_poses(draft.created, poses)
            # after the poses land, so a guide rig can take over the channels
            module.wire_guides(draft.created)
            resolved = dict(inputs or {})
            if not resolved and parent is not None and module.primary_input() is not None:
                # convenience: drawing under another module's guide pre-fills
                # the primary input with a real value
                found = nodes.find_instances([parent.instance_id])
                if found:
                    parent_cls = registry.get_module(found[0].module_type)
                    output = parent_cls.output_at_role(parent.role)
                    if output:
                        resolved = {module.primary_input().name: f"{found[0].key}.{output}"}
            draft.root.meta[INPUTS] = resolved
        return nodes.instance_from_nodes(module.instance_id, draft.created)

    def delete_guides(self, instance_id: str) -> None:
        found = nodes.guide_nodes(instance_id)
        if not found:
            return
        holder = nodes.holder()
        # keep other instances' guides that hang under ours
        for node in found.values():
            for child in node.children:
                if child.meta.get(tags.INSTANCE) not in (None, instance_id):
                    child.parent = holder
        cmds.delete([node.long_name for node in found.values() if node.exists()])

    def rename_instance(self, instance_id: str, name: str) -> None:
        self._root_of(instance_id).meta[tags.NAME] = name

    def reparent_guides(self, instance_id: str, parent: Optional[ParentRef]) -> None:
        """Hang an instance's root guide under another instance's guide (or the holder)."""
        root = self._root_of(instance_id)
        if parent is None:
            target = nodes.holder()
        else:
            if parent.instance_id == instance_id:
                raise GuideError("Cannot parent guides under themselves.")
            target = nodes.guide_node(parent.instance_id, parent.role, parent.index)
            # refuse cycles: the target must not live under our root
            node = target
            while node is not None:
                if node.meta.get(tags.INSTANCE) == instance_id:
                    raise GuideError("Cannot parent guides under their own descendants.")
                node = node.parent
        with nodes.undo_chunk("Trigger reparent guides"):
            root.parent = target

    def apply_guide_poses(self, instance: ModuleInstance) -> None:
        nodes.apply_poses(nodes.guide_nodes(instance.instance_id), instance.guides)

    # ----------------------------------------------------------- settings
    def set_inputs(self, instance_id: str, inputs: dict) -> None:
        root = self._root_of(instance_id)
        root.meta[INPUTS] = {key: value for key, value in dict(inputs).items() if value}

    def read_settings(self, instance_id: str) -> dict:
        found = nodes.find_instances([instance_id])
        return dict(found[0].settings) if found else {}

    def write_settings(self, instance_id: str, settings: dict) -> None:
        found = nodes.find_instances([instance_id])
        if not found:
            raise GuideError(f"No guides for instance {instance_id}.")
        root = nodes.root_guide(nodes.guide_nodes(instance_id), found[0].module_type)
        module_cls = registry.get_module(found[0].module_type)
        module = module_cls(name=found[0].name, side=found[0].side, settings=settings)
        root.meta[tags.SETTINGS] = module.values()
        self._sync_setting_attrs(root, module)

    def settings_plug(self, instance_id: str, field_name: str):
        """The plug holding a module property (for two-way UI binding)."""
        return self._root_of(instance_id)[field_name]

    def _root_of(self, instance_id: str):
        found = nodes.find_instances([instance_id])
        if not found:
            raise GuideError(f"No guides for instance {instance_id}.")
        return nodes.root_guide(nodes.guide_nodes(instance_id), found[0].module_type)

    @staticmethod
    def _write_root_meta(root, module) -> None:
        root.meta[tags.NAME] = module.name
        root.meta[tags.SETTINGS] = module.values()
        GuideScene._write_guide_attrs(root, module)

    @staticmethod
    def _write_guide_attrs(root, module) -> None:
        """Guide-level attributes the Guide Designer edits, plus the module fields.

        ``useRefOri`` ("Inherit Orientation") is a real attribute rather than a
        module field because it is a property of the guide, not of the module
        type: the designer binds its checkbox to this plug two-way, and writes
        it across a multi-selection.
        """
        if not root.has_attr("useRefOri"):
            attribute.add_bool(root, "useRefOri", default=True)
        GuideScene._sync_setting_attrs(root, module)

    @staticmethod
    def _sync_setting_attrs(root, module) -> None:
        """Mirror module fields as real Maya attributes on the root guide.

        The Guide Designer binds its property widgets two-way to these plugs
        through ``settings_plug()``. The authoritative storage is still the
        ``trg_settings`` meta dict; non-scalar field kinds have no sensible
        single attribute and live only there.
        """
        for name, field_obj in module.fields().items():
            value = getattr(module, name)
            kind = field_obj.type_name
            if kind in ("list", "dict", "vector", "table"):
                continue
            if not root.has_attr(name):
                if kind == "bool":
                    attribute.add_bool(root, name, default=bool(value))
                elif kind == "int":
                    attribute.add_int(root, name, default=int(value), min=field_obj.min, max=field_obj.max)
                elif kind == "float":
                    attribute.add_float(root, name, default=float(value), min=field_obj.min, max=field_obj.max)
                elif kind == "choice":
                    attribute.add_enum(root, name, [str(item) for item in field_obj.choices], default=field_obj.choices.index(value))
                else:
                    attribute.add_string(root, name)
            if kind == "choice":
                root[name].value = field_obj.choices.index(value)
            elif kind in ("string", "file", "node"):
                root[name].value = str(value)
            else:
                root[name].value = value

    # ------------------------------------------------------------ layout
    def read_layout(self) -> dict:
        """Designer state on the guide holder (scene-node groups, positions, collapse)."""
        if not cmds.objExists(tags.GUIDE_HOLDER):
            return {}
        return dict(tm.Transform(tags.GUIDE_HOLDER).meta.get(tags.DESIGNER, {}) or {})

    def write_layout(self, layout: dict) -> None:
        """Store designer state; one undo chunk so 'auto layout' and node moves undo."""
        with nodes.undo_chunk("Trigger designer layout"):
            nodes.holder().meta[tags.DESIGNER] = dict(layout)

    # ------------------------------------------------------- .trg records
    def export_guide_records(self, instance_ids=None) -> list[dict]:
        """Serialize scene guides as ``.trg`` joint records."""
        found = nodes.find_instances() if instance_ids is None else nodes.find_instances(list(instance_ids))
        records: list[dict] = []
        for instance in found:
            module_cls = registry.get_module(instance.module_type)
            joints = nodes.guide_nodes(instance.instance_id)
            root_role = module_cls.guides.root
            ordered = sorted(joints.items(), key=lambda item: (item[0][0] != root_role, item[0][0], item[0][1]))
            for (role, index), node in ordered:
                parent = node.parent
                parent_name = parent.name if parent is not None and parent.meta.get(tags.KIND) == tags.GUIDE else None
                is_root = role == root_role and index == 0
                declared = module_cls.attrs_for_role(role)
                attrs = {item.name: node[item.name].value for item in declared}
                records.append(make_record(
                    name=node.name,
                    position=cmds.xform(node.long_name, query=True, worldSpace=True, translation=True),
                    rotation=tuple(node.rotate),
                    joint_orient=node.joint_orient,
                    parent=parent_name,
                    side=instance.side,
                    module=instance.module_type,
                    role=role,
                    index=index,
                    instance=instance.instance_id,
                    radius=node.radius,
                    color=node.color or 17,
                    attrs=attrs,
                    settings=dict(instance.settings) if is_root else None,
                    module_name=instance.name if is_root else None,
                ))
        return records

    def _draw_missing_roles(self, module, present_roles, holder) -> dict:
        """Draw declared roles a record omits, at their ``draw_guides`` pose.

        Import creates only what the file carries, so a module that gains a
        guide would otherwise stop building every asset written before it --
        ``rig.guide(role)`` raises on the missing one. The module owns its
        layout and nothing else knows those positions, so the honest way to
        find them is to run ``draw_guides`` into a scratch group and keep the
        joints we are short of. They come out correctly named, tagged and
        attributed, because ``GuideDraft`` made them.
        """
        missing = {role for role in module.guides.roles if role not in present_roles}
        if not missing:
            return {}
        scratch = tm.Transform.create(name="trg_import_scratch_GRP")
        try:
            draft = GuideDraft(module, scratch, None)
            module.draw_guides(draft)
            role_of = {
                joint.long_name: role for (role, _index), joint in draft.created.items()
            }
            found = {}
            for key, joint in draft.created.items():
                node = joint.parent
                found[key] = {
                    "node": joint,
                    "position": tuple(joint.world_position),
                    "parent_role": (
                        role_of.get(node.long_name) if node is not None else None
                    ),
                }
            # Flatten before deleting: removing a role the file already has
            # must not take a role we are missing down with it.
            for joint in draft.created.values():
                joint.parent = scratch
            kept = {}
            for key, info in found.items():
                if key[0] in missing:
                    kept[key] = info
                else:
                    info["node"].delete()
            for info in kept.values():
                info["node"].parent = holder
                info["node"].world_position = info["position"]
            return kept
        finally:
            scratch.delete()

    def import_guide_instances(self, guide_instances) -> list[ModuleInstance]:
        """Recreate guide joints from ``GuideInstance`` records; returns scene instances."""
        holder = nodes.holder()
        created_nodes: dict = {}  # record name -> joint
        built: list = []
        extras: dict = {}  # instance_id -> roles the file predates
        with nodes.undo_chunk("Trigger import guides"):
            for guide_instance in guide_instances:
                module_cls = registry.get_module(guide_instance.module_type)
                module = module_cls(name=guide_instance.name, side=guide_instance.side,
                                    settings=guide_instance.settings)
                joints: dict = {}
                for (role, index), record in guide_instance.joints.items():
                    joint = tm.Joint.create(name=record["name"], radius=record.get("radius", 1.0))
                    joint.world_position = record["position"]
                    joint.joint_orient = record.get("joint_orient", (0, 0, 0))
                    joint.rotate = tuple(record.get("rotation", (0, 0, 0)))
                    joint.color = record.get("color") or 17
                    for item in module_cls.attrs_for_role(role):
                        plug = tm.attribute.add_float(
                            joint, item.name, default=item.default, keyable=item.keyable
                        )
                        plug.value = record.get("attrs", {}).get(item.name, item.default)
                    joint.meta.update({
                        tags.KIND: tags.GUIDE, tags.MODULE: module.module_type,
                        tags.INSTANCE: module.instance_id, tags.ROLE: role,
                        tags.INDEX: index, tags.SIDE: module.side.value,
                    })
                    joints[(role, index)] = joint
                    created_nodes[record["name"]] = joint
                # Roles this file predates, drawn where the module puts them.
                extra = self._draw_missing_roles(
                    module, {role for (role, _index) in joints}, holder
                )
                if extra:
                    extras[module.instance_id] = extra
                    for key, info in extra.items():
                        joints[key] = info["node"]
                root = joints[(module_cls.guides.root, 0)]
                self._write_root_meta(root, module)
                root.meta[INPUTS] = dict(guide_instance.inputs)
                built.append((guide_instance, module, joints))
            for guide_instance, module, joints in built:
                for (role, index), record in guide_instance.joints.items():
                    joint = joints[(role, index)]
                    parent_name = record.get("parent")
                    parent_node = created_nodes.get(parent_name) if parent_name else None
                    joint.parent = parent_node if parent_node is not None else holder
                    cmds.xform(joint.long_name, worldSpace=True, translation=record["position"])
                for key, info in extras.get(module.instance_id, {}).items():
                    # Parented after the recorded joints, so a filled role can
                    # hang off one of them.
                    target = joints.get((info["parent_role"], 0))
                    info["node"].parent = target if target is not None else holder
                    cmds.xform(
                        info["node"].long_name,
                        worldSpace=True,
                        translation=info["position"],
                    )
            for _guide_instance, module, joints in built:
                module.wire_guides(joints)
        return [nodes.instance_from_nodes(module.instance_id, joints) for _gi, module, joints in built]

    # ----------------------------------------------------------- caching
    def _snapshot(self) -> dict[str, ModuleInstance]:
        """One scene scan, reused by every handle until something changes."""
        if self._cache is None:
            self._cache = {item.instance_id: item for item in self.find_instances()}
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
            self.delete_guides(handle.instance_id)
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
        instance = self.create_guides(module, parent=parent_ref, inputs=inputs)
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
        self.delete_guides(handle.instance_id)
        self.invalidate()
        self._forget_key(key)

    # ------------------------------------------------------------ layout
    @property
    def layout(self) -> dict:
        """Designer state stored with the guides: scene-node groups, node positions, collapse modes.

        ``{"scene_nodes": {group: [node, ...]}, "positions": {key: [x, y]}, "collapse": {key: 0|1|2}}``
        """
        return self.read_layout()

    def set_layout(self, layout: dict) -> None:
        self.write_layout(dict(layout))

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
        self.reparent_guides(handle.instance_id, parent_ref)
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
            self.apply_guide_poses(existing_instance)
            self.write_settings(existing.instance_id, instance.settings)
            self.set_inputs(
                existing.instance_id,
                {name: mirror_source(source, handle.side.value, target_side.value) for name, source in instance.inputs.items()},
            )
            self.invalidate()
            return existing
        module = handle.module_class(name=instance.name, side=target_side, settings=instance.settings)
        mirrored_inputs = {name: mirror_source(source, handle.side.value, target_side.value) for name, source in instance.inputs.items()}
        created = self.create_guides(module, parent=instance.parent, poses=poses, inputs=mirrored_inputs)
        self.invalidate()
        return GuideHandle(self, created)

    def duplicate(self, handle: GuideHandle, name: Optional[str] = None) -> GuideHandle:
        """Copy a module: same type/side/settings/inputs/poses, a unique name (``arm`` -> ``arm1``)."""
        self.invalidate()
        instance = handle.instance
        module = handle.module_class(name=name or instance.name, side=instance.side, settings=instance.settings)
        module.name = self.unique_name(module.name, module.side.value)
        created = self.create_guides(module, poses=list(instance.guides), inputs=dict(instance.inputs))
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
            from tik.trigger.maya.build import Builder

            return Builder(self.events).build(scope=scope, rig_name=rig_name, afterlife="keep")
        finally:
            self.invalidate()

    # ------------------------------------------------------------ files
    def export(self, file_path, *handles: GuideHandle) -> Path:
        wanted = {handle.instance_id for handle in handles} or None
        self.invalidate()  # export the joints as they are now
        records = self.export_guide_records(wanted)
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
        created = self.import_guide_instances(instances)
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
        return f"GuideLayout({len(self.instances())} instances)"

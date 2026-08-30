"""Maya backend: guides as tagged joints, builds on tik.maya."""

from __future__ import annotations

import contextlib
import logging
from typing import Any, Optional, Sequence

from maya import cmds

import tik.maya as tm
from tik.trigger.core import registry
from tik.trigger.core.exceptions import AttachError, GuideError
from tik.trigger.core.schemas import GuidePose, ModuleInstance, ParentRef

from tik.maya import attribute
from tik.trigger.guides.format import legacy_type, make_record

from . import tags
from .context import MayaBuildContext, MayaGuideContext

INPUTS = "trg_inputs"
SPACES = "trg_spaces"

_JOINT_SIDES = {"C": 0, "L": 1, "R": 2}
_AXES = {"upAxis": (0.0, 1.0, 0.0), "mirrorAxis": (1.0, 0.0, 0.0), "lookAxis": (0.0, 0.0, 1.0)}

logger = logging.getLogger(__name__)


class MayaBackend:
    """Implements ``tik.trigger.core.backend.Backend`` for Maya."""

    name = "maya"

    # ---------------------------------------------------------------- scene
    def new_scene(self) -> None:
        cmds.file(new=True, force=True)

    @contextlib.contextmanager
    def undo_chunk(self, label: str):
        """One undo step; a failure inside rolls the whole chunk back."""
        cmds.undoInfo(openChunk=True, chunkName=label)
        try:
            yield
        except BaseException:
            cmds.undoInfo(closeChunk=True)
            try:
                cmds.undo()
            except RuntimeError:
                pass
            raise
        else:
            cmds.undoInfo(closeChunk=True)

    # --------------------------------------------------------------- guides
    def holder(self) -> tm.Transform:
        if cmds.objExists(tags.GUIDE_HOLDER):
            return tm.Transform(tags.GUIDE_HOLDER)
        holder = tm.Transform.create(name=tags.GUIDE_HOLDER)
        holder.meta[tags.KIND] = "guide_holder"
        return holder

    # ------------------------------------------------------------- layout
    def read_layout(self) -> dict:
        """Designer state stored on the guide holder (scene-node groups, node positions, collapse modes)."""
        if not cmds.objExists(tags.GUIDE_HOLDER):
            return {}
        return dict(tm.Transform(tags.GUIDE_HOLDER).meta.get(tags.DESIGNER, {}) or {})

    def write_layout(self, layout: dict) -> None:
        """Store designer state; one undo chunk so 'auto layout' and node moves undo in Maya."""
        with self.undo_chunk("Trigger designer layout"):
            self.holder().meta[tags.DESIGNER] = dict(layout)

    def guide_nodes(self, instance_id: str) -> dict[tuple[str, int], tm.Joint]:
        nodes = tm.find_by_meta(tags.INSTANCE, instance_id, node_type="joint")
        found: dict[tuple[str, int], tm.Joint] = {}
        for node in nodes:
            if node.meta.get(tags.KIND) != tags.GUIDE:
                continue
            found[(node.meta[tags.ROLE], int(node.meta.get(tags.INDEX, 0)))] = node
        return found

    def guide_node(self, instance_id: str, role: str, index: int = 0):
        nodes = self.guide_nodes(instance_id)
        try:
            return nodes[(role, index)]
        except KeyError:
            raise GuideError(f"No guide '{role}' [{index}] for instance {instance_id}.") from None

    def _root_guide(self, nodes: dict, module_type: str):
        module_cls = registry.get_module(module_type)
        return nodes.get((module_cls.guides.root, 0))

    def _parent_ref(self, root_guide) -> Optional[ParentRef]:
        parent = root_guide.parent
        own = root_guide.meta.get(tags.INSTANCE)
        while parent is not None:
            instance = parent.meta.get(tags.INSTANCE)
            if instance and instance != own and parent.meta.get(tags.KIND) == tags.GUIDE:
                return ParentRef(instance, parent.meta.get(tags.ROLE, ""), int(parent.meta.get(tags.INDEX, 0)))
            parent = parent.parent
        return None

    def _instance_from_nodes(self, instance_id: str, nodes: dict, meta: Optional[dict] = None) -> Optional[ModuleInstance]:
        """Build a ``ModuleInstance`` from ``{(role, index): joint}``.

        ``meta`` may carry the already-read ``node.meta.as_dict()`` per joint
        (keyed by long name) so a scene scan reads each attribute once.
        """
        meta = meta or {}

        def read(node):
            data = meta.get(node.long_name)
            if data is None:
                data = meta[node.long_name] = node.meta.as_dict()
            return data

        any_node = next(iter(nodes.values()))
        module_type = read(any_node).get(tags.MODULE, "")
        if not registry.is_module_registered(module_type):
            logger.warning("Skipping guides of unknown module type '%s'.", module_type)
            return None
        root = self._root_guide(nodes, module_type)
        if root is None:
            logger.warning("Instance %s has no root guide; skipped.", instance_id)
            return None
        root_meta = read(root)
        poses = []
        for (role, index), node in sorted(nodes.items(), key=lambda item: (item[0][0], item[0][1])):
            position = tuple(cmds.xform(node.long_name, query=True, worldSpace=True, translation=True))
            rotation = tuple(cmds.xform(node.long_name, query=True, worldSpace=True, rotation=True))
            rotate_order = cmds.getAttr(f"{node.long_name}.rotateOrder")
            poses.append(GuidePose(role, index, position, rotation, rotate_order))
        return ModuleInstance(
            module_type=module_type,
            instance_id=instance_id,
            name=root_meta.get(tags.NAME, module_type),
            side=root_meta.get(tags.SIDE, "C"),
            settings=root_meta.get(tags.SETTINGS, {}) or {},
            guides=poses,
            parent=self._parent_ref(root),
            attach=root_meta.get(tags.ATTACH),
            inputs=dict(root_meta.get(INPUTS, {}) or {}),
            spaces={
                key: list(value)
                for key, value in dict(root_meta.get(SPACES, {}) or {}).items()
            },
        )

    def find_instances(self, scope: Any = "scene") -> list[ModuleInstance]:
        """Scan the scene once: every guide joint's meta is read a single time."""
        meta: dict[str, dict] = {}
        joints = []
        for name in cmds.ls(f"*.{tm.META_PREFIX}{tags.KIND}", long=True, objectsOnly=True, type="joint") or []:
            node = tm.resolve(name)
            data = node.meta.as_dict()
            if data.get(tags.KIND) == tags.GUIDE and tags.INSTANCE in data:
                meta[node.long_name] = data
                joints.append(node)
        if scope == "selection":
            selected = set(cmds.ls(selection=True, long=True, dagObjects=True) or [])
            joints = [node for node in joints if node.long_name in selected]
        elif scope != "scene":
            wanted = set(scope)
            joints = [node for node in joints if meta[node.long_name][tags.INSTANCE] in wanted]

        grouped: dict[str, dict] = {}
        for node in joints:
            data = meta[node.long_name]
            grouped.setdefault(data[tags.INSTANCE], {})[(data[tags.ROLE], int(data.get(tags.INDEX, 0)))] = node
        if scope == "selection":
            # complete partially selected instances
            for instance_id in list(grouped):
                grouped[instance_id] = self.guide_nodes(instance_id)

        instances = []
        for instance_id, nodes in grouped.items():
            instance = self._instance_from_nodes(instance_id, nodes, meta)
            if instance is not None:
                instances.append(instance)
        instances.sort(key=lambda item: item.name)
        return instances

    def create_guides(
        self,
        module,
        parent: Optional[ParentRef] = None,
        poses: Optional[Sequence[GuidePose]] = None,
        attach: Optional[str] = None,
        inputs: Optional[dict] = None,
    ) -> ModuleInstance:
        if self.guide_nodes(module.instance_id):
            raise GuideError(f"Guides for instance {module.instance_id} already exist.")
        parent_node = None
        if parent is not None:
            parent_node = self.guide_node(parent.instance_id, parent.role, parent.index)
        with self.undo_chunk(f"Trigger guides: {module.name}"):
            ctx = MayaGuideContext(module, self.holder(), parent_node)
            module.draw_guides(ctx)
            if ctx.root is None:
                raise GuideError(f"'{module.module_type}' drew no guides.")
            self._write_root_meta(ctx.root, module, attach)
            for (role, _index), node in ctx.created.items():
                self._tag_legacy_joint(node, type(module), role, module.side.value)
            if poses:
                self._apply_poses(ctx.created, poses)
            resolved_inputs = dict(inputs or {})
            if not resolved_inputs and parent is not None and module.primary_input() is not None:
                # convenience: parenting under another module's guide pre-fills the primary input
                parent_instance = self.find_instances([parent.instance_id])
                if parent_instance:
                    parent_cls = registry.get_module(parent_instance[0].module_type)
                    output = attach or parent_cls.output_for_role(parent.role)
                    if output:
                        resolved_inputs = {module.primary_input().name: f"{parent_instance[0].key}.{output}"}
            ctx.root.meta[INPUTS] = resolved_inputs
        instance = self._instance_from_nodes(module.instance_id, ctx.created)
        return instance

    def set_inputs(self, instance_id: str, inputs: dict) -> None:
        instance = self.find_instances([instance_id])
        if not instance:
            raise GuideError(f"No guides for instance {instance_id}.")
        root = self._root_guide(self.guide_nodes(instance_id), instance[0].module_type)
        root.meta[INPUTS] = {key: value for key, value in dict(inputs).items() if value}

    def set_spaces(self, instance_id: str, spaces: dict) -> None:
        """Store ``{space name: [sources]}`` on the instance's root guide."""
        instance = self.find_instances([instance_id])
        if not instance:
            raise GuideError(f"No guides for instance {instance_id}.")
        root = self._root_guide(self.guide_nodes(instance_id), instance[0].module_type)
        root.meta[SPACES] = {
            key: list(value) for key, value in dict(spaces).items() if value
        }

    @staticmethod
    def scene_node(name: str):
        if not name or not cmds.objExists(name):
            return None
        return tm.resolve(name)

    @staticmethod
    def _write_root_meta(root, module, attach) -> None:
        root.meta[tags.NAME] = module.name
        root.meta[tags.SETTINGS] = module.values()
        if attach:
            root.meta[tags.ATTACH] = attach
        MayaBackend._write_legacy_attrs(root, module)

    @staticmethod
    def _write_legacy_attrs(root, module) -> None:
        """Old-Trigger style attributes on the root guide (+ typed module properties)."""
        if not root.has_attr("moduleName"):
            attribute.add_string(root, "moduleName")
        root["moduleName"].value = module.name
        for axis_name, vector in _AXES.items():
            if not root.has_attr(axis_name):
                cmds.addAttr(root.long_name, longName=axis_name, attributeType="float3")
                for component in "XYZ":
                    cmds.addAttr(root.long_name, longName=f"{axis_name}{component}", attributeType="float", parent=axis_name)
            for component, value in zip("XYZ", vector):
                root[f"{axis_name}{component}"].value = value
        if not root.has_attr("useRefOri"):
            attribute.add_bool(root, "useRefOri", default=True)
        MayaBackend._sync_setting_attrs(root, module)

    @staticmethod
    def _sync_setting_attrs(root, module) -> None:
        """Mirror module fields as real attributes (for UI binding and old-style export)."""
        for name, field_obj in module.fields().items():
            value = getattr(module, name)
            kind = field_obj.type_name
            if kind in ("list", "dict", "vector"):
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

    @staticmethod
    def _tag_legacy_joint(node, module_cls, role: str, side: str) -> None:
        """Old joint labelling: side + type 'Other' with the legacy type name."""
        node["side"].value = _JOINT_SIDES.get(side, 0)
        node["type"].value = 18  # Other
        node["otherType"].value = legacy_type(module_cls, role)

    @staticmethod
    def _apply_poses(nodes: dict, poses: Sequence[GuidePose]) -> None:
        for pose in poses:
            node = nodes.get((pose.role, pose.index))
            if node is None:
                continue
            cmds.xform(node.long_name, worldSpace=True, translation=pose.position)
            # The order must be set before the rotation: xform interprets the
            # euler triple in the node's current rotateOrder.
            cmds.setAttr(f"{node.long_name}.rotateOrder", pose.rotate_order)
            cmds.xform(node.long_name, worldSpace=True, rotation=pose.rotation)

    def apply_guide_poses(self, instance: ModuleInstance) -> None:
        self._apply_poses(self.guide_nodes(instance.instance_id), instance.guides)

    def delete_guides(self, instance_id: str) -> None:
        nodes = self.guide_nodes(instance_id)
        if not nodes:
            return
        holder = self.holder()
        # keep other instances' guides that hang under ours
        for node in nodes.values():
            for child in node.children:
                if child.meta.get(tags.INSTANCE) not in (None, instance_id):
                    child.parent = holder
        cmds.delete([node.long_name for node in nodes.values() if node.exists()])

    def write_settings(self, instance_id: str, settings: dict) -> None:
        instance = self.find_instances([instance_id])
        if not instance:
            raise GuideError(f"No guides for instance {instance_id}.")
        root = self._root_guide(self.guide_nodes(instance_id), instance[0].module_type)
        module_cls = registry.get_module(instance[0].module_type)
        module = module_cls(name=instance[0].name, side=instance[0].side, settings=settings)
        root.meta[tags.SETTINGS] = module.values()
        self._sync_setting_attrs(root, module)

    def settings_plug(self, instance_id: str, field_name: str):
        """The plug holding a module property (for two-way UI binding)."""
        instance = self.find_instances([instance_id])
        if not instance:
            raise GuideError(f"No guides for instance {instance_id}.")
        root = self._root_guide(self.guide_nodes(instance_id), instance[0].module_type)
        return root[field_name]

    # ------------------------------------------------------- .trg records
    def export_guide_records(self, instance_ids=None) -> list[dict]:
        """Serialize scene guides in the legacy ``.trg`` layout (+ explicit keys)."""
        instances = self.find_instances() if instance_ids is None else self.find_instances(list(instance_ids))
        records: list[dict] = []
        for instance in instances:
            module_cls = registry.get_module(instance.module_type)
            nodes = self.guide_nodes(instance.instance_id)
            root_role = module_cls.guides.root
            ordered = sorted(nodes.items(), key=lambda item: (item[0][0] != root_role, item[0][0], item[0][1]))
            for (role, index), node in ordered:
                parent = node.parent
                parent_name = parent.name if parent is not None and parent.meta.get(tags.KIND) == tags.GUIDE else None
                is_root = role == root_role and index == 0
                records.append(make_record(
                    name=node.name,
                    position=cmds.xform(node.long_name, query=True, worldSpace=True, translation=True),
                    rotation=tuple(node.rotate),
                    joint_orient=node.joint_orient,
                    parent=parent_name,
                    side=instance.side,
                    legacy=legacy_type(module_cls, role),
                    module=instance.module_type,
                    role=role,
                    index=index,
                    instance=instance.instance_id,
                    radius=node.radius,
                    color=node.color or 17,
                    settings=dict(instance.settings) if is_root else None,
                    module_name=instance.name if is_root else None,
                ))
        return records

    def import_guide_instances(self, guide_instances) -> list[ModuleInstance]:
        """Recreate guide joints from ``GuideInstance`` records; returns scene instances."""
        holder = self.holder()
        created_nodes: dict[str, tm.Joint] = {}  # record name -> joint
        built: list = []
        with self.undo_chunk("Trigger import guides"):
            for guide_instance in guide_instances:
                module_cls = registry.get_module(guide_instance.module_type)
                module = module_cls(name=guide_instance.name, side=guide_instance.side, settings=guide_instance.settings)
                nodes: dict = {}
                for (role, index), record in guide_instance.joints.items():
                    joint = tm.Joint.create(name=record["name"], radius=record.get("radius", 1.0))
                    joint.world_position = record["position"]
                    joint.joint_orient = record.get("joint_orient", (0, 0, 0))
                    joint.rotate = tuple(record.get("rotation", (0, 0, 0)))
                    joint.color = record.get("color") or 17
                    joint.meta.update({
                        tags.KIND: tags.GUIDE, tags.MODULE: module.module_type, tags.INSTANCE: module.instance_id,
                        tags.ROLE: role, tags.INDEX: index, tags.SIDE: module.side.value,
                    })
                    self._tag_legacy_joint(joint, module_cls, role, module.side.value)
                    nodes[(role, index)] = joint
                    created_nodes[record["name"]] = joint
                root = nodes[(module_cls.guides.root, 0)]
                self._write_root_meta(root, module, None)
                root.meta[INPUTS] = dict(guide_instance.inputs)
                # Legacy .trg records carry no spaces; guard rather than assume.
                root.meta[SPACES] = dict(getattr(guide_instance, "spaces", {}) or {})
                built.append((guide_instance, module, nodes))
            for guide_instance, module, nodes in built:
                for (role, index), record in guide_instance.joints.items():
                    joint = nodes[(role, index)]
                    parent_name = record.get("parent")
                    parent_node = created_nodes.get(parent_name) if parent_name else None
                    joint.parent = parent_node if parent_node is not None else holder
                    cmds.xform(joint.long_name, worldSpace=True, translation=record["position"])
        return [self._instance_from_nodes(module.instance_id, nodes) for _gi, module, nodes in built]

    def read_settings(self, instance_id: str) -> dict:
        instance = self.find_instances([instance_id])
        return dict(instance[0].settings) if instance else {}

    def rename_instance(self, instance_id: str, name: str) -> None:
        instance = self.find_instances([instance_id])
        if not instance:
            raise GuideError(f"No guides for instance {instance_id}.")
        root = self._root_guide(self.guide_nodes(instance_id), instance[0].module_type)
        root.meta[tags.NAME] = name

    def reparent_guides(self, instance_id: str, parent: Optional[ParentRef]) -> None:
        """Hang an instance's root guide under another instance's guide (or the holder)."""
        instance = self.find_instances([instance_id])
        if not instance:
            raise GuideError(f"No guides for instance {instance_id}.")
        root = self._root_guide(self.guide_nodes(instance_id), instance[0].module_type)
        if parent is None:
            target = self.holder()
        else:
            if parent.instance_id == instance_id:
                raise GuideError("Cannot parent guides under themselves.")
            target = self.guide_node(parent.instance_id, parent.role, parent.index)
            # refuse cycles: the target must not live under our root
            node = target
            while node is not None:
                if node.meta.get(tags.INSTANCE) == instance_id:
                    raise GuideError("Cannot parent guides under their own descendants.")
                node = node.parent
        with self.undo_chunk("Trigger reparent guides"):
            root.parent = target

    def make_observer(self, callback):
        from .observer import SceneObserver

        return SceneObserver(callback)

    # ------------------------------------------------------------ selection
    def selected_guide(self) -> Optional[ParentRef]:
        """Return the first selected guide as a ``ParentRef`` (for UI parenting)."""
        for name in cmds.ls(selection=True, long=True, type="joint") or []:
            node = tm.Joint(name)
            if node.meta.get(tags.KIND) == tags.GUIDE and tags.INSTANCE in node.meta:
                return ParentRef(
                    node.meta[tags.INSTANCE],
                    node.meta.get(tags.ROLE, ""),
                    int(node.meta.get(tags.INDEX, 0)),
                )
        return None

    def select_guides(self, instance_id: str) -> None:
        nodes = self.guide_nodes(instance_id)
        cmds.select([node.long_name for node in nodes.values()], replace=True)

    @staticmethod
    def selected_node_name() -> str:
        selected = cmds.ls(selection=True) or []
        return selected[0] if selected else ""

    @staticmethod
    def selected_node_names() -> list[str]:
        return list(cmds.ls(selection=True) or [])

    @staticmethod
    def select_nodes(nodes) -> None:
        names = [getattr(node, "long_name", node) for node in nodes]
        cmds.select(names, replace=True)

    # ---------------------------------------------------------------- build
    def ensure_rig_root(self, rig_name: str) -> tm.Transform:
        for node in tm.find_by_meta(tags.KIND, tags.RIG_ROOT):
            if node.meta.get(tags.NAME) == rig_name:
                return node
        root = tm.Transform.create(name=f"{rig_name}_rig")
        root.meta.update({tags.KIND: tags.RIG_ROOT, tags.NAME: rig_name})
        return root

    def build_context(
        self, module, instance: ModuleInstance, rig_root, bind_parent=None
    ) -> MayaBuildContext:
        guide_nodes = self.guide_nodes(instance.instance_id)
        return MayaBuildContext(module, instance, rig_root, guide_nodes, bind_parent)

    def finalize(self, ctx: MayaBuildContext) -> None:
        for name, node in ctx.outputs.items():
            # Every output is a bind joint, so trg_kind must stay "deform" -
            # overwriting it with "output" would erase the classification that
            # skinning and export read. The output role gets its own key.
            marks = {
                tags.INSTANCE: ctx.instance.instance_id,
                tags.ROLE: name,
                tags.OUTPUT_NAME: name,
            }
            if node.meta.get(tags.KIND) is None:
                marks[tags.KIND] = tags.OUTPUT
            tags.tag(node, **marks)
        for name, node in ctx.attachments.items():
            tags.tag(node, **{tags.KIND: tags.INPUT, tags.INSTANCE: ctx.instance.instance_id, tags.ROLE: name})

    def connect(self, ctx: MayaBuildContext, input_name: str, source_node) -> None:
        target = ctx.attachments[input_name]
        tm.MatrixConstraint.create(
            source_node, target, maintain_offset=True, name=ctx.name("attach", input_name)
        )

    def afterlife(self, instances: Sequence[ModuleInstance], mode: str) -> None:
        if mode == "keep" or not cmds.objExists(tags.GUIDE_HOLDER):
            return
        holder = self.holder()
        if mode == "hide":
            holder.visibility = False
        elif mode == "delete":
            for instance in instances:
                self.delete_guides(instance.instance_id)
            if not holder.children:
                holder.delete()

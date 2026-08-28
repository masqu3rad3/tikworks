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

from . import tags
from .context import MayaBuildContext, MayaGuideContext

logger = logging.getLogger(__name__)


class MayaBackend:
    """Implements ``tik.trigger.core.backend.Backend`` for Maya."""

    name = "maya"

    # ---------------------------------------------------------------- scene
    def new_scene(self) -> None:
        cmds.file(new=True, force=True)

    @contextlib.contextmanager
    def undo_chunk(self, label: str):
        cmds.undoInfo(openChunk=True, chunkName=label)
        try:
            yield
        finally:
            cmds.undoInfo(closeChunk=True)

    # --------------------------------------------------------------- guides
    def holder(self) -> tm.Transform:
        if cmds.objExists(tags.GUIDE_HOLDER):
            return tm.Transform(tags.GUIDE_HOLDER)
        holder = tm.Transform.create(name=tags.GUIDE_HOLDER)
        holder.meta[tags.KIND] = "guide_holder"
        return holder

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

    def _instance_from_nodes(self, instance_id: str, nodes: dict) -> Optional[ModuleInstance]:
        any_node = next(iter(nodes.values()))
        module_type = any_node.meta.get(tags.MODULE, "")
        if not registry.is_module_registered(module_type):
            logger.warning("Skipping guides of unknown module type '%s'.", module_type)
            return None
        root = self._root_guide(nodes, module_type)
        if root is None:
            logger.warning("Instance %s has no root guide; skipped.", instance_id)
            return None
        poses = []
        for (role, index), node in sorted(nodes.items(), key=lambda item: (item[0][0], item[0][1])):
            position = tuple(cmds.xform(node.long_name, query=True, worldSpace=True, translation=True))
            rotation = tuple(cmds.xform(node.long_name, query=True, worldSpace=True, rotation=True))
            poses.append(GuidePose(role, index, position, rotation))
        return ModuleInstance(
            module_type=module_type,
            instance_id=instance_id,
            name=root.meta.get(tags.NAME, module_type),
            side=root.meta.get(tags.SIDE, "C"),
            settings=root.meta.get(tags.SETTINGS, {}) or {},
            guides=poses,
            parent=self._parent_ref(root),
            attach=root.meta.get(tags.ATTACH),
        )

    def find_instances(self, scope: Any = "scene") -> list[ModuleInstance]:
        joints = [
            node
            for node in tm.find_by_meta(tags.KIND, tags.GUIDE, node_type="joint")
            if tags.INSTANCE in node.meta
        ]
        if scope == "selection":
            selected = set(cmds.ls(selection=True, long=True, dagObjects=True) or [])
            joints = [node for node in joints if node.long_name in selected]
        elif scope != "scene":
            wanted = set(scope)
            joints = [node for node in joints if node.meta[tags.INSTANCE] in wanted]

        grouped: dict[str, dict] = {}
        for node in joints:
            grouped.setdefault(node.meta[tags.INSTANCE], {})[
                (node.meta[tags.ROLE], int(node.meta.get(tags.INDEX, 0)))
            ] = node
        if scope == "selection":
            # complete partially selected instances
            for instance_id in list(grouped):
                grouped[instance_id] = self.guide_nodes(instance_id)

        instances = []
        for instance_id, nodes in grouped.items():
            instance = self._instance_from_nodes(instance_id, nodes)
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
            if poses:
                self._apply_poses(ctx.created, poses)
        instance = self._instance_from_nodes(module.instance_id, ctx.created)
        return instance

    @staticmethod
    def _write_root_meta(root, module, attach) -> None:
        root.meta[tags.NAME] = module.name
        root.meta[tags.SETTINGS] = module.values()
        if attach:
            root.meta[tags.ATTACH] = attach

    @staticmethod
    def _apply_poses(nodes: dict, poses: Sequence[GuidePose]) -> None:
        for pose in poses:
            node = nodes.get((pose.role, pose.index))
            if node is None:
                continue
            cmds.xform(node.long_name, worldSpace=True, translation=pose.position)
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
        root.meta[tags.SETTINGS] = dict(settings)

    def read_settings(self, instance_id: str) -> dict:
        instance = self.find_instances([instance_id])
        return dict(instance[0].settings) if instance else {}

    def rename_instance(self, instance_id: str, name: str) -> None:
        instance = self.find_instances([instance_id])
        if not instance:
            raise GuideError(f"No guides for instance {instance_id}.")
        root = self._root_guide(self.guide_nodes(instance_id), instance[0].module_type)
        root.meta[tags.NAME] = name

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

    # ---------------------------------------------------------------- build
    def ensure_rig_root(self, rig_name: str) -> tm.Transform:
        for node in tm.find_by_meta(tags.KIND, tags.RIG_ROOT):
            if node.meta.get(tags.NAME) == rig_name:
                return node
        root = tm.Transform.create(name=f"{rig_name}_rig")
        root.meta.update({tags.KIND: tags.RIG_ROOT, tags.NAME: rig_name})
        return root

    def build_context(self, module, instance: ModuleInstance, rig_root) -> MayaBuildContext:
        guide_nodes = self.guide_nodes(instance.instance_id)
        return MayaBuildContext(module, instance, rig_root, guide_nodes)

    def finalize(self, ctx: MayaBuildContext) -> None:
        for name, node in ctx.plugs.items():
            tags.tag(node, **{tags.KIND: tags.PLUG, tags.INSTANCE: ctx.instance.instance_id, tags.ROLE: name})
        for name, node in ctx.sockets.items():
            tags.tag(node, **{tags.KIND: tags.SOCKET, tags.INSTANCE: ctx.instance.instance_id, tags.ROLE: name})

    def connect(self, child_ctx: MayaBuildContext, parent_ctx: MayaBuildContext, plug_name: str) -> None:
        plug_node = parent_ctx.plugs[plug_name]
        if not child_ctx.sockets:
            raise AttachError(
                f"'{child_ctx.instance.name}' exposes no socket to attach.",
                instance_id=child_ctx.instance.instance_id,
                module_type=child_ctx.instance.module_type,
            )
        socket_name = child_ctx.module.sockets[0]
        socket_node = child_ctx.sockets.get(socket_name) or next(iter(child_ctx.sockets.values()))
        tm.MatrixConstraint.create(
            plug_node,
            socket_node,
            maintain_offset=True,
            name=child_ctx.name("attach"),
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

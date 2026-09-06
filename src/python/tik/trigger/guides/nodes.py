"""Guide joints in the Maya scene: create, tag, scan, pose.

These are the primitives ``GuideScene`` is built from. They hold no state —
the scene is the state. Everything here works in terms of tik.maya nodes and
the ``trg_*`` meta keys in :mod:`tik.trigger.maya.tags`.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Sequence

from maya import cmds

import tik.maya as tm
from tik.maya import naming
from tik.maya.core.decorators import undo_chunk  # noqa: F401 - the guides' undo step
from tik.trigger.core import registry
from tik.trigger.core.exceptions import GuideError
from tik.trigger.core.manifest import instance_key
from tik.trigger.core.schemas import GuidePose, ModuleInstance, ParentRef
from tik.trigger.maya import tags

INPUTS = "trg_inputs"

SIDE_COLORS = {"L": 6, "R": 13, "C": 17}

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------- scene
def new_scene() -> None:
    """Open a new, empty scene without asking, keeping the persp camera."""
    tm.reset_scene()


def scene_node(name: str):
    """The node called ``name``, or None when it does not exist."""
    if not name or not cmds.objExists(name):
        return None
    return tm.resolve(name)


def find_output(instance_id: str, output_name: str):
    """The built node fulfilling ``instance_id``'s ``output_name``, or None.

    How a later build pass reaches a module an earlier one produced. Outputs
    are looked up by their *output* tag, never by their role tag: ``finalize``
    writes ``trg_role`` on a module's inputs as well as its outputs, so one
    instance can legitimately carry the same role name twice.

    Guides are irrelevant here -- an earlier pass may well have deleted its
    own -- so this scans the built rig, not the guide holder.
    """
    pattern = f"*.{tm.META_PREFIX}{tags.OUTPUT_NAME}"
    for name in cmds.ls(pattern, long=True, objectsOnly=True) or []:
        node = tm.resolve(name)
        data = node.meta.as_dict()
        if (
            data.get(tags.INSTANCE) == instance_id
            and data.get(tags.OUTPUT_NAME) == output_name
        ):
            return node
    return None


def holder() -> tm.Transform:
    """The group every unparented guide hangs under."""
    if cmds.objExists(tags.GUIDE_HOLDER):
        return tm.Transform(tags.GUIDE_HOLDER)
    node = tm.Transform.create(name=tags.GUIDE_HOLDER)
    node.meta[tags.KIND] = "guide_holder"
    return node


# ------------------------------------------------------------------ create
def create_guide_joint(
    module,
    role: str,
    position: Sequence[float],
    *,
    index: int = 0,
    parent=None,
    radius: float = 1.0,
) -> tm.Joint:
    """Create one tagged guide joint for ``module``."""
    joint = tm.Joint.create(
        name=naming.format_name(
            module.name,
            role,
            index if index else None,
            side=module.side.value,
            suffix="guide",
        ),
        parent=parent.long_name if hasattr(parent, "long_name") else parent,
        radius=radius,
    )
    joint.world_position = position
    tags.tag(
        joint,
        **{
            tags.KIND: tags.GUIDE,
            tags.MODULE: module.module_type,
            tags.INSTANCE: module.instance_id,
            tags.ROLE: role,
            tags.INDEX: index,
            tags.SIDE: module.side.value,
            # what this rendering was drawn as, so reconcile can notice a
            # rename -- guides are matched on the uuid, never on names
            tags.DRAWN_KEY: instance_key(module.name, module.side.value),
        },
    )
    joint.color = SIDE_COLORS.get(module.side.value, 17)
    return joint


# -------------------------------------------------------------------- read
def guide_nodes(instance_id: str) -> dict[tuple[str, int], tm.Joint]:
    """``{(role, index): joint}`` for one instance."""
    found: dict[tuple[str, int], tm.Joint] = {}
    for node in tm.find_by_meta(tags.INSTANCE, instance_id, node_type="joint"):
        if node.meta.get(tags.KIND) != tags.GUIDE:
            continue
        found[(node.meta[tags.ROLE], int(node.meta.get(tags.INDEX, 0)))] = node
    return found


def guide_node(instance_id: str, role: str, index: int = 0) -> tm.Joint:
    """The joint drawn for ``role``/``index`` of an instance; raises when missing."""
    try:
        return guide_nodes(instance_id)[(role, index)]
    except KeyError:
        raise GuideError(
            f"No guide '{role}' [{index}] for instance {instance_id}."
        ) from None


def root_guide(nodes: dict, module_type: str):
    """The root-role joint out of ``{(role, index): joint}``."""
    return nodes.get((registry.get_module(module_type).guides.root, 0))


def parent_ref(root) -> Optional[ParentRef]:
    """The guide of another instance ``root`` hangs under, if any."""
    parent = root.parent
    own = root.meta.get(tags.INSTANCE)
    while parent is not None:
        instance = parent.meta.get(tags.INSTANCE)
        if instance and instance != own and parent.meta.get(tags.KIND) == tags.GUIDE:
            return ParentRef(
                instance,
                parent.meta.get(tags.ROLE, ""),
                int(parent.meta.get(tags.INDEX, 0)),
            )
        parent = parent.parent
    return None


def instance_from_nodes(
    instance_id: str, nodes: dict, meta: Optional[dict] = None, entry=None
) -> Optional[ModuleInstance]:
    """Build a ``ModuleInstance`` from ``{(role, index): joint}``.

    The joints supply identity and poses only. Name, settings and inputs come
    from ``entry`` -- the module's document entry -- because structure no longer
    lives on the guides; without one the instance carries the module defaults.

    ``meta`` may carry the already-read ``node.meta.as_dict()`` per joint
    (keyed by long name) so a scene scan reads each attribute once.
    """
    meta = meta or {}

    def read(node):
        data = meta.get(node.long_name)
        if data is None:
            data = meta[node.long_name] = node.meta.as_dict()
        return data

    module_type = read(next(iter(nodes.values()))).get(tags.MODULE, "")
    if not registry.is_module_registered(module_type):
        logger.warning("Skipping guides of unknown module type '%s'.", module_type)
        return None
    root = root_guide(nodes, module_type)
    if root is None:
        logger.warning("Instance %s has no root guide; skipped.", instance_id)
        return None
    root_meta = read(root)
    poses = []
    for (role, index), node in sorted(nodes.items(), key=lambda item: item[0]):
        # cmds rather than tik.maya: world-space queries in one call, and this
        # runs once per guide joint on every scene scan.
        position = tuple(
            cmds.xform(node.long_name, query=True, worldSpace=True, translation=True)
        )
        rotation = tuple(
            cmds.xform(node.long_name, query=True, worldSpace=True, rotation=True)
        )
        rotate_order = cmds.getAttr(f"{node.long_name}.rotateOrder")
        poses.append(GuidePose(role, index, position, rotation, rotate_order))
    return ModuleInstance(
        module_type=module_type,
        instance_id=instance_id,
        name=entry.name if entry is not None else module_type,
        side=entry.side if entry is not None else root_meta.get(tags.SIDE, "C"),
        settings=dict(entry.settings) if entry is not None else {},
        guides=poses,
        parent=parent_ref(root),
        inputs=dict(entry.inputs) if entry is not None else {},
    )


def find_instances(scope: Any = "scene", document=None) -> list[ModuleInstance]:
    """Every guide instance in ``scope``, ordered by name.

    ``scope`` is ``"scene"``, ``"selection"``, or a collection of instance ids.
    The scene is scanned once: every guide joint's meta is read a single time.

    Instances are hydrated from the guide document, and their connection sources
    are translated from ``"<uuid>.<output>"`` to ``"<key>.<output>"`` here. The
    uuid is the storage format; the key is the build-time one, and translating
    at this single boundary means the Builder keeps working unchanged and the
    two can never drift -- the map is rebuilt on every scan.
    """
    meta: dict[str, dict] = {}
    joints = []
    # cmds rather than tik.maya: one attribute-qualified ls finds every tagged
    # joint in the scene without walking the DAG.
    for name in (
        cmds.ls(
            f"*.{tm.META_PREFIX}{tags.KIND}", long=True, objectsOnly=True, type="joint"
        )
        or []
    ):
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
        joints = [
            node for node in joints if meta[node.long_name][tags.INSTANCE] in wanted
        ]

    grouped: dict[str, dict] = {}
    for node in joints:
        data = meta[node.long_name]
        grouped.setdefault(data[tags.INSTANCE], {})[
            (data[tags.ROLE], int(data.get(tags.INDEX, 0)))
        ] = node
    if scope == "selection":
        # complete partially selected instances
        for instance_id in list(grouped):
            grouped[instance_id] = guide_nodes(instance_id)

    from tik.trigger.core.guide_document import GuideDocument

    # None means "no document to check against", so the guard below would
    # otherwise reject every instance in the scene.
    known = (
        None if document is None else {entry.instance_id for entry in document.modules}
    )
    document = document if document is not None else GuideDocument()
    keys = {entry.instance_id: entry.key for entry in document.modules}
    instances = []
    for instance_id, nodes in grouped.items():
        if known is not None and instance_id not in known:
            continue  # an orphan: reconcile reports it, the build never sees it
        entry = document.module(instance_id)
        instance = instance_from_nodes(instance_id, nodes, meta, entry)
        if instance is None:
            continue
        instance.inputs = {
            name: _source_as_key(source, keys)
            for name, source in instance.inputs.items()
        }
        instances.append(instance)
    instances.sort(key=lambda item: item.name)
    return instances


def _source_as_key(source: str, keys: dict) -> str:
    """``"<uuid>.hand"`` -> ``"L_arm.hand"``; scene-node sources pass through."""
    if not source or "." not in source:
        return source
    instance_id, _dot, output = source.rpartition(".")
    key = keys.get(instance_id)
    return f"{key}.{output}" if key else source


# -------------------------------------------------------------------- pose
def apply_poses(nodes: dict, poses: Sequence[GuidePose]) -> None:
    """Place ``{(role, index): joint}`` at the given world poses."""
    for pose in poses:
        node = nodes.get((pose.role, pose.index))
        if node is None:
            continue
        cmds.xform(node.long_name, worldSpace=True, translation=pose.position)
        # The order must be set before the rotation: xform interprets the
        # euler triple in the node's current rotateOrder.
        cmds.setAttr(f"{node.long_name}.rotateOrder", pose.rotate_order)
        cmds.xform(node.long_name, worldSpace=True, rotation=pose.rotation)


# --------------------------------------------------------------- selection
def selected_guide() -> Optional[ParentRef]:
    """The first selected guide as a ``ParentRef`` (for UI parenting)."""
    for name in cmds.ls(selection=True, long=True, type="joint") or []:
        node = tm.Joint(name)
        if node.meta.get(tags.KIND) == tags.GUIDE and tags.INSTANCE in node.meta:
            return ParentRef(
                node.meta[tags.INSTANCE],
                node.meta.get(tags.ROLE, ""),
                int(node.meta.get(tags.INDEX, 0)),
            )
    return None


def select_guides(instance_id: str) -> None:
    """Select every guide joint of an instance."""
    tm.select_nodes(list(guide_nodes(instance_id).values()), replace=True)


def select_nodes(nodes) -> None:
    """Replace the selection with ``nodes`` (wrappers or names)."""
    tm.select_nodes(list(nodes), replace=True)


def selected_node_names() -> list[str]:
    """The names of the selected nodes."""
    return list(cmds.ls(selection=True) or [])


def selected_node_name() -> str:
    """The first selected node's name, or ``""``."""
    selected = cmds.ls(selection=True) or []
    return selected[0] if selected else ""

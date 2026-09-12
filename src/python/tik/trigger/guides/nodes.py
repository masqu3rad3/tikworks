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
from tik.trigger.core.manifest import GuideKind, instance_key
from tik.trigger.core.schemas import GuidePose, ModuleInstance, ParentRef
from tik.trigger.maya import tags

INPUTS = "trg_inputs"

SIDE_COLORS = {"L": 6, "R": 13, "C": 17}
MARKER_COLOR = 14  # green: a reference guide, never a chain link

#: The kind -> appearance table. The *only* place a guide's look is decided.
#: A module states a kind; nothing anywhere states a radius or a colour --
#: ``radius=1.5`` on a collar was only ever "this is the module root" written
#: in a language nothing could read.
KIND_RADIUS = {
    GuideKind.ROOT: 1.5,
    GuideKind.JOINT: 1.0,
    GuideKind.DRIVEN: 0.5,
}
#: localScale of a reference guide's locator shape.
REFERENCE_SCALE = 0.6
#: A railed guide reads as subordinate to the chain it sits in, so it takes a
#: darker shade of its side colour rather than a colour of its own.
DRIVEN_COLORS = {"L": 15, "R": 12, "C": 3}
#: Maya's joint-label side enum: 0 centre, 1 left, 2 right, 3 none.
LABEL_SIDES = {"C": 0, "L": 1, "R": 2}

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


def find_output(instance_id: str, output_name: str, under: Optional[str] = None):
    """The built node fulfilling ``instance_id``'s ``output_name``, or None.

    How a later build pass reaches a module an earlier one produced. Outputs
    are looked up by their *output* tag, never by their role tag: ``finalize``
    writes ``trg_role`` on a module's inputs as well as its outputs, so one
    instance can legitimately carry the same role name twice.

    Guides are irrelevant here -- an earlier pass may well have deleted its
    own -- so this scans the built rig, not the guide holder.

    ``under`` is the long path of a rig root. A scene can hold the real rig and
    the Guide Designer's test rig at once, and both answer to the same
    ``trg_instance``; every output is a bind joint, so restricting the scan to
    one root's subtree is exact. None scans the whole scene, which is what a
    caller with no root in hand wants.

    ``recursive`` is what lets the scan see the test rig at all: a wildcard
    ``ls`` does not cross a namespace boundary, and the test rig lives in one.
    It is safe precisely because ``under`` scopes the result -- the two go
    together, and neither is sound on its own.
    """
    pattern = f"*.{tm.META_PREFIX}{tags.OUTPUT_NAME}"
    prefix = f"{under}|" if under else ""
    found = cmds.ls(pattern, long=True, objectsOnly=True, recursive=True) or []
    for name in found:
        if prefix and not name.startswith(prefix):
            continue
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
def make_guide_shell(name: str, kind: GuideKind, parent=None) -> tm.Transform:
    """The bare node for one guide of ``kind`` -- no tags, no pose, no label.

    Shared by a fresh draw and by ``.trg`` import, so the two can never
    disagree about what a kind renders as.

    A ``REFERENCE`` guide is a plain transform because that is the only thing
    that suppresses the bone. Measured in Maya: the bone belongs to the
    *parent* joint, so ``drawStyle`` on the child does nothing and
    ``drawStyle`` on the parent removes every one of its bones; and an
    intervening transform does not break it either, because joint drawing
    walks through transforms to find descendant joints. A non-joint child
    draws nothing at all, which is the whole mechanism.
    """
    parent_name = parent.long_name if hasattr(parent, "long_name") else parent
    if kind is GuideKind.REFERENCE:
        node = tm.Transform.create(name=name, parent=parent_name)
        # The shape is created straight under the transform rather than via
        # ``spaceLocator`` and a reparent: importing a ``.trg`` draws a scratch
        # copy of a module beside the real one, so two guides legitimately
        # share a short name, and anything that looks one up by it raises.
        shape = tm.create_node("locator", name=f"{name}Shape", parent=node.long_name)
        for axis in "XYZ":
            shape[f"localScale{axis}"].value = REFERENCE_SCALE
        return node
    return tm.Joint.create(name=name, parent=parent_name, radius=KIND_RADIUS[kind])


def guide_color(kind: GuideKind, side: str) -> int:
    """The colour index for a guide of ``kind`` on ``side``."""
    if kind is GuideKind.REFERENCE:
        return MARKER_COLOR
    table = DRIVEN_COLORS if kind is GuideKind.DRIVEN else SIDE_COLORS
    return table.get(side, 17)


def create_guide_node(
    module,
    role: str,
    position: Sequence[float],
    *,
    kind: GuideKind,
    index: int = 0,
    parent=None,
    tag_role: str = "",
) -> tm.Transform:
    """Create one tagged guide node for ``module``, rendered by its ``kind``.

    ``tag_role`` is the role the *document* keys this guide by, when that
    differs from the one the node is named after. A module's second copy
    keys its guides ``c1_root`` while the joint reads ``L_thumb_root_guide``:
    the slug is bookkeeping and has no business in a name a rigger reads.
    Defaults to ``role``, which is every non-copy case.
    """
    name = naming.format_name(
        module.name,
        role,
        index if index else None,
        side=module.side.value,
        suffix="guide",
    )
    node = make_guide_shell(name, kind, parent=parent)
    node.world_position = position
    tags.tag(
        node,
        **{
            tags.KIND: tags.GUIDE,
            tags.MODULE: module.module_type,
            tags.INSTANCE: module.instance_id,
            tags.ROLE: tag_role or role,
            tags.INDEX: index,
            tags.SIDE: module.side.value,
            # what this rendering was drawn as, so reconcile can notice a
            # rename -- guides are matched on the uuid, never on names
            tags.DRAWN_KEY: instance_key(module.name, module.side.value),
        },
    )
    node.color = guide_color(kind, module.side.value)
    return node


# -------------------------------------------------------------------- read
def guide_nodes(instance_id: str) -> dict[tuple[str, int], tm.Transform]:
    """``{(role, index): node}`` for one instance.

    ``node_type="transform"`` rather than ``"joint"``: ``joint`` inherits from
    ``transform``, so this is a widening that cannot lose a node, and a
    reference guide *is* a transform. The KIND check below is what makes it
    exact -- it always was; the joint filter was only ever narrowing for speed.
    """
    found: dict[tuple[str, int], tm.Transform] = {}
    for node in tm.find_by_meta(tags.INSTANCE, instance_id, node_type="transform"):
        if node.meta.get(tags.KIND) != tags.GUIDE:
            continue
        found[(node.meta[tags.ROLE], int(node.meta.get(tags.INDEX, 0)))] = node
    return found


def guide_node(instance_id: str, role: str, index: int = 0) -> tm.Transform:
    """The node drawn for ``role``/``index`` of an instance; raises when missing."""
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
    # guide node in the scene without walking the DAG. type="transform" catches
    # joints too -- joint inherits from transform -- and reference guides are
    # transforms; the KIND check below is what makes the result exact.
    for name in (
        cmds.ls(
            f"*.{tm.META_PREFIX}{tags.KIND}",
            long=True,
            objectsOnly=True,
            type="transform",
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
    for name in cmds.ls(selection=True, long=True, type="transform") or []:
        node = tm.resolve(name)
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

"""``GuideScene``: the guides in the current Maya scene.

Authoring, settings, connections, layout and ``.trg`` exchange, in one place.
The joint-level primitives it is built on live in :mod:`.nodes`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from maya import cmds

import tik.maya as tm
from tik.core.side import Side
from tik.trigger.core import registry
from tik.trigger.core.events import EventBus
from tik.trigger.core.exceptions import GuideError
from tik.trigger.core.guide_document import GuideDocument
from tik.trigger.core.manifest import instance_key
from tik.trigger.core.schemas import GuidePose, ModuleInstance, ParentRef
from tik.trigger.maya import tags
from tik.trigger.maya.rig import GuideDraft

from . import nodes
from . import regenerate as regenerate_module
from .capture import capture
from .format import GuideFile, make_record
from .handle import GuideHandle, mirror_source
from .regenerate import regenerate
from .snapshot import snapshot


class GuideScene:
    """The guides in the current Maya scene: author, connect, exchange, build."""

    def __init__(self, events: Optional[EventBus] = None, session=None) -> None:
        self.events = events or EventBus()
        self._session = session
        # unbound: a free-standing document for scripting, that no session sees
        self._own = None if session is not None else GuideDocument()
        self._syncing = False
        # Governs ONE thing: whether a scene event may start a sync. It must
        # never gate the capture in _apply -- "a write always captures first;
        # Auto only decides whether the scene may start a sync" (spec 3.1).
        # Nothing in Maya fires when a guide is dragged, so a write that skipped
        # capture would redraw from stale records and discard the posing.
        self.auto_sync = True

    # ------------------------------------------------------- the document
    @property
    def session(self):
        """The session that owns these guides, or None when unbound."""
        return self._session

    @property
    def document(self) -> GuideDocument:
        """The guides. Owned by the session; the Maya scene only renders them."""
        return self._session.document.guides if self._session is not None else self._own

    def _touch(self) -> None:
        """Record the edit on the session's undo stack."""
        if self._session is not None:
            self._session.touch()

    def _apply(self, entry) -> None:
        """Persist an edit and redraw the module it touched.

        Capture comes first, and that is the whole point: **nothing in Maya
        fires when a guide is dragged**, so the document only learns a pose
        when we go and read it. A redraw that skipped this would rebuild from
        stale records and throw the rigger's posing away -- which is exactly
        what changing any property used to do.
        """
        capture(self.document, snapshot())
        self._touch()
        regenerate(entry, self.document)

    def clear_rendering(self) -> None:
        """Delete every guide joint in the scene without touching the document.

        Every guide, not just this document's: taking the scene over from
        another session has to clear what is actually drawn.
        """
        drawn = {guide.node for guide in snapshot()}
        if not drawn:
            return
        with nodes.undo_chunk("Trigger clear guides"):
            cmds.delete([name for name in drawn if cmds.objExists(name)])

    def _module_for(self, entry):
        module_cls = registry.get_module(entry.module_type)
        return module_cls(
            instance_id=entry.instance_id,
            name=entry.name,
            side=entry.side,
            settings=dict(entry.settings),
        )

    def _primary_input_name(self, entry) -> Optional[str]:
        primary = registry.get_module(entry.module_type).primary_input()
        return primary.name if primary else None

    @property
    def dismissed(self) -> bool:
        """True when the guides are deliberately not drawn (a build cleared them)."""
        return self.document.dismissed

    @dismissed.setter
    def dismissed(self, value: bool) -> None:
        self.document.dismissed = bool(value)

    def restore(self):
        """Draw the guides again after a build took them away."""
        self.dismissed = False
        return self.sync()

    def sync(self, regenerate_stale: bool = True):
        """Capture, reconcile, and redraw whatever is structurally stale.

        The order is the point (spec 5): capture runs first, so pose drift is
        absorbed *before* reconcile sees it and can never be mistaken for a
        reason to redraw a guide the rigger has just dragged.

        Args:
            regenerate_stale: False computes and reports without touching the
                scene -- the checkpointed policy.

        Returns:
            The :class:`~tik.trigger.core.reconcile.GuideDiff`. Reflects the
            scene as it now stands: if regenerate actually redrew anything,
            the diff is recomputed afterwards so callers (the drift pill)
            never see staleness this same call just fixed. When nothing was
            regenerated -- nothing was stale, or ``dismissed`` forced the
            redraw off -- the original diff comes back unchanged, which is
            already accurate (``dismissed`` legitimately still reports its
            outstanding staleness).
        """
        from tik.trigger.core.reconcile import GuideDiff

        if self._syncing:
            return GuideDiff()
        self._syncing = True
        try:
            rendered = snapshot()
            if capture(self.document, rendered):
                self._touch()
            diff = self.diff()
            # a rendering that is *meant* to be absent is not damage
            if regenerate_stale and self.dismissed:
                regenerate_stale = False
            if regenerate_stale and diff.structural:
                with nodes.undo_chunk("Trigger lockstep redraw"):
                    stale = [
                        entry
                        for entry in regenerate_module.ordered(self.document)
                        if entry.instance_id in set(diff.structural)
                    ]
                    for entry in stale:
                        regenerate(entry, self.document)
                # GuideDiff.structural is a property over fixed ModuleDiff
                # records -- nothing recomputes it just because the loop
                # above mutated the scene. Rescan once, only here, so the
                # diff we return matches what regenerate actually did.
                diff = self.diff()
            return diff
        finally:
            self._syncing = False

    def diff(self):
        """Reconcile the document against what the scene renders."""
        from tik.trigger.core.reconcile import reconcile

        return reconcile(
            self.document, snapshot(), primary_input_of=self._primary_input_name
        )

    def snapshot_from_scene(self) -> tuple:
        """Read the scene into a fresh document. Commits nothing.

        The caller shows the report first: replacing the module list is
        destructive, so it never happens as a side effect of looking.
        """
        from .from_scene import read

        return read()

    def inputs_as_keys(self, entry) -> dict:
        """``{input: "<key>.<output>"}`` -- uuid sources resolved for display."""
        keys = {item.instance_id: item.key for item in self.document.modules}
        found = {}
        for name, source in entry.inputs.items():
            if source and "." in source:
                instance_id, _dot, output = source.rpartition(".")
                key = keys.get(instance_id)
                found[name] = f"{key}.{output}" if key else source
            else:
                found[name] = source
        return found

    def source_as_id(self, source: str) -> str:
        """``"L_arm.hand"`` -> ``"<uuid>.hand"``; scene-node sources pass through."""
        if not source or "." not in source:
            return source
        key, _dot, output = source.rpartition(".")
        entry = self.document.by_key(key)
        if entry is not None:
            return f"{entry.instance_id}.{output}"
        if self.document.module(key) is not None:
            return source  # already a uuid
        return source

    # ------------------------------------------------------- scene access
    def find_instances(self, scope: Any = "scene") -> list[ModuleInstance]:
        """Build-time instances: identity and settings from the document, poses
        from the joints."""
        return nodes.find_instances(scope, self.document)

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
    def create_guides(
        self, module, parent=None, poses=None, inputs=None
    ) -> ModuleInstance:
        """Write a module's document entry, then render its guides."""
        from tik.trigger.core.guide_document import ModuleEntry, expand_guides

        if self.document.module(module.instance_id) is not None:
            raise GuideError(f"Module {module.instance_id} already exists.")
        resolved = {
            name: self.source_as_id(source) for name, source in (inputs or {}).items()
        }
        if not resolved and parent is not None and module.primary_input() is not None:
            # convenience: drawing under another module's guide pre-fills the
            # primary input with a real value
            producer = self.document.module(parent.instance_id)
            if producer is not None:
                parent_cls = registry.get_module(producer.module_type)
                output = parent_cls.output_at_role(parent.role)
                if output:
                    resolved = {
                        module.primary_input().name: f"{producer.instance_id}.{output}"
                    }
        entry = ModuleEntry(
            instance_id=module.instance_id,
            module_type=module.module_type,
            name=module.name,
            side=module.side.value,
            settings=module.values(),
            inputs=resolved,
        )
        expand_guides(entry, module.guides, module.guide_count())
        for pose in poses or []:
            record = entry.guide(pose.role, pose.index)
            if record is not None:
                record.position = tuple(pose.position)
                record.rotation = tuple(pose.rotation)
                record.rotate_order = pose.rotate_order
        with nodes.undo_chunk(f"Trigger guides: {module.name}"):
            self.dismissed = False  # authoring again means showing them again
            self.document.modules.append(entry)
            created = regenerate(entry, self.document)
            if not created:
                raise GuideError(f"'{module.module_type}' drew no guides.")
            if not poses:
                # the first render defines the poses the document then owns
                capture(self.document, snapshot())
            self._touch()
        return nodes.instance_from_nodes(module.instance_id, created, entry=entry)

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
        """Rename a module. Guide joint names follow on the next regenerate."""
        entry = self._entry(instance_id)
        with nodes.undo_chunk("Trigger rename module"):
            entry.name = name
            self._apply(entry)

    def reparent_guides(self, instance_id: str, parent: Optional[ParentRef]) -> None:
        """Hang an instance's root guide under another's guide, or the holder."""
        root = self._root_node(instance_id)
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
                    raise GuideError(
                        "Cannot parent guides under their own descendants."
                    )
                node = node.parent
        with nodes.undo_chunk("Trigger reparent guides"):
            root.parent = target

    def apply_guide_poses(self, instance: ModuleInstance) -> None:
        nodes.apply_poses(nodes.guide_nodes(instance.instance_id), instance.guides)

    # ----------------------------------------------------------- settings
    def set_inputs(self, instance_id: str, inputs: dict) -> None:
        """Replace a module's connections wholesale."""
        entry = self._entry(instance_id)
        with nodes.undo_chunk("Trigger set inputs"):
            entry.inputs = {
                name: self.source_as_id(source)
                for name, source in dict(inputs).items()
                if source
            }
            self._apply(entry)

    def set_input(
        self, instance_id: str, input_name: str, source: Optional[str]
    ) -> None:
        """Connect or disconnect one input."""
        entry = self._entry(instance_id)
        with nodes.undo_chunk("Trigger set input"):
            if source:
                entry.inputs[input_name] = self.source_as_id(source)
            else:
                entry.inputs.pop(input_name, None)
            self._apply(entry)

    def read_settings(self, instance_id: str) -> dict:
        entry = self.document.module(instance_id)
        return dict(entry.settings) if entry is not None else {}

    def write_settings(self, instance_id: str, settings: dict) -> None:
        """Store settings and redraw, so the guides match them immediately.

        A settings change that adds or removes guides (``fkchain.segments``)
        expands the entry first, which keeps every surviving pose.
        """
        from tik.trigger.core.guide_document import expand_guides

        entry = self._entry(instance_id)
        module_cls = registry.get_module(entry.module_type)
        module = module_cls(
            instance_id=instance_id, name=entry.name, side=entry.side, settings=settings
        )
        with nodes.undo_chunk("Trigger module settings"):
            entry.settings = module.values()
            expand_guides(entry, module.guides, module.guide_count())
            self._apply(entry)

    def _root_node(self, instance_id: str):
        """This module's root guide joint, from the document's module type."""
        entry = self._entry(instance_id)
        module_cls = registry.get_module(entry.module_type)
        root = nodes.guide_nodes(instance_id).get((module_cls.guides.root, 0))
        if root is None:
            raise GuideError(f"Module '{entry.name}' has no root guide in the scene.")
        return root

    def _entry(self, instance_id: str):
        entry = self.document.module(instance_id)
        if entry is None:
            raise GuideError(f"No module {instance_id}.")
        return entry

    # ------------------------------------------------------- .trg records
    def export_guide_records(self, instance_ids=None) -> list[dict]:
        """Serialize scene guides as ``.trg`` joint records."""
        found = nodes.find_instances(
            "scene" if instance_ids is None else list(instance_ids), self.document
        )
        records: list[dict] = []
        for instance in found:
            module_cls = registry.get_module(instance.module_type)
            joints = nodes.guide_nodes(instance.instance_id)
            root_role = module_cls.guides.root
            ordered = sorted(
                joints.items(),
                key=lambda item: (item[0][0] != root_role, item[0][0], item[0][1]),
            )
            for (role, index), node in ordered:
                parent = node.parent
                parent_name = (
                    parent.name
                    if parent is not None and parent.meta.get(tags.KIND) == tags.GUIDE
                    else None
                )
                is_root = role == root_role and index == 0
                declared = module_cls.attrs_for_role(role)
                attrs = {item.name: node[item.name].value for item in declared}
                records.append(
                    make_record(
                        name=node.name,
                        position=cmds.xform(
                            node.long_name,
                            query=True,
                            worldSpace=True,
                            translation=True,
                        ),
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
                    )
                )
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
        """Recreate guide joints from ``GuideInstance`` records; return instances."""
        holder = nodes.holder()
        created_nodes: dict = {}  # record name -> joint
        built: list = []
        extras: dict = {}  # instance_id -> roles the file predates
        with nodes.undo_chunk("Trigger import guides"):
            for guide_instance in guide_instances:
                module_cls = registry.get_module(guide_instance.module_type)
                module = module_cls(
                    name=guide_instance.name,
                    side=guide_instance.side,
                    settings=guide_instance.settings,
                )
                joints: dict = {}
                for (role, index), record in guide_instance.joints.items():
                    joint = tm.Joint.create(
                        name=record["name"], radius=record.get("radius", 1.0)
                    )
                    joint.world_position = record["position"]
                    joint.joint_orient = record.get("joint_orient", (0, 0, 0))
                    joint.rotate = tuple(record.get("rotation", (0, 0, 0)))
                    joint.color = record.get("color") or 17
                    for item in module_cls.attrs_for_role(role):
                        plug = joint[item.name].create(
                            "float", default=item.default, keyable=item.keyable
                        )
                        plug.value = record.get("attrs", {}).get(
                            item.name, item.default
                        )
                    joint.meta.update(
                        {
                            tags.KIND: tags.GUIDE,
                            tags.MODULE: module.module_type,
                            tags.INSTANCE: module.instance_id,
                            tags.ROLE: role,
                            tags.INDEX: index,
                            tags.SIDE: module.side.value,
                        }
                    )
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
                built.append((guide_instance, module, joints))
            for guide_instance, module, joints in built:
                for (role, index), record in guide_instance.joints.items():
                    joint = joints[(role, index)]
                    parent_name = record.get("parent")
                    parent_node = (
                        created_nodes.get(parent_name) if parent_name else None
                    )
                    joint.parent = parent_node if parent_node is not None else holder
                    cmds.xform(
                        joint.long_name, worldSpace=True, translation=record["position"]
                    )
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
            self._entries_from_import(built)
        # guide_nodes rather than the joints we built: a renamed module was
        # redrawn, so the dict from before is full of deleted nodes
        return [
            nodes.instance_from_nodes(
                module.instance_id,
                nodes.guide_nodes(module.instance_id),
                entry=self.document.module(module.instance_id),
            )
            for _gi, module, _joints in built
        ]

    def _entries_from_import(self, built) -> None:
        """Create document entries for imported guides and wire their inputs.

        A ``.trg`` names its connections by display key, and import mints fresh
        uuids, so sources are resolved in a second pass once every key is known.
        """
        from tik.trigger.core.guide_document import ModuleEntry, expand_guides

        document = self.document
        entries = {}
        # The file's keys, mapped to the ids we mint for them. Built from the
        # *original* names, because that is what the file's own connections say.
        original_keys = {}
        for guide_instance, module, _joints in built:
            module.name = self.unique_name(module.name, module.side.value)
            entry = ModuleEntry(
                instance_id=module.instance_id,
                module_type=module.module_type,
                name=module.name,
                side=module.side.value,
                settings=module.values(),
            )
            expand_guides(entry, module.guides, module.guide_count())
            # radius/colour/orient aren't captured from the scene (spec 4.2 gap),
            # so the .trg file is their only source -- fill them in directly from
            # what the file recorded, for regenerate to re-apply from here on.
            for pair, record in guide_instance.joints.items():
                target = entry.guide(*pair)
                if target is None:
                    continue
                target.radius = float(record.get("radius", 1.0))
                target.color = int(record.get("color") or 17)
                target.joint_orient = tuple(record.get("joint_orient", (0.0, 0.0, 0.0)))
            # appended as we go, so a two-module import uniquifies against itself
            document.modules.append(entry)
            entries[module.instance_id] = (entry, guide_instance)
            original_keys[guide_instance.key] = entry.instance_id

        def as_instance_source(source: str) -> str:
            """``<file key>.<output>`` -> ``<instance id>.<output>``; nodes as-is."""
            key, dot, output = source.rpartition(".")
            if dot and key in original_keys:
                return f"{original_keys[key]}.{output}"
            return source

        for entry, guide_instance in entries.values():
            entry.inputs = {
                name: as_instance_source(source)
                for name, source in guide_instance.inputs.items()
                if source
            }
        # the imported joints are the authored poses, so record them
        capture(document, snapshot())
        for entry, _gi in entries.values():
            self._touch()
        # Every imported entry gets a regenerate, producers before consumers:
        # a renamed module needs its joints redrawn under the new name, and
        # every module needs one so its root guide picks up the entry
        # breadcrumb that only regenerate stamps (spec 4.1). Poses were just
        # captured above, so this redraw lands exactly where the file put them.
        imported_ids = set(entries)
        for ordered_entry in regenerate_module.ordered(document):
            if ordered_entry.instance_id in imported_ids:
                regenerate(ordered_entry, document)

    # ----------------------------------------------------------- listing
    def instances(self) -> list[GuideHandle]:
        return [GuideHandle(self, entry.instance_id) for entry in self.document.modules]

    def roots(self) -> list[GuideHandle]:
        return [handle for handle in self.instances() if handle.parent is None]

    def get(self, instance_id: str) -> Optional[GuideHandle]:
        entry = self.document.module(instance_id)
        return GuideHandle(self, entry.instance_id) if entry is not None else None

    def find(self, name: str, side: Optional[str] = None) -> Optional[GuideHandle]:
        for entry in self.document.modules:
            if entry.name == name and (
                side is None or entry.side == Side.from_value(side).value
            ):
                return GuideHandle(self, entry.instance_id)
        return None

    def __getitem__(self, name: str) -> GuideHandle:
        handle = self.find(name)
        if handle is None:
            raise GuideError(f"No guides named '{name}'.")
        return handle

    def clear(self) -> None:
        with nodes.undo_chunk("Trigger clear guides"):
            for entry in list(self.document.modules):
                self.delete_guides(entry.instance_id)
            self.document.modules = []
            self._touch()

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
        self.create_guides(module, parent=parent_ref, inputs=inputs)
        return GuideHandle(self, module.instance_id)

    def unique_name(self, name: str, side: str) -> str:
        """``arm`` -> ``arm``, ``arm1``, ``arm2``... until ``<side>_<name>`` is free."""
        taken = {entry.key for entry in self.document.modules} | {
            group.name for group in self.document.scene_groups
        }
        base = name.rstrip("0123456789") or name
        candidate, index = name, 1
        while instance_key(candidate, side) in taken:
            candidate = f"{base}{index}"
            index += 1
        return candidate

    def remove(self, handle: GuideHandle) -> None:
        """Delete a module: its entry, its guides and its layout."""
        instance_id = handle.instance_id
        with nodes.undo_chunk("Trigger remove module"):
            self.delete_guides(instance_id)
            document = self.document
            document.modules = [
                entry for entry in document.modules if entry.instance_id != instance_id
            ]
            document.positions.pop(instance_id, None)
            document.collapse.pop(instance_id, None)
            for entry in document.modules:
                entry.inputs = {
                    name: source
                    for name, source in entry.inputs.items()
                    if source.rpartition(".")[0] != instance_id
                }
            self._touch()

    # ------------------------------------------------------------ layout
    @property
    def layout(self) -> dict:
        """Designer state stored with the guides, projected under display keys.

        ``{"scene_nodes": {group: [node, ...]}, "positions": {key: [x, y]},
        "collapse": {key: 0|1|2}}``
        """
        return self.document.layout_as_keys()

    def set_layout(self, layout: dict) -> None:
        """Store designer state back into the document, keyed by id."""
        self.document.layout_from_keys(dict(layout))
        with nodes.undo_chunk("Trigger designer layout"):
            self._touch()

    def update_layout(self, **sections) -> dict:
        """Replace whole sections (``positions=``, ``scene_nodes=``, ``collapse=``)."""
        layout = self.layout
        for name, value in sections.items():
            layout[name] = value
        self.set_layout(layout)
        return layout

    # ------------------------------------------------------ scene nodes
    def scene_groups(self) -> dict[str, list[str]]:
        """``{group name: [scene node, ...]}``: Maya nodes modules connect to."""
        return {
            name: list(nodes)
            for name, nodes in self.layout.get("scene_nodes", {}).items()
        }

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
        document = self.document
        for table in (document.positions, document.collapse):
            if old in table:
                table[new] = table.pop(old)
        self.update_layout(scene_nodes=groups)

    def remove_scene_group(self, name: str) -> None:
        groups = self.scene_groups()
        nodes = set(groups.pop(name, []))
        self.update_layout(scene_nodes=groups)
        for item in self.connections():
            if item["source"] in nodes and not self.scene_node_group(item["source"]):
                self.disconnect(item["input"])
        document = self.document
        document.positions.pop(name, None)
        document.collapse.pop(name, None)
        self._touch()

    def scene_node_group(self, node: str) -> Optional[str]:
        """The group that lists scene node ``node`` (first match)."""
        for name, members in self.scene_groups().items():
            if node in members:
                return name
        return None

    # -------------------------------------------------------- connections
    def by_key(self, key: str) -> Optional[GuideHandle]:
        entry = self.document.by_key(key)
        return GuideHandle(self, entry.instance_id) if entry is not None else None

    def connect(self, target: str, source: str) -> None:
        """Connect an input to a module output or a scene node.

        ``connect("L_arm.root", "body.root")`` or ``connect("tail.space", "jnt")``.
        """
        key, _dot, input_name = target.rpartition(".")
        handle = self.by_key(key)
        if handle is None or not input_name:
            raise GuideError(f"No module input '{target}'.")
        source_key, _d, output = source.rpartition(".")
        producer = self.by_key(source_key) if source_key else None
        if producer is not None and output not in producer.outputs:
            raise GuideError(
                f"'{source_key}' has no output '{output}' "
                f"(has {list(producer.outputs)})."
            )
        handle.set_input(input_name, source)

    def disconnect(self, target: str) -> None:
        key, _dot, input_name = target.rpartition(".")
        handle = self.by_key(key)
        if handle is None:
            raise GuideError(f"No module input '{target}'.")
        handle.set_input(input_name, None)

    def connections(self) -> list[dict]:
        """``[{"input": "L_arm.root", "source": "spine.hip"}]`` -- display keys."""
        found = []
        for entry in self.document.modules:
            for input_name, source in self.inputs_as_keys(entry).items():
                found.append({"input": f"{entry.key}.{input_name}", "source": source})
        return found

    def reparent(
        self, handle: GuideHandle, parent: Optional[GuideHandle | ParentRef]
    ) -> None:
        """Attach ``handle`` to ``parent``, or detach it.

        This sets the *primary input*, not the DAG: guide parenting is a
        rendering of the connection graph and is rebuilt from it on every
        regenerate (spec 4.4), so there is only one hierarchy to keep straight.
        """
        primary = handle.module_class.primary_input()
        if primary is None:
            raise GuideError(f"'{handle.module_type}' has no primary input.")
        if parent is None:
            self.set_input(handle.instance_id, primary.name, None)
            return
        producer_id = parent.instance_id
        if producer_id == handle.instance_id:
            raise GuideError("Cannot attach a module to itself.")
        producer = self._entry(producer_id)
        producer_cls = registry.get_module(producer.module_type)
        role = getattr(parent, "role", None) or producer_cls.guides.root
        output = producer_cls.output_at_role(role) or producer_cls.outputs[0]
        self.set_input(handle.instance_id, primary.name, f"{producer_id}.{output}")

    def mirror(self, handle: GuideHandle) -> GuideHandle:
        """Create (or update) the opposite-side copy of ``handle``."""
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
            GuidePose(
                pose.role,
                pose.index,
                (-pose.position[0], pose.position[1], pose.position[2]),
                (pose.rotation[0], -pose.rotation[1], -pose.rotation[2]),
                pose.rotate_order,
            )
            for pose in instance.guides
        ]
        if existing is not None:
            from tik.trigger.core.guide_document import expand_guides

            # Capture *before* writing the mirrored poses, not after: this
            # method sets poses deliberately, and the usual capture-then-redraw
            # of ``_apply`` would overwrite them with what the scene still shows.
            capture(self.document, snapshot())
            existing_entry = existing.entry
            module_cls = registry.get_module(existing_entry.module_type)
            module = module_cls(
                instance_id=existing_entry.instance_id,
                name=existing_entry.name,
                side=existing_entry.side,
                settings=instance.settings,
            )
            existing_entry.settings = module.values()
            expand_guides(existing_entry, module.guides, module.guide_count())
            existing_entry.inputs = {
                name: self.source_as_id(
                    mirror_source(source, handle.side.value, target_side.value)
                )
                for name, source in instance.inputs.items()
                if source
            }
            for pose in poses:
                record = existing_entry.guide(pose.role, pose.index)
                if record is not None:
                    record.position = tuple(pose.position)
                    record.rotation = tuple(pose.rotation)
                    record.rotate_order = pose.rotate_order
            self._touch()
            regenerate(existing_entry, self.document)
            return existing
        module = handle.module_class(
            name=instance.name, side=target_side, settings=instance.settings
        )
        mirrored_inputs = {
            name: mirror_source(source, handle.side.value, target_side.value)
            for name, source in instance.inputs.items()
        }
        self.create_guides(
            module, parent=instance.parent, poses=poses, inputs=mirrored_inputs
        )
        return GuideHandle(self, module.instance_id)

    def duplicate(self, handle: GuideHandle, name: Optional[str] = None) -> GuideHandle:
        """Copy a module with a unique name (``arm`` -> ``arm1``).

        Type, side, settings, inputs and poses are copied.
        """
        instance = handle.instance
        module = handle.module_class(
            name=name or instance.name, side=instance.side, settings=instance.settings
        )
        module.name = self.unique_name(module.name, module.side.value)
        self.create_guides(
            module, poses=list(instance.guides), inputs=dict(instance.inputs)
        )
        collapse = self.document.collapse
        if handle.instance_id in collapse:
            collapse[module.instance_id] = collapse[handle.instance_id]
            self._touch()
        return GuideHandle(self, module.instance_id)

    # ------------------------------------------------------------- build
    def test_build(self, *handles: GuideHandle, rig_name: str = "test") -> Any:
        scope = [handle.instance_id for handle in handles] or "scene"
        from tik.trigger.maya.build import Builder

        # poses may have been edited by hand since the last sync
        self.sync(regenerate_stale=False)
        return Builder(self.events).build(
            scope=scope, document=self.document, rig_name=rig_name, afterlife="keep"
        )

    # ------------------------------------------------------------ files
    def export(self, file_path, *handles: GuideHandle) -> Path:
        wanted = {handle.instance_id for handle in handles} or None
        records = self.export_guide_records(wanted)
        keys = {handle.key for handle in (handles or self.instances())}
        connections = [
            item for item in self.connections() if item["input"].split(".")[0] in keys
        ]
        layout = self.layout
        sources = {item["source"] for item in connections}
        groups = {
            name: nodes
            for name, nodes in layout.get("scene_nodes", {}).items()
            if not handles or set(nodes) & sources
        }
        wanted = keys | set(groups)
        designer = {
            "scene_nodes": groups,
            "positions": {
                key: value
                for key, value in layout.get("positions", {}).items()
                if key in wanted
            },
            "collapse": {
                key: value
                for key, value in layout.get("collapse", {}).items()
                if key in wanted
            },
        }
        designer = {name: value for name, value in designer.items() if value}
        return GuideFile(records, connections, designer=designer).save(file_path)

    def import_(self, file_path, reset: bool = False) -> list[GuideHandle]:
        guide_file = GuideFile.load(file_path)
        instances = guide_file.instances()
        if guide_file.unknown:
            self.events.log(
                f"Guide file has unknown module types: {guide_file.unknown}",
                level="warning",
            )
        if reset:
            self.clear()
            self.set_layout({})
        created = self.import_guide_instances(instances)
        if guide_file.designer:
            layout = {} if reset else self.layout
            for section in ("scene_nodes", "positions", "collapse"):
                merged = dict(layout.get(section, {}))
                merged.update(guide_file.designer.get(section, {}))
                if merged:
                    layout[section] = merged
            self.set_layout(layout)
        return [GuideHandle(self, item.instance_id) for item in created]

    load = import_

    def __repr__(self) -> str:
        return f"GuideLayout({len(self.instances())} instances)"

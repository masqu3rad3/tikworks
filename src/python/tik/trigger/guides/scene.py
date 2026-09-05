"""``GuideScene``: the guides in the current Maya scene.

Authoring, settings, connections, layout and ``.trg`` exchange, in one place.
The joint-level primitives it is built on live in :mod:`.nodes`.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from maya import cmds

from tik.core.side import Side
from tik.trigger.core import registry
from tik.trigger.core.events import EventBus
from tik.trigger.core.exceptions import GuideError
from tik.trigger.core.guide_document import GuideDocument
from tik.trigger.core.manifest import instance_key
from tik.trigger.core.schemas import GuidePose, ModuleInstance, ParentRef
from tik.trigger.maya import tags

from . import nodes
from . import regenerate as regenerate_module
from .capture import capture
from .exchange import GuideExchangeMixin
from .handle import GuideHandle, mirror_source
from .regenerate import regenerate
from .scene_groups import SceneGroupsMixin
from .snapshot import snapshot


class GuideScene(GuideExchangeMixin, SceneGroupsMixin):
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
        # Creation is the one automatic draw left: the rigger just asked for
        # the module and it has no joints yet, so nothing can be moved or
        # discarded. It governs creation and nothing else -- it can never
        # bring back the redraw-on-edit this design removed.
        self.draw_on_create = True

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
        """Record a document edit. **The scene is not touched.**

        This used to capture and then redraw the module. Both are gone: a
        redraw that happens because a field changed is the tool moving the
        rigger's work without being asked, and the capture only existed to
        stop that redraw from rebuilding on stale records. With no redraw
        there is nothing to protect against, and capture goes back to being a
        deliberate act -- ``sync()``.

        ``entry`` is kept so every call site reads as "apply this entry", and
        so a future change can scope work to it without touching them all.
        """
        self._touch()

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

    def sync(self, scope: Optional[Iterable[str]] = None):
        """Read the scene's poses and guide attrs into the document.

        One direction, always. Sync can create nothing, delete nothing and
        move nothing: after this call the scene is what it was. Rebuilding a
        rendering is :meth:`draw`'s job and only ever happens because
        somebody pressed a button.

        Args:
            scope: Instance ids to capture, or None for every module.

        Returns:
            The :class:`~tik.trigger.core.reconcile.GuideDiff` as the scene
            now stands.
        """
        from tik.trigger.core.reconcile import GuideDiff

        if self._syncing:
            return GuideDiff()
        self._syncing = True
        try:
            if capture(self.document, snapshot(), scope=scope):
                self._touch()
            return self.diff()
        finally:
            self._syncing = False

    def draw(self, scope: Optional[Iterable[str]] = None, poses: str = "keep"):
        """Render modules into the scene, rebuilding what is already there.

        The other direction, and the only thing that ever creates a guide
        joint. Never automatic once a module exists: every call is a button
        somebody pressed.

        Args:
            scope: Instance ids to draw, or None for every module.
            poses: ``"keep"`` captures the scoped drift first, so a guide the
                rigger has dragged goes back where they put it.
                ``"discard"`` skips that capture and rebuilds at the stored
                poses.

        Returns:
            The :class:`~tik.trigger.core.reconcile.GuideDiff` afterwards.

        Raises:
            GuideError: when ``poses`` is neither ``"keep"`` nor ``"discard"``.
        """
        if poses not in ("keep", "discard"):
            raise GuideError(f"draw(poses={poses!r}): expected 'keep' or 'discard'.")
        wanted = None if scope is None else set(scope)
        entries = [
            entry
            for entry in regenerate_module.ordered(self.document)
            if wanted is None or entry.instance_id in wanted
        ]
        if not entries:
            return self.diff()
        if poses == "keep":
            # Scoped deliberately: drawing one module must not quietly pull
            # the rest of the scene into the document as a side effect.
            if capture(
                self.document,
                snapshot(),
                scope=[entry.instance_id for entry in entries],
            ):
                self._touch()
        with nodes.undo_chunk("Trigger draw guides"):
            for entry in entries:
                regenerate(entry, self.document)
        return self.diff()

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
        """The joint for ``role``/``index`` of an instance; raises when missing."""
        return nodes.guide_node(instance_id, role, index)

    def guide_nodes(self, instance_id: str) -> dict:
        """``{(role, index): joint}`` for one instance."""
        return nodes.guide_nodes(instance_id)

    def select_guides(self, instance_id: str) -> None:
        """Select every guide joint of an instance."""
        nodes.select_guides(instance_id)

    def scene_node(self, name: str):
        """The Maya node called ``name``, or None (used to validate sources)."""
        return nodes.scene_node(name)

    def selected_guide(self) -> Optional[ParentRef]:
        """The first selected guide as a ``ParentRef``, or None."""
        return nodes.selected_guide()

    def selected_node_name(self) -> str:
        """The first selected node's name, or ``""``."""
        return nodes.selected_node_name()

    def selected_node_names(self) -> list[str]:
        """The names of the selected nodes."""
        return nodes.selected_node_names()

    def select_nodes(self, items) -> None:
        """Replace the selection with ``items`` (nodes or names)."""
        nodes.select_nodes(items)

    def make_observer(self, callback):
        """A scene observer that calls ``callback`` on scene events."""
        from tik.trigger.maya.observer import SceneObserver

        return SceneObserver(callback)

    # ---------------------------------------------------------- authoring
    def _write_entry(self, module, parent=None, poses=None, inputs=None):
        """Write a module's document entry. **Touches nothing in the scene.**

        Split out of :meth:`create_guides` so ``add()`` can put a module in
        the session without rendering it -- which is what lets opening a
        session or importing a ``.trg`` leave the scene alone.
        """
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
        self.document.modules.append(entry)
        self._touch()
        return entry

    def create_guides(
        self, module, parent=None, poses=None, inputs=None
    ) -> ModuleInstance:
        """Write a module's document entry, draw it, and own the first render.

        The draw is not optional here and the name says so: this is the
        low-level call scripts and tests use to get guides into the scene.
        The authoring path is :meth:`add`, which consults ``draw_on_create``.

        The capture at the end is where a module's poses come from at all:
        ``expand_guides`` writes unposed records and the module's own
        ``draw_guides`` decides where its guides actually sit, so the
        document only learns those positions by drawing once and reading
        them back.
        """
        with nodes.undo_chunk(f"Trigger guides: {module.name}"):
            entry = self._write_entry(module, parent, poses, inputs)
            created = regenerate(entry, self.document)
            if not created:
                raise GuideError(f"'{module.module_type}' drew no guides.")
            if not poses:
                capture(self.document, snapshot(), scope=[entry.instance_id])
        return nodes.instance_from_nodes(module.instance_id, created, entry=entry)

    def delete_guides(self, instance_id: str) -> None:
        """Delete an instance's guides, keeping other instances' guides under them."""
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
        """Move an instance's guide joints to the poses it records."""
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
        """A copy of the settings stored for an instance (empty when unknown)."""
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

    # ----------------------------------------------------------- listing
    def instances(self) -> list[GuideHandle]:
        """A handle for every module in the document."""
        return [GuideHandle(self, entry.instance_id) for entry in self.document.modules]

    def roots(self) -> list[GuideHandle]:
        """The modules with no parent."""
        return [handle for handle in self.instances() if handle.parent is None]

    def get(self, instance_id: str) -> Optional[GuideHandle]:
        """The handle for ``instance_id``, or None."""
        entry = self.document.module(instance_id)
        return GuideHandle(self, entry.instance_id) if entry is not None else None

    def find(self, name: str, side: Optional[str] = None) -> Optional[GuideHandle]:
        """The first module called ``name`` (on ``side`` when given), or None."""
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
        """Remove every module and its guide joints (one undo step)."""
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
        """Add a module to the session, drawing it when ``draw_on_create`` is set.

        ``parent`` also hangs the joints under that guide and pre-fills the primary
        input; ``inputs`` sets connections explicitly without any scene parenting
        (what the Guide Designer does).
        """
        module_cls = registry.get_module(module_type)
        module = module_cls(name=name, side=side, settings=settings)
        module.name = self.unique_name(module.name, module.side.value)
        parent_ref = parent
        if isinstance(parent, GuideHandle):
            parent_ref = ParentRef(parent.instance_id, parent.module_class.guides.root)
        if self.draw_on_create:
            self.create_guides(module, parent=parent_ref, inputs=inputs)
        else:
            self._write_entry(module, parent=parent_ref, inputs=inputs)
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

    # -------------------------------------------------------- connections
    def by_key(self, key: str) -> Optional[GuideHandle]:
        """The handle for display key ``key`` (``L_arm``), or None."""
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
        """Clear the input at ``<key>.<input>``."""
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
    def test_build(self, *handles: GuideHandle) -> Any:
        """Build the given modules (or every module) into a throwaway rig.

        Draws first, and has to: ``find_instances`` reads tagged joints, so a
        module nobody has drawn contributes nothing and would be skipped in
        silence. The sync before it makes that draw lossless, which is why
        this path never has to ask about discarding poses.
        """
        ids = [handle.instance_id for handle in handles]
        scope = ids or "scene"
        from tik.trigger.maya.build import Builder

        self.sync()
        self.draw(ids or None)
        return Builder(self.events).build(
            scope=scope, document=self.document, afterlife="keep"
        )

    def __repr__(self) -> str:
        return f"GuideLayout({len(self.instances())} instances)"

"""An in-memory stand-in for ``GuideScene``, for the Qt tests.

Maya standalone cannot host a QApplication — creating one crashes the
interpreter — so ``tests/ui`` runs with ``TIK_TESTS_NO_MAYA=1`` and never has
a scene. This is an ordinary Qt test double: it keeps ``ModuleInstance``
objects in a dict, hands back real ``GuideHandle`` objects, and records the
calls the tests assert on. It exists only so the designer's *wiring* can be
tested; what the guides do in Maya is covered by ``tests/integration``.
"""

from __future__ import annotations

from typing import Optional

from tik.core.side import Side
from tik.trigger.core import registry
from tik.trigger.core.events import EventBus
from tik.trigger.core.exceptions import GuideError
from tik.trigger.core.manifest import instance_key
from tik.trigger.core.reconcile import GuideDiff
from tik.trigger.core.schemas import GuidePose, ModuleInstance, ParentRef
from tik.trigger.guides.format import GuideFile
from tik.trigger.guides.handle import GuideHandle, mirror_source


class StubScene:
    """The ``GuideScene`` surface the Guide Designer touches."""

    def __init__(self) -> None:
        self.events = EventBus()
        self._instances: dict[str, ModuleInstance] = {}
        self.calls: list[tuple] = []
        self.scene_nodes: set[str] = set()
        self.selection: Optional[ParentRef] = None
        # stored by id, exactly like the real document, so a rename
        # cannot orphan a node's position
        self._positions: dict = {}
        self._collapse: dict = {}
        self._scene_nodes: dict = {}
        # what write_settings stored, so tests can assert on it directly
        self.settings: dict[str, dict] = {}
        self._scene_jobs: dict = {}
        self._cache: Optional[list] = None
        self._document_cache = None
        # matches GuideScene's default (spec 3.1): governs whether a scene
        # event may start a sync, nothing else
        self.auto_sync = True
        # mirrors GuideScene.session: None for a free-standing double, or set
        # by a test to the Session that owns it -- snapshot_guides reads this
        self.session = None

    # ------------------------------------------------------------ document
    @property
    def document(self):
        """A ``GuideDocument`` view over the stub's instances.

        The Designer reads structure through the document now, so the double
        has to speak it too. Built on demand from ``_instances`` -- this is a
        test stand-in, not a store.
        """
        from tik.trigger.core.guide_document import (
            GuideDocument,
            GuideRecord,
            ModuleEntry,
            SceneGroup,
        )

        if self._document_cache is not None:
            return self._document_cache
        document = GuideDocument()
        for instance_id in self._snapshot():
            instance = self._instances[instance_id]
            entry = ModuleEntry(
                instance_id=instance.instance_id,
                module_type=instance.module_type,
                name=instance.name,
                side=instance.side,
                settings=dict(instance.settings),
                inputs=dict(instance.inputs),
                guides=[
                    GuideRecord(
                        role=pose.role,
                        index=pose.index,
                        position=tuple(pose.position),
                        rotation=tuple(pose.rotation),
                        rotate_order=pose.rotate_order,
                    )
                    for pose in instance.guides
                ],
            )
            document.modules.append(entry)
        document.scene_groups = [
            SceneGroup(group_id=name, name=name, nodes=list(group_nodes))
            for name, group_nodes in self._scene_nodes.items()
        ]
        document.positions = dict(self._positions)
        document.collapse = dict(self._collapse)
        self._document_cache = document
        return document

    def inputs_as_keys(self, entry) -> dict:
        """The stub stores sources as display keys already."""
        return dict(entry.inputs)

    def set_input(self, instance_id: str, input_name: str, source) -> None:
        instance = self._instances[instance_id]
        if source:
            instance.inputs[input_name] = source
        else:
            instance.inputs.pop(input_name, None)
        self.calls.append(("set_input", instance_id, input_name, source))
        self._invalidate()

    def guide_nodes(self, instance_id: str) -> dict:
        instance = self._instances.get(instance_id)
        if instance is None:
            return {}
        return {
            (pose.role, pose.index): f"{instance.key}_{pose.role}{pose.index}"
            for pose in instance.guides
        }

    # ------------------------------------------------------------ listing
    def _invalidate(self) -> None:
        """Internal to the double. The real GuideScene has no such method --
        the session's document is always current -- so this is deliberately
        not named ``invalidate``: a stub that keeps a removed method alive is
        how a stale call site survives the test suite."""
        self._cache = None
        self._document_cache = None

    def _snapshot(self) -> list:
        """Instance ids, in scan order."""
        if self._cache is None:
            self._cache = [item.instance_id for item in self.find_instances()]
        return self._cache

    def instances(self) -> list[GuideHandle]:
        return [GuideHandle(self, item) for item in self._snapshot()]

    def roots(self) -> list[GuideHandle]:
        return [item for item in self.instances() if item.parent is None]

    def get(self, instance_id: str) -> Optional[GuideHandle]:
        found = instance_id in self._instances
        return GuideHandle(self, instance_id) if found else None

    def find(self, name: str, side: Optional[str] = None) -> Optional[GuideHandle]:
        for handle in self.instances():
            if handle.name == name and (
                side is None or handle.side == Side.from_value(side)
            ):
                return handle
        return None

    def by_key(self, key: str) -> Optional[GuideHandle]:
        return next((handle for handle in self.instances() if handle.key == key), None)

    def __getitem__(self, name: str) -> GuideHandle:
        handle = self.find(name)
        if handle is None:
            raise GuideError(f"No guides named '{name}'.")
        return handle

    # ---------------------------------------------------------- authoring
    def unique_name(self, name: str, side: str) -> str:
        taken = {handle.key for handle in self.instances()} | set(
            self.layout.get("scene_nodes", {})
        )
        base = name.rstrip("0123456789") or name
        candidate, index = name, 1
        while instance_key(candidate, side) in taken:
            candidate = f"{base}{index}"
            index += 1
        return candidate

    def add(
        self, module_type, side="C", name=None, parent=None, inputs=None, **settings
    ) -> GuideHandle:
        module_cls = registry.get_module(module_type)
        module = module_cls(name=name, side=side, settings=settings)
        module.name = self.unique_name(module.name, module.side.value)
        parent_ref = parent
        if isinstance(parent, GuideHandle):
            parent_ref = ParentRef(parent.instance_id, parent.module_class.guides.root)
        resolved = dict(inputs or {})
        if (
            not resolved
            and parent_ref is not None
            and module.primary_input() is not None
        ):
            producer = self._instances.get(parent_ref.instance_id)
            if producer is not None:
                output = registry.get_module(producer.module_type).output_at_role(
                    parent_ref.role
                )
                if output:
                    resolved = {module.primary_input().name: f"{producer.key}.{output}"}
        instance = module.to_instance(
            guides=[GuidePose(role, index) for role, index in module.expected_guides()],
            parent=parent_ref,
            inputs=resolved,
        )
        self._instances[instance.instance_id] = instance
        self.calls.append(("create_guides", instance.instance_id))
        self._invalidate()
        return GuideHandle(self, instance.instance_id)

    def remove(self, handle: GuideHandle) -> None:
        key = handle.key  # read before the instance is gone
        self.delete_guides(handle.instance_id)

    def delete_guides(self, instance_id: str) -> None:
        self._instances.pop(instance_id, None)
        self.calls.append(("delete_guides", instance_id))
        self._invalidate()

    def clear(self) -> None:
        self._instances.clear()
        self._invalidate()

    def duplicate(self, handle: GuideHandle, name: Optional[str] = None) -> GuideHandle:
        instance = handle.instance
        copy = handle.module_class(
            name=name or instance.name, side=instance.side, settings=instance.settings
        )
        copy.name = self.unique_name(copy.name, copy.side.value)
        created = copy.to_instance(
            guides=list(instance.guides), inputs=dict(instance.inputs)
        )
        self._instances[created.instance_id] = created
        self._invalidate()
        collapse = self.layout.get("collapse", {})
        if handle.key in collapse:
            collapse[copy.key] = collapse[handle.key]
            self.update_layout(collapse=collapse)
        return GuideHandle(self, created.instance_id)

    def mirror(self, handle: GuideHandle) -> GuideHandle:
        instance = handle.instance
        if handle.side is Side.CENTER:
            raise GuideError("Center guides cannot be mirrored.")
        target = handle.side.mirror
        mirrored = {
            name: mirror_source(source, handle.side.value, target.value)
            for name, source in instance.inputs.items()
        }
        existing = self.find(instance.name, target.value)
        if existing is not None:
            self.set_inputs(existing.instance_id, mirrored)
            return existing
        module = handle.module_class(
            name=instance.name, side=target, settings=instance.settings
        )
        created = module.to_instance(guides=list(instance.guides), inputs=mirrored)
        self._instances[created.instance_id] = created
        self._invalidate()
        return GuideHandle(self, created.instance_id)

    def reparent(self, handle: GuideHandle, parent) -> None:
        parent_ref = parent
        if isinstance(parent, GuideHandle):
            parent_ref = ParentRef(parent.instance_id, parent.module_class.guides.root)
        self.reparent_guides(handle.instance_id, parent_ref)

    def reparent_guides(self, instance_id: str, parent: Optional[ParentRef]) -> None:
        # data only: the designer never parents joints, and the tests assert it
        self.calls.append(
            ("reparent", instance_id, parent.instance_id if parent else None)
        )

    def rename_instance(self, instance_id: str, name: str) -> None:
        self._instances[instance_id].name = name
        self._invalidate()

    # ----------------------------------------------------------- settings
    def read_settings(self, instance_id: str) -> dict:
        return dict(self._instances[instance_id].settings)

    def write_settings(self, instance_id: str, settings: dict) -> None:
        self._instances[instance_id].settings = dict(settings)
        self.settings[instance_id] = dict(settings)
        self._invalidate()

    def set_inputs(self, instance_id: str, inputs: dict) -> None:
        self._instances[instance_id].inputs = {
            key: value for key, value in inputs.items() if value
        }
        self._invalidate()

    # -------------------------------------------------------- connections
    def connect(self, target: str, source: str) -> None:
        key, _dot, input_name = target.rpartition(".")
        handle = self.by_key(key)
        if handle is None or not input_name:
            raise GuideError(f"No module input '{target}'.")
        source_key, _d, output = source.rpartition(".")
        producer = self.by_key(source_key) if source_key else None
        if producer is not None and output not in producer.outputs:
            raise GuideError(f"'{source_key}' has no output '{output}'.")
        handle.set_input(input_name, source)

    def disconnect(self, target: str) -> None:
        key, _dot, input_name = target.rpartition(".")
        handle = self.by_key(key)
        if handle is None:
            raise GuideError(f"No module input '{target}'.")
        handle.set_input(input_name, None)

    def connections(self) -> list[dict]:
        return [
            {"input": f"{handle.key}.{name}", "source": source}
            for handle in self.instances()
            for name, source in handle.inputs.items()
        ]

    # ------------------------------------------------------------ layout
    @property
    def layout(self) -> dict:
        return self.document.layout_as_keys()

    def set_layout(self, layout: dict) -> None:
        document = self.document
        document.layout_from_keys(layout)
        self._scene_nodes = {
            group.name: list(group.nodes) for group in document.scene_groups
        }
        self._positions = dict(document.positions)
        self._collapse = dict(document.collapse)
        self._invalidate()

    def update_layout(self, **sections) -> dict:
        layout = self.layout
        layout.update(sections)
        self.set_layout(layout)
        return layout

    # ------------------------------------------------------- scene nodes
    def scene_groups(self) -> dict[str, list[str]]:
        return {
            name: list(nodes)
            for name, nodes in self.layout.get("scene_nodes", {}).items()
        }

    def add_scene_group(self, name: str = "", nodes: Optional[list] = None) -> str:
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

    def set_scene_group(self, name: str, nodes: list) -> None:
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

    def remove_scene_group(self, name: str) -> None:
        groups = self.scene_groups()
        gone = set(groups.pop(name, []))
        self.update_layout(scene_nodes=groups)
        for item in self.connections():
            if item["source"] in gone and not self.scene_node_group(item["source"]):
                self.disconnect(item["input"])

    def scene_node_group(self, node: str) -> Optional[str]:
        for name, nodes in self.scene_groups().items():
            if node in nodes:
                return name
        return None

    # --------------------------------------------------------- selection
    def scene_node(self, name: str):
        return name if name in self.scene_nodes else None

    def selected_guide(self) -> Optional[ParentRef]:
        return self.selection

    def select_guides(self, instance_id: str) -> None:
        self.calls.append(("select", instance_id))

    def select_nodes(self, nodes) -> None:
        self.calls.append(("select_nodes", [str(node) for node in nodes]))

    def selected_node_name(self) -> str:
        return "picked_node"

    def selected_node_names(self) -> list[str]:
        return list(getattr(self, "selected_names", []))

    def sync(self, regenerate_stale: bool = True):
        """No scene to reconcile against; the double just records the call.

        Matches ``GuideScene.sync()``'s contract -- callers now use this
        return value instead of a second ``diff()`` walk, so the stub must
        hand back a ``GuideDiff`` too, not ``None``.
        """
        self.calls.append(("sync",))
        return GuideDiff()

    def diff(self):
        """Stands in for a clean scene: nothing stale, nothing drifted."""
        self.calls.append(("diff",))
        return GuideDiff()

    def snapshot_from_scene(self):
        """An empty, lossless read by default; a test overrides this to shape
        the ``RecoveryReport`` the snapshot command sees."""
        from tik.trigger.core.guide_document import GuideDocument
        from tik.trigger.core.scene_recovery import RecoveryReport

        self.calls.append(("snapshot_from_scene",))
        return GuideDocument(), RecoveryReport()

    def find_instances(self, scope="scene") -> list:
        """The one scene scan the handles share; tests count calls to it."""
        return list(self._instances.values())

    def install_scene_job(self, event, callback):
        self._scene_jobs[event] = callback
        return len(self._scene_jobs)

    def kill_scene_job(self, job) -> None:
        pass

    def fire(self, event) -> None:
        callback = self._scene_jobs.get(event)
        if callback:
            callback()

    def make_observer(self, callback):
        self.observer_callback = callback

        class _Observer:
            active = False
            muted = False

            def start(self_inner):
                self_inner.active = True

            def stop(self_inner):
                self_inner.active = False

        return _Observer()

    def guide_node(self, instance_id: str, role: str, index: int = 0) -> str:
        return f"{instance_id}_{role}_{index}"

    # ------------------------------------------------------------- files
    # Joint records are the scene's job; the tests monkeypatch these two and
    # assert on everything the designer itself authored.
    def export_guide_records(self, instance_ids=None) -> list:
        """Minimal but real ``.trg`` joint records, so a file round-trips.

        Without these the file carries no modules, nothing is recreated on
        import, and layout keyed by module identity is (correctly) dropped --
        which would make an export/import test assert nothing.
        """
        from tik.trigger.guides.format import make_record

        records = []
        for instance in self._instances.values():
            if instance_ids is not None and instance.instance_id not in instance_ids:
                continue
            module_cls = registry.get_module(instance.module_type)
            root_role = module_cls.guides.root
            for pose in instance.guides:
                is_root = pose.role == root_role and pose.index == 0
                records.append(
                    make_record(
                        name=f"{instance.key}_{pose.role}{pose.index}",
                        position=pose.position,
                        rotation=pose.rotation,
                        joint_orient=(0, 0, 0),
                        parent=None,
                        side=instance.side,
                        module=instance.module_type,
                        role=pose.role,
                        index=pose.index,
                        instance=instance.instance_id,
                        settings=dict(instance.settings) if is_root else None,
                        module_name=instance.name if is_root else None,
                    )
                )
        return records

    def import_guide_instances(self, guide_instances) -> list:
        """Recreate instances from ``.trg`` records.

        Real enough that layout keyed by module identity survives an import --
        with nothing created, there would be no module for a position to belong
        to and the projection would (correctly) drop it.
        """
        created = []
        for guide_instance in guide_instances:
            instance = ModuleInstance(
                module_type=guide_instance.module_type,
                instance_id=guide_instance.instance_id,
                name=guide_instance.name,
                side=guide_instance.side,
                settings=dict(guide_instance.settings),
                guides=[
                    GuidePose(role, index, tuple(record.get("position", (0, 0, 0))))
                    for (role, index), record in guide_instance.joints.items()
                ],
                inputs=dict(guide_instance.inputs),
            )
            self._instances[instance.instance_id] = instance
            created.append(instance)
        self._invalidate()
        return created

    def export(self, file_path, *handles):
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

    def import_(self, file_path, reset: bool = False):
        guide_file = GuideFile.load(file_path)
        instances = guide_file.instances()
        if reset:
            self.clear()
            self.set_layout({})
        created = self.import_guide_instances(instances)
        self._invalidate()
        if guide_file.designer:
            layout = {} if reset else self.layout
            for section in ("scene_nodes", "positions", "collapse"):
                merged = dict(layout.get(section, {}))
                merged.update(guide_file.designer.get(section, {}))
                if merged:
                    layout[section] = merged
            self.set_layout(layout)
        return [GuideHandle(self, item.instance_id) for item in created]

    def test_build(self, *handles, rig_name: str = "test"):
        self.calls.append(("test_build", len(handles)))
        return None

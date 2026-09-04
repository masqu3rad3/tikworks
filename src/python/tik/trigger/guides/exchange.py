"""The ``.trg`` side of ``GuideScene``: joint records out, guide instances in."""

from __future__ import annotations

from pathlib import Path
from maya import cmds
import tik.maya as tm
from tik.trigger.core import registry
from tik.trigger.core.schemas import ModuleInstance
from tik.trigger.maya import tags
from tik.trigger.maya.rig import GuideDraft
from . import nodes
from . import regenerate as regenerate_module
from .capture import capture
from .format import GuideFile, make_record
from .handle import GuideHandle
from .regenerate import regenerate
from .snapshot import snapshot


class GuideExchangeMixin:
    """Mixed into :class:`~.scene.GuideScene`; reads and writes through ``self``."""

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

    # ------------------------------------------------------------ files
    def export(self, file_path, *handles: GuideHandle) -> Path:
        """Write the given modules (or every module) to a ``.trg`` file."""
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
        """Add the modules of a ``.trg`` file; ``reset`` clears the scene first."""
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

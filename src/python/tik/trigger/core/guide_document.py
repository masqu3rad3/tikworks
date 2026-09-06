"""The guide document: every guide fact, keyed by instance uuid.

Pure data. The document -- not the scene -- is the durable home for which
modules exist, what they are connected to, where their guides sit, and what the
Guide Designer laid out. Guide joints in Maya are a *rendering* of this, owned
by it and rebuildable from it.

A connection source is ``"<instance_id>.<output>"`` for a module, or a bare Maya
node name for a scene node; ``core.schemas.split_source`` splits both, because
Maya node names cannot contain a dot.

An unposed :class:`GuideRecord` (``position is None``) means "no authored pose
yet" -- regenerate places it wherever the module's ``draw_guides`` puts it,
never at the origin. The same rule now covers ``joint_orient``, ``radius`` and
``color``: ``None`` means "never authored", so regenerate leaves whatever the
module's own ``draw_guides`` (or ``create_guide_joint``) chose -- side colour
included -- rather than stamping a default over it.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Optional

SCHEMA_VERSION = 2


def _serialize_references(document) -> list:
    """Links carrying freshly diffed overrides. Local import: avoids a cycle."""
    from .guide_reference import serialize_references

    return serialize_references(document)


def _triple(value, default=(0.0, 0.0, 0.0)) -> tuple:
    return default if value is None else tuple(float(item) for item in value)


@dataclass
class GuideRecord:
    """One guide joint's durable data."""

    role: str
    index: int = 0
    #: ``None`` means "never authored"; regenerate uses the draw_guides pose.
    position: Optional[tuple] = None
    rotation: Optional[tuple] = None
    rotate_order: int = 0
    #: ``None`` means "never authored"; regenerate leaves draw_guides' choice.
    joint_orient: Optional[tuple] = None
    #: ``None`` means "never authored"; regenerate leaves draw_guides' choice.
    radius: Optional[float] = None
    #: ``None`` means "never authored"; regenerate leaves draw_guides' choice
    #: (e.g. the module's per-side colour), rather than overwriting it.
    color: Optional[int] = None
    #: Values of the module's declared ``guide_attrs`` for this guide.
    attrs: dict = field(default_factory=dict)
    #: ``(role, index)`` of this guide's parent *within the same module*.
    parent: Optional[tuple] = None

    @property
    def pair(self) -> tuple:
        """``(role, index)``, the identity of a guide within its module."""
        return (self.role, self.index)

    @property
    def posed(self) -> bool:
        """True once a pose has been captured or imported for this guide."""
        return self.position is not None

    def to_dict(self) -> dict:
        """The JSON form stored in the document."""
        return {
            "role": self.role,
            "index": self.index,
            "position": list(self.position) if self.position is not None else None,
            "rotation": list(self.rotation) if self.rotation is not None else None,
            "rotate_order": self.rotate_order,
            "joint_orient": (
                list(self.joint_orient) if self.joint_orient is not None else None
            ),
            "radius": self.radius,
            "color": self.color,
            "attrs": dict(self.attrs),
            "parent": list(self.parent) if self.parent else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GuideRecord":
        """Rebuild a record from its JSON form; missing fields stay ``None``."""
        parent = data.get("parent")
        position = data.get("position")
        rotation = data.get("rotation")
        joint_orient = data.get("joint_orient")
        radius = data.get("radius")
        color = data.get("color")
        return cls(
            role=data["role"],
            index=int(data.get("index", 0)),
            position=None if position is None else _triple(position),
            rotation=None if rotation is None else _triple(rotation),
            rotate_order=int(data.get("rotate_order", 0)),
            joint_orient=None if joint_orient is None else _triple(joint_orient),
            radius=None if radius is None else float(radius),
            color=None if color is None else int(color),
            attrs={
                key: float(value) for key, value in (data.get("attrs") or {}).items()
            },
            parent=(str(parent[0]), int(parent[1])) if parent else None,
        )


@dataclass
class ModuleEntry:
    """One module instance: identity, settings, connections and its guides."""

    instance_id: str
    module_type: str
    name: str
    side: str = "C"
    settings: dict = field(default_factory=dict)
    #: ``{input name: "<instance_id>.<output>" | "<scene node>"}``
    inputs: dict = field(default_factory=dict)
    guides: list = field(default_factory=list)
    #: Resolution state, never serialized on the entry itself. ``origin`` is
    #: the ``ref_id`` of the link this entry arrived through (None when it is
    #: this session's own); ``source`` is a deep copy of it before overrides,
    #: so the difference between the two *is* the override set. ``enabled`` is
    #: False only for a referenced module the host left out of its rig
    #: deliberately -- which is what tells an unbuilt-module warning apart
    #: from a decision.
    #:
    #: ``compare=False`` matters: these would otherwise join the generated
    #: ``__eq__`` and make comparing two entries recurse through ``source``.
    origin: Optional[str] = field(default=None, compare=False, repr=False)
    source: Optional["ModuleEntry"] = field(default=None, compare=False, repr=False)
    enabled: bool = field(default=True, compare=False)

    @property
    def key(self) -> str:
        """Display key: ``L_arm`` / ``spine``. Never an identity -- that is the uuid."""
        return self.name if self.side in ("C", "") else f"{self.side}_{self.name}"

    @property
    def pairs(self) -> list:
        """``(role, index)`` of every guide this module owns."""
        return [record.pair for record in self.guides]

    def guide(self, role: str, index: int = 0) -> Optional[GuideRecord]:
        """The record for ``role``/``index``, or None."""
        for record in self.guides:
            if record.role == role and record.index == index:
                return record
        return None

    def to_dict(self) -> dict:
        """The JSON form stored in the document."""
        return {
            "instance_id": self.instance_id,
            "module_type": self.module_type,
            "name": self.name,
            "side": self.side,
            "settings": dict(self.settings),
            "inputs": dict(self.inputs),
            "guides": [record.to_dict() for record in self.guides],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ModuleEntry":
        """Rebuild an entry from its JSON form."""
        return cls(
            instance_id=data["instance_id"],
            module_type=data["module_type"],
            name=data.get("name", data["module_type"]),
            side=data.get("side", "C"),
            settings=dict(data.get("settings") or {}),
            inputs=dict(data.get("inputs") or {}),
            guides=[GuideRecord.from_dict(item) for item in data.get("guides", [])],
        )


@dataclass
class ModuleReference:
    """A link to another session's modules.

    The link and its overrides are the only things stored. The modules
    themselves are resolved out of the referenced file every time the document
    is loaded, so an upstream change arrives without anything here being
    touched -- which is the whole difference between referencing and copying.
    """

    ref_id: str
    file: str
    version: str = "latest"
    #: True when a pipeline ``reference`` action created this link. Such a
    #: link lives and dies with that action; one made by hand through
    #: *Reference Modules...* answers to nobody and is never auto-removed.
    auto: bool = False
    #: ``{instance_id: {enabled, name, side, settings, inputs, guides}}``, where
    #: a guide key is ``"<role>:<index>"``. Produced by diffing, never written
    #: by hand -- see ``core.guide_reference.overrides_for``.
    overrides: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """The JSON form stored in the document."""
        return {
            "ref_id": self.ref_id,
            "file": self.file,
            "version": self.version,
            "auto": self.auto,
            "overrides": copy.deepcopy(self.overrides),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ModuleReference":
        """Rebuild a reference from its JSON form."""
        return cls(
            ref_id=data["ref_id"],
            file=data.get("file", ""),
            version=data.get("version", "latest"),
            auto=bool(data.get("auto", False)),
            overrides=copy.deepcopy(data.get("overrides") or {}),
        )


@dataclass
class SceneGroup:
    """A named bag of arbitrary Maya nodes modules can connect to."""

    group_id: str
    name: str
    nodes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        """The JSON form stored in the document."""
        return {"group_id": self.group_id, "name": self.name, "nodes": list(self.nodes)}

    @classmethod
    def from_dict(cls, data: dict) -> "SceneGroup":
        """Rebuild a group from its JSON form."""
        return cls(
            group_id=data["group_id"],
            name=data.get("name", data["group_id"]),
            nodes=list(data.get("nodes") or []),
        )


@dataclass
class GuideDocument:
    """Every guide fact for one rig. Keyed by uuid throughout."""

    schema: int = SCHEMA_VERSION
    modules: list = field(default_factory=list)
    scene_groups: list = field(default_factory=list)
    #: Links to other sessions' modules.
    references: list = field(default_factory=list)
    #: Graph frame placement per reference: ``{ref_id: {position, collapsed}}``.
    #: Deliberately *not* ``positions``/``collapse``: those are projected
    #: through ``node_ids()`` and replaced wholesale by ``layout_from_keys``,
    #: so a frame stored there would be deleted by the first node drag.
    frames: dict = field(default_factory=dict)
    #: Graph node positions, keyed by instance_id or group_id.
    positions: dict = field(default_factory=dict)
    #: Graph collapse modes, keyed by instance_id or group_id.
    collapse: dict = field(default_factory=dict)

    def module(self, instance_id: str) -> Optional[ModuleEntry]:
        """The entry with ``instance_id``, or None."""
        for entry in self.modules:
            if entry.instance_id == instance_id:
                return entry
        return None

    def by_key(self, key: str) -> Optional[ModuleEntry]:
        """Look up by display key. For UI convenience only -- never for storage."""
        for entry in self.modules:
            if entry.key == key:
                return entry
        return None

    def reference(self, ref_id: str) -> Optional[ModuleReference]:
        """The link with ``ref_id``, or None."""
        for entry in self.references:
            if entry.ref_id == ref_id:
                return entry
        return None

    def group(self, group_id: str) -> Optional[SceneGroup]:
        """The scene group with ``group_id``, or None."""
        for entry in self.scene_groups:
            if entry.group_id == group_id:
                return entry
        return None

    def node_ids(self) -> dict:
        """``{display key: id}`` for everything the graph can draw a node for.

        Scene groups use their name as their id -- they exist only in the
        document, so nothing in the scene can rename one behind our back.
        """
        ids = {entry.key: entry.instance_id for entry in self.modules}
        ids.update({group.name: group.group_id for group in self.scene_groups})
        return ids

    def layout_as_keys(self) -> dict:
        """Designer layout re-keyed from ids to display keys, for the graph.

        Storage is id-keyed so a rename can never orphan a node's position; the
        graph speaks display keys, so they are translated at this boundary --
        the same trick as connections and the Builder. Entries whose module is
        gone simply do not project.
        """
        labels = {value: key for key, value in self.node_ids().items()}

        def relabel(table):
            return {labels[key]: value for key, value in table.items() if key in labels}

        sections = {
            "scene_nodes": {
                group.name: list(group.nodes) for group in self.scene_groups
            },
            "positions": {
                key: list(value) for key, value in relabel(self.positions).items()
            },
            "collapse": dict(relabel(self.collapse)),
        }
        # empty sections are omitted, so an untouched layout is simply ``{}``
        return {name: value for name, value in sections.items() if value}

    def layout_from_keys(self, layout: dict) -> None:
        """Store a display-key-keyed layout back under ids. Mutates in place.

        This is a *replacement*, not a merge: a section the caller omits is
        cleared, so ``layout_from_keys({})`` resets the layout. Partial edits go
        through ``read`` -> mutate -> ``write``, which always passes all three.
        """
        layout = dict(layout)
        self.scene_groups = [
            SceneGroup(group_id=name, name=name, nodes=list(group_nodes))
            for name, group_nodes in (layout.get("scene_nodes") or {}).items()
        ]
        ids = self.node_ids()
        self.positions = {
            ids.get(key, key): list(value)
            for key, value in (layout.get("positions") or {}).items()
        }
        self.collapse = {
            ids.get(key, key): int(value)
            for key, value in (layout.get("collapse") or {}).items()
        }

    def to_dict(self) -> dict:
        """The JSON form stored in the ``.tr`` file."""
        return {
            "schema": self.schema,
            # Referenced entries are derived, not content: the link and its
            # overrides are what this file stores.
            "modules": [
                entry.to_dict() for entry in self.modules if entry.origin is None
            ],
            "scene_groups": [entry.to_dict() for entry in self.scene_groups],
            "references": _serialize_references(self),
            "frames": copy.deepcopy(self.frames),
            "positions": {key: list(value) for key, value in self.positions.items()},
            "collapse": dict(self.collapse),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GuideDocument":
        """Rebuild a guide document from its JSON form."""
        schema = int(data.get("schema", SCHEMA_VERSION))
        if schema > SCHEMA_VERSION:
            raise ValueError(
                f"Guide document schema {schema} is newer than "
                f"supported {SCHEMA_VERSION}."
            )
        return cls(
            schema=SCHEMA_VERSION,
            modules=[ModuleEntry.from_dict(item) for item in data.get("modules", [])],
            scene_groups=[
                SceneGroup.from_dict(item) for item in data.get("scene_groups", [])
            ],
            references=[
                ModuleReference.from_dict(item)
                for item in (data.get("references") or [])
            ],
            frames=copy.deepcopy(data.get("frames") or {}),
            positions={
                key: list(value) for key, value in (data.get("positions") or {}).items()
            },
            collapse={
                key: int(value) for key, value in (data.get("collapse") or {}).items()
            },
        )


def expand_guides(entry: ModuleEntry, layout, count: int) -> None:
    """Match ``entry.guides`` to ``layout.expand(count)``, keeping authored poses.

    The document-side answer to a settings change that adds or removes guides
    (``fkchain.segments`` 3 -> 5). Survivors keep their records untouched; new
    pairs arrive unposed, so regenerate places them at their ``draw_guides``
    position rather than at the origin.
    """
    existing = {record.pair: record for record in entry.guides}
    entry.guides = [
        existing.get(pair) or GuideRecord(role=pair[0], index=pair[1])
        for pair in layout.expand(count)
    ]

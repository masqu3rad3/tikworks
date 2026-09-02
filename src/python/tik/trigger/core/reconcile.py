"""Reconcile the guide document against what the Maya scene renders.

Pure comparison -- no Maya, no writes, no registry. The document records which
guides a module should have, so nothing here instantiates a module class.

The output separates the two kinds of drift, and the separation is the point:

===============================  ===========  ==============
Drift                            Resolved by  Winner
===============================  ===========  ==============
pose / guide attr differs        capture      the scene
absent, missing, unexpected,     regenerate   the document
  wrong parent
orphans, duplicates              reported     nothing
===============================  ===========  ==============

A regenerate triggered by pose drift would teleport a guide away from where the
rigger just dragged it, so ``needs_regenerate`` deliberately ignores
``drifted``. Orphans and duplicates are never acted on automatically: they may
be a rigger's scratch work, and destroying untracked scene content is not a
repair.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from .guide_document import GuideDocument

POSE_TOLERANCE = 1e-5


@dataclass
class RenderedGuide:
    """One guide joint as the scene currently has it."""

    instance_id: str
    role: str
    index: int
    #: Opaque scene identifier (a long name). Reported, never parsed.
    node: str
    position: tuple = (0.0, 0.0, 0.0)
    rotation: tuple = (0.0, 0.0, 0.0)
    rotate_order: int = 0
    attrs: dict = field(default_factory=dict)
    #: ``(instance_id, role, index)`` of the DAG parent guide, or None.
    parent: Optional[tuple] = None

    @property
    def pair(self) -> tuple:
        return (self.role, self.index)


@dataclass
class ModuleDiff:
    """How one module's rendering differs from its document entry."""

    instance_id: str
    absent: bool = False
    missing: list = field(default_factory=list)
    unexpected: list = field(default_factory=list)
    drifted: list = field(default_factory=list)
    parent_wrong: bool = False

    @property
    def needs_regenerate(self) -> bool:
        """Structural staleness only. Never true merely because a guide moved."""
        return bool(self.absent or self.missing or self.unexpected or self.parent_wrong)

    @property
    def needs_capture(self) -> bool:
        return bool(self.drifted)

    @property
    def is_clean(self) -> bool:
        return not self.needs_regenerate and not self.needs_capture


@dataclass
class GuideDiff:
    """The whole comparison."""

    modules: dict = field(default_factory=dict)
    orphans: list = field(default_factory=list)
    duplicates: list = field(default_factory=list)

    @property
    def structural(self) -> list:
        """Instance ids whose rendering must be rebuilt."""
        return [key for key, diff in self.modules.items() if diff.needs_regenerate]

    @property
    def drifted(self) -> list:
        """Instance ids whose poses must be captured."""
        return [key for key, diff in self.modules.items() if diff.needs_capture]

    @property
    def is_clean(self) -> bool:
        return not (self.structural or self.drifted or self.orphans or self.duplicates)


def _same(left, right, tolerance: float) -> bool:
    if left is None or right is None:
        return left is right
    return all(abs(float(a) - float(b)) <= tolerance for a, b in zip(left, right))


def reconcile(
    document: GuideDocument,
    rendered: list,
    tolerance: float = POSE_TOLERANCE,
    primary_input_of: Optional[Callable] = None,
) -> GuideDiff:
    """Compare ``document`` with a flat list of :class:`RenderedGuide`.

    Args:
        document: The durable guide document.
        rendered: What the scene currently draws.
        tolerance: Float slack before a pose counts as drifted.
        primary_input_of: ``entry -> input name``, used to find the module a root
            guide should hang under. Omitted (the default) skips the root-parent
            check, which is what unit tests without a registry want.
    """
    diff = GuideDiff()
    by_instance: dict = {}
    for guide in rendered:
        by_instance.setdefault(guide.instance_id, []).append(guide)

    known = {entry.instance_id for entry in document.modules}
    for instance_id, guides in by_instance.items():
        if instance_id not in known:
            diff.orphans.extend(guide.node for guide in guides)

    for entry in document.modules:
        module_diff = ModuleDiff(entry.instance_id)
        guides = by_instance.get(entry.instance_id, [])
        if not guides:
            module_diff.absent = True
            diff.modules[entry.instance_id] = module_diff
            continue

        # A Maya-duplicate copies trg_instance, so several nodes can claim one
        # pair. The first wins; the rest are duplicates and are only reported.
        seen: dict = {}
        for guide in guides:
            if guide.pair in seen:
                diff.duplicates.append(guide.node)
            else:
                seen[guide.pair] = guide

        expected = {record.pair: record for record in entry.guides}
        module_diff.missing = sorted(pair for pair in expected if pair not in seen)
        module_diff.unexpected = sorted(pair for pair in seen if pair not in expected)

        root_pair = entry.guides[0].pair if entry.guides else None
        primary_source = None
        if primary_input_of is not None:
            name = primary_input_of(entry)
            primary_source = entry.inputs.get(name) if name else None

        for pair, record in expected.items():
            guide = seen.get(pair)
            if guide is None:
                continue
            # ``rotation is None`` means "no opinion recorded", not "zero": a
            # record can carry a position from an import that had no rotation.
            # Capture always writes both, so this only bites before the first
            # one -- when ``posed`` is False and the guide is drifted anyway.
            if (
                not record.posed
                or not _same(record.position, guide.position, tolerance)
                or (
                    record.rotation is not None
                    and not _same(record.rotation, guide.rotation, tolerance)
                )
                or record.rotate_order != guide.rotate_order
                or record.attrs != guide.attrs
            ):
                module_diff.drifted.append(pair)
            if pair == root_pair:
                if primary_source is not None and "." in primary_source:
                    expected_id = primary_source.rpartition(".")[0]
                    actual_id = guide.parent[0] if guide.parent else None
                    if expected_id and expected_id != actual_id:
                        module_diff.parent_wrong = True
            elif record.parent is not None:
                want = (entry.instance_id, record.parent[0], record.parent[1])
                if guide.parent != want:
                    module_diff.parent_wrong = True

        module_diff.drifted.sort()
        diff.modules[entry.instance_id] = module_diff

    return diff

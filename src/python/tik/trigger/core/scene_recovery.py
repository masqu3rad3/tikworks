"""Rebuild a guide document out of what a Maya scene carries.

The recovery half of the breadcrumb (spec 4, 5). Pure: it is handed records
another layer read out of the scene, so it unit-tests without Maya.

Two sources, and which supplies what is the whole design:

* the **breadcrumb** (``trg_entry`` on the root guide) supplies identity,
  settings and connections -- things that change only through a document write;
* the **joints** supply poses and guide attrs -- things that change whenever a
  rigger drags something, with no write to refresh a tag.

A scene drawn by an older build has no breadcrumb. That is reported, never
papered over: the module comes back with its type and side and nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import registry
from .guide_document import GuideDocument, GuideRecord, ModuleEntry


@dataclass
class SceneModule:
    """One module as the scene knows it, before any interpretation."""

    instance_id: str
    module_type: str
    side: str = "C"
    #: The ``trg_entry`` payload, or None on a scene drawn before breadcrumbs.
    entry: Optional[dict] = None


@dataclass
class RecoveredModule:
    """What one module came back as."""

    instance_id: str
    key: str
    module_type: str
    complete: bool
    guide_count: int


@dataclass
class RecoveryReport:
    """What a snapshot found, and what it could not bring back."""

    modules: list = field(default_factory=list)
    guide_count: int = 0
    #: Module types in the scene that this build does not know; skipped.
    unknown_types: list = field(default_factory=list)

    @property
    def complete(self) -> list:
        """Modules recovered with everything intact."""
        return [item for item in self.modules if item.complete]

    @property
    def partial(self) -> list:
        """Modules with no breadcrumb: name, settings and inputs are lost."""
        return [item for item in self.modules if not item.complete]

    @property
    def is_lossless(self) -> bool:
        return bool(self.modules) and not self.partial and not self.unknown_types


def _entry_for(scene_module: SceneModule) -> ModuleEntry:
    """The module's identity, from its breadcrumb or from the joints alone."""
    if scene_module.entry:
        data = dict(scene_module.entry)
        data.pop("guides", None)  # never stored; the joints are the poses
        return ModuleEntry.from_dict(data)
    # No breadcrumb: trg_module and trg_side are on every guide joint, so the
    # module comes back as itself -- unnamed, unconfigured and unconnected.
    return ModuleEntry(
        instance_id=scene_module.instance_id,
        module_type=scene_module.module_type,
        name=scene_module.module_type,
        side=scene_module.side,
    )


def document_from_scene(scene_modules: list, rendered: list) -> tuple:
    """Assemble a document and a report from scene records.

    Args:
        scene_modules: One :class:`SceneModule` per instance found.
        rendered: ``RenderedGuide`` records for every guide joint.

    Returns:
        ``(GuideDocument, RecoveryReport)``. The document is new; nothing is
        mutated in place, so a caller can show the report before committing.
    """
    by_instance: dict = {}
    for guide in rendered:
        by_instance.setdefault(guide.instance_id, []).append(guide)

    document = GuideDocument()
    report = RecoveryReport()
    for scene_module in scene_modules:
        if not registry.is_module_registered(scene_module.module_type):
            if scene_module.module_type not in report.unknown_types:
                report.unknown_types.append(scene_module.module_type)
            continue
        entry = _entry_for(scene_module)
        guides = by_instance.get(scene_module.instance_id, [])
        for guide in sorted(guides, key=lambda item: (item.role, item.index)):
            entry.guides.append(
                GuideRecord(
                    role=guide.role,
                    index=guide.index,
                    position=tuple(guide.position),
                    rotation=None if guide.rotation is None else tuple(guide.rotation),
                    rotate_order=guide.rotate_order,
                    attrs=dict(guide.attrs),
                    # RenderedGuide.parent is a global (instance, role, index);
                    # GuideRecord.parent is module-local, so a parent in another
                    # module is not an internal parent at all.
                    parent=(
                        (guide.parent[1], guide.parent[2])
                        if guide.parent and guide.parent[0] == scene_module.instance_id
                        else None
                    ),
                )
            )
        document.modules.append(entry)
        report.modules.append(
            RecoveredModule(
                instance_id=entry.instance_id,
                key=entry.key,
                module_type=entry.module_type,
                complete=bool(scene_module.entry),
                guide_count=len(entry.guides),
            )
        )
        report.guide_count += len(entry.guides)
    return document, report

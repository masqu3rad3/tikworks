"""Resolve a guide document's module references, and derive their overrides.

Pure Python: no Maya, no Qt, and deliberately no ``tik.trigger.actions`` -- the
cycle check here is its own rather than a reuse of the action reference's,
because ``core`` may not import an action package.

Two directions, and they are inverses:

* :func:`resolve` pulls referenced modules **into** the document, applying the
  stored overrides as it goes and keeping an untouched ``source`` beside each.
  They land in the real ``modules`` list, so every existing read and write in
  the guide layer works on them without knowing they are borrowed.
* :func:`overrides_for` reads the difference back **out**, which is how
  ``GuideDocument.to_dict`` produces the overrides it stores.

Nothing writes an override imperatively. That is what makes reverting one a
delete, and what makes dragging a referenced guide back to where upstream put
it *remove* the override rather than pin it at a coincidentally equal value.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from . import versioning
from .guide_document import GuideDocument, ModuleEntry


def _resolve_path(reference, base_dir: str) -> Path:
    """The referenced file, made absolute and version-resolved."""
    path = Path(reference.file)
    if not path.is_absolute() and base_dir:
        path = Path(base_dir) / path
    return versioning.resolve(path, reference.version or "latest")


def apply_overrides(entry: ModuleEntry, override: dict) -> None:
    """Apply one module's stored overrides to a freshly loaded entry."""
    if "enabled" in override:
        entry.enabled = bool(override["enabled"])
    if override.get("name"):
        entry.name = str(override["name"])
    if override.get("side"):
        entry.side = str(override["side"])
    for key, value in (override.get("settings") or {}).items():
        entry.settings[key] = value
    for key, value in (override.get("inputs") or {}).items():
        entry.inputs[key] = value
    for key, values in (override.get("guides") or {}).items():
        role, _sep, index = key.rpartition(":")
        record = entry.guide(role, int(index or 0))
        if record is None:
            continue  # structure is upstream's word: that guide is gone
        for name, value in (values or {}).items():
            if name == "attrs":
                record.attrs.update(value or {})
            elif name in ("position", "rotation", "joint_orient"):
                setattr(record, name, tuple(float(item) for item in value))
            elif name == "rotate_order":
                record.rotate_order = int(value)
            elif name == "radius":
                record.radius = float(value)
            elif name == "color":
                record.color = int(value)


def _entries_from(
    document: GuideDocument, base_dir: str, loader: Callable, chain: tuple, problems
) -> list:
    """Every module a document contributes, its own references included."""
    found = list(document.modules)
    for reference in document.references:
        found.extend(_borrowed(reference, base_dir, loader, chain, problems))
    return found


def _borrowed(reference, base_dir: str, loader: Callable, chain: tuple, problems):
    """The entries one link contributes: overrides applied, sources attached."""
    try:
        path = _resolve_path(reference, base_dir)
    except (OSError, ValueError) as error:
        problems.append(f"reference '{reference.file}': {error}")
        return []
    key = str(path)
    if key in chain:
        names = " > ".join(Path(item).name for item in chain)
        problems.append(f"reference cycle: {names} > {path.name}")
        return []
    try:
        guides = loader(path).guides
    except Exception as error:  # noqa: BLE001 - a broken link is reported, not fatal
        problems.append(f"reference '{reference.file}' could not be read: {error}")
        return []
    inner = _entries_from(guides, str(path.parent), loader, chain + (key,), problems)
    found = []
    for entry in inner:
        # Deep copy first. ``source`` must never be an object the loader's cache
        # owns: ``capture`` edits GuideRecords in place, and a shared record
        # would move the very thing it exists to be compared against.
        fresh = ModuleEntry.from_dict(entry.to_dict())
        fresh.source = ModuleEntry.from_dict(entry.to_dict())
        # An entry arriving through a chain belongs to the link it came
        # through, so a host override on it is stored on that link and the
        # host never writes into the referenced session's own overrides.
        fresh.origin = reference.ref_id
        apply_overrides(fresh, (reference.overrides or {}).get(fresh.instance_id, {}))
        found.append(fresh)
    return found


def resolve(
    document: GuideDocument, base_dir: str, loader: Optional[Callable] = None
) -> list:
    """Insert every referenced module into ``document.modules``. In place.

    Idempotent: entries from a previous resolution are dropped first, so this
    can run on every load, undo and redo without accumulating duplicates.

    Returns problems rather than raising. A broken link must not stop a session
    opening, or the Designer could not render the document well enough for
    anybody to fix it.
    """
    if loader is None:
        from .document import Document

        loader = Document.load
    document.modules = [item for item in document.modules if item.origin is None]
    problems: list = []
    seen = {item.instance_id for item in document.modules}
    for reference in document.references:
        for entry in _borrowed(reference, base_dir, loader, (), problems):
            # Dedup is by instance id, not by path: a diamond resolved from two
            # different versions is two paths carrying the same modules.
            if entry.instance_id in seen:
                problems.append(
                    f"warning: {entry.key} is already in this rig; the copy from "
                    f"'{reference.file}' was dropped."
                )
                continue
            seen.add(entry.instance_id)
            document.modules.append(entry)
    return problems


# ------------------------------------------------------------ the other way
def _same_triple(one, two, tolerance: float) -> bool:
    """Whether two optional triples agree within ``tolerance``."""
    if one is None or two is None:
        return one is None and two is None
    return all(abs(a - b) <= tolerance for a, b in zip(one, two))


def _settings_diff(entry: ModuleEntry) -> dict:
    """Settings that differ, both sides normalized through the module class.

    ``write_settings`` stores a full value dict while an entry loaded from a
    file may be sparse -- and becomes sparse whenever a module class gains a
    field -- so a raw dict comparison would report every default as an
    override.
    """
    from . import registry

    def values(settings):
        try:
            module_cls = registry.get_module(entry.module_type)
            return module_cls(settings=dict(settings)).values()
        except Exception:  # noqa: BLE001 - unregistered type: compare raw
            return dict(settings)

    mine, theirs = values(entry.settings), values(entry.source.settings)
    return {key: value for key, value in mine.items() if theirs.get(key) != value}


def _guides_diff(entry: ModuleEntry, tolerance: float) -> dict:
    """Per-guide differences, keyed ``"<role>:<index>"``."""
    sources = {record.pair: record for record in entry.source.guides}
    found: dict = {}
    for record in entry.guides:
        origin = sources.get(record.pair)
        if origin is None:
            continue  # structure is upstream's word; a new guide is not ours
        changed: dict = {}
        for name in ("position", "rotation", "joint_orient"):
            mine, theirs = getattr(record, name), getattr(origin, name)
            if not _same_triple(mine, theirs, tolerance):
                changed[name] = list(mine) if mine is not None else None
        if record.rotate_order != origin.rotate_order:
            changed["rotate_order"] = record.rotate_order
        if record.radius != origin.radius:
            changed["radius"] = record.radius
        if record.color != origin.color:
            changed["color"] = record.color
        if record.attrs != origin.attrs:
            changed["attrs"] = dict(record.attrs)
        if changed:
            found[f"{record.role}:{record.index}"] = changed
    return found


def overrides_for(entry: ModuleEntry, tolerance: Optional[float] = None) -> dict:
    """What ``entry`` differs from its source by. Empty when nothing does.

    This *is* the override set, computed rather than recorded, which is why it
    is self-cleaning: undoing an edit by hand removes the override with it.
    """
    if entry.source is None:
        return {}
    if tolerance is None:
        from .reconcile import POSE_TOLERANCE

        tolerance = POSE_TOLERANCE
    override: dict = {}
    if entry.name != entry.source.name:
        override["name"] = entry.name
    if entry.side != entry.source.side:
        override["side"] = entry.side
    if not entry.enabled:
        override["enabled"] = False
    settings = _settings_diff(entry)
    if settings:
        override["settings"] = settings
    inputs = {
        key: value
        for key, value in entry.inputs.items()
        if entry.source.inputs.get(key) != value
    }
    if inputs:
        override["inputs"] = inputs
    guides = _guides_diff(entry, tolerance)
    if guides:
        override["guides"] = guides
    return override


def serialize_references(document: GuideDocument) -> list:
    """The document's links, each carrying freshly diffed overrides.

    A link whose modules were never resolved keeps the overrides it was loaded
    with: loading a session and saving it again must not erase edits merely
    because nothing pulled the referenced file in.
    """
    by_origin: dict = {}
    resolved = set()
    for entry in document.modules:
        if entry.origin is None:
            continue
        resolved.add(entry.origin)
        if entry.source is None:
            continue
        override = overrides_for(entry)
        if override:
            by_origin.setdefault(entry.origin, {})[entry.instance_id] = override
    stored = []
    for reference in document.references:
        data = reference.to_dict()
        if reference.ref_id in resolved:
            data["overrides"] = by_origin.get(reference.ref_id, {})
        stored.append(data)
    return stored

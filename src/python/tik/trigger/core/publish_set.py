"""What a session needs to be published: artifacts, dependencies, bundles.

Pure Python. Knows files and hashes; never Maya, Qt or a provider.

A *bundle* is a folder holding the session's ``.tr`` with its file paths
rewritten, the other artifacts, and a manifest. Every dependency lives once in
a flat content-addressed *store* beside the bundles, so an unchanged file is
never copied twice however many versions are published.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from . import kinds, registry, versioning
from .action import ActionContext
from .document import BUILD, PHASES, PUBLISH, Document, split_path

logger = logging.getLogger(__name__)

MANIFEST = "manifest.json"
STORE_DIR = "_store"
INDEX = "index.json"
REFERENCE_TYPE = "reference"

#: Where each phase's actions live inside ``Document.to_dict()``.
_PHASE_KEY = {BUILD: "actions", PUBLISH: "publish"}


@dataclass(frozen=True)
class Artifact:
    """One file a publish carries as a named element."""

    kind: str
    path: Path
    label: str = ""


@dataclass(frozen=True)
class Dependency:
    """A file a document needs, and where it was written down."""

    path: Path
    original: str
    owner: str
    external: bool


@dataclass
class PublishSet:
    """Everything one publish delivers."""

    session: Path
    base_dir: Path
    document: Document
    artifacts: list[Artifact] = field(default_factory=list)
    dependencies: list[Dependency] = field(default_factory=list)

    @property
    def name(self) -> str:
        """The session's stem: ``hero`` for ``hero.tr``."""
        return self.session.stem

    @classmethod
    def collect(
        cls,
        session_file,
        document: Document,
        *,
        rig: Optional[Path] = None,
        guides: Optional[Path] = None,
        products: Iterable[Artifact] = (),
    ) -> "PublishSet":
        """The core artifacts plus every dependency the document names."""
        session = Path(session_file)
        base_dir = session.parent
        artifacts = [Artifact(kinds.SESSION, session)]
        if guides is not None:
            artifacts.append(Artifact(kinds.GUIDES, Path(guides)))
        if rig is not None:
            artifacts.append(Artifact(kinds.RIG, Path(rig)))
        artifacts.extend(products)
        return cls(
            session=session,
            base_dir=base_dir,
            document=document,
            artifacts=artifacts,
            dependencies=collect_dependencies(document, base_dir),
        )


# ------------------------------------------------------------ dependencies
def is_external(path: Path, base_dir) -> bool:
    """True when ``path`` is not inside ``base_dir``."""
    try:
        Path(path).resolve().relative_to(Path(base_dir).resolve())
    except ValueError:
        return True
    return False


def _external(value: str, resolved: Path, base_dir) -> bool:
    """True when a written value is a studio path the bundle must not touch.

    A *relative* value belongs to the session however many ``..`` it climbs --
    it is part of the project and gets bundled, or the copy could not open on
    its own. Only an absolute path pointing outside the session folder is left
    as the rigger wrote it.
    """
    return Path(value).is_absolute() and is_external(resolved, base_dir)


def _written_form(path: Path, base_dir) -> str:
    """How a file no field names is written down: session-relative when inside."""
    if is_external(path, base_dir):
        return str(path).replace("\\", "/")
    return relative(path, base_dir)


def _resolve_reference(value: str, version: str, base_dir) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = Path(base_dir) / path
    return versioning.resolve(path, version or "latest")


def _reference_links(document: Document, base_dir):
    """``(owner, original, resolved path)`` for every session this one links."""
    for path, node, _parent in document.walk(BUILD):
        if node.type == REFERENCE_TYPE and node.enabled and node.settings.get("file"):
            yield path, node.settings["file"], _resolve_reference(
                node.settings["file"], node.settings.get("version", "latest"), base_dir
            )
    for link in document.guides.references:
        if link.file:
            yield f"guides/{link.ref_id}", link.file, _resolve_reference(
                link.file, link.version, base_dir
            )


def collect_dependencies(
    document: Document, base_dir, owner_prefix: str = "", seen: Optional[set] = None
) -> list[Dependency]:
    """Every file the document's enabled actions and links need, recursively."""
    base = Path(base_dir)
    seen = set() if seen is None else seen
    found: list[Dependency] = []
    for path, node, _parent in document.walk(BUILD):
        if not node.enabled or node.type == REFERENCE_TYPE:
            continue
        if not registry.is_action_registered(node.type):
            logger.warning("publish: unknown action type '%s' at %s", node.type, path)
            continue
        action = registry.get_action(node.type)(settings=node.settings)
        ctx = ActionContext(base_dir=str(base), path=path)
        values = [
            getattr(action, name)
            for name in action.file_fields()
            if getattr(action, name)
        ]
        for dep in action.dependencies(ctx):
            original = next(
                (value for value in values if ctx.resolve(value) == dep),
                _written_form(dep, base),
            )
            found.append(
                Dependency(
                    dep,
                    original,
                    owner_prefix + path,
                    _external(original, dep, base),
                )
            )
    for owner, original, resolved in _reference_links(document, base):
        found.append(
            Dependency(
                resolved,
                original,
                owner_prefix + owner,
                _external(original, resolved, base),
            )
        )
        key = str(resolved.resolve())
        if key in seen or not resolved.exists():
            continue
        seen.add(key)
        found.extend(
            collect_dependencies(
                Document.load(resolved),
                resolved.parent,
                owner_prefix=f"{owner_prefix}{owner}/",
                seen=seen,
            )
        )
    return found


# ------------------------------------------------------------------ store
class Store:
    """A flat content-addressed folder: ``<root>/<sha1>_<name>``."""

    def __init__(self, root) -> None:
        self.root = Path(root)
        self._index: Optional[dict] = None

    # cache -----------------------------------------------------------
    @property
    def _index_file(self) -> Path:
        return self.root / INDEX

    def _load_index(self) -> dict:
        if self._index is None:
            try:
                self._index = json.loads(self._index_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._index = {}
        return self._index

    def _save_index(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._index_file.write_text(
            json.dumps(self._load_index(), indent=2), encoding="utf-8"
        )

    @staticmethod
    def _digest(data: bytes) -> str:
        return hashlib.sha1(data).hexdigest()  # noqa: S324 - content id, not security

    def hash_file(self, path) -> str:
        """SHA-1 of the content, cached by ``(size, mtime)``."""
        path = Path(path)
        stat = path.stat()
        key = str(path.resolve())
        entry = self._load_index().get(key)
        if entry and entry["size"] == stat.st_size and entry["mtime"] == stat.st_mtime:
            return entry["hash"]
        digest = self._digest(path.read_bytes())
        self._load_index()[key] = {
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            "hash": digest,
        }
        self._save_index()
        return digest

    # content ---------------------------------------------------------
    def _target(self, digest: str, name: str) -> Path:
        return self.root / f"{digest}_{name}"

    def put(self, path) -> Path:
        """Store the file once; return the stored path."""
        path = Path(path)
        target = self._target(self.hash_file(path), path.name)
        if not target.exists():
            self.root.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        return target

    def put_bytes(self, data: bytes, name: str) -> Path:
        """Store in-memory content once under ``name``; return the stored path."""
        target = self._target(self._digest(data), name)
        if not target.exists():
            self.root.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        return target

    def files(self) -> list[Path]:
        """Every stored file (the index excluded), sorted."""
        if not self.root.exists():
            return []
        return sorted(item for item in self.root.iterdir() if item.name != INDEX)


def relative(target, from_dir) -> str:
    """``target`` relative to ``from_dir`` with forward slashes."""
    return os.path.relpath(str(target), str(from_dir)).replace("\\", "/")


# --------------------------------------------------------------- bundles
def _entry(owner, original, dep_path, store_value, external, store=None) -> dict:
    """One manifest line for a rewritten (or deliberately untouched) path.

    ``store_value`` is always relative to the *bundle* folder, whatever
    document the path came from, so reading a manifest never needs to know
    where the document that named the file ended up.
    """
    return {
        "owner": owner,
        "original": original,
        "hash": "" if external or store is None else store.hash_file(dep_path),
        "size": 0 if external else Path(dep_path).stat().st_size,
        "store": store_value,
        "external": external,
    }


def _rewrite_value(
    value, base_dir, store, location, bundle, entries, owner
) -> Optional[str]:
    """Store the file ``value`` names; return its new value, or None to keep it."""
    base = Path(base_dir)
    resolved = Path(value) if Path(value).is_absolute() else base / value
    if _external(value, resolved, base) or not resolved.exists():
        entries.append(_entry(owner, value, resolved, value, True))
        return None
    stored = store.put(resolved)
    entries.append(
        _entry(owner, value, resolved, relative(stored, bundle), False, store)
    )
    return relative(stored, location)


def _copy_extra(dep: Path, base_dir, store, location, bundle, entries, owner) -> None:
    """Carry a file an action names outside its fields.

    Nothing in the document points at it by path, so it keeps its own name and
    its place beside the session -- a script importing a sibling needs both.
    That only works for the document that lands in the bundle: a *referenced*
    document lands in the store, where its extras can only sit under their
    hashed name, and a sibling import there will not find them.
    """
    base = Path(base_dir)
    original = _written_form(dep, base)
    if _external(original, dep, base) or not dep.exists():
        entries.append(_entry(owner, original, dep, original, True))
        return
    if Path(location) == Path(bundle):
        target = Path(bundle) / original
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dep, target)
        store_value = original
    else:
        store_value = relative(store.put(dep), bundle)
    entries.append(_entry(owner, original, dep, store_value, False, store))


def _rewrite_overrides(
    overrides: dict, document: Document, base_dir, store, bundle, entries, owner
) -> None:
    """Rewrite the file settings a ``reference`` action overrides.

    An override is applied to the *referenced* document's node and resolved
    against the *referenced* session's folder, so its value belongs to the
    nested ``.tr`` -- which lands in the store. Rewritten relative to the store
    root for that reason, not relative to the bundle.
    """
    for path, override in (overrides or {}).items():
        settings = (override or {}).get("settings") or {}
        node = document.find(path)
        if not settings or node is None:
            continue
        if not registry.is_action_registered(node.type):
            continue
        action_cls = registry.get_action(node.type)
        # the override is what the action will actually see, so it is what a
        # defaulted setting has to be pinned from: an override that swaps the
        # file changes the alias its name gave it, and the nested document's
        # own pin -- taken from the file the override replaced -- is wrong here.
        settings.update(action_cls.pin_settings({**node.settings, **settings}))
        for name in action_cls.file_fields():
            value = settings.get(name)
            if not value:
                continue
            new_value = _rewrite_value(
                value,
                base_dir,
                store,
                store.root,
                bundle,
                entries,
                f"{owner}/{path}",
            )
            if new_value is not None:
                settings[name] = new_value


def _rewrite_reference(
    value, version, base_dir, store, location, bundle, entries, owner, overrides=None
) -> str:
    """Bundle a referenced ``.tr`` into the store and return its new value."""
    resolved = _resolve_reference(value, version, base_dir)
    if _external(value, resolved, base_dir) or not resolved.exists():
        entries.append(_entry(owner, value, resolved, value, True))
        return value
    document = Document.load(resolved)
    nested = rewrite_document(
        document,
        resolved.parent,
        store,
        store.root,
        entries,
        owner=f"{owner}/",
        bundle=bundle,
    )
    if overrides is not None:
        _rewrite_overrides(
            overrides, document, resolved.parent, store, bundle, entries, owner
        )
    stored = store.put_bytes(
        json.dumps(nested, indent=2).encode("utf-8"), resolved.name
    )
    entries.append(_entry(owner, value, stored, relative(stored, bundle), False, store))
    return relative(stored, location)


def rewrite_document(
    document: Document,
    base_dir,
    store: Store,
    location,
    entries: list,
    owner: str = "",
    bundle=None,
) -> dict:
    """``document.to_dict()`` with every file path pointing into ``store``.

    ``location`` is the folder the rewritten document will be written to;
    paths are made relative to it. Nested references are rewritten with the
    store root as their location, since that is where they land. ``bundle``
    is the folder the manifest will sit in, which every ``entries`` line is
    written relative to; it defaults to ``location``.
    """
    base = Path(base_dir)
    bundle = Path(location if bundle is None else bundle)
    data = document.to_dict()
    for phase in PHASES:
        for path, node, _parent in document.walk(phase):
            if not registry.is_action_registered(node.type):
                continue
            action_cls = registry.get_action(node.type)
            settings = _find_node(data[_PHASE_KEY[phase]], path)["settings"]
            if node.type == REFERENCE_TYPE:
                if settings.get("file"):
                    settings["file"] = _rewrite_reference(
                        settings["file"],
                        settings.get("version", "latest"),
                        base,
                        store,
                        location,
                        bundle,
                        entries,
                        owner + path,
                        overrides=settings.get("overrides"),
                    )
                    settings["version"] = "pinned"
                continue
            # before any path moves: a setting that defaulted from the file's
            # name has to be written down, or the store's hashed name changes
            # what it means (a script's module alias, for one).
            settings.update(action_cls.pin_settings(settings))
            for name in action_cls.file_fields():
                value = settings.get(name)
                if not value:
                    continue
                new_value = _rewrite_value(
                    value, base, store, location, bundle, entries, owner + path
                )
                if new_value is not None:
                    settings[name] = new_value
            for dep in _extra_dependencies(action_cls, node, path, base):
                _copy_extra(dep, base, store, location, bundle, entries, owner + path)
    for index, link in enumerate(document.guides.references):
        if not link.file:
            continue
        link_data = data["guides"]["references"][index]
        link_data["file"] = _rewrite_reference(
            link.file,
            link.version,
            base,
            store,
            location,
            bundle,
            entries,
            f"{owner}guides/{link.ref_id}",
        )
        link_data["version"] = "pinned"
    return data


def _extra_dependencies(action_cls, node, path: str, base_dir) -> list[Path]:
    """The files ``dependencies(ctx)`` adds beyond the action's own fields."""
    action = action_cls(settings=node.settings)
    ctx = ActionContext(base_dir=str(base_dir), path=path)
    from_fields = {
        ctx.resolve(getattr(action, name))
        for name in action_cls.file_fields()
        if getattr(action, name)
    }
    return [dep for dep in action.dependencies(ctx) if dep not in from_fields]


def _find_node(nodes: list, path: str) -> dict:
    """The dict for the action at ``path`` inside a ``to_dict`` tree."""
    current = None
    for part in split_path(path):
        current = next(item for item in nodes if item["name"] == part)
        nodes = current["children"]
    return current


def write_bundle(publish_set: PublishSet, target, store_root=None) -> Path:
    """Write the bundle folder for ``publish_set`` at ``target``."""
    target = Path(target)
    store = Store(Path(store_root) if store_root else target.parent / STORE_DIR)
    target.mkdir(parents=True, exist_ok=True)
    entries: list = []
    data = rewrite_document(
        publish_set.document, publish_set.base_dir, store, target, entries
    )
    session_name = publish_set.session.name
    (target / session_name).write_text(json.dumps(data, indent=2), encoding="utf-8")
    artifacts = []
    for artifact in publish_set.artifacts:
        if artifact.kind == kinds.SESSION:
            artifacts.append(
                {"kind": artifact.kind, "path": session_name, "label": artifact.label}
            )
            continue
        shutil.copy2(artifact.path, target / artifact.path.name)
        artifacts.append(
            {"kind": artifact.kind, "path": artifact.path.name, "label": artifact.label}
        )
    manifest = {
        "session": session_name,
        "artifacts": artifacts,
        "dependencies": entries,
    }
    (target / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return target


def clean(store_root, bundle_roots: Iterable) -> list[Path]:
    """Delete store files no manifest under ``bundle_roots`` references.

    One manifest is enough: a bundle's dependency list is flat and covers the
    referenced sessions it carries and everything *they* need, each ``store``
    value written relative to the bundle folder the manifest sits in.
    """
    store = Store(store_root)
    referenced: set[Path] = set()
    for root in bundle_roots:
        for manifest in Path(root).rglob(MANIFEST):
            data = json.loads(manifest.read_text(encoding="utf-8"))
            for entry in data.get("dependencies", []):
                if entry.get("external") or not entry.get("store"):
                    continue
                referenced.add((manifest.parent / entry["store"]).resolve())
    removed: list[Path] = []
    for item in store.files():
        if item.resolve() not in referenced:
            item.unlink()
            removed.append(item)
    return removed

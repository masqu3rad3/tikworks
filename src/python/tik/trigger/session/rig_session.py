"""RigSession: one ``.trg`` document holding a guide snapshot and the action pipeline."""

from __future__ import annotations

import copy
import datetime
import getpass
import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

from tik.trigger.core import registry
from tik.trigger.core.action import ActionContext
from tik.trigger.core.events import EventBus
from tik.trigger.core.exceptions import (
    ActionExecutionError,
    SessionError,
    SessionLoadError,
    SessionSaveError,
)
from tik.trigger.core.schemas import (
    ActionInstance,
    ModuleInstance,
    RigDocument,
    order_instances,
)

logger = logging.getLogger(__name__)

EXTENSION = ".trg"


class RigSession:
    """Manage a rig document: guides snapshot, action pipeline, file I/O."""

    EXTENSION = EXTENSION

    def __init__(self, backend=None, file_path: Optional[str] = None, events=None) -> None:
        self.backend = backend
        self.events = events or EventBus()
        self.document = RigDocument()
        self.file_path: Optional[Path] = None
        self._saved_state = self.document.to_dict()
        if file_path:
            self.load(file_path)

    # ------------------------------------------------------------- document
    @property
    def actions(self) -> list[ActionInstance]:
        return self.document.actions

    @property
    def guides(self) -> list[ModuleInstance]:
        return self.document.guides

    @property
    def is_modified(self) -> bool:
        return self.document.to_dict() != self._saved_state

    def new(self) -> None:
        self.document = RigDocument()
        self.file_path = None
        self._saved_state = self.document.to_dict()

    def _stamp_meta(self) -> None:
        now = datetime.datetime.now().isoformat(timespec="seconds")
        meta = self.document.meta
        meta.setdefault("created_at", now)
        meta.setdefault("author", getpass.getuser())
        meta["modified_at"] = now
        if self.backend is not None:
            meta["backend"] = getattr(self.backend, "name", "")

    @staticmethod
    def _with_extension(path) -> Path:
        path = Path(path)
        return path if path.suffix == EXTENSION else path.with_suffix(EXTENSION)

    def save(self, file_path: Optional[str] = None) -> Path:
        target = file_path or self.file_path
        if not target:
            raise SessionSaveError("No file path given for the session.")
        path = self._with_extension(target)
        self._stamp_meta()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self.document.to_dict(), indent=2), encoding="utf-8")
        except OSError as error:
            raise SessionSaveError(f"Cannot write '{path}': {error}") from error
        self.file_path = path
        self._saved_state = self.document.to_dict()
        self.events.log(f"Session saved: {path}")
        return path

    def load(self, file_path: str) -> None:
        path = Path(file_path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.document = RigDocument.from_dict(data)
        except (OSError, ValueError, KeyError) as error:
            raise SessionLoadError(f"Cannot load '{path}': {error}") from error
        self.file_path = path
        self._saved_state = self.document.to_dict()
        self.events.log(f"Session loaded: {path}")

    # -------------------------------------------------------------- guides
    def _require_backend(self):
        if self.backend is None:
            raise SessionError("This operation needs a backend.")
        return self.backend

    def snapshot_guides(self, scope: Any = "scene") -> list[ModuleInstance]:
        """Read the guides from the scene into the document."""
        backend = self._require_backend()
        self.document.guides = backend.find_instances(scope)
        return self.document.guides

    def restore_guides(self, clear_existing: bool = False) -> list[ModuleInstance]:
        """Recreate the documented guides in the scene (parents first)."""
        backend = self._require_backend()
        if clear_existing:
            for existing in backend.find_instances("scene"):
                backend.delete_guides(existing.instance_id)
        created: list[ModuleInstance] = []
        with backend.undo_chunk("Trigger restore guides"):
            for instance in order_instances(self.document.guides):
                module_cls = registry.get_module(instance.module_type)
                module = module_cls.from_instance(instance)
                created.append(
                    backend.create_guides(
                        module,
                        parent=instance.parent,
                        poses=instance.guides,
                        attach=instance.attach,
                    )
                )
        return created

    def export_guides(self, file_path: str) -> Path:
        path = self._with_extension(file_path)
        document = RigDocument(meta={"section": "guides"}, guides=copy.deepcopy(self.document.guides))
        path.write_text(json.dumps(document.to_dict(), indent=2), encoding="utf-8")
        return path

    def import_guides(self, file_path: str, replace: bool = True) -> list[ModuleInstance]:
        data = json.loads(Path(file_path).read_text(encoding="utf-8"))
        imported = RigDocument.from_dict(data).guides
        if replace:
            self.document.guides = imported
        else:
            self.document.guides.extend(imported)
        return imported

    # ------------------------------------------------------------- actions
    def _find(self, name: str) -> ActionInstance:
        for action in self.document.actions:
            if action.name == name:
                return action
        raise SessionError(f"No action named '{name}'.")

    def _index(self, name: str) -> int:
        return self.document.actions.index(self._find(name))

    def action_names(self) -> list[str]:
        return [action.name for action in self.document.actions]

    def unique_action_name(self, base: str) -> str:
        names = set(self.action_names())
        if base not in names:
            return base
        match = re.match(r"^(.*?)(\d+)$", base)
        stem, counter = (match.group(1), int(match.group(2))) if match else (base, 0)
        while True:
            counter += 1
            candidate = f"{stem}{counter}"
            if candidate not in names:
                return candidate

    def add_action(
        self, action_type: str, name: Optional[str] = None, index: Optional[int] = None
    ) -> ActionInstance:
        action_cls = registry.get_action(action_type)
        instance = action_cls().to_instance(self.unique_action_name(name or action_type))
        if index is None:
            self.document.actions.append(instance)
        else:
            self.document.actions.insert(index, instance)
        return instance

    def remove_action(self, name: str) -> None:
        self.document.actions.remove(self._find(name))

    def rename_action(self, name: str, new_name: str) -> None:
        if new_name != name and new_name in self.action_names():
            raise SessionError(f"An action named '{new_name}' already exists.")
        self._find(name).name = new_name

    def move_action(self, name: str, index: int) -> None:
        action = self._find(name)
        self.document.actions.remove(action)
        self.document.actions.insert(index, action)

    def set_enabled(self, name: str, enabled: bool) -> None:
        self._find(name).enabled = bool(enabled)

    def duplicate_action(self, name: str) -> ActionInstance:
        source = self._find(name)
        copy_instance = ActionInstance.from_dict(source.to_dict())
        copy_instance.name = self.unique_action_name(source.name)
        self.document.actions.insert(self._index(name) + 1, copy_instance)
        return copy_instance

    def action_settings(self, name: str) -> dict:
        return dict(self._find(name).settings)

    def update_action_settings(self, name: str, settings: dict) -> None:
        action = self._find(name)
        action_cls = registry.get_action(action.action_type)
        validated = action_cls(settings=action.settings)
        validated.apply(settings)
        action.settings = validated.values()

    def action_object(self, name: str):
        """Instantiate the action class for ``name`` with its saved settings."""
        action = self._find(name)
        return registry.get_action(action.action_type).from_instance(action)

    # --------------------------------------------------------------- running
    def _context(self) -> ActionContext:
        paths = {"session": str(self.file_path) if self.file_path else ""}
        if self.file_path:
            paths["directory"] = str(self.file_path.parent)
        return ActionContext(backend=self.backend, session=self, events=self.events, paths=paths)

    def run_action(self, name: str) -> None:
        backend = self._require_backend()
        action = self.action_object(name)
        self.events.log(f"Running action: {name}")
        try:
            with backend.undo_chunk(f"Trigger action: {name}"):
                action.run(self._context())
        except Exception as error:  # noqa: BLE001 - report then wrap
            self.events.error(error, context=f"action {name}")
            raise ActionExecutionError(f"Action '{name}' failed: {error}", action_name=name) from error

    def run_all(self, until: Optional[str] = None, reset_scene: bool = False) -> list[str]:
        """Run enabled actions in order; stop after ``until`` when given."""
        backend = self._require_backend()
        if reset_scene:
            backend.new_scene()
        executed: list[str] = []
        enabled = [action for action in self.document.actions if action.enabled]
        for number, action in enumerate(enabled, start=1):
            self.events.progress(number, len(enabled), action.name)
            self.run_action(action.name)
            executed.append(action.name)
            if until is not None and action.name == until:
                break
        return executed

    def export_actions(self, file_path: str) -> Path:
        path = self._with_extension(file_path)
        document = RigDocument(meta={"section": "actions"}, actions=copy.deepcopy(self.document.actions))
        path.write_text(json.dumps(document.to_dict(), indent=2), encoding="utf-8")
        return path

    def import_actions(self, file_path: str, index: Optional[int] = None) -> list[ActionInstance]:
        data = json.loads(Path(file_path).read_text(encoding="utf-8"))
        imported = RigDocument.from_dict(data).actions
        for action in imported:
            action.name = self.unique_action_name(action.name)
            if index is None:
                self.document.actions.append(action)
            else:
                self.document.actions.insert(index, action)
                index += 1
        return imported

    def __repr__(self) -> str:
        return f"RigSession(file={self.file_path}, guides={len(self.guides)}, actions={len(self.actions)})"

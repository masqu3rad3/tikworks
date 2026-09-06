"""The TD-facing handler: ``Session`` (``ActionHandle`` lives in ``handles``).

from tik import trigger
rig = trigger.Session.open("hero.tr")
base = rig.add("reference", file="baseRig.tr")
base["scripts/head_rotation"].enabled = False
rig.build(until="weights")
rig.save(increment=True)
"""

from __future__ import annotations

import datetime
import getpass
import uuid
from pathlib import Path
from typing import Optional

from tik.trigger.core import registry, versioning
from tik.trigger.core.document import (
    BUILD,
    EXTENSION,
    PHASES,
    PUBLISH,
    ActionNode,
    Document,
    join_path,
    split_path,
)
from tik.trigger.core.events import EventBus
from tik.trigger.core.exceptions import SessionError, SessionSaveError
from tik.trigger.core.steps import StepResult
from tik.trigger.handles import ActionHandle, PhaseView  # noqa: F401 - re-exported


class Session:
    """A ``.tr`` document and the runner that builds it."""

    EXTENSION = EXTENSION

    def __init__(
        self, file_path: Optional[str] = None, events: Optional[EventBus] = None
    ) -> None:
        self.events = events or EventBus()
        self.document = Document()
        self.file_path: Optional[Path] = None
        self._saved_state = self.document.to_dict()
        self._reference_cache: dict[str, Document] = {}
        self._views: dict[str, PhaseView] = {}
        self._guides = None
        self._undo: list[dict] = []
        self._redo: list[dict] = []
        self._last_state = self.document.to_dict()
        if file_path:
            self.load(file_path)

    @classmethod
    def open(cls, file_path: str, events: Optional[EventBus] = None) -> "Session":
        """Load a ``.tr`` file into a new session."""
        return cls(file_path=file_path, events=events)

    # ------------------------------------------------------------ state
    UNDO_LIMIT = 50

    def touch(self) -> None:
        """Record an undo step when the document changed since the last touch.

        Public because the guide layer calls it: a guide edit is a document
        edit, and reaching across modules for a private method to say so is the
        kind of coupling that rots.
        """
        self._reference_cache.clear()
        state = self.document.to_dict()
        if state != self._last_state:
            self._undo.append(self._last_state)
            del self._undo[: -self.UNDO_LIMIT]
            self._redo.clear()
            self._last_state = state

    def undo(self) -> bool:
        """Undo the last document edit; False when there is nothing to undo."""
        if not self._undo:
            return False
        self._redo.append(self.document.to_dict())
        self.document = Document.from_dict(self._undo.pop())
        self._last_state = self.document.to_dict()
        self._reference_cache.clear()
        return True

    def redo(self) -> bool:
        """Re-apply the last undone edit; False when nothing to redo."""
        if not self._redo:
            return False
        self._undo.append(self.document.to_dict())
        self.document = Document.from_dict(self._redo.pop())
        self._last_state = self.document.to_dict()
        self._reference_cache.clear()
        return True

    @property
    def can_undo(self) -> bool:
        """True when the undo stack holds an earlier state."""
        return bool(self._undo)

    @property
    def is_modified(self) -> bool:
        """True when the document differs from what was last saved."""
        return self.document.to_dict() != self._saved_state

    @property
    def directory(self) -> str:
        """The folder of the session file, or ``""`` while unsaved."""
        return str(self.file_path.parent) if self.file_path else ""

    @property
    def name(self) -> str:
        """The session file name, or ``untitled`` while unsaved."""
        return self.file_path.name if self.file_path else "untitled"

    def new(self) -> None:
        """Replace the document with an empty one and forget the file path."""
        self.document = Document()
        self.file_path = None
        self._saved_state = self.document.to_dict()
        self._last_state = self._saved_state
        self._undo.clear()
        self._redo.clear()
        self._reference_cache.clear()

    def load(self, file_path: str) -> None:
        """Replace the document with the contents of ``file_path``."""
        path = Path(file_path)
        self.document = Document.load(path)
        self.file_path = path
        self._saved_state = self.document.to_dict()
        self._last_state = self._saved_state
        self._undo.clear()
        self._redo.clear()
        self._reference_cache.clear()
        self.events.log(f"Session loaded: {path}")

    def save(self, file_path: Optional[str] = None, increment: bool = False) -> Path:
        """Write the document; ``increment`` saves as the next version instead."""
        target = Path(file_path) if file_path else self.file_path
        if target is None:
            raise SessionSaveError("No file path given for the session.")
        if target.suffix != EXTENSION:
            target = target.with_suffix(EXTENSION)
        if increment:
            target = versioning.next_version(target)
        now = datetime.datetime.now().isoformat(timespec="seconds")
        self.document.meta.setdefault("created_at", now)
        self.document.meta.setdefault("author", getpass.getuser())
        self.document.meta["modified_at"] = now
        self.capture_guides()  # the file must never lag the viewport
        self.document.save(target)
        self.file_path = target
        self._saved_state = self.document.to_dict()
        self.events.log(f"Session saved: {target}")
        return target

    def increment(self) -> Path:
        """Save to the next version number and return the new path."""
        return self.save(increment=True)

    # ------------------------------------------------------------ guides
    #
    # The session is the durable home for the rig's guides; the Maya scene is a
    # working copy of exactly one session at a time, stamped so that "whose
    # guides are these?" always has an answer.

    @property
    def guides(self):
        """This session's guides. The scene renders them; the session owns them."""
        if self._guides is None:
            from tik.trigger.guides import GuideScene

            self._guides = GuideScene(events=self.events, session=self)
        return self._guides

    @property
    def session_id(self) -> str:
        """Stable id for this session, used to stamp its checkout in the scene."""
        found = self.document.meta.get("session_id")
        if not found:
            found = uuid.uuid4().hex
            self.document.meta["session_id"] = found
        return found

    @staticmethod
    def _scene_available() -> bool:
        """Whether there is a Maya scene to read guides out of."""
        try:
            from tik.trigger.guides import document_store

            document_store.read_stamp()
        except Exception:  # noqa: BLE001 - no Maya, or no scene yet
            return False
        return True

    @property
    def owns_scene_guides(self) -> bool:
        """True when the scene's guides are ours, or there are none."""
        from tik.trigger.guides import document_store

        try:
            stamp = document_store.read_stamp()
        except Exception:  # noqa: BLE001 - no Maya: nothing owns anything
            return True
        return not stamp or stamp == self.session_id

    def capture_guides(self) -> bool:
        """Read the scene's poses into this session's guides. Scene -> document.

        A no-op without a live Maya scene: a session can legitimately be opened
        and edited headlessly, and then its stored guides are already the truth.

        No guard is needed against an empty scene. Capture only updates the
        poses and guide attrs of modules the document already holds -- it cannot
        add or remove one -- so there is nothing here that could write emptiness
        over the session's guides.
        """
        if not self._scene_available():
            return False
        from tik.trigger.guides import document_store

        if not self.owns_scene_guides:
            return False
        before = self.document.guides.to_dict()
        # poses only, never a redraw: capturing must not edit the scene
        self.guides.sync()
        document_store.write_stamp(self.session_id)
        return self.document.guides.to_dict() != before

    def snapshot_guides_from_scene(self, document) -> None:
        """Replace this session's guides with ``document`` in one undo step.

        Read by the caller (``GuideScene.snapshot_from_scene``) so this module
        stays importable without Maya. No regenerate follows: the joints in the
        scene already *are* the rendering, and redrawing them would teleport
        guides that are exactly where the rigger left them.
        """
        self.document.guides = document
        self.touch()

    @staticmethod
    def hand_over(outgoing: Optional["Session"], incoming: "Session") -> None:
        """Move the scene's checkout from one session to another.

        Switching session tabs is a *deliberate* hand-off, and it needs its own
        verb because the two halves fight otherwise: ``capture_guides`` stamps
        the scene with the outgoing session's id, which is exactly what would
        make the following ``checkout_guides`` refuse.

        Forcing is safe here, but only when the outgoing session actually held
        the scene and its work is now captured. A tab that never owned the
        guides captures nothing, so there is nothing to make it safe -- and the
        checkout is left to refuse, as it should.
        """
        captured = False
        if outgoing is not None and outgoing is not incoming:
            captured = outgoing.owns_scene_guides and outgoing._scene_available()
            if captured:
                outgoing.capture_guides()
        incoming.checkout_guides(force=captured)

    def checkout_guides(self, force: bool = False) -> None:
        """Claim the scene for this session's guides. **Draws nothing.**

        The scene holds one checkout at a time. A scene stamped for another
        session is reported rather than silently adopted -- discarding someone
        else's working copy has to be a decision, not a side effect.

        Two things this deliberately does not do. It does not *draw*: opening
        a session must not put joints in a scene the rigger may have opened
        for something else, so the modules arrive not-drawn and Draw is theirs
        to press. And it only clears when the rendering belongs to somebody
        else -- the Designer sub-tab checks out on every switch, and clearing
        unconditionally would undraw the guides the rigger is working on.
        """
        from tik.trigger.guides import document_store

        if not self._scene_available():
            return  # headless: there is no scene to claim
        ours = self.owns_scene_guides
        if not force and not ours:
            raise SessionError(
                "The guides in this scene belong to another session. Save that "
                "session first, or check out with force=True."
            )
        if not ours:
            self.guides.clear_rendering()
        document_store.write_stamp(self.session_id)

    # -------------------------------------------------------------- tree
    def view(self, phase: str = BUILD) -> PhaseView:
        """The tree API of one phase. ``session.publish`` is the publish one."""
        if phase not in PHASES:
            raise SessionError(f"Unknown phase '{phase}'.")
        if phase not in self._views:
            self._views[phase] = PhaseView(self, phase)
        return self._views[phase]

    @property
    def publish(self) -> PhaseView:
        """This session's publish list. Runs only as the tail of a full build."""
        return self.view(PUBLISH)

    def root_handles(self, phase: str = BUILD) -> list[ActionHandle]:
        """Handles for the root actions of ``phase``."""
        return [
            ActionHandle(self, node, node.name, phase=phase)
            for node in self.document.roots(phase)
        ]

    @property
    def actions(self) -> list[ActionHandle]:
        """The root actions of the build list."""
        return self.root_handles(BUILD)

    def walk(self, phase: str = BUILD) -> list[ActionHandle]:
        """Every handle depth-first, including referenced (linked) ones."""
        found: list[ActionHandle] = []

        def _visit(handle: ActionHandle) -> None:
            found.append(handle)
            for child in handle.children:
                _visit(child)

        for handle in self.root_handles(phase):
            _visit(handle)
        return found

    def handle(self, path: str, phase: str = BUILD) -> ActionHandle:
        """The handle at ``path``; raises ``SessionError`` when it does not exist."""
        parts = split_path(path)
        if not parts:
            raise SessionError("Empty action path.")
        root = next(
            (item for item in self.root_handles(phase) if item.name == parts[0]), None
        )
        if root is None:
            raise SessionError(f"No action at '{parts[0]}'.")
        return root[join_path(*parts[1:])] if len(parts) > 1 else root

    def __getitem__(self, path: str) -> ActionHandle:
        return self.handle(path, BUILD)

    def find(self, path: str) -> Optional[ActionHandle]:
        """The build-list action at ``path``, or None."""
        try:
            return self[path]
        except SessionError:
            return None

    def __contains__(self, path: str) -> bool:
        return self.find(path) is not None

    def paths(self, phase: str = BUILD) -> list[str]:
        """Every action path in ``phase``, depth first."""
        return self.document.paths(phase)

    def add(
        self,
        action_type: str,
        name: Optional[str] = None,
        *,
        parent: Optional[str | ActionHandle] = None,
        after: Optional[str | ActionHandle] = None,
        index: Optional[int] = None,
        phase: str = BUILD,
        **settings,
    ) -> ActionHandle:
        """Add an action; ``after`` places it next to a sibling, ``parent`` nests it."""
        action_cls = registry.get_action(action_type)  # raises for an unknown type
        if not registry.allows(action_type, phase):
            raise SessionError(
                f"'{action_type}' cannot be placed in the {phase} list "
                f"(its scope is '{getattr(action_cls, 'scope', BUILD)}')."
            )
        action = action_cls(settings=settings)  # validates
        parent_path = parent.path if isinstance(parent, ActionHandle) else parent
        if after is not None:
            after_path = after.path if isinstance(after, ActionHandle) else after
            parts = split_path(after_path)
            parent_path = join_path(*parts[:-1]) or None
            siblings = self.document.siblings(parent_path, phase)
            index = [node.name for node in siblings].index(parts[-1]) + 1
        node = ActionNode(
            name=name or action_type, type=action_type, settings=action.values()
        )
        path = self.document.add(node, parent=parent_path, index=index, phase=phase)
        self.touch()
        return self.handle(path, phase)

    def remove(self, path: str | ActionHandle, phase: str = BUILD) -> None:
        """Remove the action at ``path`` from ``phase``."""
        self.document.remove(
            path.path if isinstance(path, ActionHandle) else path, phase=phase
        )
        self.touch()

    def move(
        self,
        path: str | ActionHandle,
        *,
        parent: Optional[str] = None,
        index: Optional[int] = None,
        after: Optional[str] = None,
        phase: str = BUILD,
    ) -> ActionHandle:
        """Move an action under ``parent``, to ``index``, or ``after`` a sibling."""
        path = path.path if isinstance(path, ActionHandle) else path
        new_path = self.document.move(
            path, parent=parent, index=index, after=after, phase=phase
        )
        self.touch()
        return self.handle(new_path, phase)

    def rename(
        self, path: str | ActionHandle, new_name: str, phase: str = BUILD
    ) -> ActionHandle:
        """Rename an action; returns the handle at its new path."""
        path = path.path if isinstance(path, ActionHandle) else path
        new_path = self.document.rename(path, new_name, phase=phase)
        self.touch()
        return self.handle(new_path, phase)

    def duplicate(self, path: str | ActionHandle, phase: str = BUILD) -> ActionHandle:
        """Copy an action next to itself with a unique name."""
        path = path.path if isinstance(path, ActionHandle) else path
        new_path = self.document.duplicate(path, phase=phase)
        self.touch()
        return self.handle(new_path, phase)

    # ------------------------------------------------------- references
    def _referenced_document(self, handle: ActionHandle) -> Document:
        from tik.trigger.actions.reference.reference import Reference

        key = handle.path
        if key not in self._reference_cache:
            document, _dir, _file = Reference.expand(handle.node, self.directory)
            self._reference_cache[key] = document
        return self._reference_cache[key]

    # ------------------------------------------------------------ running
    def _runner(self):
        from tik.trigger.maya.runner import Runner

        return Runner(self.events)

    def _module_problems(self) -> list[str]:
        """Problems and warnings from every module in the guide document.

        The rigger should not have to press Build to find out that a settings
        change orphaned an animation space.
        """
        problems: list[str] = []
        for entry in self.document.guides.modules:
            try:
                module_cls = registry.get_module(entry.module_type)
            except Exception:  # an unregistered type is the runner's report
                continue
            module = module_cls(
                instance_id=entry.instance_id,
                name=entry.name,
                side=entry.side,
                settings=entry.settings,
            )
            module.guide_pairs = list(entry.pairs)
            problems.extend(f"{entry.key}: {item}" for item in module.validate())
            problems.extend(
                f"warning: {entry.key}: {item}" for item in module.warnings()
            )
        return problems

    # ------------------------------------------------- cross-action checks
    KINEMATICS = "kinematics"

    def _kinematics_scopes(self) -> list:
        """``[(path, [instance ids])]`` for every enabled kinematics, in order."""
        return [
            (path, list(node.settings.get("modules") or []))
            for path, node, _parent in self.document.walk(BUILD)
            if node.type == self.KINEMATICS and node.enabled
        ]

    def _scope_problems(self) -> list:
        """Problems spanning several actions, which no single action can see.

        Explicit build scope is what makes these statable: until an action said
        which modules it built, "built twice", "built by nobody" and "needs
        something built later" had no way of being expressed, let alone
        checked.
        """
        from tik.trigger.core.schemas import split_source

        problems: list[str] = []
        entries = list(self.document.guides.modules)
        by_id = {entry.instance_id: entry for entry in entries}
        scopes = self._kinematics_scopes()

        def label(instance_id: str) -> str:
            entry = by_id.get(instance_id)
            return entry.key if entry is not None else instance_id

        # which pass builds what, and what is built more than once
        pass_of: dict = {}
        for index, (path, scope) in enumerate(scopes):
            for instance_id in scope:
                if instance_id in pass_of:
                    problems.append(
                        f"{label(instance_id)} is built by more than one "
                        f"kinematics action ({pass_of[instance_id][1]} and {path})."
                    )
                    continue
                pass_of[instance_id] = (index, path)

        # Only worth saying once a pipeline exists to be missing from: a
        # session still being authored in the Designer has no kinematics
        # action yet, and warning about every module would be pure noise.
        if scopes:
            for entry in entries:
                if entry.instance_id not in pass_of:
                    problems.append(
                        f"warning: {entry.key} is built by no kinematics action."
                    )

        # only modules that actually build can collide in the rig
        keys: dict = {}
        for instance_id in pass_of:
            entry = by_id.get(instance_id)
            if entry is None:
                continue
            if entry.key in keys:
                problems.append(
                    f"two modules that build share the display key "
                    f"'{entry.key}'. Rename one."
                )
            keys[entry.key] = instance_id

        # a producer must build before its consumer, and must build at all
        for entry in entries:
            here = pass_of.get(entry.instance_id)
            if here is None:
                continue
            for source in entry.inputs.values():
                source_id, _output = split_source(source)
                if source_id is None or source_id not in by_id:
                    continue
                there = pass_of.get(source_id)
                if there is None:
                    problems.append(
                        f"{entry.key} needs {label(source_id)}, but no "
                        "kinematics action builds it."
                    )
                elif there[0] > here[0]:
                    problems.append(
                        f"{entry.key} needs {label(source_id)}, which builds "
                        "in a later kinematics action."
                    )

        # what the migration could not translate
        for path, node, _parent in self.document.walk(BUILD):
            if node.type != self.KINEMATICS:
                continue
            if node.settings.get("legacy_roots"):
                problems.append(
                    f"{path}: guide roots {node.settings['legacy_roots']} could "
                    "not be migrated to module ids; open the session and list "
                    "its modules."
                )
            if node.settings.get("guides_file"):
                problems.append(
                    f"{path}: '{node.settings['guides_file']}' is no longer "
                    "built at build time; import the .trg into this session "
                    "and list its modules."
                )
        return problems

    def validate(self) -> list[str]:
        """Pre-flight problems for every runnable step, in both lists."""
        from tik.trigger.core.action import ActionContext

        runner = self._runner()
        problems: list[str] = []
        for phase in PHASES:
            prefix = "" if phase == BUILD else f"{phase}: "
            try:
                plan = runner.plan(self.document, self.directory, phase=phase)
            except SessionError as error:
                problems.append(f"{prefix}{error}")
                continue
            problems.extend(f"{prefix}{item}" for item in plan.problems)
            for step in plan.steps:
                action = registry.get_action(step.node.type)(
                    settings=step.node.settings
                )
                ctx = ActionContext(
                    session=self,
                    events=self.events,
                    base_dir=step.base_dir,
                    path=step.path,
                )
                problems.extend(
                    f"{prefix}{step.path}: {item}" for item in action.validate(ctx)
                )
        problems.extend(self._module_problems())
        problems.extend(self._scope_problems())
        return problems

    def build(
        self,
        until: Optional[str | ActionHandle] = None,
        reset_scene: bool = True,
        publish: bool = False,
    ) -> list[StepResult]:
        """Reset the scene and run the build list, then the publish list if asked.

        ``until`` stops after that build action -- and forbids ``publish``,
        because a partial build is not a rig anyone should be exporting.
        """
        until = until.path if isinstance(until, ActionHandle) else until
        if publish and until is not None:
            raise SessionError(
                "'until' cannot be combined with publish: "
                "a partial build must not publish."
            )
        blocking = [
            item for item in self._scope_problems() if not item.startswith("warning:")
        ]
        if blocking:
            raise SessionError("; ".join(blocking))
        self.events.log(f"Building{' and publishing' if publish else ''} {self.name}")
        # The runner resets the scene, so the guides have to be in the document
        # before it does. Saving already captures; building must too, or a rig
        # built from an unsaved session has no guides at all.
        self.capture_guides()
        return self._runner().run(
            self.document,
            self.directory,
            until=until,
            reset_scene=reset_scene,
            session=self,
            publish=publish,
        )

    def run(self, path: str | ActionHandle) -> StepResult:
        """Run a single build action in the current scene (no reset).

        Publish actions are deliberately excluded: the only way one executes is
        as the tail of a full clean build, so no partial or hand-edited rig can
        produce a published artifact.
        """
        path = path.path if isinstance(path, ActionHandle) else path
        if self.document.find(path, phase=PUBLISH) is not None:
            raise SessionError(
                f"'{path}' is a publish action; "
                "publish actions run only with Build & Publish."
            )
        self.capture_guides()
        return self._runner().run(
            self.document, self.directory, only=path, reset_scene=False, session=self
        )[0]

    def steps(self, until: Optional[str] = None, phase: str = BUILD):
        """The planned steps of one phase (what Build would run)."""
        return (
            self._runner()
            .plan(self.document, self.directory, until=until, phase=phase)
            .steps
        )

    def __repr__(self) -> str:
        return (
            f"Session({self.name}, {len(self.document.actions)} actions, "
            f"{len(self.document.publish)} publish)"
        )

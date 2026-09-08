"""Everything a version control provider adds to Trigger's windows.

Each piece appears only when ``vcs.active()`` returns a provider, and reads
with the provider's own label: "from Tik Manager…", never "from VCS". The
shared widgets know nothing of this; they only expose a second button.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

from tik.shared.ui.feedback import Feedback
from tik.shared.ui.Qt import QtGui, QtWidgets
from tik.trigger import vcs
from tik.trigger.core import ActionContext, kinds
from tik.trigger.vcs.provider import Context, VersionControl

logger = logging.getLogger(__name__)

LATEST = "#9fd8b3"
OLDER = "#f0b45c"


def provider() -> Optional[VersionControl]:
    """The active provider, or None."""
    return vcs.active()


def kind_of(field) -> str:
    """The kind a file field browses and publishes as."""
    return kinds.kind_for(getattr(field, "extensions", ()), getattr(field, "kind", ""))


# ------------------------------------------------------------ file fields
def _resolve(value: str, session_dir: str) -> Optional[Path]:
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute() and session_dir:
        path = Path(session_dir) / path
    return path


def field_actions(field_name, field, widget, session_dir: str) -> list:
    """``(text, callable)`` entries for a file field's VCS button.

    A ``mode="dir"`` field names a folder, not a file: ``Action.file_fields``
    already leaves those out of the dependency set, and there is nothing for a
    VCS to browse for or publish, so it gets no entries at all.
    """
    active = provider()
    if active is None or getattr(field, "mode", "open") == "dir":
        return []
    label = active.display_label()
    entries = []
    if active.supports("browse"):

        def _browse():
            picked = active.browse(
                kind_of(field),
                list(getattr(field, "extensions", ())),
                getattr(field, "mode", "open"),
            )
            if picked:
                # the same normalisation the widget's own Browse applies
                picked = str(picked).replace("\\", "/")
                widget.setValue(picked)
                widget.changed.emit(picked)

        entries.append((f"Browse {label}…", _browse))
    resolved = _resolve(widget.value(), session_dir)
    if resolved is not None and resolved.is_file() and active.supports("publish_file"):
        entries.append(
            (
                f"Publish {resolved.name} to {label}…",
                lambda: vcs.publish_file(kind_of(field), resolved),
            )
        )
    return entries


def _popup(parent, entries) -> None:
    menu = QtWidgets.QMenu(parent)
    for text, callback in entries:
        menu.addAction(text, callback)
    menu.exec_(QtGui.QCursor.pos())


def show_field_menu(field_name, field, widget, session_dir: str) -> None:
    """Run the one entry, or pop a menu when there are several."""
    entries = field_actions(field_name, field, widget, session_dir)
    if len(entries) == 1:
        entries[0][1]()
    elif entries:
        _popup(widget, entries)


def form_vcs_slot(session_dir: Callable[[], str]) -> Optional[tuple]:
    """The ``FormBuilder(file_vcs=)`` argument, or None without a provider."""
    active = provider()
    if active is None:
        return None
    return (
        f"From {active.display_label()}",
        lambda name, field, widget: show_field_menu(
            name, field, widget, session_dir() if session_dir else ""
        ),
    )


# ---------------------------------------------------------- pipeline rows
def publishable_files(handle, session) -> list:
    """``(kind, path)`` for every existing file the handle's action names."""
    action = handle.action_class(settings=dict(handle.settings))
    ctx = ActionContext(session=session, base_dir=session.directory, path=handle.path)
    found = []
    seen = set()
    for name, field in action.file_fields().items():
        value = getattr(action, name)
        if not value:
            continue
        path = ctx.resolve(value)
        if path.exists():
            found.append((kind_of(field), path))
            seen.add(path)
    for path in action.dependencies(ctx):
        if path not in seen and path.exists():
            found.append((kinds.FILE, path))
            seen.add(path)
    return found


def add_publish_submenu(menu, handle, session):
    """Add "Publish to <label>" with one entry per file; None when nothing applies."""
    active = provider()
    if active is None or handle is None or not active.supports("publish_file"):
        return None
    if session is None:
        return None
    files = publishable_files(handle, session)
    if not files:
        return None
    # Built with the menu as its C++ parent rather than ``menu.addMenu(str)``:
    # that hands ownership to Python and the submenu dies with the local.
    submenu = QtWidgets.QMenu(f"Publish to {active.display_label()}", menu)
    menu.addMenu(submenu)
    for kind, path in files:
        submenu.addAction(path.name, lambda k=kind, p=path: vcs.publish_file(k, p))
    return submenu


# ------------------------------------------------------------- pickers
def pick_file(
    parent, kind, extensions, mode, start: str = "", caption: str = ""
) -> str:
    """A path from the plain dialog or, when a provider browses, from either."""
    active = provider()
    dialog = Feedback(parent)

    def _plain() -> str:
        if mode == "save":
            return dialog.browse_save(caption or "Save", start, tuple(extensions))
        if mode == "dir":
            return dialog.browse_dir(caption or "Choose folder", start)
        return dialog.browse_open(caption or "Open", start, tuple(extensions))

    if active is None or not active.supports("browse"):
        return _plain()
    result = {"path": ""}

    def _from_vcs():
        result["path"] = active.browse(kind, list(extensions), mode)

    def _from_disk():
        result["path"] = _plain()

    _popup(
        parent,
        [("Browse…", _from_disk), (f"From {active.display_label()}…", _from_vcs)],
    )
    return result["path"]


# ----------------------------------------------------------------- window
def build_file_submenu(window, file_menu):
    """File > <label>, or None without a provider."""
    active = provider()
    if active is None:
        return None
    label = active.display_label()
    submenu = QtWidgets.QMenu(label, file_menu)
    file_menu.addMenu(submenu)
    icon = active.icon_path()
    if icon is not None:
        submenu.setIcon(QtGui.QIcon(str(icon)))
    if active.supports("open"):
        submenu.addAction(f"Open from {label}…", lambda: vcs.open())
    if active.supports("new_version"):
        submenu.addAction("Save New Version", lambda: vcs.new_version())
    window.vcs_publish_action = submenu.addAction(
        "Publish…", lambda: window._view_call("build_and_publish")
    )
    window.vcs_publish_action.setToolTip(
        "Runs Build & Publish. Add a publish action to the publish list first."
    )
    if active.supports("launch"):
        submenu.addAction(f"Open {label}", lambda: vcs.launch())
    return submenu


def sync_publish_entry(window) -> None:
    """Enable "Publish…" only when the session has something in its publish list."""
    action = getattr(window, "vcs_publish_action", None)
    if action is None:
        return
    session = window.session
    action.setEnabled(session is not None and len(session.publish) > 0)


def chip(context: Optional[Context], active: Optional[VersionControl]) -> tuple:
    """``(text, color)`` for the status chip."""
    if active is None:
        return "", ""
    if context is None:
        return f"Not a {active.display_label()} work", OLDER
    text = context.label
    if context.version is not None:
        text += f" · v{context.version:03d}"
    return text, (LATEST if context.is_latest else OLDER)


def refresh_chip(window) -> None:
    """Re-read the provider's context for the active session and paint the chip.

    Runs on every title update -- a tab change, a save, an open -- and calls
    into third-party code, so a provider that raises is logged and treated as
    "this path is not a work", exactly as ``vcs.active()`` treats a provider
    whose ``available()`` blows up. Saving a session must never fail because a
    VCS plugin did.
    """
    active = provider()
    context = None
    if active is not None and active.supports("context"):
        try:
            context = active.context(vcs.host.session_path)
        except Exception as error:  # noqa: BLE001 - a broken provider knows nothing
            logger.error(
                "vcs: provider %s failed to read its context: %s",
                active.name or type(active).__name__,
                error,
            )
    text, color = chip(context, active)
    window.status.set("vcs", text)
    window.status.set_color("vcs", color)
    window.status.labels["vcs"].setToolTip(context.detail if context else "")
    # built unconditionally so a provider arriving through the preference needs
    # no rebuilt strip, but hidden -- separator and all -- while it says nothing
    window.status.set_visible("vcs", bool(text))

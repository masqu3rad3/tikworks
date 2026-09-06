"""Session file preferences: recent list, browsing, autosave."""

from __future__ import annotations

from tik.core.fields import BoolField, FieldGroup, FileField, IntField
from tik.shared.prefs import PrefPage, register_page


@register_page
class FilesPrefs(PrefPage):
    """How Trigger opens, remembers and protects session files."""

    name, label, order = "files", "Files & Sessions", 30

    RECENT = FieldGroup("Recent")
    BROWSING = FieldGroup("Browsing")
    AUTOSAVE = FieldGroup("Autosave")
    CONFIRMATIONS = FieldGroup("Confirmations")

    remember_recent = BoolField(
        True,
        group=RECENT,
        label="Remember recent sessions",
        help="Keep the Open Recent list between launches.",
    )
    max_recent = IntField(
        8,
        min=1,
        max=30,
        group=RECENT,
        label="How many to keep",
        help="Length of the Open Recent list.",
    )
    remember_last_folder = BoolField(
        True,
        group=BROWSING,
        label="Remember last folder",
        help="Reopen file browsers in the folder you last used.",
    )
    default_folder = FileField(
        "",
        mode="dir",
        group=BROWSING,
        label="Default session folder",
        help=(
            "Where file browsers start when there is no last folder. "
            "Empty means your home folder."
        ),
    )
    autosave = BoolField(
        False,
        group=AUTOSAVE,
        label="Enable autosave",
        help=(
            "Periodically write a recovery copy beside the session file. "
            "Your own file is never written without you asking."
        ),
    )
    autosave_interval = IntField(
        300,
        min=30,
        max=3600,
        group=AUTOSAVE,
        label="Interval (seconds)",
        help="How often a recovery copy is written while the session is modified.",
    )
    confirm_unsaved_close = BoolField(
        True,
        group=CONFIRMATIONS,
        label="Warn on unsaved close",
        help="Ask before closing a tab that has unsaved changes.",
    )

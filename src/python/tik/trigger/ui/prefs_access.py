"""Preference reads that more than one UI file needs.

Lives in the UI layer deliberately: ``tik/trigger/actions`` may not import the
preferences package, because nothing on the path from a saved session to a
built rig may read a user setting.
"""

from __future__ import annotations

from tik.trigger.config import prefs


def editor_command() -> str:
    """The user's external editor command, or ``""`` for the OS default.

    ``tik.shared.io.open_external`` substitutes ``{path}`` into the command
    and otherwise appends the file, so a launcher with arguments needs no
    second setting.
    """
    return str(prefs.tools.external_editor or "")

"""User preferences: a JSON store, declarative pages, and a registry.

Pure Python by rule -- no Qt, no Maya. The Qt dialog that renders these pages
lives in ``tik.shared.ui.prefs_dialog``.
"""

from tik.shared.prefs.store import DEFAULT_FOLDER, PrefStore

__all__ = ["DEFAULT_FOLDER", "PrefStore"]

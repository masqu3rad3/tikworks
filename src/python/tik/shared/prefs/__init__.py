"""User preferences: a JSON store, declarative pages, and a registry.

Pure Python by rule -- no Qt, no Maya. The Qt dialog that renders these pages
lives in ``tik.shared.ui.prefs_dialog``.
"""

from tik.shared.prefs import registry
from tik.shared.prefs.page import PrefPage
from tik.shared.prefs.preferences import LazyPreferences, Preferences
from tik.shared.prefs.registry import clear_pages, page, pages, register_page
from tik.shared.prefs.store import DEFAULT_FOLDER, PrefStore

__all__ = [
    "DEFAULT_FOLDER",
    "LazyPreferences",
    "PrefPage",
    "PrefStore",
    "Preferences",
    "clear_pages",
    "page",
    "pages",
    "register_page",
    "registry",
]

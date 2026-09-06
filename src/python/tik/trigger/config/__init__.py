"""Trigger's user preferences.

``prefs`` is lazy: importing this package performs no file I/O, so it is safe
to import at module level from the UI. The store is read the first time a page
is touched.

Nothing on the build path may import this package -- a preference must never
be able to change a rig. ``tests/unit/test_import_boundaries.py`` enforces it.
"""

from tik.shared.prefs import LazyPreferences, Preferences, PrefStore

#: The file under ``~/TikWorks``.
STORE_NAME = "trigger"


def _build_preferences() -> Preferences:
    """Register Trigger's pages and bind them to the store."""
    from tik.shared.prefs import registry
    from tik.trigger.config import pages  # noqa: F401 - importing registers

    return Preferences(PrefStore(STORE_NAME), registry.pages())


#: Application-wide preference values. Resolved on first attribute access.
prefs = LazyPreferences(_build_preferences)

__all__ = ["LazyPreferences", "STORE_NAME", "prefs"]

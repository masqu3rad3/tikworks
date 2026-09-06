"""The live preference values: page instances backed by a ``PrefStore``.

Values live on the page instances. ``snapshot`` and ``restore`` are what give
the dialog its Cancel: it snapshots on open, edits the live pages through a
``FormBuilder``, and either saves or puts the snapshot back.

Loading is lazy. Importing a module that holds a ``Preferences`` must never
touch the disk -- under Maya the working directory is often unwritable, and an
import-time read is how the previous settings system broke.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

from tik.core.fields import FieldValidationError
from tik.shared.prefs.store import PrefStore

LOG = logging.getLogger(__name__)


class Preferences:
    """Live preference values for a set of pages."""

    def __init__(self, store: PrefStore, page_classes: Iterable[type]) -> None:
        """
        Args:
            store: Where values are read from and written to.
            page_classes: ``PrefPage`` subclasses, in display order.
        """
        self._store = store
        self._classes = list(page_classes)
        self._pages: dict[str, Any] = {}
        self._loaded = False

    # ------------------------------------------------------------- loading
    @property
    def store(self) -> PrefStore:
        """The backing file."""
        return self._store

    def _ensure_loaded(self) -> None:
        """Instantiate the pages and fill them from the file, once."""
        if self._loaded:
            return
        # Set first: a failure below must not leave us retrying on every read.
        self._loaded = True
        self._pages = {cls.name: cls() for cls in self._classes}
        stored = self._store.read()
        for key, value in stored.items():
            page_name, _, field_name = key.partition(".")
            page = self._pages.get(page_name)
            if page is None or field_name not in page.fields():
                # A key from a removed page or a renamed field. Dropping it
                # silently is the point: the file is hand-editable, and old
                # keys must never stop the tool from opening.
                continue
            try:
                setattr(page, field_name, value)
            except FieldValidationError:
                LOG.warning(
                    "Ignoring invalid stored preference %s=%r; using the default.",
                    key,
                    value,
                )

    # --------------------------------------------------------------- pages
    def pages(self) -> list:
        """Every page instance, in display order."""
        self._ensure_loaded()
        return [self._pages[cls.name] for cls in self._classes]

    def page(self, name: str):
        """The page instance registered under ``name``.

        Raises:
            KeyError: If there is no such page.
        """
        self._ensure_loaded()
        return self._pages[name]

    def __getattr__(self, name: str):
        """``prefs.interface`` returns the Interface page instance."""
        # Only reached for attributes not found normally, so the leading
        # underscore guard keeps __init__ and copy/pickle out of the lookup.
        if name.startswith("_"):
            raise AttributeError(name)
        self._ensure_loaded()
        try:
            return self._pages[name]
        except KeyError:
            raise AttributeError(f"No preferences page named '{name}'.") from None

    # ----------------------------------------------------------- snapshots
    def snapshot(self) -> dict:
        """Every value, keyed ``"<page>.<field>"``."""
        return {
            f"{page.name}.{field}": value
            for page in self.pages()
            for field, value in page.values().items()
        }

    def restore(self, snapshot: dict) -> None:
        """Put a previous :meth:`snapshot` back onto the pages."""
        self._ensure_loaded()
        for key, value in snapshot.items():
            page_name, _, field_name = key.partition(".")
            page = self._pages.get(page_name)
            if page is not None and field_name in page.fields():
                setattr(page, field_name, value)

    def changed_keys(self, snapshot: dict) -> list[str]:
        """Keys whose value differs from ``snapshot``."""
        current = self.snapshot()
        return sorted(
            key for key, value in current.items() if snapshot.get(key) != value
        )

    def reset_page(self, name: str) -> None:
        """Restore one page to its declared defaults."""
        self.page(name).reset()

    # --------------------------------------------------------------- write
    def save(self) -> None:
        """Write every page's values to the file."""
        self._store.write(self.snapshot())

    def __repr__(self) -> str:
        return f"Preferences({self._store.path.name}, {len(self._classes)} pages)"


class LazyPreferences:
    """A ``Preferences`` that builds itself on first use.

    Lets a package expose a module-level ``prefs`` object without doing any
    file I/O at import time.
    """

    def __init__(self, factory) -> None:
        """
        Args:
            factory: Zero-argument callable returning a ``Preferences``.
        """
        self._factory = factory
        self._wrapped: Optional[Preferences] = None

    def _resolve(self) -> Preferences:
        if self._wrapped is None:
            self._wrapped = self._factory()
        return self._wrapped

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._resolve(), name)

    def __repr__(self) -> str:
        if self._wrapped is None:
            return "LazyPreferences(unloaded)"
        return repr(self._wrapped)

"""The preferences dialog: a category list, a generated page, and a footer.

Generic by construction -- it renders whatever pages a ``Preferences`` holds
and knows nothing about any particular tool. Adding a setting anywhere never
requires touching this file.

Two display modes share one scroll area. Normally a single page's form is
visible and the others are hidden. While a search is active every form is
shown at once, each filtered to its matching fields and captioned with its
page label, so results read as one list across categories.
"""

from __future__ import annotations

from typing import Optional

from tik.shared.prefs import Preferences
from tik.shared.ui import theme
from tik.shared.ui.fields import FormBuilder
from tik.shared.ui.Qt import QtCore, QtWidgets


class PrefsDialog(QtWidgets.QDialog):
    """Edit a ``Preferences`` object.

    Signals:
        applied(list): keys that changed, emitted after Apply or OK writes.
    """

    applied = QtCore.Signal(list)

    def __init__(
        self,
        preferences: Preferences,
        parent=None,
        title: str = "Settings",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setObjectName("PrefsDialog")
        self.setModal(True)
        self.resize(720, 480)
        self.prefs = preferences
        # What the values were when the dialog opened, and what they were at
        # the last Apply. The first is what Cancel puts back; the second is
        # what Apply diffs against to report changed keys.
        self._opening = preferences.snapshot()
        self._last_applied = dict(self._opening)
        self.forms: dict[str, FormBuilder] = {}
        self._captions: dict[str, QtWidgets.QLabel] = {}
        self._searching = False
        self._matches: list = []
        self._build()
        theme.apply(self)

    # ---------------------------------------------------------------- build
    def _build(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        body = QtWidgets.QHBoxLayout()
        body.setSpacing(8)
        layout.addLayout(body, 1)
        body.addWidget(self._build_sidebar())
        body.addWidget(self._build_pages(), 1)
        layout.addWidget(self._build_footer())

        self.categories.setCurrentRow(0)
        self._show_page(0)

    def _build_sidebar(self) -> QtWidgets.QWidget:
        holder = QtWidgets.QWidget()
        holder.setFixedWidth(170)
        column = QtWidgets.QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)

        self.search_field = QtWidgets.QLineEdit()
        self.search_field.setPlaceholderText("Search settings…")
        self.search_field.setClearButtonEnabled(True)
        self.search_field.textChanged.connect(self.search)
        column.addWidget(self.search_field)

        self.categories = QtWidgets.QListWidget()
        self.categories.setObjectName("PrefsCategories")
        for page in self.prefs.pages():
            item = QtWidgets.QListWidgetItem(page.label or page.name)
            item.setData(QtCore.Qt.UserRole, page.name)
            self.categories.addItem(item)
        self.categories.currentRowChanged.connect(self._show_page)
        column.addWidget(self.categories, 1)
        return holder

    def _build_pages(self) -> QtWidgets.QWidget:
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        inner = QtWidgets.QWidget()
        self._page_layout = QtWidgets.QVBoxLayout(inner)
        self._page_layout.setContentsMargins(4, 4, 4, 4)
        self._page_layout.setSpacing(4)

        for page in self.prefs.pages():
            caption = QtWidgets.QLabel(page.label or page.name)
            caption.setObjectName("PrefsCaption")
            caption.hide()
            self._captions[page.name] = caption
            self._page_layout.addWidget(caption)

            form = FormBuilder(page)
            self.forms[page.name] = form
            self._page_layout.addWidget(form)

        self.empty_label = QtWidgets.QLabel("No settings match.")
        self.empty_label.setObjectName("PrefsEmpty")
        self.empty_label.setAlignment(QtCore.Qt.AlignCenter)
        self.empty_label.hide()
        self._page_layout.addWidget(self.empty_label)
        self._page_layout.addStretch(1)

        self.scroll.setWidget(inner)
        return self.scroll

    def _build_footer(self) -> QtWidgets.QWidget:
        holder = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)

        self.defaults_button = QtWidgets.QPushButton("Restore Defaults")
        self.defaults_button.clicked.connect(self.restore_defaults)
        row.addWidget(self.defaults_button)
        row.addStretch(1)

        cancel = QtWidgets.QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)

        self.apply_button = QtWidgets.QPushButton("Apply")
        self.apply_button.clicked.connect(self.apply_changes)
        row.addWidget(self.apply_button)

        ok = QtWidgets.QPushButton("OK")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        row.addWidget(ok)
        return holder

    # ----------------------------------------------------------- page view
    def _page_names(self) -> list:
        return [page.name for page in self.prefs.pages()]

    def current_page(self) -> Optional[str]:
        """The selected page's name, or None while searching."""
        if self._searching:
            return None
        row = self.categories.currentRow()
        names = self._page_names()
        return names[row] if 0 <= row < len(names) else None

    def _show_page(self, row: int) -> None:
        """Show exactly one page's form, unfiltered."""
        if self._searching:
            return
        names = self._page_names()
        if not 0 <= row < len(names):
            return
        wanted = names[row]
        for name, form in self.forms.items():
            form.set_visible_fields(None)
            form.setVisible(name == wanted)
            self._captions[name].hide()
        self.empty_label.hide()

    # -------------------------------------------------------------- search
    def _index(self) -> list:
        """``(page_name, field_name, haystack)`` for every visible field."""
        entries = []
        for page in self.prefs.pages():
            for field_name, field in type(page).fields().items():
                if field.hidden:
                    continue
                haystack = f"{field.label or field_name} {field.help}".lower()
                entries.append((page.name, field_name, haystack))
        return entries

    def search(self, text: str) -> list:
        """Filter every page down to fields matching ``text``.

        Returns the matching ``"<page>.<field>"`` keys, so a caller (and the
        tests) can see what a query resolved to.
        """
        term = (text or "").strip().lower()
        self._searching = bool(term)
        self.defaults_button.setEnabled(not self._searching)
        self.categories.setEnabled(not self._searching)

        if not self._searching:
            self._matches = []
            self._show_page(self.categories.currentRow())
            return []

        matches: dict = {name: set() for name in self.forms}
        for page_name, field_name, haystack in self._index():
            if term in haystack:
                matches[page_name].add(field_name)

        for name, form in self.forms.items():
            found = matches[name]
            form.set_visible_fields(found)
            form.setVisible(bool(found))
            self._captions[name].setVisible(bool(found))

        keys = sorted(
            f"{page}.{field}" for page, fields in matches.items() for field in fields
        )
        self.empty_label.setVisible(not keys)
        self._matches = keys
        return keys

    def visible_matches(self) -> list:
        """The keys a search is currently showing, empty when not searching.

        Read from what the last :meth:`search` resolved to rather than
        recomputed from the search field: ``search`` can be called directly,
        and then the field's text is not the query that is on screen.
        """
        return list(self._matches)

    # --------------------------------------------------------------- verbs
    def apply_changes(self) -> None:
        """Write the values and announce what changed."""
        changed = self.prefs.changed_keys(self._last_applied)
        self.prefs.save()
        self._last_applied = self.prefs.snapshot()
        self.applied.emit(changed)

    def restore_defaults(self) -> None:
        """Reset the selected page. Staged like any edit, so Cancel undoes it."""
        name = self.current_page()
        if name is None:
            return
        self.prefs.reset_page(name)
        self.forms[name].refresh()

    def accept(self) -> None:
        """Apply, then close."""
        self.apply_changes()
        super().accept()

    def reject(self) -> None:
        """Put back whatever was last written, then close."""
        self.prefs.restore(self._last_applied)
        super().reject()

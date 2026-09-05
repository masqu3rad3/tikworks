"""Generate Qt editors from ``tik.core.fields`` schemas.

``FormBuilder`` turns any ``Schema`` instance into a form: one widget per
field, grouped by ``field.group``, with validation errors surfaced inline.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from tik.core.fields import Field, FieldValidationError, Schema
from tik.shared.ui.collapsible import CollapsibleGroup
from tik.shared.ui.feedback import Feedback
from tik.shared.ui.Qt import QtCore, QtWidgets


class _VectorEditor(QtWidgets.QWidget):
    """Row of double spin boxes."""

    valueChanged = QtCore.Signal(object)

    def __init__(
        self, size: int, minimum=None, maximum=None, labels=None, parent=None
    ) -> None:
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.spins: list[QtWidgets.QDoubleSpinBox] = []
        for index in range(size):
            spin = QtWidgets.QDoubleSpinBox()
            # The field's own bounds, so the widget cannot offer a value
            # validate() would then reject.
            spin.setRange(
                float(minimum) if minimum is not None else -1e9,
                float(maximum) if maximum is not None else 1e9,
            )
            spin.setDecimals(3)
            spin.valueChanged.connect(
                lambda _value: self.valueChanged.emit(self.value())
            )
            if labels and index < len(labels):
                column = QtWidgets.QVBoxLayout()
                column.setContentsMargins(0, 0, 0, 0)
                column.setSpacing(1)
                caption = QtWidgets.QLabel(str(labels[index]))
                caption.setObjectName("FieldCaption")
                column.addWidget(caption)
                column.addWidget(spin)
                layout.addLayout(column)
            else:
                layout.addWidget(spin)
            self.spins.append(spin)

    def value(self) -> tuple:
        return tuple(spin.value() for spin in self.spins)

    def setValue(self, value) -> None:  # noqa: N802 - Qt style
        for spin, item in zip(self.spins, value):
            spin.blockSignals(True)
            spin.setValue(float(item))
            spin.blockSignals(False)


class _TableEditor(QtWidgets.QWidget):
    """A table of typed rows with add/remove buttons."""

    valueChanged = QtCore.Signal(object)  # noqa: N815 - matches the Qt widgets here

    def __init__(self, columns, choices_resolver=None, parent=None) -> None:
        super().__init__(parent)
        self.columns = list(columns)
        self._resolve = choices_resolver or (lambda _name: ())
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.table = QtWidgets.QTableWidget(0, len(self.columns))
        self.table.setHorizontalHeaderLabels(
            [column.display() for column in self.columns]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        layout.addWidget(self.table)

        buttons = QtWidgets.QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        self.add_button = QtWidgets.QPushButton("+")
        self.remove_button = QtWidgets.QPushButton("-")
        for button in (self.add_button, self.remove_button):
            button.setFixedWidth(24)
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self.add_button.clicked.connect(lambda: self.add_row())
        self.remove_button.clicked.connect(self._remove_selected)

    # ------------------------------------------------------------- rows
    def _choices(self, column):
        if column.choices_from:
            return list(self._resolve(column.choices_from))
        return list(column.choices)

    def _make_cell(self, column, value):
        if column.kind == "choice":
            widget = QtWidgets.QComboBox()
            widget.addItems([str(item) for item in self._choices(column)])
            if value:
                index = widget.findText(str(value))
                if index >= 0:
                    widget.setCurrentIndex(index)
            widget.currentIndexChanged.connect(self._emit)
            return widget
        widget = QtWidgets.QLineEdit(str(value or ""))
        widget.editingFinished.connect(self._emit)
        return widget

    def add_row(self, row: Optional[dict] = None) -> None:
        """Append a row, filled from ``row`` or the column defaults."""
        row = row or {}
        index = self.table.rowCount()
        self.table.insertRow(index)
        for column_index, column in enumerate(self.columns):
            self.table.setCellWidget(
                index, column_index, self._make_cell(column, row.get(column.name, ""))
            )
        self._emit()

    def remove_row(self, index: int) -> None:
        """Delete row ``index`` if it exists."""
        if 0 <= index < self.table.rowCount():
            self.table.removeRow(index)
            self._emit()

    def _remove_selected(self) -> None:
        rows = sorted(
            {item.row() for item in self.table.selectedIndexes()}, reverse=True
        )
        if not rows and self.table.rowCount():
            rows = [self.table.rowCount() - 1]
        for index in rows:
            if index >= 0:
                self.table.removeRow(index)
        self._emit()

    def cell_widget(self, row: int, column: int):
        """The editor widget at ``row``/``column``."""
        return self.table.cellWidget(row, column)

    # ------------------------------------------------------------ value
    def value(self) -> list:
        rows = []
        for row_index in range(self.table.rowCount()):
            row = {}
            for column_index, column in enumerate(self.columns):
                widget = self.table.cellWidget(row_index, column_index)
                if isinstance(widget, QtWidgets.QComboBox):
                    row[column.name] = widget.currentText()
                else:
                    row[column.name] = widget.text()
            rows.append(row)
        return rows

    def setValue(self, rows) -> None:  # noqa: N802 - matches the Qt widgets here
        self.table.setRowCount(0)
        for row in rows or []:
            index = self.table.rowCount()
            self.table.insertRow(index)
            for column_index, column in enumerate(self.columns):
                self.table.setCellWidget(
                    index,
                    column_index,
                    self._make_cell(column, row.get(column.name, "")),
                )

    def _emit(self, *_args) -> None:
        self.valueChanged.emit(self.value())


class _NodeEditor(QtWidgets.QWidget):
    """Line edit plus a "pick" button fed by ``picker``."""

    valueChanged = QtCore.Signal(object)

    def __init__(self, picker: Optional[Callable[[], str]] = None, parent=None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.line = QtWidgets.QLineEdit()
        self.button = QtWidgets.QPushButton("<")
        self.button.setFixedWidth(24)
        self.button.setToolTip("Use the current selection")
        layout.addWidget(self.line)
        layout.addWidget(self.button)
        self.line.editingFinished.connect(lambda: self.valueChanged.emit(self.value()))
        self.button.clicked.connect(self._pick)
        self.picker = picker
        self.button.setEnabled(picker is not None)

    def _pick(self) -> None:
        if self.picker is None:
            return
        picked = self.picker() or ""
        self.line.setText(picked)
        self.valueChanged.emit(picked)

    def value(self) -> str:
        return self.line.text()

    def setValue(self, value) -> None:  # noqa: N802
        self.line.setText(str(value or ""))


class _FileEditor(QtWidgets.QWidget):
    """Line edit + browse button (+ optional extra action button)."""

    valueChanged = QtCore.Signal(object)

    def __init__(
        self, extensions=(), mode="open", parent=None, extra=None, browser=None
    ) -> None:
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.line = QtWidgets.QLineEdit()
        self.browse = QtWidgets.QPushButton("…")
        self.browse.setFixedWidth(28)
        self.browse.setToolTip("Browse")
        layout.addWidget(self.line, 1)
        layout.addWidget(self.browse)
        self.extra_button = None
        if extra is not None:
            label, callback = extra
            self.extra_button = QtWidgets.QPushButton(label)
            self.extra_button.setFixedWidth(28)
            self.extra_button.clicked.connect(lambda: callback(self.value()))
            layout.addWidget(self.extra_button)
        self.extensions = list(extensions)
        self.mode = mode
        self.browser = browser
        self.line.editingFinished.connect(lambda: self.valueChanged.emit(self.value()))
        self.browse.clicked.connect(self._browse)

    def _browse(self) -> None:
        # an injected browser wins over the module-wide one: being handed a
        # picker is more specific than the default every tool shares
        if self.browser is not None:
            picked = self.browser(self.mode, self.extensions, self.value())
        else:
            dialog = Feedback(self)
            start = self.value()
            if self.mode == "dir":
                picked = dialog.browse_dir("Choose folder", start)
            elif self.mode == "save":
                picked = dialog.browse_save("Save", start, self.extensions)
            else:
                picked = dialog.browse_open("Open", start, self.extensions)
        if picked:
            self.line.setText(picked)
            self.valueChanged.emit(picked)

    def value(self) -> str:
        return self.line.text()

    def setValue(self, value) -> None:  # noqa: N802
        self.line.setText(str(value or ""))


class FormBuilder(QtWidgets.QWidget):
    """Form generated from a ``Schema`` object.

    Signals:
        changed(name, value): emitted after a field is successfully updated.
        error(name, message): emitted when validation rejects a value.
    """

    changed = QtCore.Signal(str, object)
    error = QtCore.Signal(str, str)

    def __init__(
        self,
        target: Optional[Schema] = None,
        parent=None,
        node_picker: Optional[Callable[[], str]] = None,
        file_browser: Optional[Callable] = None,
        file_extras: Optional[dict] = None,
        base_dir: Optional[Callable[[], str]] = None,
    ) -> None:
        """
        Args:
            target: The Schema instance to edit.
            node_picker: Callable returning a node name for NodeRefField pickers.
            file_browser: Optional ``(mode, extensions, current) -> path``
                replacing the dialogs.
            file_extras: ``{extension: (label, callback(path))}``: an extra
                button on matching FileFields.
        """
        super().__init__(parent)
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(4)
        self._plain: Optional[QtWidgets.QFormLayout] = None
        self._groups: dict[str, CollapsibleGroup] = {}
        # Fold state per target class, so tuning a group survives clicking
        # between modules and resets when the tool restarts.
        self._collapsed: dict[str, bool] = {}
        self._widgets: dict[str, QtWidgets.QWidget] = {}
        self._labels: dict[str, QtWidgets.QLabel] = {}
        self._target: Optional[Schema] = None
        self.node_picker = node_picker
        self.file_browser = file_browser
        self.file_extras = file_extras or {}
        self.base_dir = base_dir
        self._overridden: set[str] = set()
        self._reference: dict = {}
        if target is not None:
            self.set_target(target)

    # ------------------------------------------------------------ building
    @property
    def target(self) -> Optional[Schema]:
        """The schema object the form edits, or None."""
        return self._target

    def clear(self) -> None:
        """Remove every field widget and forget the target."""
        self._clear_layout(self._layout)
        self._plain = None
        self._groups.clear()
        self._widgets.clear()
        self._labels.clear()

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
            elif item.layout() is not None:
                self._clear_layout(item.layout())

    def group_widget(self, label: str) -> CollapsibleGroup:
        """The fold for a group, by label."""
        return self._groups[label]

    def _fold_key(self, group) -> str:
        return f"{type(self._target).__name__}.{group.label}"

    def _new_form(self) -> QtWidgets.QFormLayout:
        form = QtWidgets.QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        return form

    def set_target(self, target: Optional[Schema]) -> None:
        """Rebuild the form for ``target``'s fields (None clears it)."""
        self.clear()
        self._target = target
        if target is None:
            return
        # Collected rather than emitted inline, so fields sharing a group but
        # declared apart land in one fold instead of two. Order is the order
        # each group is first seen.
        order: list = []
        rows: dict = {}
        for name, field in target.fields().items():
            if field.hidden:
                continue
            key = field.group.label if field.group else None
            if key not in rows:
                rows[key] = []
                order.append((key, field.group))
            rows[key].append((name, field))

        for key, group in order:
            if key is None:
                self._plain = self._new_form()
                self._layout.addLayout(self._plain)
                form = self._plain
            else:
                expanded = self._collapsed.get(
                    self._fold_key(group), not group.collapsed
                )
                fold = CollapsibleGroup(group.label, expanded=expanded)
                fold.toggled.connect(
                    lambda state, fold=group: self._collapsed.__setitem__(
                        self._fold_key(fold), state
                    )
                )
                holder = QtWidgets.QWidget()
                form = self._new_form()
                holder.setLayout(form)
                fold.content_layout.addWidget(holder)
                self._layout.addWidget(fold)
                self._groups[group.label] = fold
            for name, field in rows[key]:
                widget = self._make_widget(name, field)
                widget.setToolTip(field.help or "")
                self._widgets[name] = widget
                label = QtWidgets.QLabel(field.label or name)
                self._labels[name] = label
                form.addRow(label, widget)
        self._layout.addStretch(1)
        self.refresh()

    def mark_overrides(self, names, reference_values: Optional[dict] = None) -> None:
        """Highlight fields carrying an override.

        ``reference_values`` show in the tooltips.
        """
        self._overridden = set(names)
        self._reference = dict(reference_values or {})
        for name, label in self._labels.items():
            if name in self._overridden:
                label.setStyleSheet("color: #FE7E00; font-weight: bold;")
                label.setToolTip(
                    f"override (referenced value: {self._reference.get(name, '?')!r})"
                )
            else:
                label.setStyleSheet("")
                label.setToolTip("")

    def widget(self, name: str) -> QtWidgets.QWidget:
        """The editor widget for field ``name``."""
        return self._widgets[name]

    def _make_widget(self, name: str, field: Field) -> QtWidgets.QWidget:
        kind = field.type_name
        if kind == "int":
            widget = QtWidgets.QSpinBox()
            widget.setRange(
                int(field.min) if field.min is not None else -(2**31),
                int(field.max) if field.max is not None else 2**31 - 1,
            )
            widget.valueChanged.connect(
                lambda value, field_name=name: self._on_change(field_name, value)
            )
        elif kind == "float":
            widget = QtWidgets.QDoubleSpinBox()
            widget.setDecimals(3)
            widget.setRange(
                float(field.min) if field.min is not None else -1e9,
                float(field.max) if field.max is not None else 1e9,
            )
            widget.valueChanged.connect(
                lambda value, field_name=name: self._on_change(field_name, value)
            )
        elif kind == "bool":
            widget = QtWidgets.QCheckBox()
            widget.toggled.connect(
                lambda value, field_name=name: self._on_change(field_name, bool(value))
            )
        elif kind == "choice":
            widget = QtWidgets.QComboBox()
            for choice in field.choices or []:
                widget.addItem(str(choice), choice)
            widget.currentIndexChanged.connect(
                lambda index, field_name=name, combo=widget: self._on_change(
                    field_name, combo.itemData(index)
                )
            )
        elif kind == "vector":
            widget = _VectorEditor(
                getattr(field, "size", 3),
                minimum=field.min,
                maximum=field.max,
                labels=getattr(field, "labels", None),
            )
            widget.valueChanged.connect(
                lambda value, field_name=name: self._on_change(field_name, value)
            )
        elif kind == "list":
            widget = QtWidgets.QLineEdit()
            widget.setPlaceholderText("comma separated")
            widget.editingFinished.connect(
                lambda field_name=name, editor=widget: self._on_change(
                    field_name, self._parse_list(editor.text())
                )
            )
        elif kind == "node":
            widget = _NodeEditor(self.node_picker)
            widget.valueChanged.connect(
                lambda value, field_name=name: self._on_change(field_name, value)
            )
        elif kind == "file":
            extra = None
            for ext in getattr(field, "extensions", []):
                if ext in self.file_extras:
                    extra = self.file_extras[ext]
                    break
            from tik.shared.ui.versioned_field import VersionedFileField

            widget = VersionedFileField(
                getattr(field, "extensions", ()),
                getattr(field, "mode", "open"),
                extra=extra,
                browser=self.file_browser,
                base_dir=self.base_dir,
            )
            widget.changed.connect(
                lambda value, field_name=name: self._on_change(field_name, value)
            )
        elif kind == "table":
            widget = _TableEditor(
                getattr(field, "columns", ()),
                choices_resolver=self._resolve_choices,
            )
            widget.valueChanged.connect(
                lambda value, field_name=name: self._on_change(field_name, value)
            )
        elif kind == "dict":
            widget = QtWidgets.QLabel("(edited in place)")
        else:  # string and unknown types
            widget = QtWidgets.QLineEdit()
            widget.editingFinished.connect(
                lambda field_name=name, editor=widget: self._on_change(
                    field_name, editor.text()
                )
            )
        return widget

    def _resolve_choices(self, attr: str) -> tuple:
        """The options a column's ``choices_from`` names on the current target.

        The attribute may be a plain sequence or a callable taking the
        target's values -- a field is a class attribute and cannot know the
        subclass it will be edited on, so a column whose options depend on the
        target's *settings* has to compute them at render time.
        """
        if self._target is None:
            return ()
        found = getattr(self._target, attr, ())
        if callable(found):
            found = found(self._target.values())
        return tuple(found or ())

    @staticmethod
    def _parse_list(text: str) -> list:
        return [item.strip() for item in text.split(",") if item.strip()]

    # ------------------------------------------------------------- syncing
    def refresh(self) -> None:
        """Push the target's current values into the widgets."""
        if self._target is None:
            return
        for name, widget in self._widgets.items():
            value = getattr(self._target, name)
            widget.blockSignals(True)
            try:
                self._set_widget_value(widget, value)
            finally:
                widget.blockSignals(False)

    @staticmethod
    def _set_widget_value(widget, value) -> None:
        if isinstance(widget, QtWidgets.QCheckBox):
            widget.setChecked(bool(value))
        elif isinstance(widget, QtWidgets.QComboBox):
            index = widget.findData(value)
            widget.setCurrentIndex(max(index, 0))
        elif isinstance(widget, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
            widget.setValue(value)
        elif hasattr(widget, "setValue") and not isinstance(
            widget, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)
        ):
            widget.setValue(value)
        elif isinstance(widget, QtWidgets.QLabel):
            return
        elif isinstance(widget, QtWidgets.QLineEdit):
            widget.setText(
                ", ".join(map(str, value)) if isinstance(value, list) else str(value)
            )

    def _on_change(self, name: str, value: Any) -> None:
        if self._target is None:
            return
        try:
            setattr(self._target, name, value)
        except FieldValidationError as failure:
            self.error.emit(name, str(failure))
            self.refresh()
            return
        self.changed.emit(name, getattr(self._target, name))

    def values(self) -> dict:
        """The target's current values, or ``{}`` without a target."""
        return self._target.values() if self._target is not None else {}

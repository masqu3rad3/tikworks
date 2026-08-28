"""Generate Qt editors from ``tik.core.fields`` schemas.

``FormBuilder`` turns any ``Schema`` instance into a form: one widget per
field, grouped by ``field.group``, with validation errors surfaced inline.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from tik.core.fields import Field, FieldValidationError, Schema
from tik.shared.ui.Qt import QtCore, QtWidgets


class _VectorEditor(QtWidgets.QWidget):
    """Row of double spin boxes."""

    valueChanged = QtCore.Signal(object)

    def __init__(self, size: int, parent=None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.spins: list[QtWidgets.QDoubleSpinBox] = []
        for _index in range(size):
            spin = QtWidgets.QDoubleSpinBox()
            spin.setRange(-1e9, 1e9)
            spin.setDecimals(3)
            spin.valueChanged.connect(lambda _value: self.valueChanged.emit(self.value()))
            layout.addWidget(spin)
            self.spins.append(spin)

    def value(self) -> tuple:
        return tuple(spin.value() for spin in self.spins)

    def setValue(self, value) -> None:  # noqa: N802 - Qt style
        for spin, item in zip(self.spins, value):
            spin.blockSignals(True)
            spin.setValue(float(item))
            spin.blockSignals(False)


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

    def __init__(self, extensions=(), mode="open", parent=None, extra=None, browser=None) -> None:
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

    def _filter(self) -> str:
        if not self.extensions:
            return "All files (*)"
        patterns = " ".join(f"*{ext}" for ext in self.extensions)
        return f"Files ({patterns})"

    def _browse(self) -> None:
        if self.browser is not None:
            picked = self.browser(self.mode, self.extensions, self.value())
        elif self.mode == "dir":
            picked = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose folder", self.value())
        elif self.mode == "save":
            picked, _filter = QtWidgets.QFileDialog.getSaveFileName(self, "Save", self.value(), self._filter())
        else:
            picked, _filter = QtWidgets.QFileDialog.getOpenFileName(self, "Open", self.value(), self._filter())
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
    ) -> None:
        """
        Args:
            target: The Schema instance to edit.
            node_picker: Callable returning a node name for NodeRefField pickers.
            file_browser: Optional ``(mode, extensions, current) -> path`` replacing the dialogs.
            file_extras: ``{extension: (label, callback(path))}`` extra button on matching FileFields.
        """
        super().__init__(parent)
        self._layout = QtWidgets.QFormLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._widgets: dict[str, QtWidgets.QWidget] = {}
        self._labels: dict[str, QtWidgets.QLabel] = {}
        self._target: Optional[Schema] = None
        self.node_picker = node_picker
        self.file_browser = file_browser
        self.file_extras = file_extras or {}
        self._overridden: set[str] = set()
        self._reference: dict = {}
        if target is not None:
            self.set_target(target)

    # ------------------------------------------------------------ building
    @property
    def target(self) -> Optional[Schema]:
        return self._target

    def clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self._widgets.clear()
        self._labels.clear()

    def set_target(self, target: Optional[Schema]) -> None:
        self.clear()
        self._target = target
        if target is None:
            return
        current_group = None
        for name, field in target.fields().items():
            if field.hidden:
                continue
            if field.group != current_group and field.group:
                label = QtWidgets.QLabel(f"<b>{field.group}</b>")
                self._layout.addRow(label)
            current_group = field.group
            widget = self._make_widget(name, field)
            widget.setToolTip(field.help or "")
            self._widgets[name] = widget
            label = QtWidgets.QLabel(field.label or name)
            self._labels[name] = label
            self._layout.addRow(label, widget)
        self.refresh()

    def mark_overrides(self, names, reference_values: Optional[dict] = None) -> None:
        """Highlight fields carrying an override; ``reference_values`` show in tooltips."""
        self._overridden = set(names)
        self._reference = dict(reference_values or {})
        for name, label in self._labels.items():
            if name in self._overridden:
                label.setStyleSheet("color: #FE7E00; font-weight: bold;")
                label.setToolTip(f"override (referenced value: {self._reference.get(name, '?')!r})")
            else:
                label.setStyleSheet("")
                label.setToolTip("")

    def widget(self, name: str) -> QtWidgets.QWidget:
        return self._widgets[name]

    def _make_widget(self, name: str, field: Field) -> QtWidgets.QWidget:
        kind = field.type_name
        if kind == "int":
            widget = QtWidgets.QSpinBox()
            widget.setRange(
                int(field.min) if field.min is not None else -(2**31),
                int(field.max) if field.max is not None else 2**31 - 1,
            )
            widget.valueChanged.connect(lambda value, n=name: self._on_change(n, value))
        elif kind == "float":
            widget = QtWidgets.QDoubleSpinBox()
            widget.setDecimals(3)
            widget.setRange(
                float(field.min) if field.min is not None else -1e9,
                float(field.max) if field.max is not None else 1e9,
            )
            widget.valueChanged.connect(lambda value, n=name: self._on_change(n, value))
        elif kind == "bool":
            widget = QtWidgets.QCheckBox()
            widget.toggled.connect(lambda value, n=name: self._on_change(n, bool(value)))
        elif kind == "choice":
            widget = QtWidgets.QComboBox()
            for choice in field.choices or []:
                widget.addItem(str(choice), choice)
            widget.currentIndexChanged.connect(
                lambda index, n=name, w=widget: self._on_change(n, w.itemData(index))
            )
        elif kind == "vector":
            widget = _VectorEditor(getattr(field, "size", 3))
            widget.valueChanged.connect(lambda value, n=name: self._on_change(n, value))
        elif kind == "list":
            widget = QtWidgets.QLineEdit()
            widget.setPlaceholderText("comma separated")
            widget.editingFinished.connect(
                lambda n=name, w=widget: self._on_change(n, self._parse_list(w.text()))
            )
        elif kind == "node":
            widget = _NodeEditor(self.node_picker)
            widget.valueChanged.connect(lambda value, n=name: self._on_change(n, value))
        elif kind == "file":
            extra = None
            for ext in getattr(field, "extensions", []):
                if ext in self.file_extras:
                    extra = self.file_extras[ext]
                    break
            widget = _FileEditor(getattr(field, "extensions", ()), getattr(field, "mode", "open"),
                                 extra=extra, browser=self.file_browser)
            widget.valueChanged.connect(lambda value, n=name: self._on_change(n, value))
        elif kind == "dict":
            widget = QtWidgets.QLabel("(edited in place)")
        else:  # string and unknown types
            widget = QtWidgets.QLineEdit()
            widget.editingFinished.connect(lambda n=name, w=widget: self._on_change(n, w.text()))
        return widget

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
        elif isinstance(widget, (_VectorEditor, _NodeEditor, _FileEditor)):
            widget.setValue(value)
        elif isinstance(widget, QtWidgets.QLabel):
            return
        elif isinstance(widget, QtWidgets.QLineEdit):
            widget.setText(", ".join(map(str, value)) if isinstance(value, list) else str(value))

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
        return self._target.values() if self._target is not None else {}

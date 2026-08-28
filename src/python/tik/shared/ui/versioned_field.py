"""Nuke-style versioned file field.

Green = the path is the latest ``_v###`` version on disk, amber = an older
one exists-newer, neutral = unversioned, red = missing. Hover the field and
press Alt+Up / Alt+Down to step through existing versions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, Sequence

from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets
from tik.trigger.core import versioning

STATE_STYLES = {
    "latest": ("#3d6b4c", "#9fd8b3", "#1e2f24"),
    "older": ("#7a5416", "#f0b45c", "#3a2a10"),
    "missing": ("#6b3d3d", "#e08b88", "#2f1e1e"),
    "plain": ("#353535", "#c0c0c0", "transparent"),
    "empty": ("#353535", "#c0c0c0", "transparent"),
}


class _HoverKeyFilter(QtCore.QObject):
    """Application-level filter routing Alt+Up/Down to the hovered field."""

    fields: list["VersionedFileField"] = []
    _instance: Optional["_HoverKeyFilter"] = None

    @classmethod
    def ensure(cls) -> "_HoverKeyFilter":
        if cls._instance is None:
            cls._instance = cls()
            app = QtWidgets.QApplication.instance()
            if app is not None:
                app.installEventFilter(cls._instance)
        return cls._instance

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() == QtCore.QEvent.KeyPress and event.modifiers() & QtCore.Qt.AltModifier:
            if event.key() in (QtCore.Qt.Key_Up, QtCore.Qt.Key_Down):
                for field in list(self.fields):
                    try:
                        hovered = field.isVisible() and field.underMouse()
                    except RuntimeError:
                        continue
                    if hovered:
                        field.step(1 if event.key() == QtCore.Qt.Key_Up else -1)
                        return True
        return False


class VersionedFileField(QtWidgets.QWidget):
    changed = QtCore.Signal(object)

    def __init__(
        self,
        extensions: Sequence[str] = (),
        mode: str = "open",
        parent=None,
        browser: Optional[Callable] = None,
        extra: Optional[tuple] = None,
        base_dir: Optional[Callable[[], str]] = None,
    ) -> None:
        super().__init__(parent)
        self.extensions = list(extensions)
        self.mode = mode
        self.browser = browser
        self._base_dir = base_dir
        self.setObjectName("VersionedFileField")
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.line = QtWidgets.QLineEdit()
        self.line.setObjectName("VersionedFileLine")
        self.badge = QtWidgets.QLabel("")
        self.badge.setObjectName("VersionBadge")
        self.badge.setVisible(False)
        self.browse = QtWidgets.QToolButton()
        self.browse.setText("…")
        self.browse.setToolTip("Browse")
        layout.addWidget(self.line, 1)
        layout.addWidget(self.badge)
        layout.addWidget(self.browse)
        self.extra_button = None
        if extra is not None:
            label, callback = extra
            self.extra_button = QtWidgets.QToolButton()
            self.extra_button.setText(label)
            self.extra_button.clicked.connect(lambda: callback(self.value()))
            layout.addWidget(self.extra_button)
        self.line.editingFinished.connect(self._commit)
        self.browse.clicked.connect(self._browse)
        self.setToolTip("Alt+Up / Alt+Down while hovering: step versions")
        _HoverKeyFilter.ensure().fields.append(self)
        self.destroyed.connect(lambda: _HoverKeyFilter.fields.remove(self) if self in _HoverKeyFilter.fields else None)
        self._state = "empty"
        self.refresh_state()

    # ------------------------------------------------------------- value
    def value(self) -> str:
        return self.line.text()

    def setValue(self, value) -> None:  # noqa: N802
        self.line.setText(str(value or ""))
        self.refresh_state()

    def set_base_dir(self, base_dir: Optional[Callable[[], str]]) -> None:
        self._base_dir = base_dir
        self.refresh_state()

    def resolved(self) -> Optional[Path]:
        text = self.value().strip()
        if not text:
            return None
        path = Path(text)
        base = self._base_dir() if self._base_dir else ""
        if not path.is_absolute() and base:
            path = Path(base) / path
        return path

    def _commit(self) -> None:
        self.refresh_state()
        self.changed.emit(self.value())

    # ------------------------------------------------------------- state
    @property
    def state(self) -> str:
        return self._state

    def refresh_state(self) -> None:
        path = self.resolved()
        if path is None:
            state, badge = "empty", ""
        else:
            _stem, version, _suffix = versioning.parse(path)
            latest = versioning.latest_version(path) if version is not None else None
            if version is None:
                state, badge = ("plain" if path.exists() else "missing"), ""
            elif not path.exists():
                state, badge = "missing", f"v{version:03d} missing"
            elif latest is not None and versioning.parse(latest)[1] > version:
                state, badge = "older", f"v{version:03d} · latest v{versioning.parse(latest)[1]:03d}"
            else:
                state, badge = "latest", "latest"
        self._state = state
        border, text, fill = STATE_STYLES[state]
        self.line.setStyleSheet(f"QLineEdit {{ border: 1px solid {border}; }}")
        self.badge.setText(badge)
        self.badge.setVisible(bool(badge))
        self.badge.setStyleSheet(
            f"QLabel {{ color: {text}; background: {fill}; border: 1px solid {border}; border-radius: 8px; padding: 0 6px; font-size: 10px; }}"
        )

    # ------------------------------------------------------------ actions
    def step(self, delta: int) -> bool:
        """Move to the next/previous existing version; returns True when moved."""
        path = self.resolved()
        if path is None:
            return False
        versions = versioning.versions(path)
        if not versions:
            return False
        current = versioning.parse(path)[1]
        numbers = [versioning.parse(item)[1] for item in versions]
        if current in numbers:
            index = numbers.index(current) + delta
        else:
            index = len(numbers) - 1 if delta > 0 else 0
        if not 0 <= index < len(numbers):
            return False
        target = versions[index]
        text = self.value()
        # keep the user's relative form: swap only the file name
        new_text = str(Path(text).with_name(target.name)) if text else str(target)
        self.line.setText(new_text.replace("\\", "/"))
        self._commit()
        return True

    def _filter(self) -> str:
        if not self.extensions:
            return "All files (*)"
        return "Files (" + " ".join(f"*{ext}" for ext in self.extensions) + ")"

    def _browse(self) -> None:
        start = str(self.resolved() or "")
        if self.browser is not None:
            picked = self.browser(self.mode, self.extensions, start)
        elif self.mode == "dir":
            picked = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose folder", start)
        elif self.mode == "save":
            picked, _f = QtWidgets.QFileDialog.getSaveFileName(self, "Save", start, self._filter())
        else:
            picked, _f = QtWidgets.QFileDialog.getOpenFileName(self, "Open", start, self._filter())
        if picked:
            self.line.setText(str(picked).replace("\\", "/"))
            self._commit()

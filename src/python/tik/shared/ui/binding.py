"""Two-way binding between Maya attributes and Qt widgets.

Ported from creature_kit ``shared/binding.py``. Maya is touched only through
an *adapter* (``MayaAttributeAdapter`` by default) so the binders are testable
without a scene, and ``maya`` is imported lazily.

    manager = BindingManager()
    manager.add(bind("L_arm_collar_guide.ribbon_joints", spin_box))
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from tik.shared.ui.Qt import QtCore, QtWidgets

LOG = logging.getLogger(__name__)


class MayaAttributeAdapter:
    """Reads/writes/observes one Maya attribute via ``cmds`` (lazy import)."""

    def __init__(self, plug_path: str) -> None:
        self.plug_path = plug_path
        self._job: Optional[int] = None

    def exists(self) -> bool:
        """True while the plug is in the scene."""
        from maya import cmds

        return cmds.objExists(self.plug_path)

    def get(self) -> Any:
        """The plug's current value."""
        from maya import cmds

        return cmds.getAttr(self.plug_path)

    def set(self, value: Any) -> None:
        """Write ``value`` to the plug (strings need the typed setAttr)."""
        from maya import cmds

        if isinstance(value, str):
            cmds.setAttr(self.plug_path, value, type="string")
        else:
            cmds.setAttr(self.plug_path, value)

    def observe(self, callback: Callable[[], None]) -> None:
        """Call ``callback`` whenever the plug changes."""
        from maya import cmds

        self.unobserve()
        self._job = cmds.scriptJob(
            attributeChange=[self.plug_path, callback], protected=False
        )

    def unobserve(self) -> None:
        """Stop watching the plug."""
        if self._job is None:
            return
        from maya import cmds

        try:
            if cmds.scriptJob(exists=self._job):
                cmds.scriptJob(kill=self._job, force=True)
        except RuntimeError:
            pass
        self._job = None


class Binder:
    """Base binder: ``adapter`` <-> ``widget``. Subclasses map values."""

    def __init__(
        self, adapter, widget: QtWidgets.QWidget, direction: str = "both"
    ) -> None:
        if direction not in ("both", "to_widget", "to_maya"):
            raise ValueError("direction must be 'both', 'to_widget' or 'to_maya'")
        self.adapter = adapter
        self.widget = widget
        self.direction = direction
        self.active = False
        self._updating = False

    # ---- mapping (override) --------------------------------------------
    def widget_value(self) -> Any:
        """The widget's current value; subclasses map their widget type."""
        raise NotImplementedError

    def set_widget_value(self, value: Any) -> None:
        """Show ``value`` in the widget; subclasses map their widget type."""
        raise NotImplementedError

    def widget_signal(self):
        """The signal the widget emits when the user edits it."""
        raise NotImplementedError

    # ---- lifecycle ------------------------------------------------------
    @property
    def plug_path(self) -> str:
        """The bound plug's path, or ``""`` for adapters without one."""
        return getattr(self.adapter, "plug_path", "")

    def start(self) -> bool:
        """Wire the widget to the plug; False (widget disabled) when it is missing."""
        if not self.adapter.exists():
            self.widget.setEnabled(False)
            self.active = False
            return False
        self.widget.setEnabled(True)
        if self.direction in ("both", "to_maya"):
            self.widget_signal().connect(self._on_widget_changed)
        if self.direction in ("both", "to_widget"):
            self.adapter.observe(self.update_widget)
        self.update_widget()
        self.active = True
        return True

    def stop(self) -> None:
        """Disconnect the widget from the plug."""
        if self.direction in ("both", "to_maya"):
            try:
                self.widget_signal().disconnect(self._on_widget_changed)
            except (RuntimeError, TypeError):
                pass
        self.adapter.unobserve()
        self.active = False

    def update_widget(self) -> None:
        """Refresh the widget from the plug without echoing the change back."""
        if self._updating or not self.adapter.exists():
            return
        self._updating = True
        try:
            self.widget.blockSignals(True)
            self.set_widget_value(self.adapter.get())
        finally:
            self.widget.blockSignals(False)
            self._updating = False

    def _on_widget_changed(self, *_args) -> None:
        if self._updating:
            return
        self._updating = True
        try:
            self.adapter.set(self.widget_value())
        except Exception as error:  # noqa: BLE001 - keep the UI alive
            LOG.warning("binding %s: %s", self.plug_path, error)
        finally:
            self._updating = False


class IntSpinnerBinder(Binder):
    """Binds a ``QSpinBox``."""

    def widget_value(self):
        """The spin box value as an int."""
        return int(self.widget.value())

    def set_widget_value(self, value):
        """Set the spin box value."""
        self.widget.setValue(int(value))

    def widget_signal(self):
        """``valueChanged``."""
        return self.widget.valueChanged


class DoubleSpinnerBinder(IntSpinnerBinder):
    """Binds a ``QDoubleSpinBox``."""

    def widget_value(self):
        """The spin box value as a float."""
        return float(self.widget.value())

    def set_widget_value(self, value):
        """Set the spin box value."""
        self.widget.setValue(float(value))


class CheckBoxBinder(Binder):
    """Binds a ``QCheckBox``."""

    def widget_value(self):
        """Whether the box is checked."""
        return bool(self.widget.isChecked())

    def set_widget_value(self, value):
        """Check or uncheck the box."""
        self.widget.setChecked(bool(value))

    def widget_signal(self):
        """``toggled``."""
        return self.widget.toggled


class LineEditBinder(Binder):
    """Binds a ``QLineEdit``."""

    def widget_value(self):
        """The edit's text."""
        return self.widget.text()

    def set_widget_value(self, value):
        """Set the edit's text (None shows empty)."""
        self.widget.setText("" if value is None else str(value))

    def widget_signal(self):
        """``editingFinished``."""
        return self.widget.editingFinished


class ComboBinder(Binder):
    """Enum attribute (index) <-> combo box index."""

    def widget_value(self):
        """The selected index."""
        return int(self.widget.currentIndex())

    def set_widget_value(self, value):
        """Select the item at ``value``."""
        self.widget.setCurrentIndex(int(value))

    def widget_signal(self):
        """``currentIndexChanged``."""
        return self.widget.currentIndexChanged


class SliderBinder(Binder):
    """Binds a ``QSlider``; ``scale`` maps the plug's floats onto the slider's ints."""

    def __init__(self, adapter, widget, direction="both", scale: float = 1.0) -> None:
        super().__init__(adapter, widget, direction)
        self.scale = scale

    def widget_value(self):
        """The slider position divided by ``scale``."""
        return self.widget.value() / self.scale

    def set_widget_value(self, value):
        """Move the slider to ``value * scale``."""
        self.widget.setValue(int(float(value) * self.scale))

    def widget_signal(self):
        """``valueChanged``."""
        return self.widget.valueChanged


_BINDERS = [
    (QtWidgets.QDoubleSpinBox, DoubleSpinnerBinder),
    (QtWidgets.QSpinBox, IntSpinnerBinder),
    (QtWidgets.QCheckBox, CheckBoxBinder),
    (QtWidgets.QComboBox, ComboBinder),
    (QtWidgets.QSlider, SliderBinder),
    (QtWidgets.QLineEdit, LineEditBinder),
]


def bind(
    plug_path: str, widget: QtWidgets.QWidget, direction: str = "both", adapter=None
) -> Binder:
    """Create the right binder for ``widget`` (not started yet)."""
    adapter = adapter or MayaAttributeAdapter(plug_path)
    for widget_type, binder_cls in _BINDERS:
        if isinstance(widget, widget_type):
            return binder_cls(adapter, widget, direction)
    raise TypeError(f"No binder for widget type {type(widget).__name__}")


class BindingManager:
    """Owns binders; retries inactive ones periodically (nodes may appear later)."""

    DEFAULT_POLL_MS = 1000

    def __init__(self, poll_interval_ms: int = DEFAULT_POLL_MS) -> None:
        self.binders: list[Binder] = []
        self._timer: Optional[QtCore.QTimer] = None
        self.poll_interval_ms = poll_interval_ms

    def add(self, binder: Binder) -> Binder:
        """Start ``binder`` and keep it; polls for the plug when it is not there yet."""
        self.binders.append(binder)
        if not binder.start():
            self._ensure_polling()
        return binder

    def remove(self, binder: Binder) -> None:
        """Stop and forget ``binder``."""
        binder.stop()
        if binder in self.binders:
            self.binders.remove(binder)

    def clear(self) -> None:
        """Stop and forget every binder."""
        for binder in self.binders:
            binder.stop()
        self.binders.clear()
        self._stop_polling()

    def update_all(self) -> None:
        """Refresh every active widget from its plug."""
        for binder in self.binders:
            if binder.active:
                binder.update_widget()

    def reconnect(self) -> int:
        """Try to start inactive binders; returns how many are still inactive."""
        pending = 0
        for binder in self.binders:
            if not binder.active and not binder.start():
                pending += 1
        if not pending:
            self._stop_polling()
        return pending

    def _ensure_polling(self) -> None:
        if self._timer is None:
            self._timer = QtCore.QTimer()
            self._timer.setInterval(self.poll_interval_ms)
            self._timer.timeout.connect(self.reconnect)
        if not self._timer.isActive():
            self._timer.start()

    def _stop_polling(self) -> None:
        if self._timer is not None and self._timer.isActive():
            self._timer.stop()

    def __len__(self) -> int:
        return len(self.binders)

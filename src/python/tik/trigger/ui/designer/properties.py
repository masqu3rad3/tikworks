"""The Guide Designer's properties panel: inputs, settings and their bindings.

A mixin on the window, for the same reason as the commands: these read and
write the current selection through ``self.guides``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from tik.shared.ui.binding import MayaAttributeAdapter, bind
from tik.shared.ui.Qt import QtWidgets
from tik.trigger.core import registry
from tik.trigger.core.exceptions import TriggerError
from tik.trigger.core.schemas import split_source

from .widgets import SCENE_NODE

if TYPE_CHECKING:
    from tik.trigger.guides import GuideHandle


class DesignerProperties:
    """Mixed into :class:`~.window.GuideDesigner`."""

    def _plug_adapter(self, handle: GuideHandle, name: str):
        """Read/write adapter for a guide attribute (the same one the two-way bindings use)."""
        plug_factory = getattr(self.guides, "settings_plug", None)
        if plug_factory is None:
            return None
        try:
            plug = plug_factory(handle.instance_id, name)
        except TriggerError:
            return None
        plug_path = plug if isinstance(plug, str) else plug.path
        return self.binding_adapter(plug_path) if self.binding_adapter else MayaAttributeAdapter(plug_path)

    def _on_inherit_toggled(self, checked: bool) -> None:
        """Single selection is handled by the two-way binding; several modules are written here."""
        if len(self._multi) < 2:
            return
        with self.watcher.mute():
            for handle in self._multi:
                adapter = self._plug_adapter(handle, "useRefOri")
                if adapter is not None:
                    adapter.set(bool(checked))

    def _bind_properties(self, handle: GuideHandle) -> None:
        plug_factory = getattr(self.guides, "settings_plug", None)
        if plug_factory is None:
            return
        for name in self._module_obj.fields():
            widget = self.form._widgets.get(name)
            if widget is None or not isinstance(widget, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox, QtWidgets.QCheckBox, QtWidgets.QComboBox, QtWidgets.QLineEdit)):
                continue
            try:
                plug = plug_factory(handle.instance_id, name)
            except TriggerError:
                continue
            plug_path = plug if isinstance(plug, str) else plug.path
            adapter = self.binding_adapter(plug_path) if self.binding_adapter else None
            self.bindings.add(bind(plug_path, widget, direction="to_widget", adapter=adapter))
        try:
            plug = plug_factory(handle.instance_id, "useRefOri")
            plug_path = plug if isinstance(plug, str) else plug.path
            adapter = self.binding_adapter(plug_path) if self.binding_adapter else None
            self.bindings.add(bind(plug_path, self.inherit_orientation, direction="both", adapter=adapter))
        except TriggerError:
            pass

    def _source_choices(self):
        """Every other module (with its outputs) and the scene nodes of every group."""
        current = self._current.instance_id if self._current else None
        modules = [
            (handle.key, handle.module_class.display_label(), list(handle.outputs))
            for handle in self.guides.instances()
            if handle.instance_id != current and handle.outputs
        ]
        return modules, self.graph.scene_nodes()

    def _selected_scene_nodes(self) -> list[str]:
        picker = getattr(self.guides, "selected_node_names", None)
        if picker is not None:
            return list(picker() or [])
        name = getattr(self.guides, "selected_node_name", lambda: "")()
        return [name] if name else []

    def _pick_source(self) -> str:
        picked = self.guides.selected_guide() if hasattr(self.guides, "selected_guide") else None
        if picked is not None:
            handle = self.guides.get(picked.instance_id)
            if handle is not None:
                output = handle.module_class.output_at_role(picked.role)
                return f"{handle.key}.{output}" if output else ""
        name = getattr(self.guides, "selected_node_name", lambda: "")()
        return name or ""

    def _on_input_changed(self, input_name: str, source: str) -> None:
        if self._current is None:
            return
        try:
            if source:
                self.guides.connect(f"{self._current.key}.{input_name}", source)
            else:
                self.guides.disconnect(f"{self._current.key}.{input_name}")
        except TriggerError as error:
            self.events.log(str(error), level="warning")
            self._input_rows[input_name].set_source(self._current.inputs.get(input_name, ""))
            return
        self.refresh()

    @staticmethod
    def _topology(handle) -> tuple:
        """What a settings change might alter: ports and guide count."""
        module_cls = handle.module_class
        settings = handle.settings
        return (
            tuple(module_cls.input_names(settings)),
            tuple(module_cls.output_names(settings)),
            len(handle.instance.guides),
        )

    def _on_setting_changed(self, name: str, _value) -> None:
        if self._current is None or self._module_obj is None:
            return
        value = getattr(self._module_obj, name)
        targets = self._multi or [self._current]
        before = [self._topology(handle) for handle in targets]
        with self.watcher.mute():
            for handle in targets:
                setattr(handle, name, value)
        # Refresh when the change moved a port or a guide, rather than keeping a
        # hand-maintained list of which fields do that.
        if any(
            self._topology(handle) != snapshot
            for handle, snapshot in zip(targets, before)
        ):
            self.refresh()

    def _on_scene_nodes_changed(self, nodes: list) -> None:
        if self._external is None:
            return
        try:
            self.guides.set_scene_group(self._external, list(nodes))
        except TriggerError as error:
            self.events.log(str(error), level="warning")
            return
        self.graph.rebuild()  # keep the rows the user is typing in; only the graph/tree change
        self.graph.select_key(self._external)
        connections = self.guides.connections()
        self.status.set("connections", f"{len(connections)} connection(s)")

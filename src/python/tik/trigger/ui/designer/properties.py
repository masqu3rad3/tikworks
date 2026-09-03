"""The Guide Designer's properties panel: inputs, settings and their bindings.

A mixin on the window, for the same reason as the commands: these read and
write the current selection through ``self.guides``.
"""

from __future__ import annotations

from tik.trigger.core.exceptions import TriggerError


class DesignerProperties:
    """Mixed into :class:`~.window.GuideDesigner`."""

    # Settings have no Maya attribute to bind to: the session owns them, and the
    # form writes them through ``write_settings``. Per-guide data (``guide_attrs``)
    # still lives on the joints and is captured from there.

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

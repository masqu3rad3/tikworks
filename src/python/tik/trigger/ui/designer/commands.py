"""The Guide Designer's verbs: create, connect, mirror, delete, import, export.

A mixin on the window rather than a free-standing object: every one of these
reads the current selection and writes back through ``self.guides``, so
splitting them off as functions would only move the coupling into arguments.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from tik.core.side import Side
from tik.shared.ui.feedback import Feedback
from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets
from tik.trigger.core import registry
from tik.trigger.core.exceptions import TriggerError
from tik.trigger.guides import EXTENSION as GUIDE_EXTENSION

from .widgets import SCENE_NODE

if TYPE_CHECKING:
    from tik.trigger.guides import GuideHandle


class DesignerCommands:
    """Mixed into :class:`~.window.GuideDesigner`."""

    def _rename_current(self) -> None:
        new_name = self.name_edit.text().strip()
        if self._current is None and self._external is not None:
            if new_name and new_name != self._external:
                old = self._external
                try:
                    self.guides.rename_scene_group(old, new_name)
                except TriggerError as error:
                    self.events.log(str(error), level="warning")
                    self.name_edit.setText(old)
                    return
                self._external = new_name
                self.refresh()
            return
        if self._current is None or self._multi:
            return
        if new_name and new_name != self._current.name:
            try:
                self._current.name = new_name
            except TriggerError as error:
                self.events.log(str(error), level="warning")
                self.name_edit.setText(self._current.name)
                return
            self.refresh()

    def show_palette(self) -> None:
        """Open the module palette under the cursor."""
        self.palette.popup(QtGui.QCursor.pos())

    def create_guides(self, module_type: str) -> list[GuideHandle]:
        """Add a module (or a scene-nodes group) for the current side and select it."""
        if module_type == SCENE_NODE:
            name = self.graph.add_scene_group(nodes=self._selected_scene_nodes())
            self._on_external_selection(name)
            self.name_edit.setFocus()
            self.name_edit.selectAll()
            return []
        module_cls = registry.get_module(module_type)
        parent_handle = (
            self._current
        )  # tree/graph selection only; nothing selected = no connection
        inputs = {}
        primary = module_cls.primary_input()
        if parent_handle is not None and primary is not None and parent_handle.outputs:
            inputs = {primary.name: f"{parent_handle.key}.{parent_handle.outputs[0]}"}
        choice = self.side
        if not module_cls.sided:
            sides = [Side.CENTER]
        elif choice == "Both":
            sides = [Side.LEFT, Side.RIGHT]
        elif choice == "Auto":
            sides = [
                (
                    parent_handle.side
                    if parent_handle is not None
                    and parent_handle.side is not Side.CENTER
                    else Side.LEFT
                )
            ]
        else:
            sides = [Side.from_value(choice)]
        created = []
        try:
            with self.watcher.mute():
                for side in sides:
                    created.append(
                        self.guides.add(module_type, side=side.value, inputs=inputs)
                    )
        except TriggerError as error:
            self.events.log(str(error), level="warning")
        self.refresh()
        if created:
            item = self.item_for(created[-1].instance_id)
            if item is not None:
                self.tree.setCurrentItem(item)
        return created

    def reparent(self, instance_id: str, parent_id: Optional[str]) -> None:
        """Point ``instance_id``'s primary input at ``parent_id`` (None detaches)."""
        handle = self.guides.get(instance_id)
        if handle is None:
            return
        parent = self.guides.get(parent_id) if parent_id else None
        primary = handle.module_class.primary_input()
        if primary is None:
            return
        try:
            with self.watcher.mute():
                if parent is not None:
                    self.guides.connect(
                        f"{handle.key}.{primary.name}",
                        f"{parent.key}.{parent.outputs[0]}",
                    )
                else:
                    self.guides.disconnect(f"{handle.key}.{primary.name}")
        except TriggerError as error:
            self.events.log(str(error), level="warning")
        self.refresh()

    def connect_dialog(self) -> None:
        """Ask for a source and connect the current module's first input to it."""
        if self._current is None or not self._current.input_names():
            return
        text = Feedback(self).ask_text(
            "Connect input",
            f"{self._current.key}.<input> = <source>",
            f"{self._current.input_names()[0]} = ",
        )
        if text and "=" in text:
            input_name, _eq, source = text.partition("=")
            self._on_input_changed(input_name.strip(), source.strip())

    def sever_current(self) -> None:
        """Drop every connection of the selected modules."""
        for handle in self.selected_handles() or (
            [self._current] if self._current else []
        ):
            self.graph.sever(handle.key)

    def disconnect_primary(self) -> None:
        """Clear the current module's primary input."""
        if self._current is None:
            return
        primary = self._current.module_class.primary_input()
        if primary is not None:
            self._on_input_changed(primary.name, "")

    def select_root(self) -> None:
        """Select the root guide joint(s) of the selected module(s) in the viewport."""
        select = getattr(self.guides, "select_nodes", None)
        with self.watcher.mute():
            roots = [
                handle.root
                for handle in self.selected_handles()
                if handle.root is not None
            ]
            if select is not None:
                select(roots)
            else:
                for root in roots:
                    getattr(root, "select", lambda: None)()

    def select_current(self) -> None:
        """Select the guide joints of the selected modules in Maya."""
        with self.watcher.mute():
            for handle in self.selected_handles():
                handle.select()

    def mirror_current(self) -> None:
        """Mirror each selected module to the other side."""
        with self.watcher.mute():
            for handle in self.selected_handles():
                try:
                    self.guides.mirror(handle)
                except TriggerError as error:
                    self.events.log(str(error), level="warning")
        self.refresh()

    def duplicate_current(self) -> list[GuideHandle]:
        """Copy each selected module; returns the copies."""
        created = []
        with self.watcher.mute():
            for handle in self.selected_handles():
                try:
                    created.append(self.guides.duplicate(handle))
                except TriggerError as error:
                    self.events.log(str(error), level="warning")
        if created:
            self._current, self._multi = created[0], created if len(created) > 1 else []
        self.refresh()
        return created

    def delete_current(self) -> None:
        """Delete the selection: graph wires first, else the module or group."""
        if self.graph.hasFocus() and self.graph.delete_selected():
            return  # Delete in the graph disconnects wires / removes scene-node groups
        if self._current is None and self._external is not None:
            self.graph.remove_scene_group(self._external)
            self._external = None
            self.refresh()
            return
        with self.watcher.mute():
            for handle in self.selected_handles():
                self.guides.remove(handle)
        self._current = None
        self._multi = []
        self.refresh()

    def clear_guides(self) -> None:
        """Remove every module, group and layout entry."""
        with self.watcher.mute():
            self.guides.clear()
            self.guides.set_layout({})
        self._current = None
        self._multi = []
        self._external = None
        self.refresh()

    def test_build(self, all_modules: bool = False):
        """Build the selected modules (or all) into a throwaway rig and report."""
        handles = [] if all_modules else self.selected_handles()
        try:
            with self.watcher.mute():
                report = self.guides.test_build(*handles)
            self.status.set_activity(
                f"Test build: {report.count} module(s), "
                f"{len(report.connections)} connection(s)"
            )
            return report
        except TriggerError as error:
            self.events.log(str(error), level="error")
            self.status.set_activity(str(error))
            return None
        finally:
            self.refresh()

    def sync_now(self) -> None:
        """Pull the scene into the session, whatever the Auto setting says."""
        diff = None
        with self.watcher.mute():
            try:
                diff = self.guides.sync()
            except Exception as error:  # noqa: BLE001 - keep the tool alive
                self.events.log(f"Guide sync failed: {error}", level="warning")
        self.refresh()
        # sync() itself rescans after regenerate when it actually redrew
        # anything, so its return value already reflects the post-fix scene
        # -- a second diff() here would just repeat a walk sync() already
        # did (or, worse, did twice) for the same answer
        self._show_drift(diff if diff is not None else self.guides.diff())

    def snapshot_guides(self) -> None:
        """Rebuild this session's modules from the guides in the scene.

        Reads and reports first: replacing the module list is destructive, so it
        never happens as a side effect of opening the dialog.
        """
        from .snapshot_dialog import SnapshotDialog

        document, report = self.guides.snapshot_from_scene()
        dialog = SnapshotDialog(report, self)
        if dialog.exec() != QtWidgets.QDialog.Accepted:
            return
        session = self.guides.session
        if session is None:
            self.events.log("Snapshot needs a session.", level="warning")
            return
        session.snapshot_guides_from_scene(document)
        self.refresh()
        self._show_drift(self.guides.diff())
        self.events.log(f"Snapshot restored {len(report.modules)} module(s).")

    def set_auto_sync(self, on: bool) -> None:
        """One setting, three front doors: the checkbox, the menu, and here.

        A genuine toggle syncs immediately -- turning Auto on should not
        leave the document behind the scene until the next event happens to
        fire. Construction restores the same flag through ``_apply_auto_sync``
        alone, deliberately without this sync (see its docstring).
        """
        self._apply_auto_sync(on)
        if on:
            self.sync_now()

    def _apply_auto_sync(self, on: bool) -> None:
        """Set the flag and its two mirrors (bar, menu), without syncing.

        Split out of ``set_auto_sync`` so construction can restore the stored
        preference without running a full ``sync()`` -- a sync captures,
        possibly regenerates and calls ``session.touch()``, which used to
        flip a freshly opened, untouched session to "modified" before the
        rigger had done anything, and prompted "discard changes?" on close.
        """
        self.guides.auto_sync = bool(on)
        self.action_bar.set_auto_sync(on)
        self.auto_sync_changed.emit(bool(on))
        QtCore.QSettings("tikworks", "trigger").setValue("designer/auto_sync", bool(on))

    def export_file(
        self, path: Optional[str] = None, ask: bool = False, selected: bool = False
    ) -> Optional[Path]:
        """Write the modules (all, or ``selected``) to a ``.trg`` file."""
        path = path or ("" if ask else self.last_guide_file) or self._pick("save")
        if not path:
            return None
        handles = self.selected_handles() if selected else []
        written = self.guides.export(path, *handles)
        self.set_file(str(written))
        self.events.log(f"GuideLayout exported: {written}")
        return written

    def import_file(
        self, path: Optional[str] = None, reset: bool = False
    ) -> list[GuideHandle]:
        """Add the modules of a ``.trg`` file; ``reset`` clears the scene first."""
        path = path or self._pick("open")
        if not path:
            return []
        with self.watcher.mute():
            handles = self.guides.import_(path, reset=reset)
        self.set_file(path)
        self.refresh()
        return handles

    def _pick(self, mode: str) -> str:
        if self.file_browser is not None:
            return (
                self.file_browser(mode, [GUIDE_EXTENSION], self.last_guide_file) or ""
            )
        dialog = Feedback(self)
        guide_filter = f"GuideLayout (*{GUIDE_EXTENSION})"
        if mode == "save":
            return dialog.browse_save(
                "Export guides",
                self.last_guide_file,
                (GUIDE_EXTENSION,),
                guide_filter,
            )
        return dialog.browse_open(
            "Import guides",
            self.last_guide_file,
            (GUIDE_EXTENSION,),
            guide_filter,
        )

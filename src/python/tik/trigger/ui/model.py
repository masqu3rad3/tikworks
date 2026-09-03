"""Qt item model over a ``Session``: nested actions, linked (referenced) rows, DnD."""

from __future__ import annotations

from typing import Optional

from tik.shared.ui.Qt import QtCore
from tik.trigger.core import registry
from tik.trigger.core.document import BUILD
from tik.trigger.core.exceptions import SessionError
from tik.trigger.session import ActionHandle, Session

MIME_PATH = "application/x-trigger-action-path"
MIME_TYPE = "application/x-trigger-action-type"

PathRole = QtCore.Qt.UserRole + 1
TypeRole = QtCore.Qt.UserRole + 2
SummaryRole = QtCore.Qt.UserRole + 3
StatusRole = QtCore.Qt.UserRole + 4
LinkedRole = QtCore.Qt.UserRole + 5
EnabledRole = QtCore.Qt.UserRole + 6
CategoryRole = QtCore.Qt.UserRole + 7
LabelRole = QtCore.Qt.UserRole + 8
ErrorRole = QtCore.Qt.UserRole + 9


class _Item:
    __slots__ = ("handle", "parent", "children", "row")

    def __init__(
        self, handle: Optional[ActionHandle], parent: Optional["_Item"]
    ) -> None:
        self.handle = handle
        self.parent = parent
        self.children: list["_Item"] = []
        self.row = 0


class PipelineModel(QtCore.QAbstractItemModel):
    """Tree of ``ActionHandle`` snapshots for one phase; rebuilt on every edit."""

    edited = QtCore.Signal()
    #: emitted when a drop pulled an action out of the *other* phase, so the
    #: view knows the other model is now stale
    cross_phase_moved = QtCore.Signal()

    def __init__(self, session: Session, parent=None, phase: str = BUILD) -> None:
        super().__init__(parent)
        self.session = session
        self.phase = phase
        self._root = _Item(None, None)
        self._status: dict[str, str] = {}
        self._errors: dict[str, str] = {}
        self.rebuild()

    @property
    def view(self):
        """The session's tree API for this model's phase."""
        return self.session.view(self.phase)

    # ------------------------------------------------------------ building
    def rebuild(self) -> None:
        self.beginResetModel()
        self._root = _Item(None, None)
        self._populate(self._root, self.view.actions)
        self.endResetModel()

    def _populate(self, item: _Item, handles: list[ActionHandle]) -> None:
        for row, handle in enumerate(handles):
            child = _Item(handle, item)
            child.row = row
            item.children.append(child)
            self._populate(child, handle.children)

    def _item(self, index: QtCore.QModelIndex) -> _Item:
        return index.internalPointer() if index.isValid() else self._root

    def handle(self, index: QtCore.QModelIndex) -> Optional[ActionHandle]:
        item = self._item(index)
        return item.handle

    def index_for_path(
        self, path: str, item: Optional[_Item] = None
    ) -> QtCore.QModelIndex:
        item = item or self._root
        for child in item.children:
            if child.handle.path == path:
                return self.createIndex(child.row, 0, child)
            found = self.index_for_path(path, child)
            if found.isValid():
                return found
        return QtCore.QModelIndex()

    # ------------------------------------------------------------- status
    def set_status(self, path: str, status: str, error: str = "") -> None:
        self._status[path] = status
        if error:
            self._errors[path] = error
        else:
            self._errors.pop(path, None)
        index = self.index_for_path(path)
        if index.isValid():
            self.dataChanged.emit(index, index)

    def clear_status(self) -> None:
        self._status.clear()
        self._errors.clear()
        if self._root.children:
            self.dataChanged.emit(self.index(0, 0), self.index(self.rowCount() - 1, 0))

    def status(self, path: str) -> str:
        return self._status.get(path, "")

    # ------------------------------------------------------- model basics
    def rowCount(self, parent=QtCore.QModelIndex()) -> int:  # noqa: N802
        return len(self._item(parent).children)

    def columnCount(self, parent=QtCore.QModelIndex()) -> int:  # noqa: N802
        return 1

    def index(
        self, row: int, column: int, parent=QtCore.QModelIndex()
    ) -> QtCore.QModelIndex:
        item = self._item(parent)
        if 0 <= row < len(item.children):
            return self.createIndex(row, column, item.children[row])
        return QtCore.QModelIndex()

    def parent(self, index: QtCore.QModelIndex) -> QtCore.QModelIndex:  # type: ignore[override]
        item = self._item(index)
        if item is self._root or item.parent is None or item.parent is self._root:
            return QtCore.QModelIndex()
        return self.createIndex(item.parent.row, 0, item.parent)

    def flags(self, index: QtCore.QModelIndex):
        base = (
            QtCore.Qt.ItemIsEnabled
            | QtCore.Qt.ItemIsSelectable
            | QtCore.Qt.ItemIsDropEnabled
        )
        if not index.isValid():
            return base
        handle = self.handle(index)
        if handle.is_linked:
            return base | QtCore.Qt.ItemIsUserCheckable
        return base | QtCore.Qt.ItemIsDragEnabled | QtCore.Qt.ItemIsEditable

    def data(self, index: QtCore.QModelIndex, role=QtCore.Qt.DisplayRole):
        handle = self.handle(index)
        if handle is None:
            return None
        if role in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole):
            return handle.name
        if role == PathRole:
            return handle.path
        if role == TypeRole:
            return handle.type
        if role == LinkedRole:
            return handle.is_linked
        if role == EnabledRole:
            return handle.enabled
        if role == StatusRole:
            return self._status.get(handle.path, "")
        if role == ErrorRole:
            return self._errors.get(handle.path, "")
        if role in (SummaryRole, CategoryRole, LabelRole):
            try:
                action_cls = registry.get_action(handle.type)
            except SessionError:
                return "" if role != CategoryRole else "utility"
            if role == CategoryRole:
                return getattr(action_cls, "category", "utility")
            if role == LabelRole:
                return action_cls.display_label()
            try:
                return action_cls(settings=handle.settings).summary()
            except Exception:  # noqa: BLE001 - never break painting
                return ""
        if role == QtCore.Qt.CheckStateRole and handle.is_linked:
            return QtCore.Qt.Checked if handle.enabled else QtCore.Qt.Unchecked
        if role == QtCore.Qt.ToolTipRole:
            error = self._errors.get(handle.path)
            if error:
                return error
            return f"{handle.path} ({handle.type})"
        return None

    def setData(
        self, index: QtCore.QModelIndex, value, role=QtCore.Qt.EditRole
    ) -> bool:  # noqa: N802
        handle = self.handle(index)
        if handle is None:
            return False
        if role == QtCore.Qt.CheckStateRole:
            handle.enabled = (
                value == QtCore.Qt.Checked or value == QtCore.Qt.Checked.value
            )
            self.dataChanged.emit(index, index)
            self.edited.emit()
            return True
        if role == QtCore.Qt.EditRole:
            new_name = str(value).strip()
            if not new_name or new_name == handle.name:
                return False
            try:
                self.view.rename(handle.path, new_name)
            except SessionError:
                return False
            self.rebuild()
            self.edited.emit()
            return True
        return False

    # ------------------------------------------------------------ editing
    def toggle(self, index: QtCore.QModelIndex) -> None:
        handle = self.handle(index)
        if handle is not None:
            handle.enabled = not handle.enabled
            self.dataChanged.emit(index, index)
            self.edited.emit()

    # ---------------------------------------------------------------- dnd
    def supportedDropActions(self):  # noqa: N802
        return QtCore.Qt.MoveAction | QtCore.Qt.CopyAction

    def mimeTypes(self):  # noqa: N802
        return [MIME_PATH, MIME_TYPE]

    def mimeData(self, indexes):  # noqa: N802
        data = QtCore.QMimeData()
        # the phase travels with the path so a drop into the other tree knows
        # where the action is coming from
        tokens = [
            f"{self.phase}:{self.handle(index).path}"
            for index in indexes
            if index.isValid()
        ]
        data.setData(MIME_PATH, ";".join(tokens).encode("utf-8"))
        return data

    def canDropMimeData(self, data, action, row, column, parent):  # noqa: N802
        target = self.handle(parent) if parent.isValid() else None
        if target is not None and target.is_linked:
            return False
        if data.hasFormat(MIME_TYPE):
            action_type = bytes(data.data(MIME_TYPE)).decode("utf-8")
            return registry.allows(action_type, self.phase)
        return data.hasFormat(MIME_PATH)

    def dropMimeData(self, data, action, row, column, parent) -> bool:  # noqa: N802
        target = self.handle(parent) if parent.isValid() else None
        parent_path = target.path if target is not None else None
        index = None if row < 0 else row
        crossed = False
        try:
            if data.hasFormat(MIME_PATH):
                for token in bytes(data.data(MIME_PATH)).decode("utf-8").split(";"):
                    if not token:
                        continue
                    source_phase, _, path = token.partition(":")
                    if source_phase == self.phase:
                        self.view.move(path, parent=parent_path, index=index)
                    elif self._move_across(source_phase, path, parent_path, index):
                        crossed = True
                    else:
                        return False
                    if index is not None:
                        index += 1
            elif data.hasFormat(MIME_TYPE):
                action_type = bytes(data.data(MIME_TYPE)).decode("utf-8")
                self.view.add(action_type, parent=parent_path, index=index)
            else:
                return False
        except SessionError:
            return False
        self.rebuild()
        self.edited.emit()
        if crossed:
            self.cross_phase_moved.emit()
        return True

    def _move_across(
        self,
        source_phase: str,
        path: str,
        parent_path: Optional[str],
        index: Optional[int],
    ) -> bool:
        """Move one action from another phase into this one.

        There is no cross-phase ``move``: the document removes it from one list
        and adds it to the other. Scope is checked *before* the remove, so a
        refused drop leaves both lists exactly as they were.
        """
        document = self.session.document
        node = document.find(path, phase=source_phase)
        if node is None or not registry.allows(node.type, self.phase):
            return False
        document.remove(path, phase=source_phase)
        document.add(node, parent=parent_path, index=index, phase=self.phase)
        self.session.touch()
        return True

"""Controller shapes Model-View-Controller UI for Maya."""

import sys

from PySide6 import QtCore, QtGui, QtWidgets

# Cleanup previous instances in sys.modules to ensure reload works during dev
kill_list = []
for name, _module in sys.modules.items():
    if name.startswith("tik.maya"):
        kill_list.append(name)
for x in kill_list:
    sys.modules.pop(x)

tikmaya_path = "D:/dev/tikworks/src"
if tikmaya_path not in sys.path:
    sys.path.append(tikmaya_path)

from tik.maya.utils import control_shapes  # noqa: E402

cs_handler = control_shapes.ControlShapeLibrary()
MOCK_DATA = cs_handler.get_shape_data()


# ==============================================================================
# 2. THE MODELS
# ==============================================================================


class ShapeLibraryModel(QtGui.QStandardItemModel):
    """
    Standard Item Model organized as a Tree: Root -> Category -> Shape
    """

    RolePath = QtCore.Qt.UserRole + 1
    RoleCategory = QtCore.Qt.UserRole + 2
    RoleThumbnail = QtCore.Qt.UserRole + 3

    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.setHorizontalHeaderLabels(["Shapes"])
        self._load_data(data)

    def _load_data(self, data):
        self.setRowCount(0)
        categories = {}

        # Sort data to ensure consistent order
        for name, info in data.items():
            cat = info.get("category", "Uncategorized")
            if cat not in categories:
                categories[cat] = []
            categories[cat].append((name, info))

        for cat_name in sorted(categories.keys()):
            cat_item = QtGui.QStandardItem(cat_name)
            cat_item.setEditable(False)
            cat_item.setData(cat_name, self.RoleCategory)
            cat_item.setIcon(self._get_std_icon(QtWidgets.QStyle.SP_DirIcon))

            for shape_name, info in sorted(categories[cat_name]):
                shape_item = QtGui.QStandardItem(shape_name)
                shape_item.setEditable(False)

                json_path = info["path"]
                shape_item.setData(str(json_path), self.RolePath)
                shape_item.setData(cat_name, self.RoleCategory)

                # Thumbnail Logic
                thumb_path = json_path.with_suffix(".png")
                if thumb_path.exists():
                    pixmap = QtGui.QPixmap(str(thumb_path))
                else:
                    pixmap = self._get_std_icon(QtWidgets.QStyle.SP_FileIcon).pixmap(
                        64, 64
                    )

                shape_item.setData(pixmap, self.RoleThumbnail)
                shape_item.setIcon(QtGui.QIcon(pixmap))

                cat_item.appendRow(shape_item)

            self.appendRow(cat_item)

    def _get_std_icon(self, style_enum):
        return QtWidgets.QApplication.style().standardIcon(style_enum)


class FlatLeafProxyModel(QtCore.QAbstractProxyModel):
    """
    A Proxy Model that recursively finds all leaf nodes (Shapes) in the source
    tree and maps them to a flat list (Row 0..N).
    Categories are ignored.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source_indices = []  # List of QPersistentModelIndex

    def setSourceModel(self, source_model):
        super().setSourceModel(source_model)
        self.rebuild_mapping()
        # If source changes, we should rebuild (omitted for brevity in this static data example)

    def rebuild_mapping(self):
        """Scans the source model and stores pointers to all leaf nodes."""
        self.beginResetModel()
        self._source_indices.clear()

        model = self.sourceModel()
        if model:
            self._recursive_fetch(QtCore.QModelIndex(), model)

        self.endResetModel()

    def _recursive_fetch(self, parent_idx, model):
        rows = model.rowCount(parent_idx)
        for r in range(rows):
            idx = model.index(r, 0, parent_idx)
            # If it has children, dive deeper (it's a category)
            if model.hasChildren(idx):
                self._recursive_fetch(idx, model)
            else:
                # It's a leaf (Shape), keep it
                self._source_indices.append(QtCore.QPersistentModelIndex(idx))

    # --- AbstractProxyModel Implementation ---

    def rowCount(self, parent=QtCore.QModelIndex()):
        return len(self._source_indices)

    def columnCount(self, parent=QtCore.QModelIndex()):
        return 1

    def index(self, row, column, parent=QtCore.QModelIndex()):
        if 0 <= row < len(self._source_indices) and column == 0:
            return self.createIndex(row, column)
        return QtCore.QModelIndex()

    def parent(self, index):
        # Flat list has no parents
        return QtCore.QModelIndex()

    def mapToSource(self, proxy_index):
        if not proxy_index.isValid():
            return QtCore.QModelIndex()
        row = proxy_index.row()
        if 0 <= row < len(self._source_indices):
            return QtCore.QModelIndex(self._source_indices[row])
        return QtCore.QModelIndex()

    def mapFromSource(self, source_index):
        # Linear search (O(N)), acceptable for < few thousand items
        if not source_index.isValid():
            return QtCore.QModelIndex()

        # Optimization: Just check if it is in our list
        # QPersistentModelIndex compares properly with QModelIndex
        try:
            row = self._source_indices.index(source_index)
            return self.index(row, 0)
        except ValueError:
            return QtCore.QModelIndex()


# ==============================================================================
# 3. HOVER OVERLAY
# ==============================================================================


class HoverOverlay(QtWidgets.QWidget):
    """Floating thumbnail widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(QtCore.Qt.ToolTip | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)

        layout = QtWidgets.QVBoxLayout(self)
        self.label = QtWidgets.QLabel()
        self.label.setStyleSheet("""
            QLabel {
                border: 2px solid #555;
                background: #2b2b2b;
                padding: 4px;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.label)

    def set_pixmap(self, pixmap):
        self.label.setPixmap(pixmap)
        self.adjustSize()


# ==============================================================================
# 4. MAIN WIDGET
# ==============================================================================


class ShapeLibraryWidget(QtWidgets.QWidget):

    def __init__(self, shape_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Controller Shape Library")
        self.resize(450, 650)
        self.shape_data = shape_data

        # -- State --
        self.is_flat_mode = False
        self.hover_thumb_enabled = False

        # -- Models --
        self.source_model = ShapeLibraryModel(self.shape_data)

        # 1. Hierarchical Proxy (Standard filtering, preserves tree)
        self.proxy_hierarchical = QtCore.QSortFilterProxyModel()
        self.proxy_hierarchical.setSourceModel(self.source_model)
        self.proxy_hierarchical.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.proxy_hierarchical.setRecursiveFilteringEnabled(True)

        # 2. Flat Proxy (Flattens tree to list)
        self.proxy_flat_internal = FlatLeafProxyModel()
        self.proxy_flat_internal.setSourceModel(self.source_model)

        # 3. Flat Search Proxy (Filters the Flat list)
        self.proxy_flat_search = QtCore.QSortFilterProxyModel()
        self.proxy_flat_search.setSourceModel(self.proxy_flat_internal)
        self.proxy_flat_search.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)

        # -- UI Layout --
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(4, 4, 4, 4)

        # Top Bar (Search + Back Button)
        top_layout = QtWidgets.QHBoxLayout()

        # Back Button (Hidden by default, used for diving into folders)
        self.btn_back = QtWidgets.QToolButton()
        self.btn_back.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_ArrowBack))
        self.btn_back.setToolTip("Back to Categories")
        self.btn_back.clicked.connect(self.go_up_level)
        self.btn_back.setVisible(False)
        top_layout.addWidget(self.btn_back)

        # Search
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("Search shapes...")
        self.search_input.textChanged.connect(self.on_search_changed)
        top_layout.addWidget(self.search_input)

        self.main_layout.addLayout(top_layout)

        # View Stack
        self.stack = QtWidgets.QStackedWidget()
        self.main_layout.addWidget(self.stack)

        # View 1: Tree View
        self.tree_view = QtWidgets.QTreeView()
        self.tree_view.setHeaderHidden(True)
        self.tree_view.setMouseTracking(True)
        self.stack.addWidget(self.tree_view)

        # View 2: List/Icon View
        self.list_view = QtWidgets.QListView()
        self.list_view.setViewMode(QtWidgets.QListView.IconMode)
        self.list_view.setResizeMode(QtWidgets.QListView.Adjust)
        self.list_view.setGridSize(QtCore.QSize(100, 110))
        self.list_view.setIconSize(QtCore.QSize(80, 80))
        self.list_view.setUniformItemSizes(True)
        self.list_view.setMouseTracking(True)
        self.list_view.setWordWrap(True)
        self.stack.addWidget(self.list_view)

        # -- Signals --
        self.tree_view.entered.connect(self.on_item_entered)
        self.list_view.entered.connect(self.on_item_entered)

        # Handle Navigation (Drill Down)
        self.list_view.doubleClicked.connect(self.on_icon_double_clicked)

        # -- Init Defaults --
        self.set_model_mode(flat=False)  # Start Hierarchical

        # Context Menu
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        # Overlay
        self.overlay = HoverOverlay(self)

        self.apply_style()

    def apply_style(self):
        self.setStyleSheet("""
            QWidget { background-color: #2b2b2b; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; font-size: 11pt; }
            QLineEdit { background-color: #3a3a3a; border: 1px solid #555; padding: 4px; border-radius: 3px; }
            QTreeView, QListView { border: none; }
            QTreeView::item:hover, QListView::item:hover { background-color: #444; }
            QTreeView::item:selected, QListView::item:selected { background-color: #5285a6; }
            QToolButton { background: transparent; border: none; padding: 2px; }
            QToolButton:hover { background-color: #444; border-radius: 3px; }
        """)

    # --- Logic: Model Switching ---

    def set_model_mode(self, flat):
        """Swaps the models used by the views based on Flat vs Hierarchical."""
        self.is_flat_mode = flat

        if flat:
            # In Flat mode, both views see a flat list
            self.tree_view.setModel(self.proxy_flat_search)
            self.list_view.setModel(self.proxy_flat_search)
            # Reset navigation root for flat mode
            self.list_view.setRootIndex(QtCore.QModelIndex())
            self.btn_back.setVisible(False)
        else:
            # In Hierarchical mode, both views see the tree
            self.tree_view.setModel(self.proxy_hierarchical)
            self.list_view.setModel(self.proxy_hierarchical)
            # Reset navigation root
            self.list_view.setRootIndex(QtCore.QModelIndex())
            self.btn_back.setVisible(False)
            self.tree_view.expandAll()

    def on_search_changed(self, text):
        # Apply filter to both proxy chains
        regex = QtCore.QRegularExpression(
            text, QtCore.QRegularExpression.CaseInsensitiveOption
        )
        self.proxy_hierarchical.setFilterRegularExpression(regex)
        self.proxy_flat_search.setFilterRegularExpression(regex)

        if not self.is_flat_mode and text:
            self.tree_view.expandAll()

    # --- Logic: Icon View Navigation ---

    def on_icon_double_clicked(self, index):
        """Handle diving into folders in Icon Mode."""
        if self.is_flat_mode:
            return  # Flat mode has no folders

        # We are in Hierarchical Proxy
        # Check if the clicked item has children (is a folder)
        if self.proxy_hierarchical.hasChildren(index):
            self.list_view.setRootIndex(index)
            self.btn_back.setVisible(True)

    def go_up_level(self):
        """Go up one directory level in Icon Mode."""
        current_root = self.list_view.rootIndex()
        if current_root.isValid():
            parent = current_root.parent()
            self.list_view.setRootIndex(parent)

            # Hide back button if we are back at root
            if not parent.isValid():
                self.btn_back.setVisible(False)

    # --- Logic: Mouse Hover ---

    def on_item_entered(self, index):
        if not self.hover_thumb_enabled:
            return

        # Determine which model is active to map properly
        active_proxy = (
            self.tree_view.model()
        )  # Both views share the same model reference at any time

        # Map recursively to source
        source_index = index
        while hasattr(active_proxy, "mapToSource"):
            source_index = active_proxy.mapToSource(source_index)
            active_proxy = active_proxy.sourceModel()

        pixmap = source_index.data(ShapeLibraryModel.RoleThumbnail)

        if pixmap and isinstance(pixmap, QtGui.QPixmap):
            self.overlay.set_pixmap(pixmap)
            cursor_pos = QtGui.QCursor.pos()
            self.overlay.move(cursor_pos + QtCore.QPoint(20, 20))
            self.overlay.show()
        else:
            self.overlay.hide()

    def leaveEvent(self, event):
        self.overlay.hide()
        super().leaveEvent(event)

    # --- Logic: Context Menu ---

    def show_context_menu(self, pos):
        menu = QtWidgets.QMenu(self)

        # View Modes
        grp_view = QtGui.QActionGroup(self)

        act_tree = menu.addAction("Tree View")
        act_tree.setCheckable(True)
        act_tree.setChecked(self.stack.currentWidget() == self.tree_view)

        act_icon = menu.addAction("Icon Grid View")
        act_icon.setCheckable(True)
        act_icon.setChecked(self.stack.currentWidget() == self.list_view)

        grp_view.addAction(act_tree)
        grp_view.addAction(act_icon)

        menu.addSeparator()

        # Flat Toggle
        act_flat = menu.addAction("Flat List (Ignore Categories)")
        act_flat.setCheckable(True)
        act_flat.setChecked(self.is_flat_mode)

        menu.addSeparator()

        # Hover Toggle
        act_hover = menu.addAction("Floating Thumbnails")
        act_hover.setCheckable(True)
        act_hover.setChecked(self.hover_thumb_enabled)

        action = menu.exec(self.mapToGlobal(pos))

        if not action:
            return

        # 1. View Switching
        if action == act_tree:
            self.stack.setCurrentWidget(self.tree_view)
        elif action == act_icon:
            self.stack.setCurrentWidget(self.list_view)

        # 2. Flat Toggle
        elif action == act_flat:
            # FIX: Use isChecked()
            self.set_model_mode(action.isChecked())

        # 3. Hover Toggle
        elif action == act_hover:
            # FIX: Use isChecked()
            self.hover_thumb_enabled = action.isChecked()
            if not self.hover_thumb_enabled:
                self.overlay.hide()


# ==============================================================================
# 5. EXECUTION
# ==============================================================================

# Test execution block
if __name__ == "__main__":
    try:
        test_ui.close()  # noqa: F821
        test_ui.deleteLater()  # noqa: F821
    except Exception:
        pass

    test_ui = ShapeLibraryWidget(MOCK_DATA)  # noqa: F841
    test_ui.show()

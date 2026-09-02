# Guide Designer as a Mode Tab — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Host the Guide Designer inside the Trigger window as a mode tab that sits above the menu bar, so switching modes swaps the menus and the status fields, with an opt-in tear-off back to a floating window.

**Architecture:** Each mode is a bundle of three plain widgets — a `QMenuBar`, a content widget, a status strip — held in three parallel `QStackedWidget`s. The mode `QTabBar` and the menu stack are installed together via `QMainWindow.setMenuWidget()`, which puts the tabs above the menus. Nothing is installed with `setMenuBar()`/`setStatusBar()`, so Qt never takes ownership of a bundle widget; detaching is pure reparenting.

**Tech Stack:** Python 3.10+, Qt via `tik.shared.ui.Qt` (vendored Qt.py shim), pytest. No third-party dependencies.

**Spec:** `docs/superpowers/specs/2026-08-30-designer-as-mode-tab-design.md`

## Global Constraints

- No third-party dependencies — stdlib and Maya-bundled modules only.
- `tik/trigger/core` stays pure Python (no Maya, no Qt). Nothing in this plan touches `core`.
- UI tests run headless: `TIK_TESTS_NO_MAYA=1`, `QT_QPA_PLATFORM=offscreen`. Anything constructed at `TriggerWindow.__init__` time must not import Maya.
- Qt binding is the vendored `Qt.py` shim. **Never reference `QAction` by class** (its module differs between PySide2 and PySide6) — walk `menu.actions()` instead.
- Test command (PowerShell, from the repo root):
  ```
  $env:PYTHONPATH="D:/dev/tikworks/src/python;$env:PYTHONPATH"; $env:TIK_TESTS_NO_MAYA="1"; $env:QT_QPA_PLATFORM="offscreen"; mayapy -m pytest tests/ui -q
  ```
  Baseline before this plan: **47 passed**.
- Existing behaviour that must not regress: `open_guide_designer(guides_path="")` keeps its name and signature (two callers), and `self._guide_designer` stays a single lazily-built instance.

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `src/python/tik/shared/ui/status.py` | status fields on a bar *or* a plain strip | modify (~15 lines) |
| `src/python/tik/trigger/ui/designer/window.py` | Designer as a page: exposes `menu_bar`, `status_strip`, `title`, `teardown()` | modify |
| `src/python/tik/trigger/ui/main.py` | mode host: mode bar, three stacks, shortcut rule, detach | modify |
| `src/python/tik/trigger/ui/shell.py` | `DesignerShell` — floating home for a detached Designer bundle | **create** |
| `tests/ui/test_ui_kit.py` | `StatusFields` on a strip | modify |
| `tests/ui/test_guide_designer.py` | `menuBar()` → `menu_bar` | modify |
| `tests/ui/test_pipeline_ui.py` | mode bar, laziness, shortcut rule, detach round-trip | modify |

`DesignerShell` gets its own module rather than living in `main.py`: `main.py` is already 380 lines, and the shell is the one piece that still needs `MayaToolWindow` and the workspace control.

---

### Task 1: `StatusFields` accepts a plain strip widget

**Files:**
- Modify: `src/python/tik/shared/ui/status.py:11-27`
- Test: `tests/ui/test_ui_kit.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `StatusFields(host, fields)` where `host` is a `QStatusBar` **or** any `QWidget` (laid out as an `QHBoxLayout` of activity label + stretch + fields). `set(name, text)`, `text(name)`, `set_activity(text, timeout_ms=0)` unchanged.

- [ ] **Step 1: Write the failing test**

In `tests/ui/test_ui_kit.py`:

```python
def test_status_fields_on_a_plain_strip(qapp):
    from tik.shared.ui.status import StatusFields

    strip = QtWidgets.QWidget()
    fields = StatusFields(strip, ("modules", "file"))
    fields.set("modules", "3 module(s)")
    fields.set_activity("Ready")
    assert fields.text("modules") == "3 module(s)"
    assert fields.activity.text() == "Ready"
    # activity, separator and both field labels all live on the strip
    assert len(strip.findChildren(QtWidgets.QLabel)) == 4
```

Add `from tik.shared.ui.Qt import QtWidgets` to the imports if it is not there already.

- [ ] **Step 2: Run it and watch it fail**

Run the test command with `-k status_fields_on_a_plain_strip`.
Expected: FAIL — `AttributeError: 'QWidget' object has no attribute 'setSizeGripEnabled'`.

- [ ] **Step 3: Implement**

Replace the body of `StatusFields.__init__` and add `_add`:

```python
class StatusFields:
    """Status bar helper: one activity label, then permanent fields.

    ``host`` is a ``QStatusBar`` or a plain ``QWidget`` used as a strip — the
    strip form lets a window keep one status bar while each mode owns its own
    set of fields.
    """

    def __init__(self, host, fields: Sequence[str]) -> None:
        self.bar = host if isinstance(host, QtWidgets.QStatusBar) else None
        self._layout = None
        if self.bar is not None:
            self.bar.setSizeGripEnabled(False)
        else:
            self._layout = QtWidgets.QHBoxLayout(host)
            self._layout.setContentsMargins(6, 0, 6, 0)
            self._layout.setSpacing(6)
        self.activity = QtWidgets.QLabel("")
        self.activity.setObjectName("StatusActivity")
        self._add(self.activity, stretch=1)
        self.labels: dict[str, QtWidgets.QLabel] = {}
        for index, name in enumerate(fields):
            if index:
                separator = QtWidgets.QLabel("·")
                separator.setObjectName("StatusSeparator")
                self._add(separator, permanent=True)
            label = QtWidgets.QLabel("")
            label.setObjectName(f"Status_{name}")
            self._add(label, permanent=True)
            self.labels[name] = label

    def _add(self, widget, stretch: int = 0, permanent: bool = False) -> None:
        if self.bar is None:
            self._layout.addWidget(widget, stretch)
        elif permanent:
            self.bar.addPermanentWidget(widget)
        else:
            self.bar.addWidget(widget, stretch)
```

And guard the one remaining bar-only call in `set_activity`:

```python
        if timeout_ms and self.bar is not None:
            self.bar.showMessage("", timeout_ms)
```

- [ ] **Step 4: Run the whole UI suite**

Expected: 48 passed (47 baseline + the new one).

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/shared/ui/status.py tests/ui/test_ui_kit.py
git commit -m "feat(tik.shared.ui): StatusFields can live on a plain strip widget"
```

---

### Task 2: `GuideDesigner` becomes a page widget

**Files:**
- Modify: `src/python/tik/trigger/ui/designer/window.py` (class line 57, `_build_central:202`, `_build_menus:238`, `_build_status:315`, `set_file:344`, `closeEvent:618`)
- Test: `tests/ui/test_guide_designer.py:93`

**Interfaces:**
- Consumes: `StatusFields(strip, fields)` from Task 1.
- Produces, on `GuideDesigner`:
  - `menu_bar: QtWidgets.QMenuBar` — built, never installed.
  - `status_strip: QtWidgets.QWidget` — hosts its `StatusFields`.
  - `title: str` property — `"Guide Designer"` or `"Guide Designer — <file>.trg"`.
  - `title_changed = QtCore.Signal(str)` — emitted by `set_file`.
  - `detach_requested = QtCore.Signal(bool)` — emitted by `View ▸ Open in Window`.
  - `detach_action` — the checkable action behind that signal.
  - `teardown()` — clears bindings and uninstalls the watcher; idempotent.

- [ ] **Step 1: Write the failing test**

Change `test_window_shell` in `tests/ui/test_guide_designer.py` and add a page test next to it:

```python
def test_window_shell(designer):
    assert [action.text() for action in designer.menu_bar.actions()] == ["&File", "&Edit", "&View", "&Build", "&Help"]
    assert designer.status.text("modules") == "0 module(s)"
    assert designer.tree_pane.isVisible() and designer.graph_pane.isVisible()
    designer.graph_action.setChecked(False)
    designer.set_pane_visible(designer.graph_pane, False)
    assert not designer.graph_pane.isVisible()


def test_designer_is_a_page_not_a_window(designer):
    assert not isinstance(designer, QtWidgets.QMainWindow)
    assert designer.menu_bar.parent() is designer          # built, not installed
    assert designer.status_strip is not None
    assert designer.title == "Guide Designer"
    seen = []
    designer.title_changed.connect(seen.append)
    designer.set_file("C:/tmp/biped.trg")
    assert seen == ["Guide Designer — biped.trg"]
    designer.teardown()
    designer.teardown()                                     # idempotent
```

- [ ] **Step 2: Run it and watch it fail**

Run with `-k "window_shell or page_not_a_window"`.
Expected: FAIL — `AttributeError: 'GuideDesigner' object has no attribute 'menu_bar'`.

- [ ] **Step 3: Implement**

In `designer/window.py`:

a. Drop the `MayaToolWindow` import and the base class; drop `WINDOW_NAME`:

```python
class GuideDesigner(DesignerCommands, DesignerProperties, QtWidgets.QWidget):
    """Guide Designer page: modules · tree · graph · properties.

    A plain widget on purpose — it is hosted as a mode of the Trigger window
    (``ui/main.py``) and can be reparented into ``DesignerShell`` to float.
    It *builds* ``menu_bar`` and ``status_strip`` but installs neither, so the
    host decides where they go.
    """

    title_changed = QtCore.Signal(str)
    detach_requested = QtCore.Signal(bool)
```

b. In `__init__`, replace `self.setWindowTitle("Guide Designer")` with `self.setObjectName("TriggerGuideDesigner")` followed by `self.setWindowTitle(self.title)` (the object name is what `SceneWatcher` probes for a dead C++ object), and add `self._torn_down = False`.

c. `_build_central` — replace `self.setCentralWidget(self.splitter)` with:

```python
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.splitter)
```

d. `_build_menus` — replace `bar = self.menuBar()` with `bar = self.menu_bar = QtWidgets.QMenuBar(self)`. Delete the `File ▸ Close` action and the separator above it (`Ctrl+W` belongs to the host). In the `View` menu, after the `Refresh` action, add:

```python
        view_menu.addSeparator()
        self.detach_action = self._action(
            view_menu, "Open in Window",
            lambda: self.detach_requested.emit(self.detach_action.isChecked()),
            checkable=True,
        )
```

e. `_build_status`:

```python
    def _build_status(self) -> None:
        self.status_strip = QtWidgets.QWidget()
        self.status = StatusFields(self.status_strip, ("modules", "connections", "file"))
        self.status.set_activity("Ready")
```

f. Title. Add the property and rewrite the title line of `set_file`:

```python
    @property
    def title(self) -> str:
        return f"Guide Designer — {Path(self.file_path).name}" if self.file_path else "Guide Designer"
```

In `set_file`, replace the `setWindowTitle(...)` call with:

```python
        self.setWindowTitle(self.title)
        self.title_changed.emit(self.title)
```

g. Teardown:

```python
    def teardown(self) -> None:
        """Release bindings and scene jobs. Safe to call more than once."""
        if self._torn_down:
            return
        self._torn_down = True
        self.bindings.clear()
        self.watcher.uninstall()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.teardown()
        super().closeEvent(event)
```

- [ ] **Step 4: Run the whole UI suite**

Expected: `tests/ui/test_guide_designer.py` fully green (26 tests) — the other 24 are untouched and are the check that the refactor did not leak. `test_pipeline_ui.py` still passes because `open_guide_designer` is not exercised there yet.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/ui/designer/window.py tests/ui/test_guide_designer.py
git commit -m "refactor(tik.trigger): the Guide Designer is a page, not a window"
```

---

### Task 3: `TriggerWindow` becomes a mode host

**Files:**
- Modify: `src/python/tik/trigger/ui/main.py` (`_build_central:45`, `_build_menus:69`, `_build_status:119`, `_update_title:323`)
- Test: `tests/ui/test_pipeline_ui.py:184`

**Interfaces:**
- Consumes: `StatusFields(strip, fields)` from Task 1.
- Produces, on `TriggerWindow`:
  - `TRIGGER_MODE = 0`, `DESIGNER_MODE = 1` (module constants in `main.py`).
  - `mode_bar: QTabBar`, `menu_stack`, `pages`, `status_stack: QStackedWidget`.
  - `add_mode(title, menu_widget, content, status_widget) -> int`.
  - `menu_bar` property → the active mode's `QMenuBar` (or `None` before one is built).
  - `_activate_mode(index)` — moves all three stacks and applies the shortcut rule.
  - `self.tabs` (session tabs) unchanged, now inside `pages` index 0.

- [ ] **Step 1: Write the failing test**

In `tests/ui/test_pipeline_ui.py`, change the one stale assertion in `test_main_window_tabs_and_files` —

```python
    assert window.menu_bar.actions()[0].text() == "&File"
```

— and add:

```python
def test_mode_bar_swaps_menus_status_and_shortcuts(qapp):
    window = TriggerWindow(designer_factory=_stub_designer)
    window.show()
    assert [window.mode_bar.tabText(i) for i in range(window.mode_bar.count())] == ["Trigger", "Guide Designer"]
    assert window.mode_bar.currentIndex() == 0
    assert window.pages.currentWidget() is window.tabs
    assert window.status_stack.currentWidget() is window.trigger_status_strip
    trigger_menus = window.menu_bar

    window.mode_bar.setCurrentIndex(1)
    assert window.menu_bar is not trigger_menus
    assert [action.text() for action in window.menu_bar.actions()][0] == "&File"
    assert window.pages.currentWidget() is not window.tabs
    # the shortcut rule: only the active mode's actions are enabled
    assert not any(action.isEnabled() for action in trigger_menus.actions())
    assert all(action.isEnabled() for action in window.menu_bar.actions())

    window.mode_bar.setCurrentIndex(0)
    assert all(action.isEnabled() for action in trigger_menus.actions())
    window.close()
```

`_stub_designer` is defined in Task 4; for this task, temporarily mark the test `@pytest.mark.skip` is **not** allowed — instead write Task 3 and Task 4 as one commit if you prefer, or define `_stub_designer` now (its body is in Task 4, Step 3) since it is only three lines. Define it now.

- [ ] **Step 2: Run it and watch it fail**

Expected: FAIL — `TypeError: TriggerWindow() got an unexpected keyword argument 'designer_factory'`.

- [ ] **Step 3: Implement the shell**

In `main.py`, add module constants next to `VERSION`:

```python
TRIGGER_MODE = 0
DESIGNER_MODE = 1
```

Add the action walker as a module function (never name `QAction` — the shim moves it between PySide versions):

```python
def _iter_actions(widget):
    """Every leaf action under a menu bar or menu, submenus included."""
    for action in widget.actions():
        submenu = action.menu()
        if submenu is not None:
            yield from _iter_actions(submenu)
        else:
            yield action
```

Rewrite `_build_central` as `_build_shell` plus mode registration (keep the log dock exactly as it is):

```python
    def _build_shell(self) -> None:
        self.mode_bar = QtWidgets.QTabBar()
        self.mode_bar.setDrawBase(False)
        self.mode_bar.setExpanding(False)
        self.menu_stack = QtWidgets.QStackedWidget()
        header = QtWidgets.QWidget()
        header_layout = QtWidgets.QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(0)
        header_layout.addWidget(self.mode_bar)
        header_layout.addWidget(self.menu_stack)
        self.setMenuWidget(header)          # tabs above the menus
        self.pages = QtWidgets.QStackedWidget()
        self.setCentralWidget(self.pages)
        self.status_stack = QtWidgets.QStackedWidget()
        self.statusBar().addWidget(self.status_stack, 1)
        self._mode_menus: dict[int, QtWidgets.QMenuBar] = {}
        self._active_mode = TRIGGER_MODE

    def add_mode(self, title: str, menu_widget, content, status_widget) -> int:
        index = self.mode_bar.addTab(title)
        self.menu_stack.insertWidget(index, menu_widget)
        self.pages.insertWidget(index, content)
        self.status_stack.insertWidget(index, status_widget)
        return index

    @property
    def menu_bar(self) -> Optional[QtWidgets.QMenuBar]:
        return self._mode_menus.get(self._active_mode)

    def _activate_mode(self, index: int) -> None:
        self._active_mode = index
        self.menu_stack.setCurrentIndex(index)
        self.pages.setCurrentIndex(index)
        self.status_stack.setCurrentIndex(index)
        self._apply_shortcut_rule()
        self._update_title()

    def _apply_shortcut_rule(self) -> None:
        """Only the active mode's actions are enabled.

        Not cosmetic: the two menu bars collide on Ctrl+B/S/O/N/D/L, Tab and F2,
        and Qt answers an ambiguous WindowShortcut by firing neither. The rule
        costs one constraint — no mode may disable an individual menu action for
        its own reasons, because switching modes re-enables everything.
        """
        for mode, bar in self._mode_menus.items():
            enabled = mode == self._active_mode
            for action in _iter_actions(bar):
                action.setEnabled(enabled)
```

`__init__` order becomes:

```python
        self._build_shell()
        self._build_trigger_mode()      # session tabs + menus + status, index 0
        self._build_designer_mode()     # empty holders, index 1 (Task 4)
        self.mode_bar.currentChanged.connect(self._activate_mode)
        theme.apply(self)
```

`_build_trigger_mode` builds the pieces that used to be installed directly:

```python
    def _build_trigger_mode(self) -> None:
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(lambda _index: self._update_title())
        self.trigger_menus = QtWidgets.QMenuBar()
        self._build_menus(self.trigger_menus)
        self.trigger_status_strip = QtWidgets.QWidget()
        self._build_status(self.trigger_status_strip)
        self._mode_menus[TRIGGER_MODE] = self.trigger_menus
        self.add_mode("Trigger", self.trigger_menus, self.tabs, self.trigger_status_strip)
```

`_build_menus(self, bar)` takes the bar as an argument — delete its `bar = self.menuBar()` line and change the signature. `_build_status(self, strip)` likewise: `self.status = StatusFields(strip, ("references", "maya", "version"))`.

The log dock code stays where it was, moved into `_build_shell` after `setCentralWidget`.

- [ ] **Step 4: Run the whole UI suite**

Expected: `test_pipeline_ui.py` green including the new test.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/ui/main.py tests/ui/test_pipeline_ui.py
git commit -m "feat(tik.trigger): the Trigger window hosts modes above the menu bar"
```

---

### Task 4: The Designer mode, built lazily

**Files:**
- Modify: `src/python/tik/trigger/ui/main.py` (`__init__:27`, `open_guide_designer:342`, `closeEvent:364`)
- Test: `tests/ui/test_pipeline_ui.py`

**Interfaces:**
- Consumes: `add_mode`, `_activate_mode`, `_mode_menus` (Task 3); `GuideDesigner.menu_bar` / `.status_strip` / `.title_changed` / `.teardown()` (Task 2).
- Produces:
  - `TriggerWindow(parent=None, file_browser=None, designer_factory=None)` — `designer_factory()` returns a `GuideDesigner`-shaped page; default builds the real one.
  - `_ensure_designer()` — builds on first use, fills the three holders, registers `_mode_menus[DESIGNER_MODE]`, returns the page.
  - `open_guide_designer(guides_path="")` — unchanged signature; selects the Designer mode.

- [ ] **Step 1: Write the failing test**

In `tests/ui/test_pipeline_ui.py`, add the stub factory and the tests:

```python
def _stub_designer():
    from stub import StubScene
    from tik.trigger.ui.designer import GuideDesigner

    return GuideDesigner(scene=StubScene())


def test_designer_mode_is_built_lazily(qapp):
    window = TriggerWindow(designer_factory=_stub_designer)
    window.show()
    assert window._guide_designer is None
    assert window.designer_page_holder.layout().count() == 0
    window.mode_bar.setCurrentIndex(1)
    assert window._guide_designer is not None
    assert window.designer_page_holder.layout().count() == 1
    window.close()


def test_open_guide_designer_selects_the_mode_and_sets_the_file(qapp, tmp_path):
    window = TriggerWindow(designer_factory=_stub_designer)
    window.show()
    designer = window.open_guide_designer(str(tmp_path / "biped.trg"))
    assert window.mode_bar.currentIndex() == 1
    assert designer.file_path.endswith("biped.trg")
    assert window.mode_bar.tabText(1) == "Guide Designer — biped.trg"
    window.close()
```

- [ ] **Step 2: Run it and watch it fail**

Expected: FAIL — `AttributeError: 'TriggerWindow' object has no attribute 'designer_page_holder'`.

- [ ] **Step 3: Implement**

`__init__` gains the seam:

```python
    def __init__(self, parent=None, file_browser=None, designer_factory=None) -> None:
        ...
        self.designer_factory = designer_factory
        self._guide_designer = None
        self._shell = None
```

Holders, registered at startup so the tab indices are stable from the first paint:

```python
    def _build_designer_mode(self) -> None:
        """Register the tab now, build the Designer on first use.

        ``GuideDesigner`` constructs a ``GuideScene``, which imports Maya, so it
        cannot be built at window startup — the UI tests run without Maya.
        """
        self.designer_menu_holder = _holder()
        self.designer_page_holder = _holder()
        self.designer_status_holder = _holder()
        self.add_mode("Guide Designer", self.designer_menu_holder,
                      self.designer_page_holder, self.designer_status_holder)
```

with a module helper:

```python
def _holder() -> QtWidgets.QWidget:
    """An empty widget whose zero-margin layout a mode bundle drops into."""
    widget = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    return widget
```

Construction and hosting:

```python
    def _ensure_designer(self):
        if self._guide_designer is None:
            if self.designer_factory is not None:
                designer = self.designer_factory()
            else:
                from .designer import GuideDesigner

                designer = GuideDesigner(events=self.events, file_browser=self.file_browser)
            self._guide_designer = designer
            designer.title_changed.connect(self._on_designer_title)
            designer.detach_requested.connect(self.set_designer_detached)
            self._mode_menus[DESIGNER_MODE] = designer.menu_bar
            self._host_designer()
        return self._guide_designer

    def _host_designer(self) -> None:
        """Put the Designer's three widgets back into the mode holders."""
        designer = self._guide_designer
        self.designer_menu_holder.layout().addWidget(designer.menu_bar)
        self.designer_page_holder.layout().addWidget(designer)
        self.designer_status_holder.layout().addWidget(designer.status_strip)

    def _on_designer_title(self, title: str) -> None:
        self.mode_bar.setTabText(DESIGNER_MODE, title)
        if self._shell is not None:
            self._shell.setWindowTitle(title)
        self._update_title()
```

`_activate_mode` builds the Designer when its tab is chosen — insert at the top of the method:

```python
        if index == DESIGNER_MODE:
            self._ensure_designer()
```

`open_guide_designer` keeps its signature:

```python
    def open_guide_designer(self, guides_path: str = ""):
        designer = self._ensure_designer()
        if guides_path:
            designer.set_file(guides_path)
        if self._shell is not None:
            self._shell.show_tool()
            self._shell.raise_()
        else:
            self.mode_bar.setCurrentIndex(DESIGNER_MODE)
        return designer
```

`_update_title` grows a Designer branch — insert before the `session = self.session` line:

```python
        if self._active_mode == DESIGNER_MODE and self._guide_designer is not None:
            self.setWindowTitle(f"Trigger {VERSION} — {self._guide_designer.title}")
            return
```

Note the session-tab retitling loop at the top of `_update_title` stays where it is: it must run in either mode.

`closeEvent` tears the Designer down (a page never gets its own close event):

```python
    def closeEvent(self, event) -> None:  # noqa: N802
        for view in self.views:
            if view.session.is_modified and not self.ask_discard(view.session):
                event.ignore()
                return
        if self._guide_designer is not None:
            self._guide_designer.teardown()
        super().closeEvent(event)
```

- [ ] **Step 4: Run the whole UI suite**

Expected: green, with the two new tests passing.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/ui/main.py tests/ui/test_pipeline_ui.py
git commit -m "feat(tik.trigger): the Guide Designer is a mode of the Trigger window"
```

---

### Task 5: Tear-off into a floating shell

**Files:**
- Create: `src/python/tik/trigger/ui/shell.py`
- Modify: `src/python/tik/trigger/ui/main.py` (add `set_designer_detached`; `_apply_shortcut_rule`; `closeEvent`)
- Test: `tests/ui/test_pipeline_ui.py`

**Interfaces:**
- Consumes: `GuideDesigner.menu_bar` / `.status_strip` / `.title` / `.detach_action` (Task 2); `_host_designer`, `_ensure_designer`, `_apply_shortcut_rule` (Tasks 3-4).
- Produces:
  - `DesignerShell(host, designer)` in `ui/shell.py`, `WINDOW_NAME = "TriggerGuideDesigner"`, `release()`.
  - `TriggerWindow.set_designer_detached(detached: bool)`.

- [ ] **Step 1: Write the failing test**

```python
def test_designer_detaches_and_reattaches(qapp):
    window = TriggerWindow(designer_factory=_stub_designer)
    window.show()
    designer = window._ensure_designer()
    tree = designer.tree

    window.set_designer_detached(True)
    assert window._shell is not None
    assert designer.parent() is not window.designer_page_holder
    assert window.designer_page_holder.layout().count() == 0
    assert window.mode_bar.count() == 2          # the tab stays
    assert window.mode_bar.currentIndex() == 0   # and we fall back to Trigger
    # a detached menu bar is in its own window: its shortcuts stop colliding
    assert all(action.isEnabled() for action in designer.menu_bar.actions())
    # selecting the Designer tab raises the shell instead of showing an empty page
    window.mode_bar.setCurrentIndex(1)
    assert window.mode_bar.currentIndex() == 0

    window.set_designer_detached(False)
    assert window._shell is None
    assert window.designer_page_holder.layout().count() == 1
    assert designer.tree is tree                 # same page, state intact
    assert window.mode_bar.currentIndex() == 1
    window.close()
```

- [ ] **Step 2: Run it and watch it fail**

Expected: FAIL — `AttributeError: 'TriggerWindow' object has no attribute 'set_designer_detached'`.

- [ ] **Step 3: Implement**

`src/python/tik/trigger/ui/shell.py`:

```python
"""Floating home for a detached Guide Designer.

The Designer is a page (``ui/designer/window.py``); this is the frame it lives
in when you tear it off. The bundle — menu bar, page, status strip — is only
ever *reparented*, never installed with ``setMenuBar``/``setStatusBar``, so Qt
never takes ownership of a widget the host expects to get back.
"""

from __future__ import annotations

from tik.shared.ui import theme
from tik.shared.ui.maya_window import MayaToolWindow
from tik.shared.ui.Qt import QtWidgets


class DesignerShell(MayaToolWindow):
    WINDOW_NAME = "TriggerGuideDesigner"

    def __init__(self, host, designer) -> None:
        super().__init__(host)
        self.host = host
        self.designer = designer
        body = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(designer.menu_bar)
        layout.addWidget(designer, 1)
        layout.addWidget(designer.status_strip)
        self.setCentralWidget(body)
        self.setWindowTitle(designer.title)
        self.resize(1240, 680)
        theme.apply(self)

    def release(self) -> None:
        """Give the bundle back to the host before this window goes away."""
        self.designer.menu_bar.setParent(None)
        self.designer.status_strip.setParent(None)
        self.designer.setParent(None)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.host.set_designer_detached(False)
        super().closeEvent(event)
```

In `main.py`:

```python
    def set_designer_detached(self, detached: bool) -> None:
        """Move the Designer bundle between the mode holders and a floating shell."""
        designer = self._ensure_designer()
        if detached == (self._shell is not None):
            return
        if detached:
            from .shell import DesignerShell

            DesignerShell.teardown_workspace_control()
            self._shell = DesignerShell(self, designer)
            self._shell.show_tool()
            self.mode_bar.setCurrentIndex(TRIGGER_MODE)
        else:
            shell, self._shell = self._shell, None   # first, so the shell's
            shell.release()                          # closeEvent is a no-op
            self._host_designer()
            shell.close()
            self.mode_bar.setCurrentIndex(DESIGNER_MODE)
        designer.detach_action.setChecked(detached)
        self._apply_shortcut_rule()
```

The shortcut rule learns the one exception — a detached menu bar is in another window, so nothing collides:

```python
        for mode, bar in self._mode_menus.items():
            enabled = mode == self._active_mode
            if mode == DESIGNER_MODE and self._shell is not None:
                enabled = True
```

And `_activate_mode` bounces off the Designer tab while detached — replace the `_ensure_designer()` line added in Task 4 with:

```python
        if index == DESIGNER_MODE:
            self._ensure_designer()
            if self._shell is not None:
                self._shell.raise_()
                self.mode_bar.setCurrentIndex(self._active_mode)
                return
```

`closeEvent` closes the shell with the window — add before the teardown call:

```python
        if self._shell is not None:
            self.set_designer_detached(False)
```

- [ ] **Step 4: Run the whole UI suite**

Expected: green.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/ui/shell.py src/python/tik/trigger/ui/main.py tests/ui/test_pipeline_ui.py
git commit -m "feat(tik.trigger): tear the Guide Designer off into its own window"
```

---

### Task 6: Documentation

**Files:**
- Modify: `CLAUDE.md` (tik.trigger status paragraph)
- Modify: `src/python/tik/trigger/ui/designer/window.py` (module docstring — it still says "dockable tool window")

- [ ] **Step 1: Update the docstring**

`designer/window.py`'s first line reads "Guide Designer: dockable tool window — modules · tree · graph · properties." Change it to "Guide Designer: a mode of the Trigger window — modules · tree · graph · properties." and add a sentence noting the page/host split and the tear-off.

- [ ] **Step 2: Update `CLAUDE.md`**

In the tik.trigger status line, replace "Guide Designer with two-way binding" with "Guide Designer as a mode tab of the pipeline UI (tear-off supported), two-way binding", and add the new spec to the design-specs list.

- [ ] **Step 3: Full verification**

Run the whole UI suite and confirm the count: 47 baseline + 6 new = **53 passed**. Then run the unit suite (`mayapy tests/unit/invoke.py`) to prove the import-boundary test still holds.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md src/python/tik/trigger/ui/designer/window.py
git commit -m "docs(tik.trigger): the Guide Designer is a mode, not a window"
```

## Self-Review

**Spec coverage:** §3 page bundles → Task 3; §3 `StatusFields` → Task 1; §4 laziness + `designer_factory` → Task 4; §5 page conversion → Task 2; §6 tear-off → Task 5; §7 entry points + shortcut rule → Tasks 3-5; §8 testing → every task's Step 1; §9 docs → Task 6. The memory-file correction in §9 is not a repo file and is handled outside the plan.

**Placeholders:** none — every step carries the code it needs.

**Type consistency:** `menu_bar`, `status_strip`, `title`, `title_changed`, `detach_requested`, `detach_action`, `teardown()` are defined in Task 2 and used under those exact names in Tasks 3-5. `add_mode`, `_activate_mode`, `_apply_shortcut_rule`, `_mode_menus`, `_holder`, `_iter_actions` are defined in Task 3; `_ensure_designer`, `_host_designer`, `designer_factory`, `designer_page_holder` in Task 4; `DesignerShell.release()` in Task 5.

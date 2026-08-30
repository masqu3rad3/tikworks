# Guide Designer as a Mode Tab — Design Spec

Date: 2026-08-30
Status: brainstormed with Arda Kutlu; approved in chat, implementing directly.
Revises `2026-08-29-trigger-ui-v3-and-io-graph-design.md`, which put the Guide
Designer in its own dockable window. The module I/O model, the graph, and the
`.trg` format are untouched.

## 1. Goal

Guides are what you reach for when you want to mock something up fast, and the
Designer being a second floating window taxes exactly that: every glance at the
session means finding another window. Old trigger's guides section was more
practical for this reason alone.

So: host the Guide Designer inside the Trigger window as a **mode**, selected by
a tab bar that sits *above* the menu bar, so the menus and the status fields
change with the mode.

```
┌──────────────────────────────────────────┐
│ Trigger │ Guide Designer                 │  ← mode bar   (QTabBar)
├──────────────────────────────────────────┤
│ File  Edit  Session  Tools  Help         │  ← per-mode   (QMenuBar stack)
├──────────────────────────────────────────┤
│ untitled │ biped.tr │                    │  ← sessions   (unchanged)
│                content                   │
├──────────────────────────────────────────┤
│ Ready                 3 module(s) · 2 …  │  ← per-mode   (strip stack)
└──────────────────────────────────────────┘
```

**Out of scope**, deliberately: the `.trg` round-trip, how a session picks up
guides, and what `Build all` does. The friction being fixed is the window split
and nothing else.

## 2. What forces the design

`GuideDesigner` and `TriggerWindow` each own three window-level things:

| Thing | `TriggerWindow` | `GuideDesigner` |
|---|---|---|
| menu bar | `self.menuBar()` (`main.py:70`) | `self.menuBar()` (`designer/window.py:238`) |
| status bar | `StatusFields(self.statusBar(), …)` (`main.py:120`) | same (`designer/window.py:316`) |
| content | `setCentralWidget(self.tabs)` (`main.py:52`) | `setCentralWidget(self.splitter)` (`designer/window.py:202`) |

Hosting one inside the other means deciding who owns the menu bar and the status
bar — and that decision also decides how hard the tear-off is.

Two approaches were rejected:

- **Nested `QMainWindow`** (drop the Designer, unchanged, into the stack). Almost
  no churn: each mode keeps its own menu bar and status bar, and popping one out
  is `setParent(None); show()`. Rejected here because Trigger's menus would sit on
  the host bar while the Designer's sat *inside* the page. **Weak reason, and
  half wrong** (noted 2026-08-31): a nested menu bar spans the page, the page
  spans the window, so the two rows land in the same place — which is what Arda's
  hand-built version showed. This shape remains a legitimate alternative; the
  chosen one differs only in owning one menu bar and one status bar centrally.
- **Rebuild one shared bar per switch** (`bar.clear(); page.build_menus(bar)`).
  Smallest host, but the Designer keeps `QAction`s as attributes
  (`self.grid_action`, `self.snap_action`) and pushes them onto the graph widget
  with `addAction` (`designer/window.py:285-287`); rebuilding duplicates those and
  strands the old ones.

## 3. Page bundles

Every mode is a triple of plain widgets — **a `QMenuBar`, a content widget, a
status strip** — held in three parallel `QStackedWidget`s. Nothing is installed
with `setMenuBar()` or `setStatusBar()`, so Qt never takes ownership of a bundle
widget and never deletes one behind our back; that is what makes the tear-off in
section 6 a matter of reparenting.

`TriggerWindow._build_shell()`:

```python
self.mode_bar = QtWidgets.QTabBar()            # document mode, not closable
self.menu_stack = QtWidgets.QStackedWidget()
header = QtWidgets.QWidget()                   # VBox, 0 margins, 0 spacing
header.layout().addWidget(self.mode_bar)
header.layout().addWidget(self.menu_stack)
self.setMenuWidget(header)                     # tabs above the menus
self.pages = QtWidgets.QStackedWidget();  self.setCentralWidget(self.pages)
self.status_stack = QtWidgets.QStackedWidget()
self.statusBar().addWidget(self.status_stack, 1)
self.mode_bar.currentChanged.connect(self._activate_mode)
```

`add_mode(title, menu_bar, content, status_strip) -> int` appends one entry to
each stack so the indices stay in lockstep. `_activate_mode(index)` sets all
three stacks and refreshes the title.

`setMenuWidget` and `menuBar()` are mutually exclusive, so `TriggerWindow` stops
calling `self.menuBar()`: `_build_menus` builds into an explicit
`QtWidgets.QMenuBar()`, and `_build_status` builds into a strip widget. The log
dock stays a `QDockWidget` on the host and is visible in both modes — logging is
global.

**Shared-library change.** `StatusFields` (`tik/shared/ui/status.py`) today
requires a `QStatusBar`. It grows a second accepted host — a plain `QWidget`,
laid out as activity label + stretch + fields with separators — so each mode can
own a strip. `set()`, `text()` and `set_activity()` keep their signatures; no
call site changes. This is the only edit outside `tik/trigger/ui`, and it exists
so we do not have to nest a `QStatusBar` inside a `QStatusBar`.

## 4. Laziness

`GuideDesigner` constructs a `GuideScene`, which imports Maya, so it cannot be
built at window startup — `tests/ui` runs under `TIK_TESTS_NO_MAYA=1`.

The Designer mode therefore registers **at startup with empty containers** in all
three stacks; `_ensure_designer()` fills them on first activation. Tab indices
are stable from the first paint, and nothing Maya-flavoured runs until the tab is
clicked. `TriggerWindow` takes a `designer_factory` argument (default: construct
a real `GuideDesigner`) so `tests/ui` can inject one built on `StubScene`. This
is the only new seam in the public surface.

## 5. `GuideDesigner` becomes a page

`class GuideDesigner(DesignerCommands, DesignerProperties, QtWidgets.QWidget)`,
same constructor signature. The mixins in `designer/commands.py` and
`designer/properties.py` need no changes — neither touches `menuBar`,
`statusBar`, or any window API.

- `_build_central` (`:202`): `setCentralWidget(self.splitter)` becomes a
  zero-margin `QVBoxLayout` on `self`.
- `_build_menus` (`:238`): `bar = self.menuBar()` becomes
  `self.menu_bar = QtWidgets.QMenuBar(self)`. `File > Close` is dropped —
  closing is the host's `Ctrl+W`, and dropping it removes one collision.
- `_build_status` (`:316`): `StatusFields(self.status_strip, …)`.
- `set_file` (`:347`): stops calling `setWindowTitle`, emits `title_changed(str)`.
  The host retitles the mode tab (`Guide Designer — biped.trg`) and, when
  detached, the shell.
- Teardown: a non-top-level `QWidget` never receives `closeEvent`, so the
  bindings/watcher cleanup at `:618` moves into `teardown()`, called by the
  host's `closeEvent` and by the surviving `closeEvent` (which still fires when
  the page is shown as its own window, as the tests do). The `destroyed` to
  `watcher.uninstall()` net at `:97` stays. `setObjectName("TriggerGuideDesigner")`
  is kept: `SceneWatcher` calls `objectName()` to detect a dead C++ object
  (`scene_watcher.py:125`).

`WINDOW_NAME`, `show_tool` and the workspace-control teardown leave the class —
they move to the shell in section 6.

## 6. Tear-off

Default is the tab. **Double-clicking the Designer's mode tab** tears it off —
the gesture people expect from a tab — and `View > Open in Window` (checkable, no
shortcut) is the discoverable menu route to the same thing.

```python
class DesignerShell(QtWidgets.QMainWindow):   # plain, floating, parented to the host
```

Its central widget is a `QVBoxLayout` of `[page.menu_bar, page, page.status_strip]`
— the same visual stack the host gives it, minus the mode bar. Detach reparents
those three out of the host's stacks; re-attach puts them back.

**Not a `MayaToolWindow`** (corrected 2026-08-31). It was one, and showing it
handed the widget to a Maya workspace control, which reparents it — the bundle
came apart into three top-level windows: one with the menus and status bar, one
with the content, and the shell. A plain `QMainWindow` with the `Qt.Window` flag,
parented to the Trigger window, holds the bundle correctly and follows its host.
The cost is that a detached Designer floats above Maya instead of docking into
Maya's layout, which is the right trade for a tear-off nobody uses daily.

**Not drag-off.** Tearing a tab out by dragging it, the way Maya's own panels
work, would mean making the modes `QDockWidget`s and tabifying them. Qt then owns
the tab bar and puts it *inside* the central area — below the menu bar — which
undoes the layout this whole spec exists to get. Double-click is the gesture.

Two rules keep it honest: while detached the Designer **mode tab stays**, and
selecting it raises the shell rather than switching to an empty page; and the
shell's `closeEvent` re-attaches rather than destroys, so the scene watcher,
bindings and graph state survive.

## 7. Entry points and the shortcut rule

`open_guide_designer(guides_path="")` keeps its name and signature, so both
callers are untouched — `Tools > Guide Designer` / `Ctrl+G` (`main.py:106`) and
`view.open_guides_requested` from the settings panel (`main.py:161`). Its body
becomes: ensure the Designer exists, `set_file(path)` when given, select the mode
tab (or raise the shell). `self._guide_designer` stays the single instance it is
today.

**Shortcuts need no rule at all — corrected 2026-08-31.** The two bars do bind
the same keys (`Ctrl+B`, `Ctrl+S`, `Ctrl+O`, `Ctrl+N`, `Ctrl+D`, `Ctrl+L`, `Tab`,
`F2`), and this spec originally called for disabling the inactive mode's actions
on every switch to keep Qt from resolving an ambiguous `WindowShortcut` by firing
*neither*. Measured in Maya, that ambiguity does not arise: a `WindowShortcut`
only matches while its action's widget is **visible**, and the inactive mode's
menu bar sits in a hidden stack page. `Ctrl+B` reaches the Trigger build in
Trigger mode and the Designer build in Designer mode with nothing disabled.

The same holds for the shape this spec rejected in section 2 (each mode a nested
`QMainWindow` in a `QTabWidget`) — measured too, same result. So the rule, its
`_iter_actions` walker, and the constraint it imposed ("no mode may disable an
individual menu action for its own reasons") are all gone. The Designer's
graph-scoped `Grid`/`Snap` actions (`WidgetWithChildrenShortcut`, added to the
graph widget) were never affected either way.

## 8. Testing

Everything here is Qt-only: `tests/ui`, `TIK_TESTS_NO_MAYA=1`, offscreen, via
`make tests-ui`. No Maya.

- `tests/ui/test_guide_designer.py` — the fixture keeps working (`QWidget.show()`
  makes it a window); `test_window_shell` changes `designer.menuBar()` to
  `designer.menu_bar`. That the other tests are untouched is the check that the
  refactor did not leak.
- `tests/ui/test_pipeline_ui.py` — new coverage: the mode bar has two tabs and
  starts on Trigger; activating a mode moves all three stacks together and leaves
  every action enabled (the inactive bar is hidden, which is what keeps the
  shortcuts apart); the Designer page stays empty until first activation;
  double-clicking the tab detaches and re-attaching leaves the menu bar in
  exactly one parent with the tree and graph intact; `open_guide_designer(path)`
  selects the mode and sets the file.
- `tests/ui/test_guide_designer.py` — `show_palette` opens the palette. `Tab` had
  been raising `NameError` since the file split in `9beab14`: `commands.py` calls
  `QtGui.QCursor.pos()` and imported only `QtWidgets`.

## 9. Documentation

`CLAUDE.md`'s tik.trigger status line calls the Designer a separate thing; it
becomes a mode of the pipeline UI. The `trigger-io-graph-decision` memory still
records "dockable windows" plural and gets the same correction.

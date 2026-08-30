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
  no churn, but Trigger's menus would render on the host bar while the Designer's
  render *inside* the page — two rows at two insets, and two status bars. It
  defeats the one menu row that changes, which is the point.
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
three stacks, applies the shortcut rule (section 7), and refreshes the title.

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

Default is the tab; `View > Open in Window` (checkable, no shortcut) detaches.

```python
class DesignerShell(MayaToolWindow):
    WINDOW_NAME = "TriggerGuideDesigner"   # inherits the old workspace control
```

Its central widget is a `QVBoxLayout` of `[page.menu_bar, page, page.status_strip]`
— the same visual stack the host gives it, minus the mode bar. Detach reparents
those three out of the host's stacks; re-attach puts them back.

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

**The shortcut rule: only the active mode's actions are enabled.**
`_activate_mode` walks `menu_bar.findChildren(QAction)` for every registered mode
and sets the enabled state. This is not cosmetic — the two bars collide on
`Ctrl+B`, `Ctrl+S`, `Ctrl+O`, `Ctrl+N`, `Ctrl+D`, `Ctrl+L`, `Tab` and `F2`, and
with both parented to one window Qt resolves an ambiguous `WindowShortcut` by
firing *neither*.

The constraint this imposes, recorded in the docstring: **no mode may disable an
individual menu action for its own reasons**, because a mode switch re-enables
everything. Nothing does today. The Designer's graph-scoped `Grid`/`Snap` actions
(`WidgetWithChildrenShortcut`, added to the graph widget) are unaffected.

## 8. Testing

Everything here is Qt-only: `tests/ui`, `TIK_TESTS_NO_MAYA=1`, offscreen, via
`make tests-ui`. No Maya.

- `tests/ui/test_guide_designer.py` — the fixture keeps working (`QWidget.show()`
  makes it a window); `test_window_shell` changes `designer.menuBar()` to
  `designer.menu_bar`. That the other tests are untouched is the check that the
  refactor did not leak.
- `tests/ui/test_pipeline_ui.py` — new coverage: the mode bar has two tabs and
  starts on Trigger; activating a mode moves all three stacks together; the
  Designer page stays empty until first activation; switching disables the
  inactive bar's actions and enables the active one; detach then re-attach leaves
  the menu bar in exactly one parent and the tree and graph intact;
  `open_guide_designer(path)` selects the mode and sets the file.

## 9. Documentation

`CLAUDE.md`'s tik.trigger status line calls the Designer a separate thing; it
becomes a mode of the pipeline UI. The `trigger-io-graph-decision` memory still
records "dockable windows" plural and gets the same correction.

The Trigger Window
==================

.. code-block:: python

   import tik.trigger.ui

   tik.trigger.ui.show()

A dockable Maya tool window. One menu bar sits **above** the session tabs, and
each session tab holds two sub-tabs — *Session* and *Guide Designer* — because
they are two views of one document.

.. code-block:: text

   ┌ menu bar ─────────────────────────────────────┐
   ├ [ hero.tr ] [ prop.tr ] [ + ] ────────────────┤   session tabs
   │ ┌ Session | Guide Designer ─────────────────┐ │   sub-tabs
   │ │                                           │ │
   │ └───────────────────────────────────────────┘ │
   ├ status strip ─────────────────────────────────┤
   └───────────────────────────────────────────────┘

The Session sub-tab
-------------------

Three panes in a splitter — the action shelf, the pipeline tree, and the
properties panel — over a build bar.

- Add an action from the tile shelf (click places it after the selection, drag
  places it anywhere, dropping onto a row nests it), or press **Tab** for the
  search palette (:kbd:`Enter` adds a sibling, :kbd:`Shift+Enter` a child).
- Referenced rows render inline and dimmed, with checkboxes. Editing one stores
  an override in *this* session; the referenced file is untouched.
- Versioned file fields are Nuke-style: green means latest, amber means older,
  and :kbd:`Alt+Up` / :kbd:`Alt+Down` step versions while hovering.
- The settings form is generated from the action's fields, so a new field shows
  up with no UI work.

The Guide Designer sub-tab
--------------------------

Four panes — modules, tree, node graph, properties — over a full-width action
bar. The tree and the graph are two views of the *same* connections.

.. note::
   The designer never parents guide joints into each other and never changes the
   Maya selection on its own. Use *Select guides* when you want the joints
   selected.

The action bar
~~~~~~~~~~~~~~

The bar's controls do not share a scope, and the layout makes that visible:

.. list-table::
   :header-rows: 1
   :widths: 16 40 44

   * - Group
     - Controls
     - Acts on
   * - ``SELECTION``
     - *Select guides* · *Mirror* · *Build selected*
     - the selected module(s)
   * - ``SCENE``
     - *Sync* · *Auto*
     - the Maya scene
   * - ``SESSION``
     - *Build all*
     - every module

The selection label answers "what will Mirror mirror?" — it shows the selected
module's display key (``L_arm``), ``2 modules`` when several are picked, and a
dimmed ``none`` when nothing is, which is also when the three selection buttons
are disabled.

Sync is explicit
~~~~~~~~~~~~~~~~

*Auto* governs one thing: whether a scene event may start a sync. With it off,
scene events only compute a read-only diff, and a drift pill reports how many
modules have changed — the document is not touched until *Sync* is pressed.

The *Auto* setting is a working preference. It persists per user in ``QSettings``
(``designer/auto_sync`` under ``tikworks/trigger``), never in the ``.tr``: a
session handed to a colleague does not carry your sync habits.

The graph
~~~~~~~~~

- :kbd:`Alt+MMB` pans, :kbd:`Alt+RMB` zooms about the press point, the wheel
  zooms under the pointer, :kbd:`F` fits.
- Drag output → input to connect; drag a plugged input away to unplug;
  :kbd:`Delete` disconnects selected wires; :kbd:`Ctrl` + drag **slices** every
  wire the line crosses.
- Nodes collapse like Maya's node editor: the ``≡`` glyph, or :kbd:`1` /
  :kbd:`2` / :kbd:`3` for header only / connected plugs / everything.
- **Scene Nodes** is a group of arbitrary Maya nodes exposed as outputs — one
  group with ten outputs or ten groups with one. Right-click an input field for
  a menu of every other module and its outputs, plus the scene nodes by group.

Selecting several modules of one type edits them together (the panel says so);
a mixed selection shows nothing.

Menus
-----

.. list-table::
   :header-rows: 1
   :widths: 14 86

   * - Menu
     - Contents
   * - **File**
     - New / Open / Open Recent, Save (:kbd:`Ctrl+S`), Save As, Increment
       Version (:kbd:`Ctrl+Alt+S`), Import & Export Actions, Import & Export
       Guides, Close Tab, Quit.
   * - **Edit**
     - Undo (:kbd:`Ctrl+Z`) / Redo, Add… (:kbd:`Tab`), Add Child Action,
       Duplicate (:kbd:`Ctrl+D`), Rename (:kbd:`F2`), Delete,
       Enable/Disable (:kbd:`Ctrl+E`).
   * - **Session**
     - Build Rig (:kbd:`Ctrl+B`), Build Until Here (:kbd:`Ctrl+Shift+B`),
       Run Step (:kbd:`Ctrl+R`), Validate, Clear Statuses.
   * - **Guides**
     - Add Module, Add Scene Nodes, Select Root / All Guides, Mirror
       (:kbd:`Ctrl+M`), Connect Input, Disconnect Primary Input, Sever
       Connections (:kbd:`Ctrl+Shift+D`), Build Selected / All Guides, the
       scene-boundary group (below), Clear Scene Guides, and a Layout submenu
       (Auto Layout :kbd:`Ctrl+L`, Fit :kbd:`F`, collapse modes, Redraw Views
       :kbd:`F5`).
   * - **Tools**
     - Guide Designer (:kbd:`Ctrl+G`), Show Action Shelf, Show Log, Settings.
   * - **Help**
     - Documentation, About.

.. note::
   ``Ctrl+S`` saves the *session*, guides included. A ``.trg`` is a guide
   library now, not the session's document, so exporting one has no save
   shortcut.

The scene-boundary group
~~~~~~~~~~~~~~~~~~~~~~~~

Four verbs cross the session/scene line, and they are kept together so their
directions can be read side by side:

.. list-table::
   :header-rows: 1
   :widths: 34 22 44

   * - Command
     - Direction
     - Effect
   * - **Sync From Scene** (:kbd:`F6`)
     - scene → session
     - Capture, reconcile, redraw what is structurally stale.
   * - **Auto Sync**
     - —
     - Whether a scene event may start that sync.
   * - **Snapshot Guides From Scene…**
     - scene → session
     - Rebuild the module list from the guides in the scene. Shows a report
       before it replaces anything.
   * - **Clear Scene Guides**
     - session → scene
     - Remove the rendering. The document keeps the modules.

.. warning::
   *Redraw Views* (:kbd:`F5`, in Layout) redraws the UI from the document.
   *Sync From Scene* runs the other way. Two neighbouring commands that both
   read as "update" is exactly the ambiguity the split exists to remove.

Undo
----

:kbd:`Ctrl+Z` in the Trigger window undoes *Trigger* actions — everything
structural, in both sub-tabs, off the session's own stack. Moving a guide in the
viewport is a scene edit and undoes with Maya's :kbd:`Ctrl+Z`.

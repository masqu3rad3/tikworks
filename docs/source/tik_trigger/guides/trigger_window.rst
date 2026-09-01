The Trigger window
==================

.. code-block:: python

   import tik.trigger.ui
   tik.trigger.ui.show()          # show(dockable=False) for a floating window

A dockable Maya tool window. One menu bar sits above a row of **session tabs**,
one per open ``.tr``. Each session tab holds two **sub-tabs**, *Session* and
*Guide Designer*, because they are two views of one document: the pipeline and
the guides of the same rig.

.. figure:: /_static/screenshots/trigger_window_session.png
   :class: screenshot
   :alt: The Trigger window on the Session sub-tab

   The Session sub-tab of ``hero_v002.tr``. The action shelf, the pipeline with a
   referenced ``baseRig.tr`` expanded inline, and the settings of the selected
   ``build_rig`` step.

.. code-block:: text

   ┌ File  Edit  Session  Guides  Tools  Help ──────────────────┐   menu bar
   ├ [ hero_v002.tr ] [ prop.tr ] ──────────────────────────────┤   session tabs
   │ ┌ Session │ Guide Designer ────────────────────────────────┐│   sub-tabs
   │ │  shelf  │  pipeline                    │  properties     ││
   │ ├─────────┴──────────────────────────────┴─────────────────┤│
   │ │ ▶ Build rig   Build until here   Build & Publish   ═════ ││   build bar
   ├ 1 reference(s) · latest · Maya 2026 · tik.trigger 0.2.0 ───┤   status strip
   └─────────────────────────────────────────────────────────────┘

The Session sub-tab
-------------------

Three panes in a splitter over a build bar.

**The action shelf** (left) shows one tile per registered action, grouped by
category. Click a tile to add that action after the current selection; drag it
into the pipeline to place it anywhere, and drop it onto a row to nest it under
that row. :kbd:`Ctrl+Shift+A` hides the shelf when you know the actions by name.

**The pipeline** (middle) is the action tree. Each row shows a status dot, the
type icon, the name and a short summary (the file an import points at, for
instance). Checkboxes enable and disable steps. Rows can be reordered and nested
by drag and drop. Press :kbd:`Tab` for the search palette:

.. figure:: /_static/screenshots/search_palette.png
   :class: screenshot
   :alt: The action search palette

   Type to filter. :kbd:`Enter` adds the action after the selection,
   :kbd:`Shift+Enter` adds it as a child.

**The properties panel** (right) is the form for the selected action, generated
from its fields. A new field on an action shows up here with no UI work. Folds
(*Build Options*, *Scope*) group related settings; the ``?`` button shows the
action's description. Two buttons at the bottom run the step on its own or run
the pipeline up to it.

**The build bar** runs the whole session (*Build rig*, :kbd:`Ctrl+B`), or up to
the selected step (*Build until here*, :kbd:`Ctrl+Shift+B`), with a progress bar
and a step counter. Row status dots turn amber while a step runs, green when it
passed, red when it failed; *Session → Clear Statuses* resets them.

References
~~~~~~~~~~

A ``reference`` action expands the actions of another ``.tr`` inline, drawn
dimmed and italic with a link glyph. You can toggle and edit them like your own
rows, and each edit is stored as an **override in this session**. The referenced
file is never written. In the screenshot above, ``head_rotation`` is unticked in
``hero_v002.tr`` while ``baseRig.tr`` still has it on.

You cannot add a new action inside a reference; open the referenced session and
add it there. The reference's *version* field (``latest``, ``pinned`` or an
explicit ``v003``) decides which file on disk is expanded, and the status strip
shows how many references the session has and whether the current one is the
latest.

Versioned file fields
~~~~~~~~~~~~~~~~~~~~~

File fields for versioned paths (``name_v###.ext``) carry a state pill.

.. figure:: /_static/screenshots/versioned_file_field.png
   :class: screenshot
   :alt: Three versioned file fields in the latest, older and missing states

   Green: this is the newest version on disk. Amber: a newer one exists. Red:
   the file is missing.

Hover a versioned field and press :kbd:`Alt+Up` or :kbd:`Alt+Down` to step
through the versions that exist next to it.

The Guide Designer sub-tab
--------------------------

The guides side of the same session: :doc:`guide_designer` covers it in full.

Menus and shortcuts
-------------------

.. list-table::
   :header-rows: 1
   :widths: 14 86

   * - Menu
     - Contents
   * - **File**
     - New Session (:kbd:`Ctrl+N`), Open… (:kbd:`Ctrl+O`), Open Recent, Save
       (:kbd:`Ctrl+S`), Save As… (:kbd:`Ctrl+Shift+S`), Increment Version
       (:kbd:`Ctrl+Alt+S`), Import / Export Actions…, Import / Export Guides…,
       Close Tab (:kbd:`Ctrl+W`), Quit (:kbd:`Ctrl+Q`).
   * - **Edit**
     - Undo (:kbd:`Ctrl+Z`), Redo (:kbd:`Ctrl+Y`), Add… (:kbd:`Tab`), Add Child
       Action…, Duplicate (:kbd:`Ctrl+D`), Rename (:kbd:`F2`), Delete
       (:kbd:`Del`), Enable / Disable (:kbd:`Ctrl+E`). One Edit menu serves both
       sub-tabs: the verbs act on whichever view is in front.
   * - **Session**
     - Build Rig (:kbd:`Ctrl+B`), Build Until Here (:kbd:`Ctrl+Shift+B`), Run
       Step (:kbd:`Ctrl+R`), Validate, Clear Statuses.
   * - **Guides**
     - Add Module…, Add Scene Nodes, Select Root, Select All Guides, Mirror
       (:kbd:`Ctrl+M`), Connect Input…, Disconnect Primary Input, Sever
       Connections (:kbd:`Ctrl+Shift+D`), Build Selected Guides, Build All
       Guides, Sync From Scene (:kbd:`F6`), Auto Sync, Snapshot Guides From
       Scene…, Clear Scene Guides, and a *Layout* submenu: Auto Layout
       (:kbd:`Ctrl+L`), Fit Graph (:kbd:`F`), the three collapse modes
       (:kbd:`1` :kbd:`2` :kbd:`3`), Redraw Views (:kbd:`F5`).
   * - **Tools**
     - Guide Designer (:kbd:`Ctrl+G`), Show Action Shelf (:kbd:`Ctrl+Shift+A`),
       Show Log, Settings…
   * - **Help**
     - Documentation, About Trigger.

.. note::

   :kbd:`Ctrl+S` saves the *session*, guides included. A ``.trg`` is a guide
   library, not this session's document, so exporting one has no shortcut; it
   lives under *File → Export Guides…*.

Saving and versions
-------------------

*Save* writes the ``.tr`` after capturing the guide poses from the scene, so a
saved file never lags the viewport. *Increment Version* saves to the next
``_v###`` number next to the current file and switches the tab to it. Closing a
tab with unsaved changes asks first.

Switching tabs
--------------

The Maya scene holds one session's guides at a time. Switching to another
session tab captures the outgoing session's guides, clears the rendering, and
draws the incoming session's guides: a deliberate hand-over. If the scene's
guides belong to a session that is not open in the window, the checkout is
refused and reported on the status strip rather than silently overwriting them.

Undo
----

:kbd:`Ctrl+Z` in the Trigger window undoes *Trigger* edits, structural changes in
both sub-tabs, off the session's own stack. Moving a guide in the viewport is a
scene edit and undoes with Maya's :kbd:`Ctrl+Z`. :doc:`../concepts` explains why
there are two.

Settings
--------

*Tools → Settings…* edits the user settings stored in
``tik_trigger_settings.json`` (recent sessions, mirror mapping, auto-save).
The Guide Designer's *Auto* sync toggle is a per-user working preference too, but
it is kept in ``QSettings`` under ``tikworks/trigger``, never in the ``.tr``: a
session handed to a colleague does not carry your sync habits.

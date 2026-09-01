The Guide Designer
==================

The Guide Designer is the second sub-tab of every session: where modules are
added, connected and configured, and where the guides in the scene are kept in
step with the session. Open it with the sub-tab or :kbd:`Ctrl+G`.

.. figure:: /_static/screenshots/trigger_window_designer.png
   :class: screenshot
   :alt: The Guide Designer with several modules

   Four panes over the action bar. ``L_arm`` is selected: its row in the tree,
   its node in the graph and its properties on the right all show the same
   module.

Four panes
----------

**Modules** (far left). *Side* decides which side new modules get: ``L``, ``R``,
``C``, ``Both`` (creates a left and a right at once) or ``Auto`` (the side of the
selected module, or left). Below it, one tile per registered module type,
grouped by category, plus *Scene* for a scene-nodes group. Click a tile to add a
module; if a module is selected at that moment, the new one's primary input is
pre-filled with the selected module's first output.

**Tree** (left). Every module instance, nested under whatever feeds its primary
input. Columns: name, type (with the guide count for multi-guide modules), side
and primary source. Dragging a row onto another sets its primary input. The
filter bar above it narrows the list by keyword; :kbd:`Enter` keeps a keyword as
a pill so several can be combined.

**Graph** (middle). The same connections as the tree, as a node graph: inputs on
the left of a node, outputs on the right, the primary connection drawn in the
accent colour. Scene-node groups are dashed nodes with one output per Maya node.

**Properties** (right). The selected module's name, side and type; its
*inputs*, one row each, with a source field, a pick-from-selection button and a
clear button; and *module*, the settings form generated from the module's
fields. Selecting several modules of one type edits them together (the panel
says so); a mixed selection shows nothing.

.. figure:: /_static/screenshots/form_builder_arm.png
   :class: screenshot
   :alt: The generated settings form of the arm module

   The arm's settings form. Every fold is a ``FieldGroup`` declared in the
   module; every row is a ``Field``.

The graph
---------

- **Navigate**: :kbd:`Alt` + middle drag pans, :kbd:`Alt` + right drag zooms
  about the press point, the wheel zooms under the pointer, :kbd:`F` fits
  everything.
- **Connect**: drag from an output port to an input port. Drag a connected input
  port away to unplug it, then drop on another input to re-plug or on empty space
  to disconnect. Select wires and press :kbd:`Delete` to disconnect them.
  :kbd:`Ctrl` + left drag draws a slice line; every wire it crosses is
  disconnected.
- **Collapse**: :kbd:`1` header only, :kbd:`2` connected plugs, :kbd:`3`
  everything, on the selected nodes, or click the ``≡`` glyph in a node header.
- **Right-click an input field** in the properties panel for a menu of every
  other module's outputs plus the scene nodes by group.
- **Layout** is stored with the session (node positions, collapse modes, groups),
  so the graph looks the same when the file is reopened. *Auto Layout*
  (:kbd:`Ctrl+L`) rearranges producers to the left of consumers.

Scene nodes
~~~~~~~~~~~

A *Scene Nodes* group exposes arbitrary Maya nodes as outputs, so a module can
hang off a locator or a joint that is not part of any module. Add one with the
*Scene* tile (the current Maya selection fills it), rename it in the properties
panel, and edit its node list there. One group with ten outputs or ten groups
with one, whichever reads better. Nodes that do not exist in the scene are
flagged in the node header.

The action bar
--------------

The bar at the bottom groups its controls by what they act on, and the layout
makes that visible.

.. figure:: /_static/screenshots/designer_action_bar.png
   :class: screenshot
   :alt: The Guide Designer action bar with L_arm selected

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

The selection label answers "what will *Mirror* mirror?". It shows the selected
module's key (``L_arm``), ``2 modules`` when several are picked, and a dimmed
``none`` when nothing is, which is also when the three selection buttons are
disabled.

*Select guides* selects the module's joints in Maya; the designer never changes
the Maya selection on its own. *Mirror* creates the opposite-side copy, or
updates it if it already exists, with poses mirrored across YZ and connections
rewired to their opposite-side equivalents. *Build selected* and *Build all* run
a **test build**: the same builder the ``kinematics`` action uses, but the guides
stay in the scene afterwards so you can keep adjusting.

Sync, and the Auto toggle
~~~~~~~~~~~~~~~~~~~~~~~~~

*Sync* (also :kbd:`F6`, *Sync From Scene*) runs the lockstep described in
:doc:`../concepts`: capture the poses from the scene, reconcile the document
against what is drawn, redraw whatever is structurally stale.

*Auto* governs exactly one thing: whether a **scene event** (a node created, a
scene opened, an undo) may start that sync on its own. With *Auto* off, scene
events only compute a read-only diff, and a drift pill reports how many modules
differ from the scene until you press *Sync*.

.. figure:: /_static/screenshots/designer_action_bar_drift.png
   :class: screenshot
   :alt: The action bar with Auto off and two modules changed

   Auto off, two modules selected, two modules waiting to be synced.

*Auto* does **not** gate the capture that precedes every structural edit. Change
a setting, rename or connect something, and the scene's poses are read into the
document before the module is redrawn, whatever the toggle says. Otherwise
editing any property would throw away the posing you just did.

Snapshot from scene
~~~~~~~~~~~~~~~~~~~

*Guides → Snapshot Guides From Scene…* goes the other way from *Sync*: it reads
the guide joints in the scene and **rebuilds the session's module list** from
them. It exists for the scene whose ``.tr`` was never saved, or a Maya file you
received from someone else: the joints are right there, tagged, and this is how
the tool gets them back. Replacing the module list is destructive, so a report
comes first.

.. figure:: /_static/screenshots/snapshot_dialog.png
   :class: screenshot
   :alt: The snapshot report dialog

   What the snapshot found, what it could not bring back, and the button that
   commits it. Nothing is changed until you press it.

Guide joints carry their full module entry, so a snapshot of a scene drawn by
this tool is lossless. Joints from an older scene without that entry come back
with the type's default name and settings and no connections; the report says
which.

The scene-boundary commands
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Four verbs in the *Guides* menu cross the line between the session and the
scene. They sit together so their directions can be read side by side.

.. list-table::
   :header-rows: 1
   :widths: 34 20 46

   * - Command
     - Direction
     - Effect
   * - **Sync From Scene** (:kbd:`F6`)
     - scene → session
     - Capture poses, reconcile, redraw what is structurally stale.
   * - **Auto Sync**
     - —
     - Whether a scene event may start that sync.
   * - **Snapshot Guides From Scene…**
     - scene → session
     - Rebuild the module list from the guides in the scene, after a report.
   * - **Clear Scene Guides**
     - session → scene
     - Remove the rendering. The document keeps every module.

.. warning::

   *Redraw Views* (:kbd:`F5`, in the *Layout* submenu) redraws the **UI** from
   the document. *Sync From Scene* runs the other way. Two neighbouring commands
   that both read as "refresh" is exactly the ambiguity the split removes.

After a build
-------------

A build may hide or delete the guides (the ``kinematics`` action's
``after_build`` setting: ``keep``, ``hide`` or ``delete``). The session records
that as deliberate, so the next sync does not treat the missing rendering as
damage and draw everything straight back; the status line reads *guides not
drawn (cleared by a build)* instead. Opening the Guide Designer sub-tab again is
the request to see them: it redraws the guides from the document. Adding a
module does the same, since authoring guides means showing them.

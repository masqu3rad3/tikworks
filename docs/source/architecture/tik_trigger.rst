tik.trigger
===========

Purpose
-------
A rigging and automation framework for Maya.

What lives here
---------------

- Rig blueprints
- Rig components
- Behavioral rules and relationships
- Automation graphs
- Abstractions over Maya mechanics
- Authoring and execution logic for rigs

This is not a utility layer. This is a system.

Rules
-----

- May depend on ``tik.maya``
- May depend on ``tik.shared``
- May use Qt for authoring, debugging, and visualization
- Must not leak its concepts downward
- Must not be required for basic Maya usage

Mental model
------------

``A rigging language and framework.`` This is intent, structure, and meaning, not infrastructure.

Status
------

The ``tik.trigger`` package currently contains a placeholder module; implementation work is pending. This page captures the intended boundaries until concrete APIs land.

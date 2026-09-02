"""Policy-bearing rig sub-assemblies.

A *system* composes ``tik.maya`` constructs **and** creates controllers, naming
the animator-facing attributes. Mechanism belongs one layer down in
``tik.maya``; a construct there never creates a controller, names a user-facing
attribute, or encodes a side convention.

Layer escalation::

    nodes -> types -> roles -> constructs -> systems -> modules

Modules compose systems. Modules never inherit from other modules: their
``guides``, ``inputs``, ``outputs`` and ``Field`` objects are class attributes
read by the registry and the UI form builder, so shared behaviour lives here
instead.
"""

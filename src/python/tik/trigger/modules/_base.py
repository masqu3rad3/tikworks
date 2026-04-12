"""Base template for trigger modules.

This module provides a template for creating new modules. Each module requires:
1. A RigModule subclass that combines guide creation and rig building
2. Apply @register_module("module_name") decorator
3. Implement all abstract methods for guide phase and build pipeline

The module folder structure should be:
    my_module/
    ├── my_module.py      # Contains the RigModule subclass
    ├── ui_definition.json  # (optional) UI settings
    └── data.json         # (optional) Module-specific data

Example:
    from tik.trigger.core import RigModule, register_module

    @register_module("my_module")
    class MyModule(RigModule):
        _module_name = "my_module"

        # Guide Phase
        def _create_guides_impl(self):
            # Create Maya guide nodes based on self._guides
            pass

        def _update_guide_impl(self, index, guide_data):
            # Update guide position/rotation in scene
            pass

        def _delete_guides_impl(self):
            # Remove guide nodes from scene
            pass

        def _get_guide_data_impl(self):
            # Query current guide positions from scene
            return self._guides.copy()

        # Build Pipeline
        def _pre_build(self):
            # Prepare data from guides
            pass

        def _create_groups_impl(self):
            # Create essential rig groups
            pass

        def _create_joints_impl(self):
            # Create deformation joints
            pass

        def _create_controllers_impl(self):
            # Create control objects
            pass

        def _create_setup_impl(self):
            # Create IK/FK/setup connections
            pass

        def _finalize_impl(self):
            # Finalize visibility and constraints
            pass

        def _delete_impl(self):
            # Remove built rig from scene
            pass

        def _mirror_impl(self, source_guide_names):
            # Mirror the rig from source guides
            pass

        def _define_connectors(self):
            # Define plugs and sockets after joint creation
            # e.g., self._connectors.plugs["rootPlug"] = Plug(name="rootPlug", joint_name="root_jnt")
            pass
"""

from __future__ import annotations

from tik.trigger.core.module_core import GuidesCore, ModuleCore
from tik.trigger.core.rig_module import RigModule

# Re-export for backward compatibility and convenience
__all__ = ["RigModule", "GuidesCore", "ModuleCore"]
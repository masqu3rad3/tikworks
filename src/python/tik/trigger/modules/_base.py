"""Base template for trigger modules.

This module provides a template for creating new modules. Each module requires:
1. A GuidesCore subclass for guide creation/manipulation
2. A ModuleCore subclass for rig building
3. Both should apply @register_module("module_name") decorator

The module folder structure should be:
    my_module/
    ├── my_module.py      # Contains both Guide and Module classes
    ├── ui_definition.json  # (optional) UI settings
    └── data.json         # (optional) Module-specific data

Example:
    from tik.trigger.core import GuidesCore, ModuleCore, register_module

    @register_module("my_module")
    class MyModuleGuide(GuidesCore):
        _module_name = "my_module"

        def create_guides(self):
            # Create Maya guide nodes
            pass

        def update_guide(self, index, guide_data):
            # Update guide position/rotation
            pass

        def delete_guides(self):
            # Remove guide nodes from scene
            pass

    @register_module("my_module")
    class MyModule(ModuleCore):
        _module_name = "my_module"
        _guide_class = MyModuleGuide

        def build(self):
            # Build rig from guides
            pass

        def delete(self):
            # Remove built rig
            pass

        def mirror(self, source_guide_names):
            # Mirror the rig
            pass
"""

from __future__ import annotations

from tik.trigger.core.module_core import GuidesCore, ModuleCore

# Re-export for convenience
__all__ = ["GuidesCore", "ModuleCore"]

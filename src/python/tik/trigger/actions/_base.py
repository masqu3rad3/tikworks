"""Base template for trigger actions.

This module provides a template for creating new actions. Each action should:
1. Inherit from ActionCore
2. Apply the @register_action("action_name") decorator
3. Implement the feed() and action() abstract methods
4. Provide ui_definition.json and defaults.json in the action folder

Example folder structure:
    actions/
    └── my_action/
        ├── my_action.py      # Must match folder name
        ├── ui_definition.json  # UI definitions (SOLE SOURCE)
        └── defaults.json       # Default values

Example action class:
    from tik.trigger.core import ActionCore, register_action

    @register_action("my_action")
    class MyAction(ActionCore):
        _defaults = {"radius": 1.0}

        def feed(self, selection):
            # Validate selection and return feed data
            return {"selection": selection}

        def action(self, feed_data):
            # Perform the actual Maya operation
            pass
"""

from __future__ import annotations

from tik.trigger.core.action_core import ActionCore

# Re-export for convenience
__all__ = ["ActionCore"]

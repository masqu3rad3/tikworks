"""Factory default settings for tik.trigger.

This module defines the FACTORY_DEFAULTS dictionary containing
immutable default values for all user-level settings.

Note: This should be kept in sync with defaults.json.
"""

from __future__ import annotations

FACTORY_DEFAULTS: dict = {
    "debug_mode": False,
    "external_editor": "",
    "mirror_mapping": {
        "L_*": "R_*",
        "*_L": "*_R",
    },
    "recent_sessions": [],
    "max_number_of_recent_sessions": 10,
    "auto_save": True,
    "auto_save_interval": 300,
    "default_units": {
        "linear": "cm",
        "angular": "deg",
    },
    "guide_display": {
        "size": 1.0,
        "color": [255, 200, 100],
        "selected_color": [100, 200, 255],
    },
    "rig_build": {
        "side_suffixes": ["L", "R", "C"],
        "center_prefix": "",
        "attribute_locking": True,
    },
}

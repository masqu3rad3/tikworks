"""Configuration settings for the Tik Polish tool.

This module defines factory defaults and creates a settings manager
for the Polish tool, including library paths and mirror mappings.
"""

from tik.shared.user_settings import SettingsManager

FACTORY_DEFAULTS = {
    "additional_library_paths": [],
    "mirror_mapping": {
        "L_*": "R_*",
        "Right *": "Left *",
        "*_L": "*_R",
        "* Right": "* Left",
    },
}

settings = SettingsManager("tik_polish_settings", FACTORY_DEFAULTS)

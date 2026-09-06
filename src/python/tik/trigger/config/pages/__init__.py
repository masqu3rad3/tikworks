"""Trigger's preference pages.

Importing this package is what registers them, so ``tik.trigger.config``
imports it inside its lazy factory rather than at module level.
"""

from tik.trigger.config.pages.files import FilesPrefs
from tik.trigger.config.pages.guides import GuidesPrefs
from tik.trigger.config.pages.interface import InterfacePrefs
from tik.trigger.config.pages.tools import ToolsPrefs

__all__ = ["FilesPrefs", "GuidesPrefs", "InterfacePrefs", "ToolsPrefs"]

"""Built-in rig modules. Importing this package discovers every module folder."""

from tik.trigger.core.discovery import discover

DISCOVERED = discover(__name__, __path__)

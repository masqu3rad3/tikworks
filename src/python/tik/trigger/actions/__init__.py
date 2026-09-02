"""Built-in actions. Importing this package discovers every action folder."""

from tik.trigger.core.discovery import discover

DISCOVERED = discover(__name__, __path__)

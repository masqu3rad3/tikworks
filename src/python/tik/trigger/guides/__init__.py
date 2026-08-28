"""Guides as an asset: ``.trg`` files and the live-scene ``Guides`` handler."""

from .format import EXTENSION, GuideFile, GuideInstance, legacy_table, legacy_type, make_record
from .handler import GuideHandle, Guides

__all__ = [
    "EXTENSION",
    "GuideFile",
    "GuideInstance",
    "GuideHandle",
    "Guides",
    "legacy_table",
    "legacy_type",
    "make_record",
]

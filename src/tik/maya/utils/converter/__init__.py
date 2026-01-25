"""
tik.maya bidirectional code converter.

A rule-based code conversion tool that translates between tik.maya
and maya.cmds through semantic expansion/lifting.

Directions:
- tik.maya → maya.cmds: Semantic expansion (convert)
- maya.cmds → tik.maya: Semantic lifting (convert_to_tik)
"""

# Forward direction: tik.maya → maya.cmds
from .engine import Converter, convert

# Reverse direction: maya.cmds → tik.maya
from .engine_reverse import ReverseConverter, convert_to_tik

# Shared reporting
from .report import ConversionEntry, ConversionReport

__all__ = [
    # Forward (tik → cmds)
    "Converter",
    "convert",
    # Reverse (cmds → tik)
    "ReverseConverter",
    "convert_to_tik",
    # Reporting
    "ConversionReport",
    "ConversionEntry",
]

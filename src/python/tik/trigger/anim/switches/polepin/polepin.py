"""Freeze the pole pin. Declared, not built.

See ``ikfk.py`` for why a placeholder is a declared class rather than a gap.
"""

from __future__ import annotations

from tik.trigger.anim.registry import register_switch
from tik.trigger.anim.switch import Switch


@register_switch("polepin")
class PolePinSwitch(Switch):
    """Reserved: locks the elbow to the pole control where it already is.

    Held across the switch: the elbow's world position.
    """

    label = "Pin"
    help = (
        "Will lock the elbow to the pole control at its current position, "
        "holding the elbow's world position."
    )
    order = 30
    available = False

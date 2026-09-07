"""Match and switch a limb between IK and FK. Declared, not built.

It exists now so the shell, the tab order and the registry are exercised by
something other than the one switch that works, and so the shape a future
implementation has to fill is written down rather than remembered.
"""

from __future__ import annotations

from tik.trigger.anim.registry import register_switch
from tik.trigger.anim.switch import Switch


@register_switch("ikfk")
class IkFkSwitch(Switch):
    """Reserved: matches the other chain to the pose on screen, then flips.

    Held across the switch: the limb's silhouette.
    """

    label = "IK / FK"
    help = (
        "Will match the other chain to the pose on screen and flip the blend, "
        "holding the limb's silhouette."
    )
    order = 20
    available = False

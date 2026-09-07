"""Which point a control turns about."""

from __future__ import annotations

from typing import Optional, Sequence

from tik.trigger.anim.registry import register_switch
from tik.trigger.anim.switch import Switch
from tik.trigger.maya import pivot as ops


@register_switch("pivot")
class PivotSwitch(Switch):
    """Snap a control's rotate pivot to one of its rigger-placed presets.

    Held across the switch: the control's world matrix. Everything the tab
    needs is on the control itself -- the ``pivotPreset`` enum and the hidden
    preset attributes the build wrote -- so it never consults a session.
    """

    label = "Pivot"
    help = "Which point the control turns about."
    order = 10

    def states(self, context) -> list[str]:
        """Presets every selected control has, in the first one's order.

        The intersection, not the union: offering a preset only some of the
        selection can reach would apply to some controls and silently skip the
        rest.
        """
        shared: Optional[list[str]] = None
        for control in context.controls:
            labels = ops.preset_labels(control.node)
            if not labels:
                return []
            if shared is None:
                shared = list(labels)
            else:
                shared = [item for item in shared if item in labels]
        return shared or []

    def current(self, context) -> Optional[str]:
        """The preset every selected control is on; None when they disagree."""
        seen = set()
        answer = None
        for control in context.controls:
            if not ops.preset_labels(control.node):
                return None
            answer = ops.current_preset(control.node)
            seen.add(answer)
        return answer if len(seen) == 1 else None

    def apply(self, context, state: str, *, key: bool, times: Sequence[float]) -> str:
        """Switch every selected control that has ``state``, holding each pose."""
        done = 0
        for control in context.controls:
            if state not in ops.preset_labels(control.node):
                continue
            ops.switch_pivot_preset(control.node, state, key=key, times=times)
            done += 1
        if not done:
            return f"No selected control has a '{state}' pivot"
        span = f" over {len(times)} keys" if len(times) > 1 else ""
        if done == 1:
            return f"Snapped to {state}{span} — pose held"
        return f"Snapped {done} controls to {state}{span} — pose held"

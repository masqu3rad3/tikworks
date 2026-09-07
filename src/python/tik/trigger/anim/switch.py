"""The tab contract: a named set of states you pick between."""

from __future__ import annotations

from typing import Optional, Sequence

from .context import SwitchContext


class Switch:
    """One tab in the Switches dock.

    A switch changes what a control *does*, and the pose survives it. Anything
    that cannot name what it promises not to disturb is not a switch and does
    not belong here.

    A subclass declares a label and overrides three methods; the shell owns the
    chips, the keying, the frame scope and the status line, so a new tab adds
    labels rather than a user interface.
    """

    label: str = ""
    help: str = ""
    order: int = 100
    #: False marks a switch that is declared but not built. The shell shows
    #: ``help`` under a "not built yet" line instead of an empty state picker,
    #: so a placeholder never reads as broken.
    available: bool = True

    switch_type: str = ""  # stamped by @register_switch
    icon: str = ""  # stamped by @register_switch

    @classmethod
    def display_label(cls) -> str:
        """The tab text (falls back to the registered type)."""
        return cls.label or cls.switch_type

    def states(self, context: SwitchContext) -> list[str]:
        """The states offered for ``context``. Empty means nothing to offer."""
        return []

    def current(self, context: SwitchContext) -> Optional[str]:
        """The state ``context`` is in; None when it has none or they disagree."""
        return None

    def apply(
        self,
        context: SwitchContext,
        state: str,
        *,
        key: bool,
        times: Sequence[float],
    ) -> str:
        """Switch ``context`` to ``state``; return one line for the status bar."""
        raise NotImplementedError

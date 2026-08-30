"""Context protocols handed to modules by a backend.

These are *interfaces*; the Maya implementation lives in
``tik.trigger.backends.maya.context``. Modules only ever talk to these.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Protocol, Sequence


@dataclass
class RigGroups:
    """The four groups created for every module instance, under ``limb``.

    ``socket`` holds input attach transforms driven by parent module outputs.
    ``control`` holds controllers and their offset/space groups, nothing else.
    ``rig`` holds the puppet: IK/FK chains, handles, math, helpers.
    ``bind`` holds deform/export joints only, and is empty when the module is
    connected to a parent (its joints are created in the parent's hierarchy).
    """

    limb: Any = None  # top group of the module
    socket: Any = None
    control: Any = None
    rig: Any = None
    bind: Any = None


class GuideContext(Protocol):
    """Given to ``Module.draw_guides``."""

    module: Any
    side: Any
    side_mult: int

    def joint(
        self,
        role: str,
        position: Sequence[float],
        *,
        index: int = 0,
        parent: Any = None,
        radius: float = 1.0,
    ) -> Any:
        """Create and tag a guide joint for ``role`` at world ``position``."""


class BuildContext(Protocol):
    """Given to ``Module.build``."""

    module: Any
    instance: Any
    side: Any
    side_mult: int
    groups: RigGroups
    rig_root: Any
    bind_parent: Any
    outputs: dict
    attachments: dict
    controllers: list
    deform_joints: list

    def guide(self, role: str, index: int = 0) -> Any:
        """Return the guide node for ``role``."""

    def guides(self, role: str) -> list:
        """Return every guide node with ``role`` ordered by index."""

    def name(self, *tokens, suffix: Optional[str] = None) -> str:
        """Apply the naming convention (side + instance name + tokens + suffix)."""

    def controller(
        self,
        name: str,
        *,
        shape: str = "Circle",
        size: float = 1.0,
        parent: Any = None,
        color: Any = None,
        match: Any = None,
        mirror: str = "world",
    ) -> Any:
        """Create a tagged controller; ``match`` snaps it to a node.

        ``mirror`` is ``"behaviour"`` (FK-like, follows its joint) or
        ``"world"`` (IK/world-aligned), recorded for a pose-mirror tool.
        """

    def tweak_control(
        self, main: Any, *, size: Optional[float] = None, shape: str = "Circle"
    ) -> Any:
        """Create a secondary tweak controller under ``main``.

        The tweak is a child of the main, so it rides along when the animator
        moves the main control instead of being left behind. It is what the rig
        reads downstream.
        """

    def controller_by_role(self, role: str) -> Any:
        """Return the controller registered under ``role``, or None."""

    def bind_joint(
        self,
        name: str,
        *,
        parent: Any = None,
        match: Any = None,
        radius: float = 1.0,
    ) -> Any:
        """Create a tagged bind joint under ``parent`` or ``bind_parent``."""

    def deform_joint(self, node: Any) -> Any:
        """Register (and tag) a deformation joint."""

    def output(self, name: str, node: Any) -> None:
        """Register the built node for declared output ``name``."""

    def attach(self, input_name: str, node: Any) -> None:
        """Register the node driven by whatever is connected to ``input_name``."""

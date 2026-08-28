"""Context protocols handed to modules by a backend.

These are *interfaces*; the Maya implementation lives in
``tik.trigger.backends.maya.context``. Modules only ever talk to these.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Protocol, Sequence


@dataclass
class RigGroups:
    """Standard group nodes created for every module instance."""

    limb: Any = None  # top group of the module
    scale: Any = None  # scaled with the rig, holds controllers/plugs
    nonscale: Any = None  # non-inheriting, holds skinned helper geometry
    controllers: Any = None
    joints: Any = None  # deformation joints
    rig: Any = None  # internal nodes (ik handles, helpers)


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
    plugs: dict
    sockets: dict
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
    ) -> Any:
        """Create a tagged controller; ``match`` snaps it to a node."""

    def deform_joint(self, node: Any) -> Any:
        """Register (and tag) a deformation joint."""

    def plug(self, name: str, node: Any) -> None:
        """Expose ``node`` as output plug ``name`` (children attach here)."""

    def socket(self, name: str, node: Any) -> None:
        """Expose ``node`` as input socket ``name`` (attaches to a parent plug)."""

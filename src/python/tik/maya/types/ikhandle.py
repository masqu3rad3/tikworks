"""IK handle node type wrapper."""

from __future__ import annotations

from typing import Optional

from maya import cmds

from ..core.registry import register, resolve
from .transform import Transform


@register("ikHandle")
class IkHandle(Transform):
    """Wrapper for ikHandle nodes."""

    @classmethod
    def create(
        cls, start, end, solver: str = "ikRPsolver", name: Optional[str] = None
    ) -> "IkHandle":
        """Create an IK handle between two joints.

        Args:
            start: Start joint (wrapper or name).
            end: End joint (wrapper or name); the effector is created here.
            solver: ``"ikRPsolver"`` or ``"ikSCsolver"``.
            name: Handle name.
        """
        kwargs = {
            "startJoint": str(resolve(start).long_name),
            "endEffector": str(resolve(end).long_name),
            "solver": solver,
        }
        if name:
            kwargs["name"] = name
        handle, _effector = cmds.ikHandle(**kwargs)
        return cls(handle)

    @property
    def solver(self) -> str:
        """Return the solver node type name."""
        solver_nodes = cmds.listConnections(f"{self.long_name}.ikSolver") or []
        return cmds.nodeType(solver_nodes[0]) if solver_nodes else ""

    @property
    def start_joint(self):
        """Return the start joint wrapper."""
        return resolve(cmds.ikHandle(self.long_name, query=True, startJoint=True))

    @property
    def end_effector(self):
        """Return the end effector wrapper."""
        return resolve(cmds.ikHandle(self.long_name, query=True, endEffector=True))

    @property
    def twist(self):
        """Return the twist plug."""
        return self["twist"]

    def pole_vector(self, node):
        """Create a poleVectorConstraint from ``node`` to this handle."""
        constraint = cmds.poleVectorConstraint(resolve(node).long_name, self.long_name)[
            0
        ]
        return resolve(constraint)

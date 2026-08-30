"""Per-segment length drivers for a joint chain.

Owns nothing but segment lengths::

    tx_i = side_sign * rest_i * PRODUCT(factors)

``rest_plugs`` are live and writable, so one multiply on a rest plug rescales
that bone consistently through anything downstream that reads
``total_length``. Stretch and squash are merely factors added from outside; an
unbuilt factor is ``1.0``, so flags never interact.
"""

from __future__ import annotations

from typing import Optional, Sequence

from maya import cmds

from ..core import attribute
from ..core.decorators import undo
from ..core.plug import Plug
from ..core.registry import resolve
from ..types.transform import Transform


def _node(item):
    return resolve(item) if isinstance(item, str) else item


class ChainLengths:
    """Drives ``translateX`` of every joint after the root."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.holder: Optional[Transform] = None
        self.joints: list = []
        self.rest_plugs: list[Plug] = []
        self._outputs: list[Plug] = []
        self._factors: list[Plug] = []
        self._nodes: list = []  # plug-arithmetic nodes, for delete()
        self._side_sign = 1
        self._total: Optional[Plug] = None

    @classmethod
    @undo
    def create(
        cls,
        joints: Sequence,
        *,
        side_sign: int = 1,
        name: Optional[str] = None,
    ) -> "ChainLengths":
        """Build the length network for ``joints``.

        Args:
            joints: The chain, root first. At least two joints.
            side_sign: ``-1`` on a mirrored-behaviour side, where the aim axis
                points back up the chain and ``translateX`` is negative.
            name: Prefix for created nodes.

        Returns:
            The construct.
        """
        joints = [_node(joint) for joint in joints]
        if len(joints) < 2:
            raise ValueError("ChainLengths needs at least two joints.")
        chain = cls(name or "chainLengths")
        chain.joints = joints
        chain._side_sign = -1 if side_sign < 0 else 1

        chain.holder = Transform.create(name=f"{chain.name}_lengths_grp")
        attribute.lock_and_hide(chain.holder, attribute.TRANSFORM_ATTRS)

        for index in range(len(joints) - 1):
            rest = abs(joints[index + 1].translate.x)
            plug = attribute.add_float(chain.holder, f"restLength{index}", default=rest)
            chain.rest_plugs.append(plug)
            chain._outputs.append(plug)
        chain._connect()
        return chain

    # ----------------------------------------------------------- internals
    def _track(self, plug: Plug) -> Plug:
        """Record a plug's node so ``delete`` can clean it up."""
        node = getattr(plug, "node", None)
        if node is not None and node not in self._nodes:
            self._nodes.append(node)
        return plug

    def _connect(self) -> None:
        """Drive each joint's ``translateX`` from its current output plug.

        The side sign is applied last, so a factor scales the magnitude and can
        never flip the direction.
        """
        for index, plug in enumerate(self._outputs):
            driver = plug if self._side_sign > 0 else self._track(plug * -1.0)
            driver >> self.joints[index + 1]["translateX"]

    def _rebuild(self, outputs: list[Plug]) -> None:
        """Swap the output plugs and rewire the joints."""
        self._outputs = outputs
        self._connect()

    # ----------------------------------------------------------- accessors
    @property
    def segment_count(self) -> int:
        """Number of segments (one fewer than the joint count)."""
        return len(self.rest_plugs)

    @property
    def total_length(self) -> Plug:
        """Plug carrying the sum of every rest length."""
        if self._total is None:
            total = self.rest_plugs[0]
            for plug in self.rest_plugs[1:]:
                total = self._track(total + plug)
            self._total = total
        return self._total

    @undo
    def add_factor(self, plug: Plug) -> None:
        """Multiply every segment's output by ``plug``."""
        self._factors.append(plug)
        self._rebuild([self._track(output * plug) for output in self._outputs])

    @undo
    def add_override(self, lengths: Sequence, weight) -> None:
        """Blend every segment towards an explicit length by ``weight``."""
        lengths = list(lengths)
        if len(lengths) != self.segment_count:
            raise ValueError("add_override needs one length per segment.")
        # Expanded rather than calling Plug.lerp, so every intermediate node is
        # tracked for delete(); lerp builds three and would only hand back one.
        outputs = []
        for output, target in zip(self._outputs, lengths):
            difference = self._track(target - output)
            scaled = self._track(difference * weight)
            outputs.append(self._track(output + scaled))
        self._rebuild(outputs)

    @undo
    def delete(self) -> None:
        """Delete the network, leaving the joints unconnected."""
        for joint in self.joints[1:]:
            plug = f"{joint.long_name}.translateX"
            for source in (
                cmds.listConnections(plug, source=True, destination=False, plugs=True)
                or []
            ):
                cmds.disconnectAttr(source, plug)
        names = [node.long_name for node in self._nodes if node.exists()]
        if self.holder is not None and self.holder.exists():
            names.append(self.holder.long_name)
        if names:
            cmds.delete(names)

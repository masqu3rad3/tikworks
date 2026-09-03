"""Matrix based parent constraint.

Drives a transform from one or more driver matrices through a
``multMatrix`` -> ``decomposeMatrix`` network. Joints get a joint-orient
compensation strand so the driven rotation stays clean.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Optional, Sequence, Union

from maya import cmds
from maya.api import OpenMaya

from ..core.decorators import undo
from ..core.plug import Plug, world_matrix_plug
from ..core.registry import resolve
from ..core.scene import create_node, ensure_plugin

if TYPE_CHECKING:
    from ..types.transform import Transform

DriverType = Union[str, "Transform", Plug, Sequence[Union[str, "Transform", Plug]]]


class MatrixConstraint:
    """Matrix constraint wrapper holding the created network nodes."""

    def __init__(
        self,
        driven,
        mult_matrix,
        decompose,
        average=None,
        rotate_nodes: Optional[list] = None,
    ) -> None:
        self.driven = driven
        self.mult_matrix = mult_matrix
        self.decompose = decompose
        self.average = average
        self._rotate_nodes = rotate_nodes or []

    @classmethod
    @undo
    def create(
        cls,
        driver: DriverType,
        driven,
        *,
        maintain_offset: bool = True,
        skip_translate: Iterable[str] = (),
        skip_rotate: Iterable[str] = (),
        skip_scale: Iterable[str] = (),
        name: Optional[str] = None,
        cutoff=None,
    ) -> "MatrixConstraint":
        """Constrain ``driven`` to ``driver``.

        Args:
            driver: Node, name, matrix plug, or a list of those (averaged).
            driven: Transform (or name) to drive.
            maintain_offset: Keep the current offset between driver and driven.
            skip_translate: Axes (``"x"``, ``"y"``, ``"z"``) left unconnected.
            skip_rotate: Axes left unconnected.
            skip_scale: Axes left unconnected.
            name: Prefix for created nodes (defaults to the driven name).
            cutoff: Node whose world transform (and everything above it) is
                removed from the driver's contribution. Use when the driver
                lives under groups that would otherwise double-transform the
                driven.
        """
        driven = resolve(driven) if isinstance(driven, str) else driven
        name = name or driven.name
        skip_translate = {axis.lower() for axis in skip_translate}
        skip_rotate = {axis.lower() for axis in skip_rotate}
        skip_scale = {axis.lower() for axis in skip_scale}

        drivers = list(driver) if isinstance(driver, (list, tuple)) else [driver]
        driver_plugs = [world_matrix_plug(item) for item in drivers]

        average = None
        if len(driver_plugs) > 1:
            average = create_node("wtAddMatrix", name=f"{name}_averageMatrix")
            weight = 1.0 / len(driver_plugs)
            for index, plug in enumerate(driver_plugs):
                plug >> average[f"wtMatrix[{index}].matrixIn"]
                average[f"wtMatrix[{index}].weightIn"].value = weight
            source_plug = average["matrixSum"]
        else:
            source_plug = driver_plugs[0]

        if cutoff is not None:
            cutoff = resolve(cutoff) if isinstance(cutoff, str) else cutoff
            cutoff_mult = create_node("multMatrix", name=f"{name}_cutoffMultMatrix")
            source_plug >> cutoff_mult["matrixIn[0]"]
            cutoff["worldInverseMatrix[0]"] >> cutoff_mult["matrixIn[1]"]
            source_plug = cutoff_mult["matrixSum"]

        mult_matrix = create_node("multMatrix", name=f"{name}_multMatrix")
        decompose = create_node("decomposeMatrix", name=f"{name}_decomposeMatrix")

        parent = driven.parent
        index = 0
        offset = None
        if maintain_offset:
            driven_world = OpenMaya.MMatrix(driven["worldMatrix[0]"].value)
            driver_world = OpenMaya.MMatrix(source_plug.value)
            offset = driven_world * driver_world.inverse()
            mult_matrix[f"matrixIn[{index}]"].value = list(offset)
            index += 1
        source_plug >> mult_matrix[f"matrixIn[{index}]"]
        index += 1
        if parent is not None:
            parent["worldInverseMatrix[0]"] >> mult_matrix[f"matrixIn[{index}]"]
        mult_matrix["matrixSum"] >> decompose["inputMatrix"]

        rotate_nodes: list = []
        rotate_source = decompose
        is_joint = driven.type == "joint"
        if is_joint and len(skip_rotate) < 3:
            rotate_source, rotate_nodes = cls._joint_rotation_strand(
                name, driven, parent, source_plug, offset
            )

        cls._connect_channels(decompose, "outputTranslate", driven, "translate", skip_translate)
        cls._connect_channels(rotate_source, "outputRotate", driven, "rotate", skip_rotate)
        cls._connect_channels(decompose, "outputScale", driven, "scale", skip_scale)

        return cls(driven, mult_matrix, decompose, average, rotate_nodes)

    @staticmethod
    def _joint_rotation_strand(name, joint, parent, source_plug, offset=None):
        """Build the joint orient compensation network for a joint driven.

        A joint's world orientation is ``rotate * jointOrient * parentWorld``,
        so the rotation this drives is the target world matrix with
        ``(jointOrient * parentWorld)`` divided out.

        ``offset`` must be prepended exactly as the translate/scale strands do.
        Without it a joint constrained with ``maintain_offset=True`` snaps to
        the driver's orientation at build time, discarding its own.
        """
        ensure_plugin("matrixNodes")
        compose = create_node("composeMatrix", name=f"{name}_rotateComposeMatrix")
        first_mult = create_node("multMatrix", name=f"{name}_firstRotateMultMatrix")
        inverse = create_node("inverseMatrix", name=f"{name}_rotateInverseMatrix")
        second_mult = create_node("multMatrix", name=f"{name}_secRotateMultMatrix")
        rotate_decompose = create_node(
            "decomposeMatrix", name=f"{name}_rotateDecomposeMatrix"
        )

        compose["inputRotate"].value = joint["jointOrient"].value[0]
        compose["outputMatrix"] >> first_mult["matrixIn[0]"]
        if parent is not None:
            parent["worldMatrix[0]"] >> first_mult["matrixIn[1]"]
        first_mult["matrixSum"] >> inverse["inputMatrix"]

        index = 0
        if offset is not None:
            second_mult[f"matrixIn[{index}]"].value = list(offset)
            index += 1
        source_plug >> second_mult[f"matrixIn[{index}]"]
        index += 1
        inverse["outputMatrix"] >> second_mult[f"matrixIn[{index}]"]
        second_mult["matrixSum"] >> rotate_decompose["inputMatrix"]
        return rotate_decompose, [compose, first_mult, inverse, second_mult, rotate_decompose]

    @staticmethod
    def _connect_channels(source_node, source_attr, target, target_attr, skip):
        if len(skip) == 3:
            return
        if not skip:
            source_node[source_attr] >> target[target_attr]
            return
        for axis in "xyz":
            if axis in skip:
                continue
            upper = axis.upper()
            source_node[f"{source_attr}{upper}"] >> target[f"{target_attr}{upper}"]

    @property
    def nodes(self) -> list:
        """Return every network node created by this constraint."""
        created = [self.mult_matrix, self.decompose, *self._rotate_nodes]
        if self.average is not None:
            created.append(self.average)
        return created

    @undo
    def delete(self) -> None:
        """Delete the constraint network, leaving the driven node in place."""
        cmds.delete([node.long_name for node in self.nodes if node.exists()])

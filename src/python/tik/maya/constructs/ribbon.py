"""Ribbon: a pure-math strip of deformer joints between two ends.

No geometry. Start/end "plug" transforms are what callers pin to their
controllers; ``MatrixSpline`` blends the plugs and the mid plugs into
swing-only frames, and every deformer joint is a flat joint with live TRS
channels: translate/scale/swing decomposed from its spline output and the
interpolated twist added as a float onto ``rotateX`` — never through a
matrix, so twist is unbounded.

The aim up frame is the pinned start matrix with the wired ``start_twist``
removed (``Rx(-twist) * start_plug.worldMatrix``): it swings with the limb
but carries no twist.
"""

from __future__ import annotations

from typing import Optional, Sequence

from maya import cmds

from ..core.decorators import undo
from ..core.plug import Plug
from ..core.registry import ensure_node
from ..core.scene import create_node, ensure_plugin
from ..types.joint import Joint
from ..types.transform import Transform
from .matrix_constraint import MatrixConstraint
from .matrix_spline import MatrixSpline
from .measure import Measure

ROTATE_ORDER_XYZ = 0


class Ribbon:
    """Wrapper holding every node of a ribbon setup."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.group: Transform = None
        self.start_plug: Transform = None
        self.end_plug: Transform = None
        self.start_twist: Plug = None
        self.end_twist: Plug = None
        self.up_frame: Plug = None
        self.control_spline: Optional[MatrixSpline] = None
        self.spline: MatrixSpline = None
        self.joint_group: Transform = None
        self.mid_frames: list[Transform] = []
        self.mid_plugs: list[Transform] = []
        self.deformer_joints: list[Joint] = []
        self.scale_switch: Optional[Plug] = None
        self.measure: Optional[Measure] = None
        self._decomposes: list = []
        self._nodes: list = []

    # ------------------------------------------------------------------ build
    @classmethod
    @undo
    def create(
        cls,
        start,
        end,
        *,
        name: str,
        joint_count: int = 5,
        mid_count: int = 1,
        degree: int = 3,
        up_vector: Sequence[float] = (0, 1, 0),
        scaleable: bool = True,
        preserve_volume: bool = False,
        parent=None,
    ) -> "Ribbon":
        """Build a ribbon between ``start`` and ``end``.

        Args:
            start: Transform at the ribbon start.
            end: Transform at the ribbon end.
            name: Prefix for all created nodes.
            joint_count: Number of deformer joints.
            mid_count: Number of mid plugs between the ends. Pin a
                controller to each with ``pin_mid``; the frame it rides is
                in ``mid_frames``.
            degree: B-spline degree of the joint strip (clamped to the number
                of drivers minus one; 0 mid plugs is always linear).
            up_vector: World up used for the initial placement of the group.
            scaleable: Add stretch driven ``scaleX`` on the deformer joints.
            preserve_volume: With ``scaleable``, counter-scale Y/Z by
                ``ratio ** -0.5``.
            parent: Optional parent for the ribbon group.
        """
        start, end = ensure_node(start), ensure_node(end)
        if joint_count < 1:
            raise ValueError("Ribbon needs at least one deformer joint.")
        length = start.distance_to(end)
        if length <= 0:
            raise ValueError("Ribbon start and end must not overlap.")
        ribbon = cls(name)
        ribbon._create_group(parent)
        ribbon._create_plugs(length, scaleable)
        ribbon._create_up_frame()
        ribbon._create_mids(mid_count)
        ribbon._create_joints(joint_count, degree)
        ribbon._place(start, end, up_vector)
        if scaleable:
            ribbon._create_scaling(preserve_volume)
        return ribbon

    def _create_group(self, parent) -> None:
        self.group = Transform.create(name=f"{self.name}_ribbon_grp")
        if parent is not None:
            self.group.parent = ensure_node(parent)

    def _create_plugs(self, length: float, scaleable: bool) -> None:
        half = length * 0.5
        self.start_plug = Transform.create(name=f"{self.name}_start_plug", parent=self.group.long_name)
        self.end_plug = Transform.create(name=f"{self.name}_end_plug", parent=self.group.long_name)
        self.start_plug.translate = (-half, 0, 0)
        self.end_plug.translate = (half, 0, 0)
        self.start_twist = self.start_plug["twist"].create("float")
        self.end_twist = self.end_plug["twist"].create("float")
        if scaleable:
            self.scale_switch = self.start_plug["scaleSwitch"].create(
                "float", default=1.0, min=0.0, max=1.0
            )

    def _create_up_frame(self) -> None:
        """``Rx(-start_twist) * start_plug.worldMatrix``: swings with the pin, no twist."""
        ensure_plugin("matrixNodes")
        compose = create_node("composeMatrix", name=f"{self.name}_upFrame_composeMatrix")
        negated = self.start_twist * -1.0
        negated >> compose["inputRotateX"]
        mult = create_node("multMatrix", name=f"{self.name}_upFrame_multMatrix")
        compose["outputMatrix"] >> mult["matrixIn[0]"]
        self.start_plug["worldMatrix[0]"] >> mult["matrixIn[1]"]
        self.up_frame = mult["matrixSum"]
        self._nodes.extend([negated.node, compose, mult])

    def _create_mids(self, count: int) -> None:
        """Mid plugs on the control spline, for the caller to pin controllers to.

        The frame carries the interpolated twist so a controller riding it
        travels with the ribbon; the plug is the transform the joint spline
        reads, so pinning it is what lets the caller drive the strip. Shapes,
        colours and tags are policy and belong to the caller.
        """
        if count < 1:
            return
        parameters = [(index + 1) / (count + 1) for index in range(count)]
        self.control_spline = MatrixSpline.create(
            [self.start_plug, self.end_plug],
            parameters,
            name=f"{self.name}_ctrl",
            degree=1,
            twists=[self.start_twist, self.end_twist],
            up_matrix=self.up_frame,
            parent=self.group,
        )
        for index, output in enumerate(self.control_spline.outputs):
            # the output frame carries the interpolated twist so the plug rides it
            output.transform["rotateOrder"].value = ROTATE_ORDER_XYZ
            output.twist >> output.transform["rotateX"]
            plug = Transform.create(
                name=f"{self.name}_mid{index}_plug", parent=output.transform.long_name
            )
            plug["rotateOrder"].value = ROTATE_ORDER_XYZ
            self.mid_frames.append(output.transform)
            self.mid_plugs.append(plug)

    def _mid_twists(self) -> list[Plug]:
        """Per mid plug: interpolated end twist plus that plug's own roll."""
        twists = []
        outputs = self.control_spline.outputs if self.control_spline is not None else []
        for output, plug in zip(outputs, self.mid_plugs):
            twist = output.twist + plug["rotateX"]
            self._nodes.append(twist.node)
            twists.append(twist)
        return twists

    def _create_joints(self, count: int, degree: int) -> None:
        drivers = [self.start_plug, *self.mid_plugs, self.end_plug]
        twists = [self.start_twist, *self._mid_twists(), self.end_twist]
        parameters = [(index + 0.5) / count for index in range(count)]
        self.spline = MatrixSpline.create(
            drivers,
            parameters,
            name=self.name,
            degree=degree,
            twists=twists,
            up_matrix=self.up_frame,
            parent=self.group,
        )
        self.joint_group = Transform.create(name=f"{self.name}_joints_grp", parent=self.group.long_name)
        # joints hold world-space channel values; the group must not transform them again
        self.joint_group["inheritsTransform"].value = False
        for index, output in enumerate(self.spline.outputs):
            joint = Joint.create(name=f"{self.name}_{index}_jnt", parent=self.joint_group.long_name)
            joint["rotateOrder"].value = ROTATE_ORDER_XYZ
            decompose = create_node("decomposeMatrix", name=f"{self.name}_{index}_decomposeMatrix")
            output.transform["worldMatrix[0]"] >> decompose["inputMatrix"]
            decompose["outputTranslate"] >> joint["translate"]
            decompose["outputRotateY"] >> joint["rotateY"]
            decompose["outputRotateZ"] >> joint["rotateZ"]
            # twist is added after decomposition so rotateX stays an unbounded float
            rotate_x = decompose["outputRotateX"] + output.twist
            rotate_x >> joint["rotateX"]
            for axis in "XYZ":
                decompose[f"outputScale{axis}"] >> joint[f"scale{axis}"]
            self.deformer_joints.append(joint)
            self._decomposes.append(decompose)
            self._nodes.extend([decompose, rotate_x.node])

    def _place(self, start, end, up_vector) -> None:
        self.group.world_position = Transform.between(start, end)
        self.group.aim_at(
            end, aim_vector=(1, 0, 0), up_vector=(0, 1, 0), world_up=tuple(up_vector)
        )

    def _create_scaling(self, preserve_volume: bool) -> None:
        self.measure = Measure.create(self.start_plug, self.end_plug, name=f"{self.name}_ribbon")
        ratio = self.measure.ratio_plug()
        # blend between 1.0 (switch off) and the live ratio (switch on)
        stretch = (ratio - 1.0) * self.scale_switch + 1.0
        volume = None
        if preserve_volume:
            volume = (ratio ** -0.5 - 1.0) * self.scale_switch + 1.0
        for joint, decompose in zip(self.deformer_joints, self._decomposes):
            scale_x = decompose["outputScaleX"] * stretch
            scale_x >> joint["scaleX"]
            self._nodes.append(scale_x.node)
            if volume is not None:
                for axis in "YZ":
                    scaled = decompose[f"outputScale{axis}"] * volume
                    scaled >> joint[f"scale{axis}"]
                    self._nodes.append(scaled.node)

    # -------------------------------------------------------------- pinning
    @undo
    def pin_start(self, node, maintain_offset: bool = True) -> MatrixConstraint:
        """Drive the start plug from ``node`` (full TRS)."""
        return MatrixConstraint.create(
            node, self.start_plug, maintain_offset=maintain_offset,
            name=f"{self.name}_startPin",
        )

    @undo
    def pin_end(self, node, maintain_offset: bool = True) -> MatrixConstraint:
        """Drive the end plug from ``node`` (full TRS)."""
        return MatrixConstraint.create(
            node, self.end_plug, maintain_offset=maintain_offset,
            name=f"{self.name}_endPin",
        )

    @undo
    def pin_mid(self, index: int, node, maintain_offset: bool = True) -> MatrixConstraint:
        """Drive mid plug ``index`` from ``node`` (full TRS)."""
        return MatrixConstraint.create(
            node, self.mid_plugs[index], maintain_offset=maintain_offset,
            name=f"{self.name}_mid{index}Pin",
        )

    @undo
    def delete(self) -> None:
        """Delete the entire ribbon hierarchy and network."""
        if self.measure is not None:
            self.measure.delete()
        for spline in (self.control_spline, self.spline):
            if spline is not None:
                spline.delete()
        cmds.delete([node.long_name for node in self._nodes if node.exists()])
        if self.group is not None and self.group.exists():
            cmds.delete(self.group.long_name)

"""Ribbon: a NURBS strip with follicle-driven joints between two ends.

The ribbon is built along +X in its own group, then the group is placed
between ``start`` and ``end``. Start/end "plug" transforms are what callers
pin to their controllers; everything else is internal.
"""

from __future__ import annotations

from typing import Optional, Sequence

from maya import cmds

from ..core import attribute
from ..core.decorators import undo
from ..core.plug import Plug
from ..core.registry import resolve
from ..roles.controller import Controller
from ..types.joint import Joint
from ..types.transform import Transform
from .matrix_constraint import MatrixConstraint
from .measure import Measure


def _node(item):
    return resolve(item) if isinstance(item, str) else item


class Ribbon:
    """Wrapper holding every node of a ribbon setup."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.group: Transform = None
        self.scale_group: Transform = None
        self.nonscale_group: Transform = None
        self.surface = None
        self.surface_transform: Transform = None
        self.deformer_joints: list[Joint] = []
        self.controllers: list[Controller] = []
        self.bind_joints: list[Joint] = []
        self.follicles: list[Transform] = []
        self.start_plug: Transform = None
        self.end_plug: Transform = None
        self.start_aim: Transform = None
        self.end_aim: Transform = None
        self.start_up: Transform = None
        self.end_up: Transform = None
        self.scale_switch: Optional[Plug] = None
        self.measure: Optional[Measure] = None
        self.skin_cluster = None
        self._aim_constraints: list = []

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
        controller_count: int = 1,
        up_vector: Sequence[float] = (0, 1, 0),
        scaleable: bool = True,
        parent=None,
    ) -> "Ribbon":
        """Build a ribbon between ``start`` and ``end``.

        Args:
            start: Transform at the ribbon start.
            end: Transform at the ribbon end.
            name: Prefix for all created nodes.
            joint_count: Number of follicle-driven deformer joints.
            controller_count: Number of mid controllers between the ends.
            up_vector: World up used to orient the ribbon plane.
            scaleable: Add stretch driven scaling on the deformer joints.
            parent: Optional parent for the ribbon group.
        """
        start, end = _node(start), _node(end)
        ribbon = cls(name)
        length = start.distance_to(end)
        if length <= 0:
            raise ValueError("Ribbon start and end must not overlap.")

        ribbon._create_groups(parent)
        ribbon._create_surface(length)
        ribbon._create_plugs(length, scaleable)
        ribbon._create_follicles(joint_count)
        ribbon._create_controllers(controller_count, length)
        ribbon._bind_surface()
        ribbon._place(start, end, up_vector)
        if scaleable:
            ribbon._create_scaling()
        return ribbon

    def _create_groups(self, parent) -> None:
        self.group = Transform.create(name=f"{self.name}_ribbon_grp")
        if parent is not None:
            self.group.parent = _node(parent)
        self.scale_group = Transform.create(
            name=f"{self.name}_ribbonScale_grp", parent=self.group.long_name
        )
        self.nonscale_group = Transform.create(
            name=f"{self.name}_ribbonNonScale_grp", parent=self.group.long_name
        )
        # follicles output world-space values; do not let the group transform
        # them a second time.
        self.nonscale_group["inheritsTransform"].value = False

    def _create_surface(self, length: float) -> None:
        transform_name = cmds.nurbsPlane(
            axis=(0, 0, 1),
            patchesU=5,
            patchesV=1,
            width=length,
            lengthRatio=1.0 / length,
            name=f"{self.name}_ribbon_surface",
            constructionHistory=False,
        )[0]
        cmds.rebuildSurface(
            transform_name,
            constructionHistory=False,
            replaceOriginal=True,
            rebuildType=0,
            endKnots=1,
            keepRange=2,
            keepControlPoints=False,
            keepCorners=False,
            spansU=5,
            degreeU=3,
            spansV=1,
            degreeV=1,
            direction=1,
        )
        self.surface_transform = Transform(transform_name)
        # skinned geometry lives in the non-inheriting group, otherwise the
        # bind joints and the surface transform would both move it.
        self.surface_transform.parent = self.nonscale_group
        self.surface = self.surface_transform.shapes[0]
        self.surface_transform.visibility = False

    def _create_plugs(self, length: float, scaleable: bool) -> None:
        half = length * 0.5
        self.start_plug = self._locator(f"{self.name}_start_plug", (-half, 0, 0))
        self.end_plug = self._locator(f"{self.name}_end_plug", (half, 0, 0))
        self.start_up = self._locator(f"{self.name}_start_up", (-half, 1, 0))
        self.end_up = self._locator(f"{self.name}_end_up", (half, 1, 0))
        self.start_aim = Transform.create(name=f"{self.name}_start_aim")
        self.end_aim = Transform.create(name=f"{self.name}_end_aim")
        self.start_aim.translate = (-half, 0, 0)
        self.end_aim.translate = (half, 0, 0)
        for node in (self.start_up, self.start_aim):
            node.parent = self.start_plug
        for node in (self.end_up, self.end_aim):
            node.parent = self.end_plug
        for node in (self.start_plug, self.end_plug):
            node.parent = self.scale_group

        self._aim_constraints.append(
            cmds.aimConstraint(
                self.end_plug.long_name,
                self.start_aim.long_name,
                aimVector=(1, 0, 0),
                upVector=(0, 1, 0),
                worldUpType="object",
                worldUpObject=self.start_up.long_name,
            )[0]
        )
        self._aim_constraints.append(
            cmds.aimConstraint(
                self.start_plug.long_name,
                self.end_aim.long_name,
                aimVector=(-1, 0, 0),
                upVector=(0, 1, 0),
                worldUpType="object",
                worldUpObject=self.end_up.long_name,
            )[0]
        )
        if scaleable:
            self.scale_switch = attribute.add_float(
                self.start_plug, "scaleSwitch", default=1.0, min=0.0, max=1.0
            )

    def _locator(self, name: str, position) -> Transform:
        transform_name = cmds.spaceLocator(name=name)[0]
        locator = Transform(transform_name)
        locator.translate = position
        for shape in locator.shapes:
            shape.visibility = False
        return locator

    def _create_follicles(self, joint_count: int) -> None:
        for index in range(joint_count):
            follicle = Transform.create(
                name=f"{self.name}_follicle{index}", parent=self.nonscale_group.long_name
            )
            shape = cmds.createNode(
                "follicle", name=f"{follicle.name}Shape", parent=follicle.long_name
            )
            shape = resolve(shape)
            self.surface["local"] >> shape["inputSurface"]
            self.surface["worldMatrix[0]"] >> shape["inputWorldMatrix"]
            shape["outTranslate"] >> follicle["translate"]
            shape["outRotate"] >> follicle["rotate"]
            shape["parameterU"].value = (index + 0.5) / joint_count
            shape["parameterV"].value = 0.5
            shape.visibility = False
            attribute.lock_and_hide(follicle, attribute.TRANSFORM_ATTRS[:6], hide=False)
            joint = Joint.create(
                name=f"{self.name}_{index}_jnt", parent=follicle.long_name
            )
            self.follicles.append(follicle)
            self.deformer_joints.append(joint)

    def _create_controllers(self, controller_count: int, length: float) -> None:
        start_bind = Joint.create(
            name=f"{self.name}_start_bind_jnt", parent=self.start_aim.long_name
        )
        end_bind = Joint.create(
            name=f"{self.name}_end_bind_jnt", parent=self.end_aim.long_name
        )
        start_bind.visibility = False
        end_bind.visibility = False
        self.bind_joints = [start_bind]
        for index in range(controller_count):
            ratio = (index + 1) / (controller_count + 1)
            position_x = -length * 0.5 + length * ratio
            controller = Controller.create(
                name=f"{self.name}_mid{index}_ctrl",
                shape="Circle",
                size=length * 0.15,
                parent=self.scale_group.long_name,
            )
            controller.transform.translate = (position_x, 0, 0)
            offset = controller.transform.create_offset_group(
                name=f"{self.name}_mid{index}_ctrl_offset"
            )
            MatrixConstraint.create(
                [self.start_aim, self.end_aim],
                offset,
                maintain_offset=True,
                name=f"{self.name}_mid{index}",
            )
            bind = Joint.create(
                name=f"{self.name}_mid{index}_bind_jnt",
                parent=controller.transform.long_name,
            )
            bind.visibility = False
            self.controllers.append(controller)
            self.bind_joints.append(bind)
        self.bind_joints.append(end_bind)

    def _bind_surface(self) -> None:
        from ..types.skincluster import SkinCluster

        self.skin_cluster = SkinCluster.create(
            self.surface_transform.long_name,
            [joint.long_name for joint in self.bind_joints],
            name=f"{self.name}_ribbon_skinCluster",
            toSelectedBones=True,
            maximumInfluences=2,
            dropoffRate=2.0,
        )

    def _place(self, start, end, up_vector) -> None:
        self.group.world_position = Transform.between(start, end)
        self.group.aim_at(
            end, aim_vector=(1, 0, 0), up_vector=(0, 1, 0), world_up=tuple(up_vector)
        )

    def _create_scaling(self) -> None:
        self.measure = Measure.create(
            self.start_plug, self.end_plug, name=f"{self.name}_ribbon"
        )
        ratio = self.measure.ratio_plug()
        # blend between 1.0 (switch off) and the live ratio (switch on)
        scaled = (ratio - 1.0) * self.scale_switch + 1.0
        for joint in self.deformer_joints:
            scaled >> joint["scaleX"]

    # -------------------------------------------------------------- pinning
    @undo
    def pin_start(self, node, maintain_offset: bool = True) -> MatrixConstraint:
        """Drive the start plug from ``node``."""
        return MatrixConstraint.create(
            node, self.start_plug, maintain_offset=maintain_offset,
            name=f"{self.name}_startPin",
        )

    @undo
    def pin_end(self, node, maintain_offset: bool = True) -> MatrixConstraint:
        """Drive the end plug from ``node``."""
        return MatrixConstraint.create(
            node, self.end_plug, maintain_offset=maintain_offset,
            name=f"{self.name}_endPin",
        )

    @undo
    def orient_start(self, node, maintain_offset: bool = True) -> MatrixConstraint:
        """Replace the start aim behaviour with rotation from ``node``."""
        cmds.delete(self._aim_constraints[0])
        return MatrixConstraint.create(
            node, self.start_aim, maintain_offset=maintain_offset,
            skip_translate=("x", "y", "z"), skip_scale=("x", "y", "z"),
            name=f"{self.name}_startOrient",
        )

    @undo
    def delete(self) -> None:
        """Delete the entire ribbon hierarchy."""
        if self.measure is not None:
            self.measure.delete()
        if self.group is not None and self.group.exists():
            cmds.delete(self.group.long_name)

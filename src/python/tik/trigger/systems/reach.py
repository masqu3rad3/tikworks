"""Reach: a base rotates as an end-effector swings away from a neutral.

Auto-clavicle is shoulder reach; the same system serves a hip. It is named
for the behaviour rather than the anatomy, and it names no animator-facing
attribute itself -- the module supplies a prefix, because wording is policy::

    frame       static transform at `origin`, X aimed at the neutral point,
                up from `rest_from`  ->  both neutrals are zero by construction
    probe       transform under the frame, point-constrained to `ik_target`
                -> probe.translate IS the direction, already in frame space
    fk_ref      static transform under the frame at the FK root's rest pose
                -> its `matrix` is the constant that opens the FK product
    driver      blendColors(fk_product, probe.translate, ikFk)
    elevation   atan2(y, hypot(x, z))        signed, +/-90, never wraps
    azimuth     atan2(z, hypot(x, y))        signed, +/-90, never wraps
    lift        remap(elevation) * <prefix>Lift   -> group.rotateZ
    swing       remap(azimuth)   * <prefix>Swing  -> group.rotateY

Three things earn their keep here.

**The frame carries the neutral.** Because the driver is measured in a frame
whose X *is* the neutral direction, both neutral angles are exactly zero by
construction -- no neutral attribute, no subtract node, and nothing that can
drift out of step with the guide that authored it. It is built with
`aim_at`, which bakes plain rotation values, so it is static once parented
under `rest_from`; aimConstraint's orthogonalisation IS the Gram-Schmidt
step against the socket's Y.

**The angles are off-plane.** `atan2(y, hypot(x, z))` rather than
`atan2(y, x)`: the latter has a branch cut on -X, the arm folded across the
chest, where the clamped output would jump from one limit to the other.

**The falloff is one three-point ramp per axis, not two.** A raised cosine
has zero derivative at every ramp point, so a single `smooth` ramp is C1 at
the neutral crossing and at both saturation limits, for any asymmetric pair
of limits and outputs. Two back-to-back ramps would kink at zero unless the
rigger happened to author matching slopes.

The animator's scalars multiply the remap *output*. Scaling the input, as an
earlier version did, warps the angle as well as the magnitude and moves the
neutral -- which is why that version could not reproduce its own bind pose.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import tik.maya as tm


@dataclass(frozen=True)
class ReachAxis:
    """One signed falloff: an input angle range onto an output degree range.

    The neutral is always the zero angle, because the driver is measured in a
    frame whose X *is* the neutral direction. ``min_angle`` must be negative
    and ``max_angle`` positive so the neutral lies strictly inside the range --
    a ramp point at 0.0 or 1.0 would collide with an endpoint.

    Both limits must also sit strictly inside +/-90. The driver's angles are
    off-plane -- ``atan2(y, hypot(x, z))`` -- which is what frees them of a
    branch cut, and the price is that they saturate at +/-90 whatever the arm
    does. A limit at or beyond 90 is unreachable, so the falloff would never
    complete and the rig would creep for its whole range. Better a build
    error than a rig that quietly never saturates.
    """

    LIMIT = 90.0

    min_angle: float
    max_angle: float
    min_output: float
    max_output: float

    def validate(self, label: str) -> None:
        """Raise ``ValueError`` if this axis cannot carry a neutral."""
        if not self.min_angle < 0.0 < self.max_angle:
            raise ValueError(
                f"{label} angle range must straddle zero, so the neutral sits "
                f"inside it ({self.min_angle} .. {self.max_angle})."
            )
        if not -self.LIMIT < self.min_angle or not self.max_angle < self.LIMIT:
            raise ValueError(
                f"{label} angle range must stay inside +/-{self.LIMIT:.0f}: the "
                f"driver's off-plane angles saturate there, so a wider limit "
                f"is never reached ({self.min_angle} .. {self.max_angle})."
            )
        if self.min_output >= self.max_output:
            raise ValueError(
                f"{label} output range must increase "
                f"({self.min_output} >= {self.max_output})."
            )

    def ramp_points(self) -> list:
        """``(position, value)`` pairs placing the neutral on zero output."""
        position = (0.0 - self.min_angle) / (self.max_angle - self.min_angle)
        value = (0.0 - self.min_output) / (self.max_output - self.min_output)
        return [(0.0, 0.0), (position, value), (1.0, 1.0)]


@dataclass
class Reach:
    """What ``build_reach`` made. Parent the driven controller under ``align``."""

    frame: object = None
    group: object = None
    align: object = None
    lift_plug: object = None
    swing_plug: object = None


def _hypot(rig, components, first: str, second: str, name: str):
    """Length of two of a direction's three components."""
    node = tm.create_node("distanceBetween", name=rig.name(name))
    components[first] >> node[f"point1{first}"]
    components[second] >> node[f"point1{second}"]
    return node["distance"]


def _signed_angle(rig, components, numerator: str, others, name: str):
    """``atan2(numerator, hypot(others))`` -- signed, +/-90, never wraps."""
    hypot = _hypot(rig, components, others[0], others[1], f"{name}Hypot")
    node = tm.create_node("atan2", name=rig.name(name))
    components[numerator] >> node["input1"]
    hypot >> node["input2"]
    return node["output"]


def _fk_direction(rig, frame, fk_controls, name: str):
    """Wrist position in frame space, from the FK controls' LOCAL matrices.

    Each FK controller is parented under the previous *controller* and carries
    its own offset group (``systems/limb.py:219,244``), so the hierarchy is
    ``o_0 -> c0 -> o_1 -> c1 -> o_2 -> c2``. Only ``o_0`` is animated -- it
    carries the constraint to the limb parent -- so ``fk_ref``, a static child
    of the frame snapped to ``o_0``'s rest pose, supplies that term instead.
    Every other matrix in the product is either a controller's own local
    matrix (an animator input) or plain static parenting.

    Reading *local* matrices is what keeps this acyclic: the FK controls'
    world matrices are downstream of the base we drive; their local ones are
    not. If an intermediate FK offset is ever constrained to something
    downstream, this branch cycles silently.
    """
    fk_ref = tm.Transform.create(name=rig.name(name, "fkRef"), parent=frame.long_name)
    fk_ref.align_to(fk_controls[0].offset)
    product = tm.create_node("multMatrix", name=rig.name(name, "fkProduct"))
    index = 0
    for control in reversed(fk_controls):
        control.transform["matrix"] >> product[f"matrixIn[{index}]"]
        index += 1
        if control is not fk_controls[0]:
            control.offset["matrix"] >> product[f"matrixIn[{index}]"]
            index += 1
    fk_ref["matrix"] >> product[f"matrixIn[{index}]"]
    point = tm.create_node("translationFromMatrix", name=rig.name(name, "fkPoint"))
    product["matrixSum"] >> point["input"]
    return {"X": point["outputX"], "Y": point["outputY"], "Z": point["outputZ"]}


def build_reach(
    rig,
    parent,
    origin,
    rest_from,
    neutral_position,
    ik_target,
    control,
    *,
    lift: ReachAxis,
    swing: ReachAxis,
    fk_controls=None,
    switch_plug=None,
    prefix: str = "autoReach",
    interpolation: str = "smooth",
    name: Optional[str] = None,
) -> Reach:
    """Rotate a group as ``ik_target`` swings away from the neutral direction.

    Args:
        rig: The module's ``ModuleRig``.
        parent: Where the driven group hangs, usually a controller's offset.
        origin: Transform whose pivot the rotation happens about.
        rest_from: The module's socket. Parents the frame and supplies the up
            vector, so it must be upstream of everything read here.
        neutral_position: World point the neutral direction passes through.
        ik_target: What the base reaches toward. MUST be upstream of any IK
            solve it feeds, or the graph cycles.
        control: Transform carrying the animator-facing attributes.
        lift: Falloff for elevation, driving the group's Z.
        swing: Falloff for azimuth, driving the group's Y.
        fk_controls: Optional FK controllers, root first. With them the driver
            reads the same quantity in FK as in IK.
        switch_plug: The ikFk switch. Required when ``fk_controls`` is given.
        prefix: Attribute prefix, e.g. ``autoCollar``.
        interpolation: ``linear``, ``smooth`` or ``spline``. Only ``smooth``
            is free of a slope discontinuity at the neutral and the limits.
        name: Prefix for created nodes.

    Returns:
        The ``Reach``. Parent the driven controller under ``reach.align``.
    """
    if fk_controls and switch_plug is None:
        raise ValueError("fk_controls needs switch_plug to blend against.")
    lift.validate(f"{prefix} lift")
    swing.validate(f"{prefix} swing")
    name = name or prefix

    # The neutral frame. `aim_at` bakes rotation values, so this is static
    # once parented; the up vector is the socket's own Y, read off its matrix
    # rather than passed as an up *object* -- the socket and the origin nearly
    # coincide, which would leave an up-at-object aim degenerate.
    socket_matrix = list(rest_from["worldMatrix[0]"].value)
    frame = tm.Transform.create(
        name=rig.name(name, "neutralFrame"), parent=rest_from.long_name
    )
    frame.snap_to(origin, rotation=False)
    marker = tm.Transform.create(name=rig.name(name, "neutralMarker"))
    marker.world_position = neutral_position
    frame.aim_at(
        marker,
        aim_vector=(1, 0, 0),
        up_vector=(0, 1, 0),
        world_up=(socket_matrix[4], socket_matrix[5], socket_matrix[6]),
    )
    marker.delete()

    # `n x u` lands on the socket's -Z for a mirrored limb, so "front" reads as
    # a negative azimuth there and the authored front/back numbers would swap.
    # Derived from the geometry rather than from a side flag, so an unusually
    # placed neutral guide still resolves correctly.
    frame_z = frame.world_axis("z")
    socket_z = (socket_matrix[8], socket_matrix[9], socket_matrix[10])
    azimuth_sign = (
        -1.0
        if sum(left * right for left, right in zip(frame_z, socket_z)) < 0.0
        else 1.0
    )

    # A transform under the frame whose local translate IS the direction in
    # that frame. Avoids pointMatrixMult, which is plugin-gated.
    probe = tm.Transform.create(name=rig.name(name, "probe"), parent=frame.long_name)
    tm.MatrixConstraint.create(
        ik_target, probe, maintain_offset=False, skip_rotate="xyz", skip_scale="xyz"
    )
    components = {
        "X": probe["translateX"],
        "Y": probe["translateY"],
        "Z": probe["translateZ"],
    }

    if fk_controls:
        fk = _fk_direction(rig, frame, fk_controls, name)
        blend = tm.create_node("blendColors", name=rig.name(name, "ikFkBlend"))
        # blendColors takes color1 at blender = 1, and ikFk = 1 is IK
        # (limb.py:209 defaults it to 1.0; limb.py:404 drives the IK control's
        # visibility straight off it), so the probe belongs on color1.
        for axis, channel in (("X", "R"), ("Y", "G"), ("Z", "B")):
            components[axis] >> blend[f"color1{channel}"]
            fk[axis] >> blend[f"color2{channel}"]
        switch_plug >> blend["blender"]
        components = {
            "X": blend["outputR"],
            "Y": blend["outputG"],
            "Z": blend["outputB"],
        }

    # The driven group takes the frame's orientation, so rotateZ is lift and
    # rotateY is swing on either side with no per-side axis juggling. `align`
    # carries the constant rotation back to the base's own orientation, which
    # is what keeps the driven controller's channels zeroed at bind.
    # `anchor` carries the frame's orientation, `group` carries the animation.
    # They MUST be separate transforms: the remap network connects group's
    # rotateY/rotateZ, and a connection overwrites whatever alignment was baked
    # into those same channels. On an unmirrored limb the alignment happens to
    # be zero, so folding the two together looks fine and silently inverts the
    # mirrored side.
    anchor = tm.Transform.create(
        name=rig.name(name, "autoAnchor"), parent=parent.long_name
    )
    anchor.snap_to(origin, rotation=False)
    anchor.snap_to(frame, position=False)
    group = tm.Transform.create(name=rig.name(name, "auto"), parent=anchor.long_name)
    group["rotateOrder"].value = 0  # xyz composes as Rz * Ry * Rx: lift outermost
    align = tm.Transform.create(name=rig.name(name, "align"), parent=group.long_name)
    align.align_to(origin)

    rig.separator(control, "auto_")
    plugs = {}
    for label, axis, channel, numerator, others, in_sign, out_sign in (
        # Lift reads the frame's Y, which is the socket's up on either side, so
        # it needs no handedness correction. A positive rotation about the
        # frame's Z already tilts its X toward that up.
        ("Lift", lift, "rotateZ", "Y", ("X", "Z"), 1.0, 1.0),
        # Swing reads the frame's Z, which mirrors. `in_sign` puts "front" on
        # the front branch of the curve; `out_sign` is the opposite, because a
        # positive rotation about the frame's Y tilts its X toward -Z.
        ("Swing", swing, "rotateY", "Z", ("X", "Y"), azimuth_sign, -azimuth_sign),
    ):
        scalar = control[f"{prefix}{label}"].create(
            "float", default=0.0, min=-2.0, max=2.0, soft_min=0.0, soft_max=1.0
        )
        angle = _signed_angle(rig, components, numerator, others, f"{name}{label}Angle")
        if in_sign < 0:
            angle = angle * in_sign
        ramp = tm.Remap.create(
            angle,
            input_min=axis.min_angle,
            input_max=axis.max_angle,
            output_min=axis.min_output,
            output_max=axis.max_output,
            interpolation=interpolation,
            points=axis.ramp_points(),
            name=rig.name(name, label.lower()),
        )
        driven = ramp.output * scalar
        if out_sign < 0:
            driven = driven * out_sign
        driven >> group[channel]
        plugs[label] = scalar

    return Reach(
        frame=frame,
        group=group,
        align=align,
        lift_plug=plugs["Lift"],
        swing_plug=plugs["Swing"],
    )

"""IK/FK limb: the shared recipe behind the arm, the leg and the fkik module.

Chain count is three sets, not four::

    ik_*   joints  (rig_grp)   ONE ikRPsolver handle. No second IK chain.
    fk_*   joints  (rig_grp)   driven by FK controls
    bind   joints  (bind_grp)  <- MatrixBlend(fk[i], ik[i], weight = ikFk)

The bind joints *are* the blend result, so no redundant blend chain exists.

Stretch and squash are factors on opposite sides of 1.0 that never overlap::

    gap            = soft_ik.gap_plug                        # stretch * (d - f(d))
    stretch_factor = min(1 + gap/L, 1 + limitPct/100)         >= 1
    squash_factor  = 1 + (min(d/L, 1) - 1) * squashAmount     <= 1
    tx_i           = side_sign * rest_i * stretch_factor * squash_factor

An unbuilt factor is 1.0, so the flags never interact and ``stretch=False``
really does produce a smaller graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

import tik.maya as tm
from tik.maya import attribute


@dataclass
class LimbResult:
    """Everything a module needs after the limb is built."""

    ik_joints: list = field(default_factory=list)
    fk_joints: list = field(default_factory=list)
    ik_handle: object = None
    ik_lengths: object = None
    fk_lengths: object = None
    soft_ik: object = None
    pole_base: object = None
    puppet_group: object = None
    fk_controls: list = field(default_factory=list)
    ik_control: object = None
    pole_control: object = None
    switch_control: object = None  # retired; ikFk lives on the IK control
    switch_plug: object = None
    size: float = 0.0
    hinge_axis: Optional[str] = None
    ik_tweak: object = None
    pole_tweak: object = None


def build_ikfk_limb(
    ctx,
    guides: Sequence,
    *,
    name: str = "",
    parent=None,
    bind_joints: Optional[Sequence] = None,
    controller_size: Optional[float] = None,
    soft_ik: bool = True,
    stretch: bool = True,
    squash: bool = True,
    stretch_limit_default: float = 50.0,
    pole_pin: bool = False,
    labels: Optional[Sequence[str]] = None,
) -> LimbResult:
    """Build an IK/FK limb driving ``bind_joints``.

    Args:
        ctx: The module build context.
        guides: Guide nodes, root first. At least three.
        name: Extra token for every created name; empty by default, since
            ``ctx.name`` already prefixes the instance name. Set it only to
            disambiguate a module that builds two limbs.
        parent: Transform the limb hangs from; defaults to ``ctx.groups.socket``.
        bind_joints: Bind joints to drive, one per guide. When omitted the
            puppet is built but nothing is blended onto a deform skeleton.
        controller_size: Base controller size; derived from the limb length
            when omitted.
        soft_ik: Build the soft-IK network. Always True for an arm.
        stretch: Build the extend-side factor and its limit clamp.
        squash: Build the compress-side factor.
        stretch_limit_default: Default percentage for the ``stretchLimit`` attr.
        pole_pin: Build the elbow pin override.
        labels: Segment labels; defaults to indices.

    Returns:
        A :class:`LimbResult`.
    """
    guides = list(guides)
    if len(guides) < 3:
        raise ValueError("build_ikfk_limb needs at least three guides.")
    labels = list(labels) if labels else [str(index) for index in range(len(guides))]
    parent = parent if parent is not None else ctx.groups.socket
    if controller_size is None:
        controller_size = _derive_size(guides)
    result = LimbResult()
    result.size = controller_size
    side_sign = ctx.side_mult

    _build_chains(ctx, guides, name, parent, side_sign, result)
    # Captured before the solve is wired: the pole and soft-IK constraints
    # move the chain, and every offset baked afterwards depends on this pose.
    pole_rest = _pole_rest_position(result.ik_joints)
    _build_pole_base(ctx, name, parent, result)
    _build_controls(ctx, name, parent, controller_size, labels, result)
    control = result.ik_control.transform  # animator-facing attributes
    driver = result.ik_tweak.transform  # what the rig actually follows

    attribute.add_separator(control, "segments_")
    segment_scales = [
        attribute.add_float(control, f"s{label.capitalize()}", default=1.0, min=0.001)
        for label in labels[:-1]
    ]

    result.ik_handle = tm.IkHandle.create(
        result.ik_joints[0],
        result.ik_joints[-1],
        solver="ikRPsolver",
        name=ctx.name(name, suffix="ikHandle"),
    )
    result.ik_handle.parent = ctx.groups.rig
    tm.MatrixConstraint.create(
        driver,
        result.ik_joints[-1],
        maintain_offset=True,
        skip_translate="xyz",
        skip_scale="xyz",
    )

    _build_lengths(ctx, name, side_sign, segment_scales, result)
    _build_soft_ik(ctx, name, soft_ik, control, driver, result)
    _build_stretch(ctx, name, stretch, squash, stretch_limit_default, control, driver, result)
    _build_pole(ctx, name, controller_size, pole_pin, control, driver, pole_rest, result)
    _build_visibility(ctx, name, result)
    _blend_to_bind(ctx, name, bind_joints, result)
    return result


# --------------------------------------------------------------------- puppet
def _build_chains(ctx, guides, name, parent, side_sign, result) -> None:
    """Create the IK and FK chains from a throwaway oriented source chain.

    The chains hang under a group that is constrained to ``parent``, rather
    than constraining the chain roots directly: ``MatrixConstraint`` routes a
    joint driven's rotation through its joint-orient strand, which does not
    carry the maintained offset, so constraining an oriented root to an
    identity group would force the root's world orientation to identity and
    swing the whole chain out of its guide pose.
    """
    result.puppet_group = tm.Transform.create(
        name=ctx.name(name, "puppet", suffix="grp"), parent=ctx.groups.rig.long_name
    )
    tm.MatrixConstraint.create(parent, result.puppet_group, maintain_offset=True)

    source = tm.Joint.chain(
        [tuple(guide.world_position) for guide in guides],
        name_pattern=ctx.name(name, "src{index}", suffix="jnt"),
        parent=result.puppet_group,
        orient=False,
    )
    # A mirrored-behaviour side aims the axis back up the chain, so translateX
    # goes negative and ChainLengths reads the sign.
    tm.Joint.orient_chain(
        source, reverse_aim=side_sign < 0, reverse_up=side_sign < 0
    )
    result.ik_joints = tm.Joint.duplicate_chain(
        source, prefix=ctx.name(name, "ik"), parent=result.puppet_group
    )
    result.fk_joints = tm.Joint.duplicate_chain(
        source, prefix=ctx.name(name, "fk"), parent=result.puppet_group
    )
    tm.delete(source[0].long_name)


def _build_pole_base(ctx, name, parent, result) -> None:
    """An anchor at the chain root that is upstream of the IK solve.

    ``ikRPsolver`` rotates the chain's root joint, so feeding that joint into
    the pole frame or the soft-IK root would cycle — Maya's DG will not notice
    that only the translation is actually used.
    """
    result.pole_base = tm.Transform.create(
        name=ctx.name(name, "poleBase"), parent=ctx.groups.rig.long_name
    )
    result.pole_base.align_to(result.ik_joints[0])
    tm.MatrixConstraint.create(parent, result.pole_base, maintain_offset=True)


# ------------------------------------------------------------------- controls
def _build_controls(ctx, name, parent, size, labels, result) -> None:
    """Create the IK, switch and FK controllers."""
    result.ik_control = ctx.controller(
        _role(name, "ik"),
        shape="Cube",
        size=size,
        parent=ctx.groups.control,
        match=result.ik_joints[-1],
        mirror="world",
    )
    result.ik_control.transform.create_offset_group(
        name=ctx.name(name, "ik", suffix="offset")
    )
    attribute.lock_and_hide(result.ik_control.transform, ("sx", "sy", "sz", "v"))
    # Created after the lock so it inherits the main's locked channels. The
    # tweak is what the rig follows; the main carries the attributes.
    result.ik_tweak = ctx.tweak_control(result.ik_control, size=size * 0.6)

    attribute.add_separator(result.ik_control.transform, "ikfk_")
    result.switch_plug = attribute.add_float(
        result.ik_control.transform, "ikFk", default=1.0, min=0.0, max=1.0
    )

    # Controllers live in control_grp and are *driven* by the limb's parent,
    # never parented under it: the ground rules put nothing but controllers and
    # their offset groups in control_grp.
    result.hinge_axis = _hinge_axis(result.fk_joints)
    fk_parent = None
    last = len(labels) - 1
    for index, (label, joint) in enumerate(zip(labels, result.fk_joints)):
        fk_control = ctx.controller(
            _role(name, "fk", label),
            shape="Circle",
            size=size,
            parent=fk_parent if fk_parent is not None else ctx.groups.control,
            match=joint,
            mirror="behaviour",
        )
        offset = fk_control.transform.create_offset_group(
            name=ctx.name(name, "fk", label, suffix="offset")
        )
        if fk_parent is None:
            tm.MatrixConstraint.create(parent, offset, maintain_offset=True)
        locked = ["tx", "ty", "tz", "sx", "sy", "sz", "v"]
        if 0 < index < last and result.hinge_axis is not None:
            # An elbow or knee is a hinge: only the derived axis stays.
            locked += [f"r{axis}" for axis in "xyz" if axis != result.hinge_axis]
        attribute.lock_and_hide(fk_control.transform, locked)
        tm.MatrixConstraint.create(
            fk_control.transform, joint, maintain_offset=True, skip_scale="xyz"
        )
        # The switch must stay reachable from whichever set is visible: at
        # ikFk = 0 the IK controls are hidden, so FK carries the proxy.
        attribute.add_proxy(fk_control.transform, result.switch_plug, name="ikFk")
        result.fk_controls.append(fk_control)
        fk_parent = fk_control.transform


# -------------------------------------------------------------------- lengths
def _build_lengths(ctx, name, side_sign, segment_scales, result) -> None:
    """Per-segment lengths on both chains, sharing rest plugs.

    Sharing is what makes per-segment scale work in FK too; the legacy kept
    initialDistance on the IK chains and was therefore IK-only.
    """
    result.ik_lengths = tm.ChainLengths.create(
        result.ik_joints,
        side_sign=side_sign,
        name=ctx.name(name, "ik"),
        parent=ctx.groups.rig,
    )
    result.fk_lengths = tm.ChainLengths.create(
        result.fk_joints,
        side_sign=side_sign,
        name=ctx.name(name, "fk"),
        parent=ctx.groups.rig,
    )
    for index, scale in enumerate(segment_scales):
        initial = result.ik_lengths.rest_plugs[index].value
        scaled = scale * initial
        scaled >> result.ik_lengths.rest_plugs[index]
        scaled >> result.fk_lengths.rest_plugs[index]


def _build_soft_ik(ctx, name, enabled, control, driver, result) -> None:
    """Drive the IK handle, softly or directly."""
    if enabled:
        result.soft_ik = tm.SoftIk.create(
            result.pole_base,
            driver,
            result.ik_lengths.total_length,
            name=ctx.name(name),
            parent=ctx.groups.rig,
        )
        attribute.add_proxy(control, result.soft_ik.soft_plug, name="softIk")
        tm.MatrixConstraint.create(
            result.soft_ik.goal_matrix,
            result.ik_handle,
            maintain_offset=False,
            skip_rotate="xyz",
            skip_scale="xyz",
        )
        return
    tm.MatrixConstraint.create(
        driver,
        result.ik_handle,
        maintain_offset=True,
        skip_rotate="xyz",
        skip_scale="xyz",
    )


def _build_stretch(ctx, name, stretch, squash, limit_default, control, driver, result) -> None:
    """Add the extend- and compress-side factors.

    They live on opposite sides of 1.0 and never overlap, so each is simply a
    factor; an unbuilt one is 1.0 and the flags cannot interact.
    """
    total = result.ik_lengths.total_length
    if stretch or squash:
        attribute.add_separator(control, "stretch_")
    if stretch:
        stretch_plug = attribute.add_float(
            control, "stretch", default=0.0, min=0.0, max=1.0
        )
        limit_plug = attribute.add_float(
            control, "stretchLimit", default=limit_default, min=0.0
        )
        if result.soft_ik is not None:
            # The soft blend already folds the stretch amount into the gap.
            stretch_plug >> result.soft_ik.stretch_plug
            gap = result.soft_ik.gap_plug
        else:
            measure = tm.Measure.create(
                result.pole_base["worldMatrix[0]"],
                driver["worldMatrix[0]"],
                name=ctx.name(name, "stretch"),
            )
            gap = (measure.distance - total).maximum(0.0) * stretch_plug
        ceiling = limit_plug / 100.0 + 1.0
        result.ik_lengths.add_factor((gap / total + 1.0).minimum(ceiling))

    if squash:
        squash_plug = attribute.add_float(
            control, "squash", default=0.0, min=0.0, max=1.0
        )
        measure = tm.Measure.create(
            result.pole_base["worldMatrix[0]"],
            driver["worldMatrix[0]"],
            name=ctx.name(name, "squash"),
        )
        compress = (measure.distance / total).minimum(1.0)
        result.ik_lengths.add_factor((compress - 1.0) * squash_plug + 1.0)


# ----------------------------------------------------------------------- pole
def _build_pole(ctx, name, size, pole_pin, control, driver, pole_rest, result) -> None:
    """Pole controller in a twist-aware auto space blended against a rest space."""
    attribute.add_separator(control, "pole_")
    pole_follow = attribute.add_float(
        control, "poleFollow", default=1.0, min=0.0, max=1.0
    )
    frame = tm.AimFrame.create(
        result.pole_base,
        driver,
        driver,
        twist_axis="X",
        parent=ctx.groups.rig,
        name=ctx.name(name, "pole"),
    )
    rest = tm.Transform.create(
        name=ctx.name(name, "poleRest"), parent=ctx.groups.rig.long_name
    )
    rest.snap_to(frame.transform)
    space = tm.MatrixBlend.create(
        rest, [frame.transform], [pole_follow], name=ctx.name(name, "poleSpace")
    )

    result.pole_control = ctx.controller(
        _role(name, "pole"),
        shape="Diamond",
        size=size * 0.5,
        parent=ctx.groups.control,
        mirror="world",
    )
    pole_offset = result.pole_control.transform.create_offset_group(
        name=ctx.name(name, "pole", suffix="offset")
    )
    tm.MatrixConstraint.create(space.output, pole_offset, maintain_offset=False)
    result.pole_control.transform.world_position = pole_rest
    attribute.lock_and_hide(
        result.pole_control.transform, ("rx", "ry", "rz", "sx", "sy", "sz", "v")
    )
    result.pole_tweak = ctx.tweak_control(result.pole_control, size=size * 0.3)
    result.ik_handle.pole_vector(result.pole_tweak.transform)

    if pole_pin:
        pin_plug = attribute.add_float(control, "polePin", default=0.0, min=0.0, max=1.0)
        upper = tm.Measure.create(
            result.pole_base["worldMatrix[0]"],
            result.pole_control.transform["worldMatrix[0]"],
            name=ctx.name(name, "pinUpper"),
        )
        lower = tm.Measure.create(
            result.pole_control.transform["worldMatrix[0]"],
            driver["worldMatrix[0]"],
            name=ctx.name(name, "pinLower"),
        )
        result.ik_lengths.add_override([upper.distance, lower.distance], pin_plug)


def _build_visibility(ctx, name, result) -> None:
    """IK controls show at switch 1, FK controls at switch 0."""
    result.switch_plug >> result.ik_control.transform.parent["visibility"]
    result.switch_plug >> result.pole_control.transform.parent["visibility"]
    reverse = tm.create_node("reverse", name=ctx.name(name, "ikFkReverse"))
    result.switch_plug >> reverse["inputX"]
    reverse["outputX"] >> result.fk_controls[0].transform.parent["visibility"]


def _blend_to_bind(ctx, name, bind_joints, result) -> None:
    """Blend the two puppet chains straight onto the deform skeleton."""
    if not bind_joints:
        return
    for index, bind_joint in enumerate(bind_joints):
        blend = tm.MatrixBlend.create(
            result.fk_joints[index],
            [result.ik_joints[index]],
            [result.switch_plug],
            name=ctx.name(name, f"blend{index}"),
        )
        tm.MatrixConstraint.create(blend.output, bind_joint, maintain_offset=True)


def _hinge_axis(joints: Sequence) -> Optional[str]:
    """Which local axis of the middle joint the chain bends about.

    The bend-plane normal is ``chain axis x bend direction``; the hinge is the
    middle joint's local axis most parallel to it. Returns ``None`` for a
    straight chain, which has no bend plane -- guessing two axes to lock would
    be worse than locking none.
    """
    start = joints[0].world_position
    middle = joints[len(joints) // 2]
    mid = middle.world_position
    end = joints[-1].world_position

    axis = end - start
    to_mid = mid - start
    if axis.length() < 1e-6:
        return None
    projection = start + axis * ((to_mid * axis) / (axis * axis))
    bend = mid - projection
    if bend.length() < 1e-4:
        return None

    normal = axis ^ bend
    normal.normalize()
    best, best_dot = None, 0.0
    for name in ("x", "y", "z"):
        dot = abs(middle.world_axis(name) * normal)
        if dot > best_dot:
            best, best_dot = name, dot
    return best


def _role(*parts) -> str:
    """Join non-empty name parts.

    An empty limb name must add no token: ``f"{name}_ik"`` would yield ``"_ik"``
    and a doubled underscore once ``ctx.name`` prefixes the instance.
    """
    return "_".join(part for part in parts if part)


def _derive_size(joints: Sequence) -> float:
    """Base controller size from the chain's rest length."""
    total = 0.0
    for first, second in zip(joints, joints[1:]):
        total += first.distance_to(second)
    return total * 0.15


def _pole_rest_position(joints: Sequence):
    """World position for the pole, in the chain's own bend plane.

    Projecting the mid joint onto the root-to-tip axis gives the bend
    direction; the pole sits along it, a quarter of the chain's length out.
    Placing it anywhere else would make the RP solver pull the chain out of
    the pose its guides describe, which then poisons every offset baked
    afterwards.
    """
    start = joints[0].world_position
    mid = joints[len(joints) // 2].world_position
    end = joints[-1].world_position

    axis = end - start
    to_mid = mid - start
    if axis.length() > 1e-6:
        projection = start + axis * ((to_mid * axis) / (axis * axis))
        direction = mid - projection
    else:
        direction = to_mid
    if direction.length() < 1e-4:
        # Straight chain: no bend plane to read, so fall back to the chain's
        # own up axis rather than an arbitrary world direction.
        direction = joints[0].world_axis("y")
    direction.normalize()

    total = 0.0
    for first, second in zip(joints, joints[1:]):
        total += first.distance_to(second)
    return mid + direction * (total * 0.25)

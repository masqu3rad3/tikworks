"""Reach: a base rotates toward an end-effector as it reaches away.

Auto-clavicle is shoulder reach; the same system serves a hip. It is named for
the behaviour rather than the anatomy, and it names no animator-facing
attribute itself -- the module supplies a prefix, because wording is policy.

    probe        transform under rest_from, point-constrained to the target
                 -> probe.translate IS the offset in the rest frame
    scaled       (t.x, t.y * <prefix>Vertical, t.z * <prefix>Horizontal)
    aim_point    transform under rest_from at `scaled`
    angle        AngleBetween(rest direction, scaled)
    factor       Remap(angle, start, end, 0..1, interpolation) * <prefix>
                 |
    MatrixBlend(rest, AimFrame(rest -> aim_point, up = rest_from), weight)
                 -> base_group

The offset is read off a transform parented under ``rest_from`` rather than by
multiplying matrices, because ``pointMatrixMult`` is plugin-gated and absent
from a stock Maya.
"""

from __future__ import annotations

from typing import Optional

import tik.maya as tm
from tik.maya import attribute


def build_reach(
    ctx,
    base_group,
    rest_from,
    target,
    control,
    *,
    prefix: str = "autoReach",
    start_angle: float = 0.0,
    end_angle: float = 90.0,
    interpolation: str = "smooth",
    name: Optional[str] = None,
) -> None:
    """Drive ``base_group`` to reach toward ``target``.

    Args:
        ctx: The module build context.
        base_group: Transform driven by the automation.
        rest_from: Transform the rest pose and the up vector come from
            (the module's socket).
        target: What the base reaches toward. MUST be upstream of any IK solve
            it feeds, or the graph cycles.
        control: Transform carrying the animator-facing attributes.
        prefix: Attribute prefix, e.g. ``autoCollar``.
        start_angle: Degrees below which the automation does nothing.
        end_angle: Degrees at or above which it is fully applied.
        interpolation: ``linear``, ``smooth`` or ``spline``.
        name: Prefix for created nodes.
    """
    name = name or prefix
    attribute.add_separator(control, "auto_")
    amount = attribute.add_float(control, prefix, default=0.0, min=0.0, max=1.0)
    vertical = attribute.add_float(
        control, f"{prefix}Vertical", default=0.5, min=0.0, max=1.0
    )
    horizontal = attribute.add_float(
        control, f"{prefix}Horizontal", default=0.5, min=0.0, max=1.0
    )

    # The rest pose: where the base sits with no automation at all.
    rest = tm.Transform.create(
        name=ctx.name(name, "rest"), parent=ctx.groups.rig.long_name
    )
    rest.snap_to(base_group)
    tm.MatrixConstraint.create(rest_from, rest, maintain_offset=True)

    # A transform under rest_from whose local translate IS the target offset in
    # that frame. Avoids pointMatrixMult, which is plugin-gated.
    probe = tm.Transform.create(
        name=ctx.name(name, "probe"), parent=rest_from.long_name
    )
    tm.MatrixConstraint.create(
        target, probe, maintain_offset=False, skip_rotate="xyz", skip_scale="xyz"
    )
    rest_direction = tuple(probe.translate)

    scaled = tm.create_node("multiplyDivide", name=ctx.name(name, "scaleMultiply"))
    probe["translate"] >> scaled["input1"]
    scaled["input2X"].value = 1.0
    vertical >> scaled["input2Y"]
    horizontal >> scaled["input2Z"]

    aim_point = tm.Transform.create(
        name=ctx.name(name, "aimPoint"), parent=rest_from.long_name
    )
    scaled["output"] >> aim_point["translate"]

    angle = tm.AngleBetween.create(
        rest_direction, scaled["output"], name=ctx.name(name, "angle")
    )
    ramp = tm.Remap.create(
        angle.angle,
        input_min=start_angle,
        input_max=end_angle,
        interpolation=interpolation,
        name=ctx.name(name),
    )
    weight = ramp.output * amount

    # twist_axis="X" tracks rest_from's Y. The default "Y" tracks its X, which
    # is the direction the base aims - a parallel up reference leaves
    # aimMatrix's secondary undefined and the roll drifts.
    frame = tm.AimFrame.create(
        rest,
        aim_point,
        rest_from,
        twist_axis="X",
        parent=ctx.groups.rig,
        name=ctx.name(name, "frame"),
    )
    blend = tm.MatrixBlend.create(
        rest, [frame.transform], [weight], name=ctx.name(name, "blend")
    )
    tm.MatrixConstraint.create(blend.output, base_group, maintain_offset=True)

"""Limb lock: hold the root-to-effector distance while the effector anchors.

While locked, the distance from the limb root to the IK control is held at
``lockLength``. The hand or foot is the animator's anchor, so the **root** is
what moves.

Three animator attributes, in channel-box order::

    limbLock       0-1, keyable      the blend
    currentLength  locked readout    live distance, for copy/paste
    lockLength     absolute units    what to lock to; defaults to bind pose

They exist for one workflow: at any pose, read ``currentLength``, paste it
into ``lockLength``, raise ``limbLock``. Nothing moves at that instant and the
limb is locked exactly where it stands. A normalised multiplier could not
express that, which is why the length is in absolute scene units.

**The cycle.** ``lock_root`` is *positioned* at the chain root but *driven*
from the socket, which is upstream of the push. Measuring from anything the
push moves would make root -> measure -> push -> root a DG cycle, which is
what the original implementation this replaces did. The consequence is that
the lock does not see collar rotation; under a locked limb the shoulder
rigidly follows the chest. Breaking the cycle needs some pre-push reference
and this is the closest one available.

No global rig-scale concept exists in tik.maya or tik.trigger, so nothing is
normalised. If one is ever added, ``lockLength`` becomes ``lockLength *
globalScale`` on a single connection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import tik.maya as tm
from tik.maya import attribute


@dataclass
class LimbLock:
    """Everything the lock built."""

    lock_root: Any = None
    aim_frame: Any = None
    push: Any = None
    anchor: Any = None
    measure: Any = None
    lock_plug: Any = None
    current_plug: Any = None
    length_plug: Any = None
    blend: Any = None


def build_limb_lock(
    rig,
    *,
    socket,
    chain_root,
    driver,
    control,
    target=None,
    name: str = "",
) -> LimbLock:
    """Build the limb lock network.

    Args:
        rig: The module's ``ModuleRig``.
        socket: The module's input socket. Drives ``lock_root`` (pre-push) and
            is the rest side of the blend.
        chain_root: Where ``lock_root`` is *positioned* -- the limb's first
            joint. Distinct from ``socket``, which for an arm sits at the
            collar, so measuring from it would lock collar-to-hand and seed
            ``lockLength`` with the wrong number.
        driver: What the rig follows at the far end (the IK tweak).
        control: Where the three animator attributes are added.
        target: Transform the blend drives. ``None`` selects output mode: the
            push is built and returned but nothing is driven locally.
        name: Extra name token.

    Returns:
        A :class:`LimbLock`.
    """
    result = LimbLock()

    # --- the pre-push reference ------------------------------------------
    result.lock_root = tm.Transform.create(
        name=rig.name(name, "lockRoot"), parent=rig.groups.rig.long_name
    )
    result.lock_root.align_to(chain_root)
    tm.MatrixConstraint.create(socket, result.lock_root, maintain_offset=True)

    # --- attributes, in channel-box order --------------------------------
    attribute.add_separator(control, "lock_")
    result.lock_plug = attribute.add_float(
        control, "limbLock", default=0.0, min=0.0, max=1.0
    )
    result.current_plug = attribute.add_float(control, "currentLength", default=0.0)
    rest_length = result.lock_root.distance_to(driver)
    result.length_plug = attribute.add_float(
        control, "lockLength", default=rest_length, min=0.0
    )
    result.length_plug.value = rest_length

    result.measure = tm.Measure.create(
        result.lock_root, driver, name=rig.name(name, "lock")
    )
    result.measure.distance >> result.current_plug
    # Connected first, then locked without hiding: it stays visible in the
    # channel box and copyable, which is the whole point of exposing it.
    attribute.lock_and_hide(control, ("currentLength",), hide=False)

    # --- the push ---------------------------------------------------------
    # The frame sits at the driver and aims back at the unpushed root, so a
    # child offset along +X lands exactly lockLength from the hand.
    result.aim_frame = tm.AimFrame.create(
        driver,
        result.lock_root,
        result.lock_root,
        aim_axis=(1.0, 0.0, 0.0),
        twist_axis="X",
        parent=rig.groups.rig,
        name=rig.name(name, "lockAim"),
    )
    result.push = tm.Transform.create(
        name=rig.name(name, "lockPush"), parent=result.aim_frame.transform.long_name
    )
    # A plain connection: no rest constant, no divides, no scale factor.
    result.length_plug >> result.push["translateX"]

    # The anchor rides the same frame at the *current* length, so it sits on
    # the unpushed root. Blending anchor -> push therefore interpolates
    # between two matrices with an identical rotation, and the constraint's
    # maintained offset re-applies as a pure translation delta. Blending from
    # the socket instead would drag the target by the socket-to-root offset.
    result.anchor = tm.Transform.create(
        name=rig.name(name, "lockAnchor"), parent=result.aim_frame.transform.long_name
    )
    result.measure.distance >> result.anchor["translateX"]

    if target is None:
        return result

    result.blend = tm.MatrixBlend.create(
        result.anchor, [result.push], [result.lock_plug],
        name=rig.name(name, "lockBlend"),
    )
    tm.MatrixConstraint.create(
        result.blend.output,
        target,
        maintain_offset=True,
        skip_rotate="xyz",
        skip_scale="xyz",
    )
    return result

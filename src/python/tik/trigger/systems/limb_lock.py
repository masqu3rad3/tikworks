"""Limb lock: hold the root-to-effector distance while the effector anchors.

While locked, the distance from the limb root to the IK control is held at
``lockLength``. The hand or foot is the animator's anchor, so the **root** is
what moves: lock an arm, pull the hand away, and the shoulder is dragged out
after it.

Three animator attributes, in channel-box order::

    limbLock       0-1, keyable      the blend
    currentLength  locked readout    live distance, for copy/paste
    lockLength     absolute units    what to lock to; defaults to bind pose

They exist for one workflow: at any pose, read ``currentLength``, paste it
into ``lockLength``, raise ``limbLock``. Nothing moves at that instant and the
limb is locked exactly where it stands. A normalised multiplier could not
express that, which is why the length is in absolute scene units.

**The push is a pure translation.** ``anchor`` and ``push`` ride the same aim
frame at the current and the locked length, so ``push - anchor`` is the world
displacement the root needs, and it is added to the socket's position as a
vector. An earlier version drove the target with a maintained-offset matrix
constraint off that frame; because the frame swings as the hand moves, the
maintained offset was re-expressed in a rotating basis and dragged the collar
even at ``limbLock = 0``. Never route this through a rotating frame's matrix.

**The cycle.** ``lock_root`` is *positioned* at the chain root but *driven*
from the socket, which is upstream of the push. Measuring from anything the
push moves would make root -> measure -> push -> root a DG cycle. The
consequence is that the lock does not see collar rotation; under a locked
limb the shoulder rigidly follows the chest. Breaking the cycle needs some
pre-push reference and this is the closest one available.

No global rig-scale concept exists in tik.maya or tik.trigger, so nothing is
normalised. If one is ever added, ``lockLength`` becomes ``lockLength *
globalScale`` on a single connection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import tik.maya as tm
from tik.maya import attribute

SUBTRACT = 2
SUM = 1


@dataclass
class LimbLock:
    """Everything the lock built."""

    lock_root: Any = None
    aim_frame: Any = None
    anchor: Any = None
    push: Any = None
    measure: Any = None
    lock_plug: Any = None
    current_plug: Any = None
    length_plug: Any = None
    target: Any = None


def _root_space_translate(node, rig_root, name: str):
    """``node``'s position expressed in the rig root's space.

    The module's four groups are locked at identity, so a transform parented
    under one of them has local channels in exactly this space -- which is
    what lets the delta below be added straight onto ``socket.translate``.
    """
    mult = tm.create_node("multMatrix", name=f"{name}_multMatrix")
    node["worldMatrix[0]"] >> mult["matrixIn[0]"]
    rig_root["worldInverseMatrix[0]"] >> mult["matrixIn[1]"]
    decompose = tm.create_node("decomposeMatrix", name=f"{name}_decomposeMatrix")
    mult["matrixSum"] >> decompose["inputMatrix"]
    return decompose["outputTranslate"]


def build_limb_lock(
    rig,
    *,
    socket,
    chain_root,
    driver,
    control,
    target,
    name: str = "",
) -> LimbLock:
    """Build the limb lock network.

    Args:
        rig: The module's ``ModuleRig``.
        socket: The module's input socket. Drives ``lock_root`` (pre-push) and
            supplies the rest position and orientation of ``target``.
        chain_root: Where ``lock_root`` is *positioned* -- the limb's first
            joint. Distinct from ``socket``, which for an arm sits at the
            collar, so measuring from it would lock collar-to-hand and seed
            ``lockLength`` with the wrong number.
        driver: What the rig follows at the far end (the IK tweak).
        control: Where the three animator attributes are added.
        target: The buffer everything in the module hangs off. It must sit
            between the socket and its consumers, including the auto-collar's
            ``rest_from``, or a world-pinned group downstream will discard the
            push.
        name: Extra name token.

    Returns:
        A :class:`LimbLock`.
    """
    result = LimbLock()
    result.target = target
    tm.ensure_plugin("matrixNodes")

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
    # child at translateX = d lands d units from the hand along that line.
    result.aim_frame = tm.AimFrame.create(
        driver,
        result.lock_root,
        result.lock_root,
        aim_axis=(1.0, 0.0, 0.0),
        twist_axis="X",
        parent=rig.groups.rig,
        name=rig.name(name, "lockAim"),
    )
    frame = result.aim_frame.transform.long_name
    result.anchor = tm.Transform.create(name=rig.name(name, "lockAnchor"), parent=frame)
    result.push = tm.Transform.create(name=rig.name(name, "lockPush"), parent=frame)

    # The anchor sits on the unpushed root; the push sits at the length the
    # animator asked for, faded in by limbLock. At limbLock = 0 the two
    # coincide exactly, so the delta below is identically zero and the lock
    # is genuinely inert -- not merely small.
    result.measure.distance >> result.anchor["translateX"]
    blended = (result.length_plug - result.measure.distance) * result.lock_plug
    (blended + result.measure.distance) >> result.push["translateX"]

    # --- apply it as a translation, never as a matrix ---------------------
    push_at = _root_space_translate(result.push, rig.rig_root, rig.name(name, "lockPushAt"))
    anchor_at = _root_space_translate(
        result.anchor, rig.rig_root, rig.name(name, "lockAnchorAt")
    )
    delta = tm.create_node("plusMinusAverage", name=rig.name(name, "lockDelta"))
    delta["operation"].value = SUBTRACT
    push_at >> delta["input3D[0]"]
    anchor_at >> delta["input3D[1]"]

    total = tm.create_node("plusMinusAverage", name=rig.name(name, "lockTotal"))
    total["operation"].value = SUM
    socket["translate"] >> total["input3D[0]"]
    delta["output3D"] >> total["input3D[1]"]
    total["output3D"] >> target["translate"]

    # Translation is ours; the target still takes its orientation from the
    # socket so the collar keeps following the chest.
    tm.MatrixConstraint.create(
        socket, target, maintain_offset=True, skip_translate="xyz"
    )
    return result

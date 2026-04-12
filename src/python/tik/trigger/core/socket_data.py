"""Data classes for socket and plug connection points in rig modules.

Sockets and plugs are the connection points that allow modules to be wired
together in a rig hierarchy. Plugs are output points, sockets are input points.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class JointType(Enum):
    """Classification of joint roles in the rig.

    Attributes:
        DEFINITIVE: Deformation joint - final output to skin
        RIG: Intermediate rigging joint
        CONTROL: Control joint - for controller hierarchy
        GUIDE: Guide joint - temporary, for positioning
    """

    DEFINITIVE = "jDef"
    RIG = "jRig"
    CONTROL = "jCont"
    GUIDE = "jInit"


@dataclass
class Plug:
    """Output connection point on a module.

    A plug is the "root" or "output" joint that parent modules consume.
    For example, a spine module's plug connects to a body module.

    Attributes:
        name: Identifier for this plug (e.g., "rootPlug", "limbPlug")
        joint_name: The actual Maya node name
        joint_type: Classification of the joint's role
        parent_socket: Optional reference to what this plug connects TO
    """

    name: str
    joint_name: str = ""
    joint_type: JointType = JointType.DEFINITIVE
    parent_socket: Optional[str] = None


@dataclass
class Socket:
    """Input connection point on a module where child modules attach.

    A socket is where child modules' plugs connect. For example,
    an arm module might have a socket for "hand" where a hand module connects.

    Attributes:
        name: Identifier for this socket (e.g., "hand", "root")
        joint_name: The actual Maya node name
        joint_type: Classification of the joint's role
        accepts_plugs: List of plug types this socket can accept
        connected_plug: Reference to currently connected plug, if any
    """

    name: str
    joint_name: str = ""
    joint_type: JointType = JointType.DEFINITIVE
    accepts_plugs: list[str] = field(default_factory=list)
    connected_plug: Optional[str] = None


@dataclass
class ModuleConnectors:
    """Container for a module's plugs and sockets.

    Attributes:
        plugs: Dict mapping plug name -> Plug instance
        sockets: Dict mapping socket name -> Socket instance
    """

    plugs: dict[str, Plug] = field(default_factory=dict)
    sockets: dict[str, Socket] = field(default_factory=dict)

"""Dataclasses for structured data in tik.trigger.

This module provides typed data structures for representing guides, modules,
actions, and sessions. Using dataclasses ensures consistency and enables
clear data contracts throughout the system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class GuideData:
    """Data for a single guide joint.

    Attributes:
        name: Name of the guide.
        position: XYZ position in world space.
        rotation: XYZ rotation Euler angles in degrees.
        side: Side designation ('C' for center, 'L' for left, 'R' for right).
        parent: Name of the parent guide, if any.
        children: List of child guide names.
    """

    name: str
    position: tuple[float, float, float]
    rotation: tuple[float, float, float]
    side: str = "C"
    parent: Optional[str] = None
    children: list[str] = field(default_factory=list)


@dataclass
class ModuleInstanceData:
    """Data for an instantiated module in a session.

    Attributes:
        module_type: Type identifier (e.g., 'bipedArm').
        instance_id: Unique identifier for this instance.
        guides: List of guide data for this module.
        settings: Module-specific settings as key-value pairs.
    """

    module_type: str
    instance_id: str
    guides: list[GuideData] = field(default_factory=list)
    settings: dict = field(default_factory=dict)


@dataclass
class ActionInstanceData:
    """Data for an instantiated action in a session.

    Attributes:
        action_type: Type identifier (e.g., 'jointify').
        order: Execution order in the build pipeline.
        settings: Action-specific settings as key-value pairs.
        enabled: Whether the action is enabled for execution.
    """

    action_type: str
    order: int
    settings: dict = field(default_factory=dict)
    enabled: bool = True


@dataclass
class SessionMetadata:
    """Metadata for a session.

    Attributes:
        version: File format version.
        author: Author name who created the session.
        created_at: ISO format creation timestamp.
        modified_at: ISO format last modification timestamp.
        maya_version: Maya version used for this session.
        comment: Optional description or notes.
    """

    version: str = "2.0"
    author: str = ""
    created_at: str = ""
    modified_at: str = ""
    maya_version: str = ""
    comment: str = ""


@dataclass
class SessionData:
    """Root session data structure.

    This is the top-level data container for all session information including
    modules, actions, and metadata.

    Attributes:
        version: File format version.
        modules: List of module instances in the session.
        actions: List of action instances in the session.
        metadata: Session metadata.
    """

    version: str = "2.0"
    modules: list[ModuleInstanceData] = field(default_factory=list)
    actions: list[ActionInstanceData] = field(default_factory=list)
    metadata: SessionMetadata = field(default_factory=SessionMetadata)


@dataclass
class UIDefinition:
    """UI definition for an action or module settings panel.

    Attributes:
        key: Settings key.
        display_name: User-facing label.
        setting_type: Data type (boolean, string, integer, float, etc.).
        value: Default value.
        items: Optional list of items for combo type.
        min_value: Optional minimum for spinner types.
        max_value: Optional maximum for spinner types.
    """

    key: str
    display_name: str
    setting_type: str
    value: Any = None
    items: Optional[list[str]] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None


@dataclass
class ActionDefinition:
    """Complete definition for an action.

    Attributes:
        name: Unique action identifier.
        ui_definition: List of UI definitions for settings.
          Each UIDefinition's value field serves as the default.
    """

    name: str
    ui_definition: list[UIDefinition] = field(default_factory=list)


@dataclass
class ModuleDefinition:
    """Complete definition for a module.

    Attributes:
        name: Unique module identifier.
        ui_definition: List of UI definitions for settings.
        data: Module-specific data (positions, segments, etc.).
    """

    name: str
    ui_definition: list[UIDefinition] = field(default_factory=list)
    data: dict = field(default_factory=dict)


@dataclass
class ConnectionData:
    """Serialized module connection for session persistence.

    Represents a socket-to-plug connection between two modules
    that can be saved and restored during session load.

    Attributes:
        parent_module: Instance ID of the module providing the plug.
        parent_plug: Name of the plug on the parent module.
        child_module: Instance ID of the module receiving the connection.
        child_socket: Name of the socket on the child module.
    """

    parent_module: str
    parent_plug: str
    child_module: str
    child_socket: str

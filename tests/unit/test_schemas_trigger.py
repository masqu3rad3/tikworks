"""Tests for tik.trigger.core.schemas module."""

import pytest


class TestGuideData:
    """Tests for GuideData dataclass."""

    def test_guide_data_required_fields(self):
        """Test GuideData creation with required fields only."""
        from tik.trigger.core.schemas import GuideData

        guide = GuideData(
            name="root_joint",
            position=(0.0, 10.0, 0.0),
            rotation=(0.0, 0.0, 0.0),
        )
        assert guide.name == "root_joint"
        assert guide.position == (0.0, 10.0, 0.0)
        assert guide.rotation == (0.0, 0.0, 0.0)

    def test_guide_data_all_fields(self):
        """Test GuideData creation with all fields."""
        from tik.trigger.core.schemas import GuideData

        guide = GuideData(
            name="child_joint",
            position=(5.0, 10.0, 0.0),
            rotation=(0.0, 90.0, 0.0),
            side="L",
            parent="root_joint",
            children=["leaf_joint"],
        )
        assert guide.side == "L"
        assert guide.parent == "root_joint"
        assert guide.children == ["leaf_joint"]

    def test_guide_data_default_side(self):
        """Test GuideData default side is center."""
        from tik.trigger.core.schemas import GuideData

        guide = GuideData(
            name="center_joint",
            position=(0.0, 10.0, 0.0),
            rotation=(0.0, 0.0, 0.0),
        )
        assert guide.side == "C"

    def test_guide_data_default_parent(self):
        """Test GuideData default parent is None."""
        from tik.trigger.core.schemas import GuideData

        guide = GuideData(
            name="root",
            position=(0.0, 0.0, 0.0),
            rotation=(0.0, 0.0, 0.0),
        )
        assert guide.parent is None

    def test_guide_data_default_children(self):
        """Test GuideData default children is empty list."""
        from tik.trigger.core.schemas import GuideData

        guide = GuideData(
            name="leaf",
            position=(0.0, 5.0, 0.0),
            rotation=(0.0, 0.0, 0.0),
        )
        assert guide.children == []


class TestModuleInstanceData:
    """Tests for ModuleInstanceData dataclass."""

    def test_module_instance_data_required_fields(self):
        """Test ModuleInstanceData creation with required fields."""
        from tik.trigger.core.schemas import ModuleInstanceData

        instance = ModuleInstanceData(
            module_type="bipedArm",
            instance_id="arm_001",
        )
        assert instance.module_type == "bipedArm"
        assert instance.instance_id == "arm_001"

    def test_module_instance_data_with_guides(self):
        """Test ModuleInstanceData with guides list."""
        from tik.trigger.core.schemas import GuideData, ModuleInstanceData

        root_guide = GuideData(
            name="root",
            position=(0.0, 0.0, 0.0),
            rotation=(0.0, 0.0, 0.0),
        )
        instance = ModuleInstanceData(
            module_type="bipedArm",
            instance_id="arm_001",
            guides=[root_guide],
        )
        assert len(instance.guides) == 1
        assert instance.guides[0].name == "root"

    def test_module_instance_data_with_settings(self):
        """Test ModuleInstanceData with settings."""
        from tik.trigger.core.schemas import ModuleInstanceData

        instance = ModuleInstanceData(
            module_type="bipedArm",
            instance_id="arm_001",
            settings={"segments": 3, "radius": 1.5},
        )
        assert instance.settings["segments"] == 3
        assert instance.settings["radius"] == 1.5

    def test_module_instance_data_default_fields(self):
        """Test ModuleInstanceData default values."""
        from tik.trigger.core.schemas import ModuleInstanceData

        instance = ModuleInstanceData(
            module_type="spine",
            instance_id="spine_001",
        )
        assert instance.guides == []
        assert instance.settings == {}


class TestActionInstanceData:
    """Tests for ActionInstanceData dataclass."""

    def test_action_instance_data_required_fields(self):
        """Test ActionInstanceData creation with required fields."""
        from tik.trigger.core.schemas import ActionInstanceData

        action = ActionInstanceData(
            action_type="jointify",
            order=1,
        )
        assert action.action_type == "jointify"
        assert action.order == 1

    def test_action_instance_data_with_settings(self):
        """Test ActionInstanceData with settings."""
        from tik.trigger.core.schemas import ActionInstanceData

        action = ActionInstanceData(
            action_type="jointify",
            order=1,
            settings={"radius": 1.0, "orientation": "xyz"},
        )
        assert action.settings["radius"] == 1.0

    def test_action_instance_data_enabled_default(self):
        """Test ActionInstanceData default enabled is True."""
        from tik.trigger.core.schemas import ActionInstanceData

        action = ActionInstanceData(
            action_type="jointify",
            order=1,
        )
        assert action.enabled is True

    def test_action_instance_data_disabled(self):
        """Test ActionInstanceData with enabled=False."""
        from tik.trigger.core.schemas import ActionInstanceData

        action = ActionInstanceData(
            action_type="jointify",
            order=1,
            enabled=False,
        )
        assert action.enabled is False


class TestSessionMetadata:
    """Tests for SessionMetadata dataclass."""

    def test_session_metadata_default_values(self):
        """Test SessionMetadata default values."""
        from tik.trigger.core.schemas import SessionMetadata

        metadata = SessionMetadata()
        assert metadata.version == "2.0"
        assert metadata.author == ""
        assert metadata.created_at == ""
        assert metadata.modified_at == ""
        assert metadata.maya_version == ""
        assert metadata.comment == ""

    def test_session_metadata_custom_values(self):
        """Test SessionMetadata with custom values."""
        from tik.trigger.core.schemas import SessionMetadata

        metadata = SessionMetadata(
            version="2.0",
            author="John Doe",
            created_at="2026-01-15T10:30:00",
            modified_at="2026-01-16T14:45:00",
            maya_version="Maya2024",
            comment="Initial rig setup",
        )
        assert metadata.author == "John Doe"
        assert metadata.maya_version == "Maya2024"
        assert metadata.comment == "Initial rig setup"


class TestSessionData:
    """Tests for SessionData dataclass."""

    def test_session_data_default_values(self):
        """Test SessionData default values."""
        from tik.trigger.core.schemas import SessionData, SessionMetadata

        session = SessionData()
        assert session.version == "2.0"
        assert session.modules == []
        assert session.actions == []
        assert isinstance(session.metadata, SessionMetadata)
        assert session.metadata.version == "2.0"

    def test_session_data_with_modules_and_actions(self):
        """Test SessionData with modules and actions."""
        from tik.trigger.core.schemas import (
            ActionInstanceData,
            GuideData,
            ModuleInstanceData,
            SessionData,
        )

        guide = GuideData(
            name="root",
            position=(0.0, 0.0, 0.0),
            rotation=(0.0, 0.0, 0.0),
        )
        module = ModuleInstanceData(
            module_type="bipedArm",
            instance_id="arm_001",
            guides=[guide],
        )
        action = ActionInstanceData(
            action_type="jointify",
            order=1,
        )
        session = SessionData(
            modules=[module],
            actions=[action],
        )
        assert len(session.modules) == 1
        assert len(session.actions) == 1
        assert session.modules[0].instance_id == "arm_001"
        assert session.actions[0].action_type == "jointify"


class TestUIDefinition:
    """Tests for UIDefinition dataclass."""

    def test_ui_definition_required_fields(self):
        """Test UIDefinition creation with required fields."""
        from tik.trigger.core.schemas import UIDefinition

        ui_def = UIDefinition(
            key="enabled",
            display_name="Enable Feature",
            setting_type="boolean",
        )
        assert ui_def.key == "enabled"
        assert ui_def.display_name == "Enable Feature"
        assert ui_def.setting_type == "boolean"

    def test_ui_definition_with_value(self):
        """Test UIDefinition with default value."""
        from tik.trigger.core.schemas import UIDefinition

        ui_def = UIDefinition(
            key="segment_count",
            display_name="Segment Count",
            setting_type="integer",
            value=3,
        )
        assert ui_def.value == 3

    def test_ui_definition_with_items(self):
        """Test UIDefinition with items for combo type."""
        from tik.trigger.core.schemas import UIDefinition

        ui_def = UIDefinition(
            key="orientation",
            display_name="Orientation",
            setting_type="combo",
            items=["xyz", "xzy", "zyx"],
        )
        assert ui_def.items == ["xyz", "xzy", "zyx"]

    def test_ui_definition_with_range(self):
        """Test UIDefinition with min/max for spinner types."""
        from tik.trigger.core.schemas import UIDefinition

        ui_def = UIDefinition(
            key="radius",
            display_name="Radius",
            setting_type="spinnerFloat",
            value=1.0,
            min_value=0.1,
            max_value=10.0,
        )
        assert ui_def.min_value == 0.1
        assert ui_def.max_value == 10.0


class TestActionDefinition:
    """Tests for ActionDefinition dataclass."""

    def test_action_definition_required_fields(self):
        """Test ActionDefinition creation with required fields."""
        from tik.trigger.core.schemas import ActionDefinition

        action_def = ActionDefinition(name="jointify")
        assert action_def.name == "jointify"

    def test_action_definition_with_ui_definition(self):
        """Test ActionDefinition with UI definition.

        Default values come from UIDefinition.value fields, not a separate defaults dict.
        """
        from tik.trigger.core.schemas import ActionDefinition, UIDefinition

        ui_def = UIDefinition(
            key="radius",
            display_name="Radius",
            setting_type="float",
            value=1.0,
        )
        action_def = ActionDefinition(
            name="jointify",
            ui_definition=[ui_def],
        )
        assert len(action_def.ui_definition) == 1
        assert action_def.ui_definition[0].value == 1.0


class TestModuleDefinition:
    """Tests for ModuleDefinition dataclass."""

    def test_module_definition_required_fields(self):
        """Test ModuleDefinition creation with required fields."""
        from tik.trigger.core.schemas import ModuleDefinition

        mod_def = ModuleDefinition(name="bipedArm")
        assert mod_def.name == "bipedArm"

    def test_module_definition_with_data(self):
        """Test ModuleDefinition with module data."""
        from tik.trigger.core.schemas import ModuleDefinition, UIDefinition

        ui_def = UIDefinition(
            key="segments",
            display_name="Segments",
            setting_type="integer",
            value=3,
        )
        mod_def = ModuleDefinition(
            name="bipedArm",
            ui_definition=[ui_def],
            data={"default_positions": [[0, 0, 0], [0, 5, 0], [0, 10, 0]]},
        )
        assert mod_def.data["default_positions"][0] == [0, 0, 0]

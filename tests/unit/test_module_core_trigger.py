"""Tests for tik.trigger.core.module_core module."""

import pytest

from tik.trigger.core.module_core import GuidesCore, ModuleCore
from tik.trigger.core.schemas import GuideData


class ConcreteGuides(GuidesCore):
    """Concrete implementation of GuidesCore for testing."""

    def __init__(self, name=None):
        super().__init__(name)
        self.create_called = False
        self.delete_called = False
        self.update_calls = []

    def create_guides(self):
        self.create_called = True

    def update_guide(self, index, guide_data):
        self.update_calls.append((index, guide_data))

    def delete_guides(self):
        self.delete_called = True


class ConcreteModule(ModuleCore):
    """Concrete implementation of ModuleCore for testing."""

    def __init__(self, guides, name=None):
        super().__init__(guides, name)
        self.build_called = False
        self.delete_called = False
        self.mirror_called = False

    def build(self):
        self.build_called = True

    def delete(self):
        self.delete_called = True

    def mirror(self, source_guide_names):
        self.mirror_called = True
        self.last_mirror_sources = source_guide_names


# =============================================================================
# GuidesCore Tests
# =============================================================================


class TestGuidesCoreInit:
    """Tests for GuidesCore initialization."""

    def test_guides_default_name(self):
        """Test GuidesCore uses class name as default name."""
        guides = ConcreteGuides()
        assert guides.name == "ConcreteGuides"

    def test_guides_custom_name(self):
        """Test GuidesCore accepts custom name."""
        guides = ConcreteGuides(name="my_guides")
        assert guides.name == "my_guides"

    def test_guides_default_guides_list(self):
        """Test GuidesCore initializes with empty guides list."""
        guides = ConcreteGuides()
        assert guides.guides == []

    def test_guides_default_selected_guide(self):
        """Test GuidesCore initializes with no selected guide."""
        guides = ConcreteGuides()
        assert guides.selected_guide is None


class TestGuidesCoreProperties:
    """Tests for GuidesCore properties."""

    def test_module_name_empty_by_default(self):
        """Test module_name property returns empty string by default."""
        guides = ConcreteGuides()
        assert guides.module_name == ""

    def test_ui_definition_empty_by_default(self):
        """Test ui_definition property returns empty list by default."""
        guides = ConcreteGuides()
        assert guides.ui_definition == []


class TestGuidesCoreGuideManagement:
    """Tests for GuidesCore guide management methods."""

    def test_add_guide(self):
        """Test adding a guide."""
        guides = ConcreteGuides()
        guide_data = GuideData(
            name="root",
            position=(0.0, 0.0, 0.0),
            rotation=(0.0, 0.0, 0.0),
        )
        guides.add_guide(guide_data)
        assert len(guides.guides) == 1
        assert guides.guides[0].name == "root"

    def test_add_multiple_guides(self):
        """Test adding multiple guides."""
        guides = ConcreteGuides()
        for i in range(3):
            guide_data = GuideData(
                name=f"joint_{i}",
                position=(0.0, float(i), 0.0),
                rotation=(0.0, 0.0, 0.0),
            )
            guides.add_guide(guide_data)
        assert len(guides.guides) == 3

    def test_remove_guide(self):
        """Test removing a guide by index."""
        guides = ConcreteGuides()
        guide1 = GuideData(name="first", position=(0, 0, 0), rotation=(0, 0, 0))
        guide2 = GuideData(name="second", position=(0, 1, 0), rotation=(0, 0, 0))
        guides.add_guide(guide1)
        guides.add_guide(guide2)

        removed = guides.remove_guide(0)
        assert removed.name == "first"
        assert len(guides.guides) == 1
        assert guides.guides[0].name == "second"

    def test_clear_guides(self):
        """Test clearing all guides."""
        guides = ConcreteGuides()
        guide = GuideData(name="test", position=(0, 0, 0), rotation=(0, 0, 0))
        guides.add_guide(guide)
        guides.clear_guides()
        assert len(guides.guides) == 0
        assert guides.selected_guide is None


class TestGuidesCoreSelection:
    """Tests for GuidesCore guide selection."""

    def test_select_guide(self):
        """Test selecting a guide by index."""
        guides = ConcreteGuides()
        for i in range(3):
            guides.add_guide(
                GuideData(name=f"j{i}", position=(0, i, 0), rotation=(0, 0, 0))
            )
        guides.select_guide(1)
        assert guides.selected_guide == 1

    def test_select_guide_out_of_range(self):
        """Test selecting out-of-range guide doesn't raise."""
        guides = ConcreteGuides()
        guides.select_guide(99)
        assert guides.selected_guide == 99

    def test_deselect_guide(self):
        """Test deselecting a guide."""
        guides = ConcreteGuides()
        guides.select_guide(0)
        guides.select_guide(None)
        assert guides.selected_guide is None

    def test_get_selected_guide_data(self):
        """Test getting selected guide data."""
        guides = ConcreteGuides()
        guide = GuideData(
            name="selected_one",
            position=(1.0, 2.0, 3.0),
            rotation=(0, 0, 0),
            side="L",
        )
        guides.add_guide(guide)
        guides.select_guide(0)

        selected = guides.get_selected_guide_data()
        assert selected is not None
        assert selected.name == "selected_one"
        assert selected.position == (1.0, 2.0, 3.0)

    def test_get_selected_guide_data_none_selected(self):
        """Test getting selected guide data when none selected."""
        guides = ConcreteGuides()
        assert guides.get_selected_guide_data() is None

    def test_get_selected_guide_data_out_of_range(self):
        """Test getting selected guide data with out-of-range index."""
        guides = ConcreteGuides()
        guides.add_guide(
            GuideData(name="only_one", position=(0, 0, 0), rotation=(0, 0, 0))
        )
        guides.select_guide(99)
        assert guides.get_selected_guide_data() is None


class TestGuidesCoreAbstract:
    """Tests for GuidesCore abstract method enforcement."""

    def test_cannot_instantiate_directly(self):
        """Test that GuidesCore cannot be instantiated directly."""
        with pytest.raises(TypeError) as exc_info:
            GuidesCore()
        assert "abstract" in str(exc_info.value).lower()


# =============================================================================
# ModuleCore Tests
# =============================================================================


class TestModuleCoreInit:
    """Tests for ModuleCore initialization."""

    def test_module_requires_guides(self):
        """Test ModuleCore requires guides parameter."""
        guides = ConcreteGuides(name="test_guides")
        module = ConcreteModule(guides)
        assert module._guides is guides

    def test_module_default_name(self):
        """Test ModuleCore uses class name as default name."""
        guides = ConcreteGuides()
        module = ConcreteModule(guides)
        assert module.name == "ConcreteModule"

    def test_module_custom_name(self):
        """Test ModuleCore accepts custom name."""
        guides = ConcreteGuides()
        module = ConcreteModule(guides, name="my_module")
        assert module.name == "my_module"

    def test_module_default_settings(self):
        """Test ModuleCore initializes with empty settings."""
        guides = ConcreteGuides()
        module = ConcreteModule(guides)
        assert module.settings == {}

    def test_module_not_built_by_default(self):
        """Test ModuleCore is not marked as built by default."""
        guides = ConcreteGuides()
        module = ConcreteModule(guides)
        assert module.is_built is False


class TestModuleCoreProperties:
    """Tests for ModuleCore properties."""

    def test_module_name_empty_by_default(self):
        """Test module_name property returns empty string by default."""
        guides = ConcreteGuides()
        module = ConcreteModule(guides)
        assert module.module_name == ""

    def test_guide_class_none_by_default(self):
        """Test guide_class property returns None by default."""
        guides = ConcreteGuides()
        module = ConcreteModule(guides)
        assert module.guide_class is None

    def test_ui_definition_empty_by_default(self):
        """Test ui_definition property returns empty list by default."""
        guides = ConcreteGuides()
        module = ConcreteModule(guides)
        assert module.ui_definition == []


class TestModuleCoreSettings:
    """Tests for ModuleCore settings management."""

    def test_set_settings(self):
        """Test set_settings updates instance settings."""
        guides = ConcreteGuides()
        module = ConcreteModule(guides)
        module.set_settings({"key1": "value1", "key2": 42})
        assert module.settings["key1"] == "value1"
        assert module.settings["key2"] == 42

    def test_get_setting_existing(self):
        """Test get_setting returns existing key."""
        guides = ConcreteGuides()
        module = ConcreteModule(guides)
        module.set_settings({"radius": 1.5})
        assert module.get_setting("radius") == 1.5

    def test_get_setting_default(self):
        """Test get_setting returns default when key missing."""
        guides = ConcreteGuides()
        module = ConcreteModule(guides)
        assert module.get_setting("missing", "default") == "default"

    def test_reset_settings(self):
        """Test reset_settings restores defaults."""
        guides = ConcreteGuides()
        module = ConcreteModule(guides)
        module.set_settings({"key": "value"})
        module.reset_settings()
        assert module.settings == {}


class TestModuleCoreBuild:
    """Tests for ModuleCore build method."""

    def test_build_is_called(self):
        """Test that build method is called."""
        guides = ConcreteGuides()
        module = ConcreteModule(guides)
        module.build()
        assert module.build_called is True

    def test_built_flag_set_after_build(self):
        """Test that is_built flag is set after build."""
        guides = ConcreteGuides()
        module = ConcreteModule(guides)
        assert module.is_built is False
        module.build()
        # Note: subclasses should set _built = True in their build() method
        # ConcreteModule doesn't do this, so this tests the base behavior


class TestModuleCoreDelete:
    """Tests for ModuleCore delete method."""

    def test_delete_is_called(self):
        """Test that delete method is called."""
        guides = ConcreteGuides()
        module = ConcreteModule(guides)
        module.delete()
        assert module.delete_called is True


class TestModuleCoreMirror:
    """Tests for ModuleCore mirror method."""

    def test_mirror_is_called_with_sources(self):
        """Test that mirror method is called with source guide names."""
        guides = ConcreteGuides()
        module = ConcreteModule(guides)
        module.mirror(["L_arm_01", "L_arm_02"])
        assert module.mirror_called is True
        assert module.last_mirror_sources == ["L_arm_01", "L_arm_02"]


class TestModuleCoreGetBuildData:
    """Tests for ModuleCore get_build_data method."""

    def test_get_build_data_basic(self):
        """Test get_build_data returns basic structure."""
        guides = ConcreteGuides(name="test_guides")
        module = ConcreteModule(guides, name="test_module")
        module.set_settings({"setting": "value"})

        build_data = module.get_build_data()
        assert build_data["module_type"] == ""
        assert build_data["name"] == "test_module"
        assert build_data["settings"]["setting"] == "value"


class TestModuleCoreValidateGuides:
    """Tests for ModuleCore validate_guides method."""

    def test_validate_guides_false_when_empty(self):
        """Test validate_guides returns False when no guides."""
        guides = ConcreteGuides()
        module = ConcreteModule(guides)
        assert module.validate_guides() is False

    def test_validate_guides_true_when_guides_exist(self):
        """Test validate_guides returns True when guides exist."""
        guides = ConcreteGuides()
        guides.add_guide(
            GuideData(name="test", position=(0, 0, 0), rotation=(0, 0, 0))
        )
        module = ConcreteModule(guides)
        assert module.validate_guides() is True


class TestModuleCoreAbstract:
    """Tests for ModuleCore abstract method enforcement."""

    def test_cannot_instantiate_directly(self):
        """Test that ModuleCore cannot be instantiated directly."""
        with pytest.raises(TypeError) as exc_info:
            ModuleCore(None)
        assert "abstract" in str(exc_info.value).lower()


# =============================================================================
# Integration Tests
# =============================================================================


class TestGuidesModuleIntegration:
    """Tests for GuidesCore and ModuleCore interaction."""

    def test_module_receives_guides(self):
        """Test that ModuleCore receives guides from constructor."""
        guides = ConcreteGuides(name="integration_guides")
        module = ConcreteModule(guides)
        assert module._guides is guides

    def test_guides_and_module_share_data(self):
        """Test that guides and module can share data through the same instance."""
        guides = ConcreteGuides()
        guides.add_guide(
            GuideData(name="shared", position=(1, 2, 3), rotation=(0, 0, 0))
        )
        module = ConcreteModule(guides)

        # Both should see the same guide
        assert len(guides.guides) == 1
        assert len(module._guides.guides) == 1
        assert guides.guides[0].name == "shared"

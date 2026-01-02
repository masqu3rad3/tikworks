import pytest
from maya import cmds
from tik.maya.types.locator import Locator
from tik.maya.types.transform import Transform

class TestLocator:
    def test_create_locator(self):
        loc = Locator.create()
        assert isinstance(loc, Locator)
        assert cmds.nodeType(loc.name) == "locator"
        # Locator wraps the shape, so transform property should be the parent
        assert isinstance(loc.transform, Transform)

    def test_create_locator_with_name(self):
        loc = Locator.create(name="myLoc")
        assert loc.transform.name == "myLoc"
        assert loc.name == "myLocShape" # Default Maya naming behavior

    def test_init_from_existing(self):
        # Create using cmds directly
        res = cmds.spaceLocator(name="existingLoc")
        transform_name = res[0]

        # Wrap using transform name
        loc = Locator(transform_name)
        assert isinstance(loc, Locator)
        assert loc.transform.name == "existingLoc"

        # Wrap using shape name
        shape_name = cmds.listRelatives(transform_name, shapes=True)[0]
        loc_shape = Locator(shape_name)
        assert isinstance(loc_shape, Locator)
        assert loc_shape.name == shape_name

    def test_create_returns_locator_instance(self):
        # Verify the return type of create explicitly
        loc = Locator.create(name="returnTest")
        assert type(loc) is Locator


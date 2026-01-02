import sys
import pytest
from maya import cmds
from tik.maya.core.decorators import add_aliases, alias, undo, keepselection

# Helper for alias test at module level
@alias("module_level_alias")
def module_level_func():
    return "module_level"

class TestAddAliases:
    def test_add_aliases_proxies_property(self):
        @add_aliases({"original": "aliased"})
        class MyClass:
            @property
            def original(self):
                return "value"

        obj = MyClass()
        assert obj.original == "value"
        assert obj.aliased == "value"

    def test_add_aliases_proxies_method(self):
        @add_aliases({"original": "aliased"})
        class MyClass:
            def original(self):
                return "called"

        obj = MyClass()
        assert obj.original() == "called"
        assert obj.aliased() == "called"

class TestAlias:
    def test_alias_injects_into_module(self):
        # The decorator runs at definition time.
        # module_level_func is defined at module level of this test file.
        current_module = sys.modules[__name__]

        assert hasattr(current_module, "module_level_alias")
        assert current_module.module_level_alias is module_level_func
        assert current_module.module_level_alias() == "module_level"

    def test_alias_dynamic_injection(self):
        # Test defining a function inside a method
        @alias("dynamic_alias")
        def local_func():
            return "dynamic"

        current_module = sys.modules[__name__]
        assert hasattr(current_module, "dynamic_alias")
        assert current_module.dynamic_alias is local_func
        assert current_module.dynamic_alias() == "dynamic"

class TestUndo:
    def test_undo_groups_operations(self):
        cmds.file(new=True, force=True)

        @undo
        def create_two_cubes():
            cmds.polyCube(name="cube1")
            cmds.polyCube(name="cube2")

        create_two_cubes()

        assert cmds.objExists("cube1")
        assert cmds.objExists("cube2")

        # Undo should remove both because they are in one chunk
        cmds.undo()

        assert not cmds.objExists("cube1")
        assert not cmds.objExists("cube2")

    def test_undo_propagates_exception(self):
        cmds.file(new=True, force=True)

        @undo
        def fail_operation():
            cmds.polyCube(name="cube1")
            raise ValueError("Intentional Failure")

        # This test is expected to fail if the decorator swallows the exception
        with pytest.raises(ValueError, match="Intentional Failure"):
            fail_operation()

        # Verify we can undo the partial operation
        assert cmds.objExists("cube1")
        cmds.undo()
        assert not cmds.objExists("cube1")

class TestKeepSelection:
    def test_keepselection_restores_selection(self):
        cmds.file(new=True, force=True)
        c1 = cmds.polyCube(name="c1")[0]
        c2 = cmds.polyCube(name="c2")[0]

        cmds.select(c1)

        @keepselection
        def select_other():
            cmds.select(c2)
            assert cmds.ls(selection=True)[0] == "c2"

        select_other()

        assert cmds.ls(selection=True)[0] == "c1"

    def test_keepselection_restores_selection_on_exception(self):
        cmds.file(new=True, force=True)
        c1 = cmds.polyCube(name="c1")[0]
        c2 = cmds.polyCube(name="c2")[0]

        cmds.select(c1)

        @keepselection
        def fail_select():
            cmds.select(c2)
            raise ValueError("Fail")

        with pytest.raises(ValueError):
            fail_select()

        assert cmds.ls(selection=True)[0] == "c1"


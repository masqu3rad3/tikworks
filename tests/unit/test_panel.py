"""Unit tests for the Panel construct."""

from unittest.mock import patch

import pytest
from maya import cmds

from tik.maya.constructs.panel import Panel
from tik.maya.types.camera import Camera
from tik.maya.types.transform import Transform


@pytest.fixture
def mock_ui_cmds():
    """Mock Maya UI commands that fail in standalone mode."""
    with (
        patch("maya.cmds.window") as m_window,
        patch("maya.cmds.paneLayout"),
        patch("maya.cmds.modelPanel") as m_modelPanel,
        patch("maya.cmds.modelEditor") as m_modelEditor,
        patch("maya.cmds.showWindow") as m_showWindow,
        patch("maya.cmds.deleteUI") as m_deleteUI,
        patch("maya.cmds.getPanel") as m_getPanel,
    ):

        # Setup defaults
        m_window.return_value = "tik_panel_window"
        m_modelPanel.return_value = "tik_panel"
        m_getPanel.return_value = []

        yield {
            "window": m_window,
            "modelPanel": m_modelPanel,
            "modelEditor": m_modelEditor,
            "getPanel": m_getPanel,
            "deleteUI": m_deleteUI,
            "showWindow": m_showWindow,
        }


def test_init_with_camera_name(mock_ui_cmds):
    """Test initializing Panel with a camera name (transform)."""
    cam_shape = cmds.createNode("camera")
    cam_trans = cmds.listRelatives(cam_shape, p=True)[0]

    panel = Panel(cam_trans, inherit=False)

    assert panel._camera.name == cam_shape
    mock_ui_cmds["window"].assert_called_once()
    mock_ui_cmds["modelPanel"].assert_called_with(camera=cam_shape)


def test_init_with_camera_shape_name(mock_ui_cmds):
    """Test initializing Panel with a camera shape name."""
    cam_shape = cmds.createNode("camera")

    panel = Panel(cam_shape, inherit=False)

    assert panel._camera.name == cam_shape


def test_init_with_camera_wrapper(mock_ui_cmds):
    """Test initializing Panel with a Camera wrapper."""
    cam_shape = cmds.createNode("camera")
    cam_wrapper = Camera(cam_shape)

    panel = Panel(cam_wrapper, inherit=False)

    assert panel._camera.name == cam_shape


def test_init_with_transform_wrapper(mock_ui_cmds):
    """Test initializing Panel with a Transform wrapper."""
    cam_shape = cmds.createNode("camera")
    cam_trans = cmds.listRelatives(cam_shape, p=True)[0]
    trans_wrapper = Transform(cam_trans)

    panel = Panel(trans_wrapper, inherit=False)

    assert panel._camera.name == cam_shape


def test_init_invalid_camera(mock_ui_cmds):
    """Test initializing Panel with invalid camera."""
    with pytest.raises(ValueError):
        Panel("non_existent_camera")

    cube = cmds.polyCube()[0]
    with pytest.raises(ValueError):
        Panel(cube)


def test_capture_camera_state(mock_ui_cmds):
    """Test that camera state is captured on init."""
    cam_shape = cmds.createNode("camera")

    # Set some non-default values
    cmds.setAttr(f"{cam_shape}.displayResolution", True)
    cmds.setAttr(f"{cam_shape}.overscan", 1.5)

    panel = Panel(cam_shape, inherit=False)

    assert panel._original_camera_state["displayResolution"] is True
    assert panel._original_camera_state["overscan"] == 1.5


def test_inherit_panel_properties(mock_ui_cmds):
    """Test inheriting properties from existing panel."""
    cam_shape = cmds.createNode("camera")

    # Mock existing panels
    mock_ui_cmds["getPanel"].return_value = ["modelPanel1", "modelPanel2"]

    # Mock modelPanel query to return our camera for modelPanel1
    def model_panel_side_effect(*args, **kwargs):
        # If querying
        if kwargs.get("q") or kwargs.get("query"):
            if args and args[0] == "modelPanel1" and kwargs.get("camera"):
                return cam_shape
            return "otherCamera"
        # If creating
        return "tik_panel"

    mock_ui_cmds["modelPanel"].side_effect = model_panel_side_effect

    # Mock modelEditor query on source panel
    def model_editor_side_effect(*args, **kwargs):
        # If querying source panel
        if (
            args
            and args[0] == "modelPanel1"
            and (kwargs.get("q") or kwargs.get("query"))
        ):
            if kwargs.get("grid"):
                return True
            if kwargs.get("polymeshes"):
                return False
        return None

    mock_ui_cmds["modelEditor"].side_effect = model_editor_side_effect

    Panel(cam_shape, inherit=True)

    # Verify modelEditor was called to set properties on new panel
    # We expect calls like: cmds.modelEditor('tik_panel', e=True, grid=True)
    # Note: 'tik_panel' is the return value of mocked modelPanel creation

    # Check if grid was set
    calls = mock_ui_cmds["modelEditor"].mock_calls
    grid_call_found = False
    for call in calls:
        # call is like call('tik_panel', e=True, grid=True)
        if (
            len(call.args) > 0
            and call.args[0] == "tik_panel"
            and call.kwargs.get("grid") is True
        ):
            grid_call_found = True
            break

    assert grid_call_found


def test_revert(mock_ui_cmds):
    """Test reverting camera settings."""
    cam_shape = cmds.createNode("camera")

    # Initial state
    cmds.setAttr(f"{cam_shape}.displayResolution", False)

    panel = Panel(cam_shape, inherit=False)

    # Change state
    cmds.setAttr(f"{cam_shape}.displayResolution", True)

    # Revert
    panel.revert()

    assert cmds.getAttr(f"{cam_shape}.displayResolution") is False


def test_close(mock_ui_cmds):
    """Test closing the panel."""
    cam_shape = cmds.createNode("camera")
    panel = Panel(cam_shape, inherit=False)

    # Mock existence checks
    mock_ui_cmds["modelPanel"].side_effect = lambda *args, **kwargs: (
        True if kwargs.get("exists") else "tik_panel"
    )
    with patch(
        "maya.cmds.window",
        side_effect=lambda *args, **kwargs: (
            True if kwargs.get("exists") else "tik_panel_window"
        ),
    ):
        panel.close()

    # Verify revert was called (implicit check via camera state if we changed it,
    # but here we just check deleteUI calls)
    assert mock_ui_cmds["deleteUI"].call_count >= 1


def test_camera_properties(mock_ui_cmds):
    """Test camera property getters and setters."""
    cam_shape = cmds.createNode("camera")
    panel = Panel(cam_shape, inherit=False)

    # Setter
    panel.display_resolution = True
    assert cmds.getAttr(f"{cam_shape}.displayResolution") is True

    # Getter
    assert panel.display_resolution is True


def test_panel_properties(mock_ui_cmds):
    """Test panel property getters and setters."""
    cam_shape = cmds.createNode("camera")
    panel = Panel(cam_shape, inherit=False)

    # Mock modelEditor for getter
    mock_ui_cmds["modelEditor"].return_value = True

    assert panel.grid is True
    mock_ui_cmds["modelEditor"].assert_called_with("tik_panel", query=True, grid=True)

    # Setter
    panel.grid = False
    mock_ui_cmds["modelEditor"].assert_called_with("tik_panel", edit=True, grid=False)


def test_set_preset(mock_ui_cmds):
    """Test setting presets."""
    cam_shape = cmds.createNode("camera")
    panel = Panel(cam_shape, inherit=False)

    panel.set_preset("preview")

    assert cmds.getAttr(f"{cam_shape}.displayResolution") is False
    assert cmds.getAttr(f"{cam_shape}.displayFilmGate") is False


def test_resolve_camera_string(mock_ui_cmds):
    """Test resolving camera from string."""
    cam_shape = cmds.createNode("camera")
    panel = Panel(cam_shape, inherit=False)
    assert panel._camera.name == cam_shape

    # Test resolving from transform name
    cam_trans = cmds.listRelatives(cam_shape, p=True)[0]
    panel_trans = Panel(cam_trans, inherit=False)
    assert panel_trans._camera.name == cam_shape


def test_all_camera_properties(mock_ui_cmds):
    """Test all camera properties."""
    cam_shape = cmds.createNode("camera")
    panel = Panel(cam_shape, inherit=False)

    props = [
        "display_field_chart",
        "display_gate_mask",
        "display_film_gate",
        "display_film_origin",
        "display_film_pivot",
        "display_safe_action",
        "display_safe_title",
        "overscan",
    ]

    for prop in props:
        # Set via property
        setattr(panel, prop, True)
        # Verify via cmds
        # Convert prop name to camelCase for cmds
        # e.g. display_field_chart -> displayFieldChart
        # overscan -> overscan
        parts = prop.split("_")
        attr_name = parts[0] + "".join(part.title() for part in parts[1:])

        # Special case for overscan which is float
        val = 1.5 if prop == "overscan" else True
        setattr(panel, prop, val)

        assert cmds.camera(cam_shape, q=True, **{attr_name: True}) == val

        # Get via property
        assert getattr(panel, prop) == val


def test_all_panel_properties(mock_ui_cmds):
    """Test all panel properties."""
    cam_shape = cmds.createNode("camera")
    panel = Panel(cam_shape, inherit=False)

    props = [
        ("all_objects", "allObjects"),
        ("display_appearance", "displayAppearance"),
        ("display_textures", "displayTextures"),
        ("use_default_material", "useDefaultMaterial"),
        ("polymeshes", "polymeshes"),
        ("nurbs_curves", "nurbsCurves"),
        ("nurbs_surfaces", "nurbsSurfaces"),
        ("joints", "joints"),
        ("locators", "locators"),
        ("pivots", "pivots"),
        ("image_plane", "imagePlane"),
        ("hud", "headsUpDisplay"),
        ("selection_highlighting", "selectionHiliteDisplay"),
        ("color_management_enabled", "cmEnabled"),
        ("manipulators", "manipulators"),
    ]

    for prop, flag in props:
        # Mock return value for getter
        mock_ui_cmds["modelEditor"].return_value = True
        assert getattr(panel, prop) is True
        mock_ui_cmds["modelEditor"].assert_called_with(
            "tik_panel", query=True, **{flag: True}
        )

        # Setter
        setattr(panel, prop, False)
        mock_ui_cmds["modelEditor"].assert_called_with(
            "tik_panel", edit=True, **{flag: False}
        )


def test_fit_view_and_activate(mock_ui_cmds):
    """Test fit_view and activate methods."""
    cam_shape = cmds.createNode("camera")
    panel = Panel(cam_shape, inherit=False)

    with (
        patch("maya.cmds.viewFit") as m_viewFit,
        patch("maya.cmds.setFocus") as m_setFocus,
    ):

        panel.fit_view(all=True)
        m_setFocus.assert_called_with("tik_panel")
        m_viewFit.assert_called_with(all=True)

        panel.activate()
        m_setFocus.assert_called_with("tik_panel")


def test_panel_name_property(mock_ui_cmds):
    """Test panel name property."""
    cam_shape = cmds.createNode("camera")
    panel = Panel(cam_shape, inherit=False)
    assert panel.name == "tik_panel"


def test_panel_camera_property(mock_ui_cmds):
    """Test panel camera property."""
    cam_shape = cmds.createNode("camera")
    panel = Panel(cam_shape, inherit=False)
    assert panel.camera.name == cam_shape


def test_resolve_camera_transform_no_shape(mock_ui_cmds):
    """Test resolving camera from transform with no camera shape."""
    trans = cmds.createNode("transform")
    # Create a non-camera shape
    cmds.createNode("mesh", p=trans)

    with pytest.raises(ValueError, match="has no camera shape"):
        Panel(trans, inherit=False)


def test_resolve_camera_invalid_type(mock_ui_cmds):
    """Test resolving camera with invalid type."""
    with pytest.raises(TypeError):
        Panel(123, inherit=False)


def test_editor_var_no_panel(mock_ui_cmds):
    """Test get/set editor var when panel is not created (or closed)."""
    cam_shape = cmds.createNode("camera")
    panel = Panel(cam_shape, inherit=False)

    # Force panel to None
    panel._panel = None

    # Set should do nothing (no error)
    panel.set_editor_var("grid", True)

    # Get should return None
    assert panel.get_editor_var("grid") is None


def test_panel_isolate_enable(mock_ui_cmds):
    """Test enabling isolation."""
    cam_shape = cmds.createNode("camera")
    panel = Panel(cam_shape, inherit=False)

    with patch("maya.cmds.isolateSelect") as m_isolateSelect:
        panel.isolate.enable()
        m_isolateSelect.assert_called_with("tik_panel", state=True)


def test_panel_isolate_add(mock_ui_cmds):
    """Test adding nodes to isolation."""
    cam_shape = cmds.createNode("camera")
    panel = Panel(cam_shape, inherit=False)
    cube = cmds.polyCube()[0]

    with (
        patch("maya.cmds.isolateSelect") as m_isolateSelect,
        patch("tik.maya.core.scene.select_nodes") as m_select_nodes,
    ):

        panel.isolate.add(cube)

        m_isolateSelect.assert_any_call("tik_panel", state=True)
        m_select_nodes.assert_called_with([cube])
        m_isolateSelect.assert_called_with("tik_panel", addSelected=True)


def test_panel_isolate_remove(mock_ui_cmds):
    """Test removing nodes from isolation."""
    cam_shape = cmds.createNode("camera")
    panel = Panel(cam_shape, inherit=False)
    cube = cmds.polyCube()[0]

    with (
        patch("maya.cmds.isolateSelect") as m_isolateSelect,
        patch("tik.maya.core.scene.select_nodes") as m_select_nodes,
    ):

        panel.isolate.remove(cube)

        m_isolateSelect.assert_any_call("tik_panel", state=True)
        m_select_nodes.assert_called_with([cube])
        m_isolateSelect.assert_called_with("tik_panel", removeSelected=True)


def test_panel_isolate_clear(mock_ui_cmds):
    """Test clearing isolation."""
    cam_shape = cmds.createNode("camera")
    panel = Panel(cam_shape, inherit=False)

    with (
        patch("maya.cmds.isolateSelect") as m_isolateSelect,
        patch("maya.cmds.select") as m_select,
    ):

        panel.isolate.clear()

        m_isolateSelect.assert_any_call("tik_panel", state=False)
        m_select.assert_any_call(clear=True)
        m_isolateSelect.assert_called_with("tik_panel", loadSelected=True)


def test_panel_isolate_call(mock_ui_cmds):
    """Test calling isolate object to replace contents."""
    cam_shape = cmds.createNode("camera")
    panel = Panel(cam_shape, inherit=False)
    cube = cmds.polyCube()[0]

    with (
        patch("maya.cmds.isolateSelect") as m_isolateSelect,
        patch("tik.maya.core.scene.select_nodes") as m_select_nodes,
        patch("maya.cmds.select") as m_select,
    ):

        panel.isolate(cube)

        # Should call clear then add
        # Clear calls:
        m_isolateSelect.assert_any_call("tik_panel", state=False)
        m_select.assert_any_call(clear=True)
        m_isolateSelect.assert_any_call("tik_panel", loadSelected=True)

        # Add calls:
        m_isolateSelect.assert_any_call("tik_panel", state=True)
        m_select_nodes.assert_called_with([cube])
        m_isolateSelect.assert_called_with("tik_panel", addSelected=True)


def test_inherit_panel_properties_self_check(mock_ui_cmds):
    """Test inherit skips self panel."""
    cam_shape = cmds.createNode("camera")

    # Mock getPanel to return tik_panel
    mock_ui_cmds["getPanel"].return_value = ["tik_panel"]

    # Mock modelPanel to return camera for tik_panel (should be skipped anyway)
    mock_ui_cmds["modelPanel"].return_value = "tik_panel"

    Panel(cam_shape, inherit=True)

    # Check that modelEditor was NOT called with query=True on tik_panel
    calls = mock_ui_cmds["modelEditor"].mock_calls
    query_calls = [call for call in calls if call.kwargs.get("query") is True]
    assert len(query_calls) == 0


def test_inherit_panel_properties_no_candidates(mock_ui_cmds):
    """Test inherit with no matching panels."""
    cam_shape = cmds.createNode("camera")

    mock_ui_cmds["getPanel"].return_value = ["otherPanel"]

    # Mock modelPanel to return other camera
    def model_panel_side_effect(*args, **kwargs):
        if (kwargs.get("q") or kwargs.get("query")) and args[0] == "otherPanel":
            return "otherCamera"
        return "tik_panel"

    mock_ui_cmds["modelPanel"].side_effect = model_panel_side_effect

    Panel(cam_shape, inherit=True)

    # Should return early
    calls = mock_ui_cmds["modelEditor"].mock_calls
    query_calls = [call for call in calls if call.kwargs.get("query") is True]
    assert len(query_calls) == 0


def test_inherit_panel_properties_active_panel(mock_ui_cmds):
    """Test inherit prefers active panel."""
    cam_shape = cmds.createNode("camera")

    mock_ui_cmds["getPanel"].side_effect = lambda **kwargs: (
        "modelPanel2" if kwargs.get("withFocus") else ["modelPanel1", "modelPanel2"]
    )

    # Both panels match camera
    def model_panel_side_effect(*args, **kwargs):
        if kwargs.get("q") or kwargs.get("query"):
            return cam_shape
        return "tik_panel"

    mock_ui_cmds["modelPanel"].side_effect = model_panel_side_effect

    # Mock modelEditor to return specific value for active panel
    def model_editor_side_effect(*args, **kwargs):
        if args and args[0] == "modelPanel2" and kwargs.get("grid"):
            return True
        if args and args[0] == "modelPanel1" and kwargs.get("grid"):
            return False
        return None

    mock_ui_cmds["modelEditor"].side_effect = model_editor_side_effect

    Panel(cam_shape, inherit=True)

    # Should have picked modelPanel2 (active) -> grid=True
    mock_ui_cmds["modelEditor"].assert_any_call("tik_panel", edit=True, grid=True)


def test_inherit_panel_properties_multiple_candidates(mock_ui_cmds):
    """Test inherit picks last candidate if active not in list."""
    cam_shape = cmds.createNode("camera")

    mock_ui_cmds["getPanel"].side_effect = lambda **kwargs: (
        "otherPanel" if kwargs.get("withFocus") else ["modelPanel1", "modelPanel2"]
    )

    # Both panels match camera
    def model_panel_side_effect(*args, **kwargs):
        if kwargs.get("q") or kwargs.get("query"):
            return cam_shape
        return "tik_panel"

    mock_ui_cmds["modelPanel"].side_effect = model_panel_side_effect

    # Mock modelEditor
    def model_editor_side_effect(*args, **kwargs):
        if args and args[0] == "modelPanel2" and kwargs.get("grid"):
            return True
        if args and args[0] == "modelPanel1" and kwargs.get("grid"):
            return False
        return None

    mock_ui_cmds["modelEditor"].side_effect = model_editor_side_effect

    Panel(cam_shape, inherit=True)

    # Should have picked modelPanel2 (last) -> grid=True
    mock_ui_cmds["modelEditor"].assert_any_call("tik_panel", edit=True, grid=True)


def test_inherit_panel_properties_runtime_error(mock_ui_cmds):
    """Test inherit handles RuntimeError."""
    cam_shape = cmds.createNode("camera")

    mock_ui_cmds["getPanel"].return_value = ["modelPanel1"]

    # Match camera
    def model_panel_side_effect(*args, **kwargs):
        if (kwargs.get("q") or kwargs.get("query")) and args[0] == "modelPanel1":
            return cam_shape
        return "tik_panel"

    mock_ui_cmds["modelPanel"].side_effect = model_panel_side_effect

    # Mock modelEditor to raise RuntimeError on edit
    def model_editor_side_effect(*args, **kwargs):
        if kwargs.get("edit"):
            raise RuntimeError("Some error")
        return True  # query returns True

    mock_ui_cmds["modelEditor"].side_effect = model_editor_side_effect

    # Should not crash
    Panel(cam_shape, inherit=True)


def test_panel_isolate_normalize_list(mock_ui_cmds):
    """Test isolate normalize with list."""
    cam_shape = cmds.createNode("camera")
    panel = Panel(cam_shape, inherit=False)
    cubes = [cmds.polyCube()[0], cmds.polyCube()[0]]

    with (
        patch("maya.cmds.isolateSelect"),
        patch("tik.maya.core.scene.select_nodes") as m_select_nodes,
    ):

        panel.isolate.add(cubes)

        m_select_nodes.assert_called_with(cubes)

"""Unit tests for the Panel construct."""

import pytest
from unittest.mock import patch
from maya import cmds

from tikmaya.constructs.panel import Panel
from tikmaya.types.camera import Camera
from tikmaya.types.transform import Transform


@pytest.fixture
def mock_ui_cmds():
    """Mock Maya UI commands that fail in standalone mode."""
    with patch('maya.cmds.window') as m_window, \
         patch('maya.cmds.paneLayout') as m_paneLayout, \
         patch('maya.cmds.modelPanel') as m_modelPanel, \
         patch('maya.cmds.modelEditor') as m_modelEditor, \
         patch('maya.cmds.showWindow') as m_showWindow, \
         patch('maya.cmds.deleteUI') as m_deleteUI, \
         patch('maya.cmds.getPanel') as m_getPanel:

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
            "showWindow": m_showWindow
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
        if args and args[0] == "modelPanel1" and (kwargs.get("q") or kwargs.get("query")):
            if kwargs.get("grid"):
                return True
            if kwargs.get("polymeshes"):
                return False
        return None

    mock_ui_cmds["modelEditor"].side_effect = model_editor_side_effect

    panel = Panel(cam_shape, inherit=True)

    # Verify modelEditor was called to set properties on new panel
    # We expect calls like: cmds.modelEditor('tik_panel', e=True, grid=True)
    # Note: 'tik_panel' is the return value of mocked modelPanel creation

    # Check if grid was set
    calls = mock_ui_cmds["modelEditor"].mock_calls
    grid_call_found = False
    for c in calls:
        # c is like call('tik_panel', e=True, grid=True)
        if len(c.args) > 0 and c.args[0] == "tik_panel" and c.kwargs.get("grid") is True:
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
        'maya.cmds.window',
        side_effect=lambda *args, **kwargs: True if kwargs.get("exists") else "tik_panel_window"
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


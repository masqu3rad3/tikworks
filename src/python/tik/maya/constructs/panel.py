"""Panel construct for managing model panels and camera settings."""

from __future__ import annotations

from typing import Any, Optional, Union

from maya import cmds

from ..core import scene
from ..core.decorators import keepselection
from ..core.registry import resolve
from ..types.camera import Camera
from ..types.transform import Transform


class Panel:
    """Construct for managing a torn-off model panel and associated camera settings.

    This construct creates a floating window with a model panel and manages
    both the panel's display options and the camera's display attributes.
    It supports reverting the camera to its original state upon destruction.
    """

    # List of modelEditor flags to inherit/manage
    MODEL_EDITOR_FLAGS = [
        "activeComponentsXray",
        "activeCustomGeometry",
        "activeCustomLighSet",
        "activeCustomOverrideGeometry",
        "activeCustomRenderer",
        "activeOnly",
        "activeShadingGraph",
        "activeView",
        "allObjects",
        "backfaceCulling",
        "bufferMode",
        "bumpResolution",
        "camera",
        "cameras",
        "clipGhosts",
        "cmEnabled",
        "colorResolution",
        "controlVertices",
        "cullingOverride",
        "deformers",
        "dimensions",
        "displayAppearance",
        "displayLights",
        "displayTextures",
        "dynamicConstraints",
        "dynamics",
        "exposure",
        "filter",
        "fluids",
        "fogColor",
        "fogDensity",
        "fogEnd",
        "fogMode",
        "fogSource",
        "fogStart",
        "fogging",
        "follicles",
        "gamma",
        "greasePencils",
        "grid",
        "hairSystems",
        "handles",
        "headsUpDisplay",
        "highlightConnection",
        "hulls",
        "ignorePanZoom",
        "ikHandles",
        "imagePlane",
        "interactive",
        "interactiveBackFaceCull",
        "interactiveDisableShadows",
        "jointXray",
        "joints",
        "lights",
        "lineWidth",
        "locators",
        "lowQualityLighting",
        "mainListConnection",
        "manipulators",
        "maxConstantTransparency",
        "maximumNumHardwareLights",
        "motionTrails",
        "nCloths",
        "nParticles",
        "nRigids",
        "nurbsCurves",
        "nurbsSurfaces",
        "objectFilter",
        "objectFilterShowInHUD",
        "occlusionCulling",
        "particleInstancers",
        "pivots",
        "planes",
        "pluginShapes",
        "polymeshes",
        "rendererName",
        "rendererOverrideName",
        "sceneRenderFilter",
        "selectionConnection",
        "selectionHiliteDisplay",
        "shadingModel",
        "shadows",
        "smallObjectCulling",
        "smoothWireframe",
        "sortTransparent",
        "stereoDrawMode",
        "strokes",
        "subdivSurfaces",
        "textureAnisotropic",
        "textureCompression",
        "textureDisplay",
        "textureEnvironmentMap",
        "textureHilight",
        "textureMaxSize",
        "textureSampling",
        "textures",
        "transpInShadows",
        "transparencyAlgorithm",
        "twoSidedLighting",
        "useBaseRenderer",
        "useDefaultMaterial",
        "useInteractiveMode",
        "useReducedRenderer",
        "viewSelected",
        "viewTransformName",
        "wireframeBackingStore",
        "wireframeOnShaded",
        "xray",
    ]

    # Camera attributes to track and revert
    CAMERA_ATTRS = [
        "displayFieldChart",
        "displayGateMask",
        "displayFilmGate",
        "displayFilmOrigin",
        "displayFilmPivot",
        "displayResolution",
        "displaySafeAction",
        "displaySafeTitle",
        "overscan",
    ]

    def __init__(
        self,
        camera: Union[str, Camera, Transform],
        resolution: tuple[int, int] = (1920, 1080),
        inherit: bool = True,
        title: str = "Tik Panel",
    ):
        """Initialize the Panel construct.

        Args:
            camera: The camera to look through (name, Camera wrapper, or Transform wrapper).
            resolution: The initial resolution of the window (width, height).
            inherit: Whether to inherit settings from the active or existing panels.
            title: The title of the window.
        """
        self._camera = self._resolve_camera(camera)
        self._window: Optional[str] = None
        self._panel: Optional[str] = None
        self._original_camera_state: dict[str, Any] = {}

        # Store original camera state
        self._capture_camera_state()

        # Create the UI
        self._create_ui(resolution, title)

        # Inherit settings if requested
        if inherit:
            self._inherit_panel_properties()
        else:
            # Default sensible settings if not inheriting
            self.display_appearance = "smoothShaded"
            self.display_textures = True
            self.polymeshes = True
            self.image_plane = True

        self._isolate = PanelIsolate(self._panel)

    @property
    def name(self) -> Optional[str]:
        """Return the model panel name."""
        return self._panel

    def _resolve_camera(self, camera: Union[str, Camera, Transform]) -> Camera:
        """Resolve the input into a Camera wrapper."""
        if isinstance(camera, Camera):
            return camera

        if isinstance(camera, Transform):
            # Find camera shape under transform
            shapes = camera.shapes
            for shape in shapes:
                if isinstance(shape, Camera):
                    return shape
            raise ValueError(f"Transform '{camera.name}' has no camera shape.")

        if isinstance(camera, str):
            if not cmds.objExists(camera):
                raise ValueError(f"Camera '{camera}' does not exist.")

            # Try to resolve using tikmaya registry
            node = resolve(camera)
            return self._resolve_camera(node)

        raise TypeError(f"Invalid camera type: {type(camera)}")

    def _capture_camera_state(self):
        """Store the current state of camera display attributes."""
        for attr in self.CAMERA_ATTRS:
            # Query the attribute value
            # Note: cmds.camera(q=True, ...) works for these flags
            val = cmds.camera(self._camera.name, query=True, **{attr: True})
            self._original_camera_state[attr] = val

    def _create_ui(self, resolution: tuple[int, int], title: str):
        """Create the window and model panel."""
        width, height = resolution
        # Compensate for menu bar height roughly
        window_height = height + 40

        # Check if window exists (though we usually want a new one,
        # but let's ensure unique name if possible or just let Maya handle it)
        # Using a unique name based on camera might be good, but for now simple is fine.

        self._window = cmds.window(
            title=title,
            widthHeight=(width, window_height),
            topLeftCorner=(0, 0),
            titleBar=True,
            menuBarVisible=False,
        )
        cmds.paneLayout()
        self._panel = cmds.modelPanel(camera=self._camera.name)
        cmds.showWindow(self._window)

    def _inherit_panel_properties(self):
        """Inherit properties from an existing model panel looking at the same camera."""
        # Find existing panels for this camera
        camera_shape_name = self._camera.name
        # Also consider the transform name just in case
        camera_transform_name = cmds.listRelatives(camera_shape_name, p=True)[0]

        candidate_panels = []
        all_panels = cmds.getPanel(type="modelPanel") or []

        for panel in all_panels:
            if panel == self._panel:
                continue

            cam = cmds.modelPanel(panel, query=True, camera=True)
            # cam returned by modelPanel might be transform or shape name, usually transform
            if cam == camera_shape_name or cam == camera_transform_name:
                candidate_panels.append(panel)

        if not candidate_panels:
            return

        # Prefer active panel if it's in the list
        active_panel = cmds.getPanel(withFocus=True)
        source_panel = candidate_panels[0]

        if active_panel in candidate_panels:
            source_panel = active_panel
        elif len(candidate_panels) > 1:
            # Pick the last one (most recently created/used?)
            source_panel = candidate_panels[-1]

        # Copy settings
        for flag in self.MODEL_EDITOR_FLAGS:
            try:
                val = cmds.modelEditor(source_panel, query=True, **{flag: True})
                if val is None:
                    continue

                # Apply to our panel
                # Some flags might be query-only or behave differently, wrap in try
                cmds.modelEditor(self._panel, edit=True, **{flag: val})
            except RuntimeError:
                # Some flags might fail depending on context
                pass

    # === Public Methods ===

    def revert(self):
        """Revert camera settings to their original state."""
        for attr, val in self._original_camera_state.items():
            cmds.camera(self._camera.name, edit=True, **{attr: val})

    def close(self):
        """Close the panel window and revert camera settings."""
        self.revert()
        if self._panel and cmds.modelPanel(self._panel, query=True, exists=True):
            # modelPanel needs to be deleted specifically sometimes?
            # Actually deleting the window usually kills the layout and children.
            # But let's be safe.
            cmds.deleteUI(self._panel, panel=True)

        if self._window and cmds.window(self._window, query=True, exists=True):
            cmds.deleteUI(self._window)

    def set_preset(self, preset: str):
        """Apply a predefined preset of settings.

        Args:
            preset: Name of the preset (e.g., 'preview').
        """
        if preset == "preview":
            self.display_field_chart = False
            self.display_gate_mask = False
            self.display_film_gate = False
            self.display_film_origin = False
            self.display_film_pivot = False
            self.display_resolution = False
            self.display_safe_action = False
            self.display_safe_title = False
            # Add more as needed

    # === Camera Properties ===

    @property
    def display_field_chart(self) -> bool:
        """Whether to display the field chart in the camera view."""
        return cmds.camera(self._camera.name, query=True, displayFieldChart=True)

    @display_field_chart.setter
    def display_field_chart(self, value: bool):
        cmds.camera(self._camera.name, edit=True, displayFieldChart=value)

    @property
    def display_gate_mask(self) -> bool:
        """Whether to display the gate mask."""
        return cmds.camera(self._camera.name, query=True, displayGateMask=True)

    @display_gate_mask.setter
    def display_gate_mask(self, value: bool):
        cmds.camera(self._camera.name, edit=True, displayGateMask=value)

    @property
    def display_film_gate(self) -> bool:
        """Whether to display the film gate."""
        return cmds.camera(self._camera.name, query=True, displayFilmGate=True)

    @display_film_gate.setter
    def display_film_gate(self, value: bool):
        cmds.camera(self._camera.name, edit=True, displayFilmGate=value)

    @property
    def display_film_origin(self) -> bool:
        """Whether to display the film origin."""
        return cmds.camera(self._camera.name, query=True, displayFilmOrigin=True)

    @display_film_origin.setter
    def display_film_origin(self, value: bool):
        cmds.camera(self._camera.name, edit=True, displayFilmOrigin=value)

    @property
    def display_film_pivot(self) -> bool:
        """Whether to display the film pivot."""
        return cmds.camera(self._camera.name, query=True, displayFilmPivot=True)

    @display_film_pivot.setter
    def display_film_pivot(self, value: bool):
        cmds.camera(self._camera.name, edit=True, displayFilmPivot=value)

    @property
    def display_resolution(self) -> bool:
        """Whether to display the resolution gate."""
        return cmds.camera(self._camera.name, query=True, displayResolution=True)

    @display_resolution.setter
    def display_resolution(self, value: bool):
        cmds.camera(self._camera.name, edit=True, displayResolution=value)

    @property
    def display_safe_action(self) -> bool:
        """Whether to display the safe action area."""
        return cmds.camera(self._camera.name, query=True, displaySafeAction=True)

    @display_safe_action.setter
    def display_safe_action(self, value: bool):
        cmds.camera(self._camera.name, edit=True, displaySafeAction=value)

    @property
    def display_safe_title(self) -> bool:
        """Whether to display the safe title area."""
        return cmds.camera(self._camera.name, query=True, displaySafeTitle=True)

    @display_safe_title.setter
    def display_safe_title(self, value: bool):
        cmds.camera(self._camera.name, edit=True, displaySafeTitle=value)

    @property
    def overscan(self) -> float:
        """The camera overscan value."""
        return cmds.camera(self._camera.name, query=True, overscan=True)

    @overscan.setter
    def overscan(self, value: float):
        cmds.camera(self._camera.name, edit=True, overscan=value)

    # === Panel Properties ===

    def set_editor_var(self, flag: str, value: Any):
        """Set a modelEditor flag value.

        Args:
            flag: The modelEditor flag name.
            value: The value to set.
        """
        if self._panel:
            cmds.modelEditor(self._panel, edit=True, **{flag: value})

    def get_editor_var(self, flag: str) -> Any:
        """Get a modelEditor flag value.

        Args:
            flag: The modelEditor flag name.

        Returns:
            The current value of the flag, or None if panel doesn't exist.
        """
        if self._panel:
            return cmds.modelEditor(self._panel, query=True, **{flag: True})
        return None

    @property
    def all_objects(self) -> bool:
        """Whether to display all object types."""
        return self.get_editor_var("allObjects")

    @all_objects.setter
    def all_objects(self, value: bool):
        self.set_editor_var("allObjects", value)

    @property
    def display_appearance(self) -> str:
        """Display appearance mode (e.g., 'wireframe', 'smoothShaded')."""
        return self.get_editor_var("displayAppearance")

    @display_appearance.setter
    def display_appearance(self, value: str):
        self.set_editor_var("displayAppearance", value)

    @property
    def display_textures(self) -> bool:
        """Whether to display textures."""
        return self.get_editor_var("displayTextures")

    @display_textures.setter
    def display_textures(self, value: bool):
        self.set_editor_var("displayTextures", value)

    @property
    def grid(self) -> bool:
        """Whether to display the grid."""
        return self.get_editor_var("grid")

    @grid.setter
    def grid(self, value: bool):
        self.set_editor_var("grid", value)

    @property
    def use_default_material(self) -> bool:
        """Whether to display objects with default material."""
        return self.get_editor_var("useDefaultMaterial")

    @use_default_material.setter
    def use_default_material(self, value: bool):
        self.set_editor_var("useDefaultMaterial", value)

    @property
    def polymeshes(self) -> bool:
        """Whether to display polygon meshes."""
        return self.get_editor_var("polymeshes")

    @polymeshes.setter
    def polymeshes(self, value: bool):
        self.set_editor_var("polymeshes", value)

    @property
    def nurbs_curves(self) -> bool:
        """Whether to display NURBS curves."""
        return self.get_editor_var("nurbsCurves")

    @nurbs_curves.setter
    def nurbs_curves(self, value: bool):
        self.set_editor_var("nurbsCurves", value)

    @property
    def nurbs_surfaces(self) -> bool:
        """Whether to display NURBS surfaces."""
        return self.get_editor_var("nurbsSurfaces")

    @nurbs_surfaces.setter
    def nurbs_surfaces(self, value: bool):
        self.set_editor_var("nurbsSurfaces", value)

    @property
    def joints(self) -> bool:
        """Whether to display joints."""
        return self.get_editor_var("joints")

    @joints.setter
    def joints(self, value: bool):
        self.set_editor_var("joints", value)

    @property
    def locators(self) -> bool:
        """Whether to display locators."""
        return self.get_editor_var("locators")

    @locators.setter
    def locators(self, value: bool):
        self.set_editor_var("locators", value)

    @property
    def pivots(self) -> bool:
        """Whether to display pivots."""
        return self.get_editor_var("pivots")

    @pivots.setter
    def pivots(self, value: bool):
        self.set_editor_var("pivots", value)

    @property
    def image_plane(self) -> bool:
        """Whether to display image planes."""
        return self.get_editor_var("imagePlane")

    @image_plane.setter
    def image_plane(self, value: bool):
        self.set_editor_var("imagePlane", value)

    @property
    def hud(self) -> bool:
        """Whether to display the heads-up display."""
        return self.get_editor_var("headsUpDisplay")

    @hud.setter
    def hud(self, value: bool):
        self.set_editor_var("headsUpDisplay", value)

    @property
    def selection_highlighting(self) -> bool:
        """Whether to highlight selected objects."""
        return self.get_editor_var("selectionHiliteDisplay")

    @selection_highlighting.setter
    def selection_highlighting(self, value: bool):
        self.set_editor_var("selectionHiliteDisplay", value)

    @property
    def camera(self):
        """The camera associated with this panel."""
        return self._camera

    @property
    def color_management_enabled(self) -> bool:
        """Whether color management is enabled."""
        return self.get_editor_var("cmEnabled")

    @color_management_enabled.setter
    def color_management_enabled(self, value: bool):
        self.set_editor_var("cmEnabled", value)

    @property
    def manipulators(self) -> bool:
        """Whether to display manipulators."""
        return self.get_editor_var("manipulators")

    @manipulators.setter
    def manipulators(self, value: bool):
        self.set_editor_var("manipulators", value)

    @property
    def isolate(self):
        """Return a PanelIsolate helper for managing isolation mode."""
        return self._isolate

    def fit_view(self, **kwargs):
        """Frame all objects in the panel."""
        if self._panel:
            self.activate()
            cmds.viewFit(**kwargs)

    def activate(self):
        """Make the panel the active panel."""
        if self._panel:
            cmds.setFocus(self._panel)


class PanelIsolate:
    """Helper class for managing isolation mode in a model panel."""

    def __init__(self, panel):
        """Initialize the PanelIsolate helper.

        Args:
            panel: The model panel name.
        """
        self._panel = panel  # modelPanel name

    # --- core entry point ---

    def __call__(self, nodes):
        """Replace isolate contents with the specified nodes.

        Args:
            nodes: Single node or list of nodes to isolate.
        """
        self.clear()
        self.add(nodes)

    # --- public API ---
    @keepselection
    def add(self, nodes):
        """Add nodes to the isolation set.

        Args:
            nodes: Single node or list of nodes to add to isolation.
        """
        nodes = self._normalize(nodes)
        self.enable()
        scene.select_nodes(nodes)
        cmds.isolateSelect(self._panel, addSelected=True)

    @keepselection
    def remove(self, nodes):
        """Remove nodes from the isolation set.

        Args:
            nodes: Single node or list of nodes to remove from isolation.
        """
        nodes = self._normalize(nodes)
        self.enable()
        scene.select_nodes(nodes)
        cmds.isolateSelect(self._panel, removeSelected=True)

    @keepselection
    def clear(self):
        """Clear all nodes from the isolation set."""
        cmds.isolateSelect(self._panel, state=False)
        cmds.select(clear=True)
        cmds.isolateSelect(self._panel, loadSelected=True)

    def enable(self):
        """Enable isolation mode for the panel."""
        cmds.isolateSelect(self._panel, state=True)

    # --- helpers ---

    def _normalize(self, nodes):
        """Normalize nodes to a list format.

        Args:
            nodes: Single node or iterable of nodes.

        Returns:
            List of nodes.
        """
        if not isinstance(nodes, (list, tuple, set)):
            return [nodes]
        return list(nodes)

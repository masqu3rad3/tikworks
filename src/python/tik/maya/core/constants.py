"""Constants for the Tik Maya Core module."""

from __future__ import annotations

from maya import cmds

#: The nine transform channels, in channel-box order.
TRANSFORM_CHANNELS = ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz")

#: The transform channels plus visibility.
ALL_CHANNELS = TRANSFORM_CHANNELS + ("v",)

NODE_FACTORIES = [
    # --- General Creation & Management ---
    # 'createNode', # CreateNode is handled specially in scene.py
    "duplicate",
    "duplicateWithTransform",
    "instance",
    "group",
    "rename",
    "sets",
    "partition",
    "container",
    "shadingNode",
    # --- Retrieval / Query ---
    # 'ls', # Wrapped separately in scene.py
    "listRelatives",
    "listConnections",
    "listHistory",
    "listTransforms",
    "selectedNodes",
    # --- Polygon Primitives ---
    "polyCube",
    "polySphere",
    "polyCylinder",
    "polyCone",
    "polyPlane",
    "polyTorus",
    "polyPrism",
    "polyPyramid",
    "polyPipe",
    "polyHelix",
    "polyPlatonicSolid",
    "polySoccerBall",
    "polyDisc",
    "polyGear",
    "polySuperShape",
    # --- NURBS Primitives ---
    "nurbsCube",
    "nurbsPlane",
    "nurbsSphere",
    "nurbsCylinder",
    "nurbsCone",
    "nurbsTorus",
    "nurbsSquare",
    "sphere",
    "cone",
    "cylinder",
    "plane",
    "torus",
    "circle",
    "square",
    # --- Curves & Text ---
    "curve",
    "textCurves",
    "bezierCurveToNurbs",
    "arcLengthDimension",
    # --- Lights & Cameras ---
    "ambientLight",
    "directionalLight",
    "pointLight",
    "spotLight",
    "areaLight",
    "volumeLight",
    "camera",
    "imagePlane",
    # --- Locators & Helpers ---
    "spaceLocator",
    "annotate",
    "distanceDimension",
    # --- Rigging (Joints, IK, Constraints) ---
    "joint",
    "ikHandle",
    "effector",
    "aimConstraint",
    "orientConstraint",
    "pointConstraint",
    "parentConstraint",
    "scaleConstraint",
    "poleVectorConstraint",
    "geometryConstraint",
    "normalConstraint",
    "tangentConstraint",
    "pointOnPolyConstraint",
    # --- Deformers ---
    "blendShape",
    "cluster",
    "lattice",
    "skinCluster",
    "wire",
    "nonLinear",
    "sculpt",
    "deltaMush",
    "deformer",
    "boneLattice",
    "flexor",
    # --- Modeling Operations (Resulting in new nodes/transforms) ---
    "polyUnite",
    "polySeparate",
    "polyBoolOp",
    "polyBooleanCmd",
    "polyDuplicateAndConnect",
    "polyMirrorFace",
    "polySmooth",
    "polyBevel",
    "polyBevel3",
    "attachCurve",
    "detachCurve",
    "alignCurve",
    "alignSurface",
    "filletCurve",
    "intersect",
    "loft",
    "revolve",
    "extrude",
    "boundary",
    "planarSrf",
    "bevel",
    "bevelPlus",
    "copySkinWeights",  # Returns list of destination objects
    # --- Dynamics / FX ---
    "emitter",
    "fluidEmitter",
    "particle",
    "nParticle",
    "nClothCreate",
    "air",
    "drag",
    "gravity",
    "newton",
    "radial",
    "turbulence",
    "uniform",
    "volumeAxis",
    "vortex",
    "rigidBody",
    "rigidSolver",
    "spring",
    # --- Animation ---
    "shot",
    "clip",
    "character",
    "expression",  # Returns the expression node name
    "animLayer",
]


class _NodeNamesConfig:
    """
    Internal configuration for node names that vary between versions.
    Acts as a singleton to allow lazy property evaluation.
    """

    _cached_version: int | None = None
    _lookdevkit_loaded: bool = False

    @property
    def maya_version(self) -> int:
        """
        Lazily retrieves the Maya version.
        Safe for use with pytest because it executes only on access, not import.
        """
        if self._cached_version is None:
            try:
                self._cached_version = int(cmds.about(version=True))
            except (AttributeError, RuntimeError, ValueError):
                # Default to 2026 if accessed during uninitialized states (e.g., test collection)
                self._cached_version = 2026
        return self._cached_version

    def ensure_lookdevkit_loaded(self) -> None:
        """
        Ensure the lookdevKit plugin is loaded (required for floatMath node).

        Only checks and loads once per session for performance.
        """
        if self._lookdevkit_loaded:
            return
        if not cmds.pluginInfo("lookdevKit", query=True, loaded=True):
            cmds.loadPlugin("lookdevKit", quiet=True)
        self._lookdevkit_loaded = True

    @property
    def MULT_DOUBLE_LINEAR(self) -> str:
        """Name for the keyable multDoubleLinear node."""
        return "multDL" if self.maya_version >= 2026 else "multDoubleLinear"

    @property
    def ADD_DOUBLE_LINEAR(self) -> str:
        """Name for the keyable addDoubleLinear node."""
        return "addDL" if self.maya_version >= 2026 else "addDoubleLinear"

    @property
    def uses_native_math_nodes(self) -> bool:
        """Check if native subtract/divide nodes are available (Maya 2025+)."""
        return self.maya_version >= 2025


# Export as a singleton instance.
# Usage remains consistent: NodeNames.MULT_DOUBLE_LINEAR
NodeNames = _NodeNamesConfig()

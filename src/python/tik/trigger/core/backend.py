"""Backend protocol: everything that touches a DCC scene."""

from __future__ import annotations

from typing import Any, ContextManager, Optional, Protocol, Sequence

from .schemas import GuidePose, ModuleInstance, ParentRef


class Backend(Protocol):
    """DCC integration surface used by the builder and sessions."""

    name: str

    # ---- scene ----------------------------------------------------------
    def new_scene(self) -> None: ...

    def undo_chunk(self, label: str) -> ContextManager: ...

    # ---- guides ---------------------------------------------------------
    def find_instances(self, scope: Any = "scene") -> list[ModuleInstance]: ...

    def create_guides(
        self,
        module: Any,
        parent: Optional[ParentRef] = None,
        poses: Optional[Sequence[GuidePose]] = None,
    ) -> ModuleInstance: ...

    def delete_guides(self, instance_id: str) -> None: ...

    def write_settings(self, instance_id: str, settings: dict) -> None: ...

    def read_settings(self, instance_id: str) -> dict: ...

    def guide_node(self, instance_id: str, role: str, index: int = 0) -> Any: ...

    # ---- build ----------------------------------------------------------
    def ensure_rig_root(self, rig_name: str) -> Any: ...

    def build_context(self, module: Any, instance: ModuleInstance, rig_root: Any) -> Any: ...

    def finalize(self, ctx: Any) -> None: ...

    def connect(self, ctx: Any, input_name: str, source_node: Any) -> None: ...

    def scene_node(self, name: str) -> Any: ...

    def set_inputs(self, instance_id: str, inputs: dict) -> None: ...

    def afterlife(self, instances: Sequence[ModuleInstance], mode: str) -> None: ...

"""What is selected, as plain data.

The shell renders a context; a switch reads one. Neither needs Maya to exist,
which is what lets ``tests/ui`` drive the whole window offscreen against a
fabricated selection -- and what keeps every scene read in one place.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Control:
    """One selected rig controller, as its tags describe it."""

    node: str
    role: str = ""
    side: str = "C"
    module: str = ""
    instance: str = ""

    @property
    def key(self) -> str:
        """Display key: ``L_arm`` / ``spine``; empty when the module is unknown."""
        if not self.module:
            return ""
        return self.module if self.side in ("C", "") else f"{self.side}_{self.module}"


@dataclass(frozen=True)
class SwitchContext:
    """The selection a switch acts on."""

    nodes: tuple[str, ...] = ()
    controls: tuple[Control, ...] = ()

    @property
    def is_empty(self) -> bool:
        """True when nothing a switch can act on is selected."""
        return not self.controls

    @property
    def keys(self) -> tuple[str, ...]:
        """Module display keys, in selection order, without repeats."""
        found: list[str] = []
        for control in self.controls:
            if control.key and control.key not in found:
                found.append(control.key)
        return tuple(found)

    @property
    def sides(self) -> tuple[str, ...]:
        """Sides present, in selection order, without repeats."""
        found: list[str] = []
        for control in self.controls:
            if control.side not in found:
                found.append(control.side)
        return tuple(found)

    @classmethod
    def from_scene(cls) -> "SwitchContext":
        """Read the current Maya selection. The one scene read in this package."""
        import tik.maya as tm
        from tik.trigger.maya import tags

        nodes: list[str] = []
        controls: list[Control] = []
        for node in tm.ls(selection=True, type="transform") or []:
            nodes.append(node.long_name)
            meta = node.meta.as_dict()
            if meta.get(tags.KIND) != tags.CONTROLLER:
                continue
            module = _owning_module(node)
            controls.append(
                Control(
                    node=node.long_name,
                    role=meta.get(tags.ROLE, ""),
                    side=module.get(tags.SIDE, "C"),
                    module=module.get(tags.NAME, "") or module.get(tags.MODULE, ""),
                    instance=meta.get(tags.INSTANCE, ""),
                )
            )
        return cls(nodes=tuple(nodes), controls=tuple(controls))


def _owning_module(node) -> dict:
    """Meta of the nearest ancestor that is a module's top group.

    ``rig.controller`` tags a controller with its kind, instance, role and
    mirror convention -- the name and side live on the module group it hangs
    under, which is the only place they are true for every controller at once.
    """
    from tik.trigger.maya import tags

    parent = node.parent
    while parent is not None:
        meta = parent.meta.as_dict()
        if meta.get(tags.KIND) == tags.RIG:
            return meta
        parent = parent.parent
    return {}

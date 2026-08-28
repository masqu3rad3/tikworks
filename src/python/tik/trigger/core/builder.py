"""Build orchestration: read guide instances, build modules, attach them."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from . import registry
from .events import EventBus
from .exceptions import AttachError, BuildError
from .schemas import ModuleInstance, order_instances

AFTERLIFE_MODES = ("keep", "hide", "delete")


@dataclass
class BuildReport:
    """What happened during a build."""

    built: list[str] = field(default_factory=list)  # instance ids in build order
    contexts: dict = field(default_factory=dict)  # instance id -> BuildContext
    rig_root: Any = None

    @property
    def count(self) -> int:
        return len(self.built)


class Builder:
    """Turn the guide instances found by a backend into a rig."""

    def __init__(self, backend, events: Optional[EventBus] = None) -> None:
        self.backend = backend
        self.events = events or EventBus()

    @staticmethod
    def order(instances: list[ModuleInstance]) -> list[ModuleInstance]:
        """Parents first, otherwise stable."""
        return order_instances(instances)

    @staticmethod
    def resolve_plug(instance: ModuleInstance, parent_ctx) -> str:
        """Pick which parent plug a child attaches to."""
        available = list(parent_ctx.plugs)
        if not available:
            raise AttachError(
                f"Parent of '{instance.name}' exposes no plugs.",
                instance_id=instance.instance_id,
                module_type=instance.module_type,
            )
        if instance.attach:
            if instance.attach not in available:
                raise AttachError(
                    f"Plug '{instance.attach}' not found on parent of '{instance.name}'. "
                    f"Available: {available}",
                    instance_id=instance.instance_id,
                    module_type=instance.module_type,
                )
            return instance.attach
        if instance.parent and instance.parent.role in available:
            return instance.parent.role
        return available[0]

    def build(
        self,
        scope: Any = "scene",
        rig_name: str = "trigger",
        afterlife: str = "delete",
    ) -> BuildReport:
        """Build every module instance in ``scope``.

        Args:
            scope: Passed to ``backend.find_instances``.
            rig_name: Name of the rig root group.
            afterlife: ``"keep"``, ``"hide"`` or ``"delete"`` the guides afterwards.
        """
        if afterlife not in AFTERLIFE_MODES:
            raise ValueError(f"afterlife must be one of {AFTERLIFE_MODES}.")
        instances = self.order(self.backend.find_instances(scope))
        report = BuildReport()
        total = len(instances)
        if not total:
            self.events.log("No module guides found to build.", level="warning")
            return report

        with self.backend.undo_chunk(f"Trigger build: {rig_name}"):
            report.rig_root = self.backend.ensure_rig_root(rig_name)
            for number, instance in enumerate(instances, start=1):
                self.events.progress(number, total, f"Building {instance.name}")
                ctx = self._build_one(instance, report.rig_root)
                report.contexts[instance.instance_id] = ctx
                report.built.append(instance.instance_id)

            for instance in instances:
                if instance.parent is None:
                    continue
                parent_ctx = report.contexts.get(instance.parent.instance_id)
                if parent_ctx is None:
                    self.events.log(
                        f"Parent of '{instance.name}' was not built; left unattached.",
                        level="warning",
                    )
                    continue
                child_ctx = report.contexts[instance.instance_id]
                plug_name = self.resolve_plug(instance, parent_ctx)
                self.backend.connect(child_ctx, parent_ctx, plug_name)

            self.backend.afterlife(instances, afterlife)
        self.events.log(f"Built {total} module(s) into '{rig_name}'.")
        return report

    def _build_one(self, instance: ModuleInstance, rig_root):
        module_cls = registry.get_module(instance.module_type)
        module = module_cls.from_instance(instance)
        problems = module.validate()
        if problems:
            raise BuildError(
                f"'{instance.name}' cannot build: " + "; ".join(problems),
                instance_id=instance.instance_id,
                module_type=instance.module_type,
            )
        try:
            ctx = self.backend.build_context(module, instance, rig_root)
            module.build(ctx)
            self.backend.finalize(ctx)
        except BuildError:
            raise
        except Exception as error:  # noqa: BLE001 - wrap with context
            self.events.error(error, context=f"building {instance.name}")
            raise BuildError(
                f"'{instance.name}' ({instance.module_type}) failed: {error}",
                instance_id=instance.instance_id,
                module_type=instance.module_type,
            ) from error
        return ctx

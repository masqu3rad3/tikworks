"""Build orchestration: build every instance, then connect declared inputs."""

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
    connections: list[tuple[str, str]] = field(default_factory=list)  # ("L_arm.root", "body.root")
    rig_root: Any = None

    @property
    def count(self) -> int:
        return len(self.built)


def derive_inputs(instance: ModuleInstance, by_id: dict) -> dict:
    """Legacy: derive the primary input from the guide DAG parent, if any."""
    if instance.inputs:
        return dict(instance.inputs)
    module_cls = registry.get_module(instance.module_type)
    primary = module_cls.primary_input()
    if primary is None or instance.parent is None:
        return {}
    parent = by_id.get(instance.parent.instance_id)
    if parent is None:
        return {}
    parent_cls = registry.get_module(parent.module_type)
    output = instance.attach or parent_cls.output_for_role(instance.parent.role)
    if output is None:
        return {}
    return {primary.name: f"{parent.key}.{output}"}


def split_source(source: str) -> tuple[Optional[str], str]:
    """``"L_arm.hand"`` -> ("L_arm", "hand"); ``"some_jnt"`` -> (None, "some_jnt")."""
    if "." in source:
        key, _dot, output = source.rpartition(".")
        return key, output
    return None, source


class Builder:
    """Turn the guide instances found by a backend into a rig."""

    def __init__(self, backend, events: Optional[EventBus] = None) -> None:
        self.backend = backend
        self.events = events or EventBus()

    @staticmethod
    def order(instances: list[ModuleInstance]) -> list[ModuleInstance]:
        return order_instances(instances)

    def build(
        self,
        scope: Any = "scene",
        rig_name: str = "trigger",
        afterlife: str = "delete",
    ) -> BuildReport:
        if afterlife not in AFTERLIFE_MODES:
            raise ValueError(f"afterlife must be one of {AFTERLIFE_MODES}.")
        instances = self.order(self.backend.find_instances(scope))
        known_keys = {item.key for item in (instances if scope == "scene" else self.backend.find_instances("scene"))}
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
            self._connect_all(instances, report, known_keys)
            self.backend.afterlife(instances, afterlife)
        self.events.log(f"Built {total} module(s) into '{rig_name}'.")
        return report

    # ------------------------------------------------------------- connect
    def _connect_all(self, instances, report: BuildReport, known_keys=frozenset()) -> None:
        by_id = {instance.instance_id: instance for instance in instances}
        by_key = {instance.key: instance for instance in instances}
        for instance in instances:
            module_cls = registry.get_module(instance.module_type)
            ctx = report.contexts[instance.instance_id]
            inputs = derive_inputs(instance, by_id)
            for declared in module_cls.inputs:
                source = inputs.get(declared.name)
                if not source:
                    if declared.optional:
                        continue
                    raise AttachError(
                        f"{instance.key}.{declared.name}: required input has no source.",
                        instance_id=instance.instance_id, module_type=instance.module_type,
                    )
                key, _output = split_source(source)
                if key is not None and key in known_keys and key not in by_key:
                    self.events.log(
                        f"{instance.key}.{declared.name}: source '{source}' is outside the build scope; left unattached.",
                        level="warning",
                    )
                    continue
                node = self._resolve_source(instance, declared.name, source, by_key, report)
                target = ctx.attachments.get(declared.name)
                if target is None:
                    raise AttachError(
                        f"{instance.key}.{declared.name}: module did not call ctx.attach() for this input.",
                        instance_id=instance.instance_id, module_type=instance.module_type,
                    )
                self.backend.connect(ctx, declared.name, node)
                report.connections.append((f"{instance.key}.{declared.name}", source))

    def _resolve_source(self, instance, input_name, source, by_key, report):
        key, output = split_source(source)
        if key is not None and key in by_key:
            producer = by_key[key]
            producer_ctx = report.contexts.get(producer.instance_id)
            if producer_ctx is None or output not in producer_ctx.outputs:
                raise AttachError(
                    f"{instance.key}.{input_name}: source '{source}' was not built "
                    f"(available outputs: {sorted(producer_ctx.outputs) if producer_ctx else []}).",
                    instance_id=instance.instance_id, module_type=instance.module_type,
                )
            return producer_ctx.outputs[output]
        node = self.backend.scene_node(source)
        if node is None:
            raise AttachError(
                f"{instance.key}.{input_name}: source '{source}' is neither a built module output nor an existing scene node.",
                instance_id=instance.instance_id, module_type=instance.module_type,
            )
        return node

    # --------------------------------------------------------------- build
    def _build_one(self, instance: ModuleInstance, rig_root):
        module_cls = registry.get_module(instance.module_type)
        module = module_cls.from_instance(instance)
        problems = module.validate()
        if problems:
            raise BuildError(
                f"'{instance.name}' cannot build: " + "; ".join(problems),
                instance_id=instance.instance_id, module_type=instance.module_type,
            )
        try:
            ctx = self.backend.build_context(module, instance, rig_root)
            module.build(ctx)
            missing = [name for name in module_cls.output_names(instance.settings) if name not in ctx.outputs]
            if missing:
                raise BuildError(
                    f"module '{instance.module_type}' did not produce output(s) {missing}",
                    instance_id=instance.instance_id, module_type=instance.module_type,
                )
            self.backend.finalize(ctx)
        except BuildError:
            raise
        except Exception as error:  # noqa: BLE001 - wrap with context
            self.events.error(error, context=f"building {instance.name}")
            raise BuildError(
                f"'{instance.name}' ({instance.module_type}) failed: {error}",
                instance_id=instance.instance_id, module_type=instance.module_type,
            ) from error
        return ctx

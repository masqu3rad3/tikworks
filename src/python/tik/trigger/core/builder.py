"""Build orchestration: build every instance, then connect declared inputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from . import registry
from .events import EventBus
from .exceptions import AttachError, BuildError
from .schemas import ModuleInstance, order_by_connections, order_instances

AFTERLIFE_MODES = ("keep", "hide", "delete")


@dataclass
class BuildReport:
    """What happened during a build."""

    built: list[str] = field(default_factory=list)  # instance ids in build order
    contexts: dict = field(default_factory=dict)  # instance id -> BuildContext
    connections: list[tuple[str, str]] = field(default_factory=list)  # ("L_arm.root", "body.root")
    spaces: list[tuple[str, str]] = field(default_factory=list)  # ("L_arm.ik_chest", "body.root")
    rig_root: Any = None

    @property
    def count(self) -> int:
        return len(self.built)


def split_source(source: str) -> tuple[Optional[str], str]:
    """``"L_arm.hand"`` -> ("L_arm", "hand"); ``"some_jnt"`` -> (None, "some_jnt")."""
    if "." in source:
        key, _dot, output = source.rpartition(".")
        return key, output
    return None, source


def space_input_names(module_cls, settings) -> set:
    """Names of the inputs derived from anim-space rows."""
    return {item.name for item in module_cls.space_inputs(settings)}


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
            # Producers must be built before consumers: rig.bind_parent is
            # resolved from the producer's output, so bind joints can be created
            # in their final hierarchy position instead of reparented later.
            def structural_inputs(item):
                module_cls = registry.get_module(item.module_type)
                skip = space_input_names(module_cls, item.settings)
                return {
                    name: source
                    for name, source in item.inputs.items()
                    if name not in skip
                }

            # Space connections are legitimately mutually referential - an arm in
            # head space while the head sits in arm space is a normal rig - so
            # they must not reach the topological sort.
            instances = order_by_connections(instances, structural_inputs)
            by_key: dict = {}
            for number, instance in enumerate(instances, start=1):
                self.events.progress(number, total, f"Building {instance.name}")
                module_cls = registry.get_module(instance.module_type)
                inputs = dict(instance.inputs)
                bind_parent = self._bind_parent_for(
                    instance, module_cls, inputs, by_key, report
                )
                ctx = self._build_one(instance, report.rig_root, bind_parent)
                report.contexts[instance.instance_id] = ctx
                report.built.append(instance.instance_id)
                by_key[instance.key] = instance
                self._connect_one(
                    instance, module_cls, inputs, by_key, report, known_keys
                )
            self._connect_spaces(instances, report, by_key)
            self.backend.afterlife(instances, afterlife)
        self.events.log(f"Built {total} module(s) into '{rig_name}'.")
        return report

    # ------------------------------------------------------------- connect
    def _bind_parent_for(self, instance, module_cls, inputs, by_key, report):
        """Resolve the bind joint that this module's bind joints hang from.

        Returns the primary input's producer output, or ``None`` when the module
        is unconnected — the context then falls back to its own ``bind_grp``.
        """
        primary = module_cls.primary_input()
        if primary is None or primary.kind == "space":
            return None
        source = inputs.get(primary.name)
        if not source:
            return None
        key, output = split_source(source)
        if key is None or key not in by_key:
            return None
        producer_ctx = report.contexts.get(by_key[key].instance_id)
        if producer_ctx is None:
            return None
        return producer_ctx.outputs.get(output)

    def _connect_one(self, instance, module_cls, inputs, by_key, report, known_keys) -> None:
        """Attach every declared input of one already-built instance."""
        ctx = report.contexts[instance.instance_id]
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

    def _connect_spaces(self, instances, report: BuildReport, by_key: dict) -> None:
        """Build one space switch per (control, mode), after all modules exist.

        Deliberately not part of ``order_by_connections``: a space switch does
        not affect the bind hierarchy, and spaces are legitimately mutually
        referential, which would be a false cycle in the topological sort.
        """
        for instance in instances:
            module_cls = registry.get_module(instance.module_type)
            ctx = report.contexts.get(instance.instance_id)
            if ctx is None:
                continue
            inputs = dict(instance.inputs)
            groups: dict = {}
            for row in module_cls.space_rows(instance.settings):
                control, mode = row.get("control", ""), row.get("mode", "parent")
                label = row.get("label", "")
                if not control or not label:
                    continue
                source = inputs.get(f"{control}_{label}")
                if not source:
                    self.events.log(
                        f"{instance.key}.{control}_{label}: no source connected; skipped.",
                        level="warning",
                    )
                    continue
                node = self._resolve_space_source(source, by_key, report)
                if node is None:
                    self.events.log(
                        f"{instance.key}.{control}_{label}: source '{source}' was not "
                        f"found; skipped.",
                        level="warning",
                    )
                    continue
                targets, labels = groups.setdefault((control, mode), ([], []))
                targets.append(node)
                labels.append(label)
                report.spaces.append((f"{instance.key}.{control}_{label}", source))
            for (control, mode), (targets, labels) in groups.items():
                self.backend.connect_space(ctx, control, mode, targets, labels)

    def _resolve_space_source(self, source: str, by_key: dict, report: BuildReport):
        """Return the node for a space source, or None when it cannot be found."""
        key, output = split_source(source)
        if key is not None and key in by_key:
            producer_ctx = report.contexts.get(by_key[key].instance_id)
            if producer_ctx is None:
                return None
            return producer_ctx.outputs.get(output)
        return self.backend.scene_node(source)

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
    def _build_one(self, instance: ModuleInstance, rig_root, bind_parent=None):
        module_cls = registry.get_module(instance.module_type)
        module = module_cls.from_instance(instance)
        problems = module.validate()
        if problems:
            raise BuildError(
                f"'{instance.name}' cannot build: " + "; ".join(problems),
                instance_id=instance.instance_id, module_type=instance.module_type,
            )
        try:
            ctx = self.backend.build_context(module, instance, rig_root, bind_parent)
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

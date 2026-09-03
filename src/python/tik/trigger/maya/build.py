"""Build orchestration: build every instance, then connect declared inputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from maya import cmds

import tik.maya as tm
from tik.trigger.core import registry
from tik.trigger.core.events import EventBus
from tik.trigger.core.exceptions import AttachError, BuildError
from tik.trigger.core.schemas import (
    AFTERLIFE_MODES,
    ModuleInstance,
    order_by_connections,
    order_instances,
    split_source,
)
from tik.trigger.guides import nodes as guide_nodes

from . import tags
from .rig import ModuleRig


@dataclass
class BuildReport:
    """What happened during a build."""

    built: list[str] = field(default_factory=list)  # instance ids in build order
    rigs: dict = field(default_factory=dict)  # instance id -> ModuleRig
    connections: list[tuple[str, str]] = field(
        default_factory=list
    )  # ("L_arm.root", "body.root")
    spaces: list[tuple[str, str]] = field(
        default_factory=list
    )  # ("L_arm.ik_chest", "body.root")
    rig_root: Any = None

    @property
    def count(self) -> int:
        return len(self.built)


# ------------------------------------------------------------------- scene
def build_context(module, instance, rig_root, bind_parent=None) -> ModuleRig:
    """The object a module builds through, wired to its guides."""
    return ModuleRig(
        module,
        instance,
        rig_root,
        guide_nodes.guide_nodes(instance.instance_id),
        bind_parent,
    )


def ensure_rig_root(rig_name: str) -> tm.Transform:
    """The tagged top group every module hangs under, created once per rig."""
    for node in tm.find_by_meta(tags.KIND, tags.RIG_ROOT):
        if node.meta.get(tags.NAME) == rig_name:
            return node
    root = tm.Transform.create(name=f"{rig_name}_rig")
    root.meta.update({tags.KIND: tags.RIG_ROOT, tags.NAME: rig_name})
    return root


def finalize(rig) -> None:
    """Tag a built module's outputs and sockets so tools can find them."""
    for name, node in rig.outputs.items():
        # Every output is a bind joint, so trg_kind must stay "deform" -
        # overwriting it with "output" would erase the classification that
        # skinning and export read. The output role gets its own key.
        marks = {
            tags.INSTANCE: rig.instance.instance_id,
            tags.ROLE: name,
            tags.OUTPUT_NAME: name,
        }
        if node.meta.get(tags.KIND) is None:
            marks[tags.KIND] = tags.OUTPUT
        tags.tag(node, **marks)
    for name, node in rig.attachments.items():
        tags.tag(
            node,
            **{
                tags.KIND: tags.INPUT,
                tags.INSTANCE: rig.instance.instance_id,
                tags.ROLE: name,
            },
        )


def connect(rig, input_name: str, source_node) -> None:
    """Drive a module's socket from the producer's output."""
    tm.MatrixConstraint.create(
        source_node,
        rig.attachments[input_name],
        maintain_offset=True,
        name=rig.name("attach", input_name),
    )


def connect_space(rig, control, mode, targets, labels) -> None:
    """Build one space switch on the controller with role ``control``.

    ``world=False``: nothing appears in the enum that the rigger did not define.
    """
    controller = rig.controller_by_role(control)
    if controller is None:
        raise AttachError(
            f"{rig.instance.key}: no controller with role '{control}'.",
            instance_id=rig.instance.instance_id,
            module_type=rig.module.module_type,
        )
    tm.SpaceSwitch.create(
        controller.transform,
        targets,
        attr_name=f"{mode}Switch",
        mode=mode,
        labels=list(labels),
        world=False,
        name=rig.name(control, mode),
    )


def apply_afterlife(instances, mode: str, document=None) -> None:
    """What happens to the guides once the rig is built.

    Anything but ``keep`` is a deliberate dismissal, and it has to be recorded:
    the document outlives the rendering now, so without this the next reconcile
    would helpfully draw every guide straight back.
    """
    if mode == "keep":
        return
    if document is not None:
        document.dismissed = True
    if not cmds.objExists(tags.GUIDE_HOLDER):
        return
    holder = guide_nodes.holder()
    if mode == "hide":
        holder.visibility = False
    elif mode == "delete":
        from tik.trigger.guides.scene import GuideScene

        scene = GuideScene()
        for instance in instances:
            scene.delete_guides(instance.instance_id)
        if not holder.children:
            holder.delete()


def space_input_names(module_cls, settings) -> set:
    """Names of the inputs derived from anim-space rows."""
    return {item.name for item in module_cls.space_inputs(settings)}


class Builder:
    """Turn the guide instances in the scene into a rig."""

    def __init__(self, events: Optional[EventBus] = None) -> None:
        self.events = events or EventBus()

    @staticmethod
    def order(instances: list[ModuleInstance]) -> list[ModuleInstance]:
        return order_instances(instances)

    def build(
        self,
        scope: Any = "scene",
        rig_name: str = "trigger",
        afterlife: str = "delete",
        document=None,
    ) -> BuildReport:
        if afterlife not in AFTERLIFE_MODES:
            raise ValueError(f"afterlife must be one of {AFTERLIFE_MODES}.")
        instances = self.order(guide_nodes.find_instances(scope, document))
        known_keys = {
            item.key
            for item in (
                instances
                if scope == "scene"
                else guide_nodes.find_instances("scene", document)
            )
        }
        report = BuildReport()
        total = len(instances)
        if not total:
            self.events.log("No module guides found to build.", level="warning")
            return report

        with guide_nodes.undo_chunk(f"Trigger build: {rig_name}"):
            report.rig_root = ensure_rig_root(rig_name)

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
                report.rigs[instance.instance_id] = ctx
                report.built.append(instance.instance_id)
                by_key[instance.key] = instance
                self._connect_one(
                    instance, module_cls, inputs, by_key, report, known_keys
                )
            self._connect_spaces(instances, report, by_key)
            apply_afterlife(instances, afterlife, document)
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
        producer_ctx = report.rigs.get(by_key[key].instance_id)
        if producer_ctx is None:
            return None
        return producer_ctx.outputs.get(output)

    def _connect_one(
        self, instance, module_cls, inputs, by_key, report, known_keys
    ) -> None:
        """Attach every declared input of one already-built instance."""
        rig = report.rigs[instance.instance_id]
        for declared in module_cls.inputs:
            source = inputs.get(declared.name)
            if not source:
                if declared.optional:
                    continue
                raise AttachError(
                    f"{instance.key}.{declared.name}: required input has no source.",
                    instance_id=instance.instance_id,
                    module_type=instance.module_type,
                )
            key, _output = split_source(source)
            if key is not None and key in known_keys and key not in by_key:
                self.events.log(
                    f"{instance.key}.{declared.name}: source '{source}' is outside the build scope; left unattached.",
                    level="warning",
                )
                continue
            node = self.resolve(
                source,
                by_key,
                report,
                where=f"{instance.key}.{declared.name}",
                instance=instance,
            )
            connect(rig, declared.name, node)
            report.connections.append((f"{instance.key}.{declared.name}", source))

    def _connect_spaces(self, instances, report: BuildReport, by_key: dict) -> None:
        """Build one space switch per (control, mode), after all modules exist.

        Deliberately not part of ``order_by_connections``: a space switch does
        not affect the bind hierarchy, and spaces are legitimately mutually
        referential, which would be a false cycle in the topological sort.
        """
        for instance in instances:
            module_cls = registry.get_module(instance.module_type)
            ctx = report.rigs.get(instance.instance_id)
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
                node = self.resolve(source, by_key, report, strict=False)
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
                connect_space(ctx, control, mode, targets, labels)

    def resolve(
        self,
        source: str,
        by_key: dict,
        report: BuildReport,
        *,
        strict: bool = True,
        where: str = "",
        instance=None,
    ):
        """The node a source names.

        A source is ``"<module key>.<output>"`` or a bare scene node name.
        Returns None instead of raising when ``strict`` is False, which is what
        a space connection wants: an unresolved space is a warning, not a
        failed build.
        """
        key, output = split_source(source)
        if key is not None and key in by_key:
            producer = report.rigs.get(by_key[key].instance_id)
            node = producer.outputs.get(output) if producer else None
            if node is None and strict:
                raise AttachError(
                    f"{where}: source '{source}' was not built "
                    f"(available outputs: {sorted(producer.outputs) if producer else []}).",
                    instance_id=instance.instance_id if instance else None,
                    module_type=instance.module_type if instance else None,
                )
            return node
        node = guide_nodes.scene_node(source)
        if node is None and strict:
            raise AttachError(
                f"{where}: source '{source}' is neither a built module output "
                f"nor an existing scene node.",
                instance_id=instance.instance_id if instance else None,
                module_type=instance.module_type if instance else None,
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
                instance_id=instance.instance_id,
                module_type=instance.module_type,
            )
        try:
            ctx = build_context(module, instance, rig_root, bind_parent)
            module.build(ctx)
            missing = [
                name
                for name in module_cls.output_names(instance.settings)
                if name not in ctx.outputs
            ]
            if missing:
                raise BuildError(
                    f"module '{instance.module_type}' did not produce output(s) {missing}",
                    instance_id=instance.instance_id,
                    module_type=instance.module_type,
                )
            finalize(ctx)
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

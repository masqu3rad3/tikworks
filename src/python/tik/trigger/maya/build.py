"""Build orchestration: build every instance, then connect declared inputs."""

from __future__ import annotations

import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Optional

from maya import cmds

import tik.maya as tm
from tik.trigger.core import registry
from tik.trigger.core.build_scope import expand_build_scope
from tik.trigger.core.events import EventBus
from tik.trigger.core.exceptions import AttachError, BuildError
from tik.trigger.core.manifest import TIERS
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
from .scaffold import RigScaffold, ensure_rig, ensure_test_rig


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
    scaffold: Any = None  # RigScaffold
    #: Instance ids removed from the test rig before this build, so a caller
    #: can say what a scoped rebuild actually replaced.
    torn_down: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        """How many modules were built."""
        return len(self.built)


# ------------------------------------------------------------------- scene
def build_context(
    module, instance, scaffold: RigScaffold, bind_parent=None
) -> ModuleRig:
    """The object a module builds through, wired to its guides."""
    return ModuleRig(
        module,
        instance,
        scaffold,
        guide_nodes.guide_nodes(instance.instance_id),
        bind_parent,
    )


def wire_preferences(rig) -> None:
    """Hand the module's visibility switches to the rig-wide preferences.

    The limb group keeps its three attributes so a module stays testable on
    its own; once built into a rig, the preferences drive them and they lock.
    """
    prefs = rig.scaffold.preferences.transform
    limb = rig.groups.limb
    for pref, attr in (
        ("controls", "controlVisibility"),
        ("rig", "rigVisibility"),
        ("joints", "bindVisibility"),
    ):
        plug = limb[attr]
        prefs[pref] >> plug
        plug.locked = True
    for pref, group in (
        ("rigDisplay", rig.groups.rig),
        ("jointsDisplay", rig.groups.bind),
    ):
        group["overrideEnabled"].value = True
        prefs[pref] >> group["overrideDisplayType"]


TIER_ITEMS = (*TIERS, "all")
ALL_INDEX = len(TIERS)


def tier_attr_name(key: str) -> str:
    """The visibilities enum for a module: its display key, made attribute-safe."""
    return re.sub(r"\W", "_", key)


def wire_tiers(rig) -> None:
    """One exclusive-tier enum per module on visibilities_ctrl, driving shapes.

    Tiers are exclusive: ``secondary`` shows secondary controls only, ``all``
    shows the three tiers. Shapes are driven, not transforms, so an FK chain
    whose next control hangs under the previous one keeps its hierarchy.
    Tweaks carry no tier and are left to ``tweakVis`` on their main.
    """
    by_tier: dict[str, list] = {}
    for controller in rig.controllers:
        tier = controller.transform.meta.get(tags.TIER)
        if tier is not None:
            by_tier.setdefault(tier, []).append(controller)
    if not by_tier:
        return
    vis = rig.scaffold.visibilities.transform
    enum = vis[tier_attr_name(rig.instance.key)]
    if not enum.exists():
        enum.create("enum", items=list(TIER_ITEMS), default=ALL_INDEX, keyable=False)
        enum.visible = True
    is_all = enum.eq(ALL_INDEX, 1, 0)
    is_all.node.rename(rig.name("vis", "all", suffix="cond"))
    for tier, controllers in by_tier.items():
        shown = enum.eq(TIERS.index(tier), 1, is_all)
        shown.node.rename(rig.name("vis", tier, suffix="cond"))
        for controller in controllers:
            for shape in controller.transform.shapes:
                shown >> shape["visibility"]


def finalize(rig) -> None:
    """Tag a built module's outputs and sockets, and wire it to the scaffold."""
    wire_preferences(rig)
    wire_tiers(rig)
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


def connect_space(rig, control, mode, targets, labels) -> bool:
    """Build one space switch on the controller with role ``control``.

    ``world=False``: nothing appears in the enum that the rigger did not define.
    Returns False, having built nothing, when no controller carries ``control``
    -- a setting that removed the control must cost a warning, not the rig.
    """
    controller = rig.controller_by_role(control)
    if controller is None:
        return False
    tm.SpaceSwitch.create(
        controller.transform,
        targets,
        attr_name=f"{mode}Switch",
        mode=mode,
        labels=list(labels),
        world=False,
        name=rig.name(control, mode),
    )
    return True


def apply_afterlife(instances, mode: str) -> None:
    """What happens to the guides once the rig is built.

    Taking the guides away needs no record. The document outlives the
    rendering and nothing redraws by itself, so the modules are simply
    not drawn, and the rigger presses Draw when they want them back.
    """
    if mode == "keep":
        return
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
        #: Display key -> instance id for every module in the document, so a
        #: pass can name a producer an earlier pass built. Filled by ``build``.
        self._keys_to_ids: dict = {}
        #: Long path of the scaffold root this build is building into. A scene
        #: can hold the real rig and the test rig at once, so an earlier-pass
        #: lookup has to say which one it means.
        self._root_path: str = ""
        #: True while building into the Guide Designer's throwaway rig.
        self._test: bool = False

    @staticmethod
    def order(instances: list[ModuleInstance]) -> list[ModuleInstance]:
        """The instances parents-first."""
        return order_instances(instances)

    def build(
        self,
        scope: Any = "scene",
        afterlife: str = "delete",
        document=None,
        test: bool = False,
    ) -> BuildReport:
        """Build every guide instance in ``scope`` into a rig.

        ``test`` builds into the Guide Designer's throwaway rig instead of the
        real one, one ``dagContainer`` per module, tearing down whatever it is
        about to rebuild first. A test build is a mock-up the rigger repeats
        while changing settings, so it has to be idempotent; the real build
        path is unchanged.
        """
        if afterlife not in AFTERLIFE_MODES:
            raise ValueError(f"afterlife must be one of {AFTERLIFE_MODES}.")
        report = BuildReport()
        self._test = test
        if test:
            scope = self._prepare_test_scope(scope, document, report)
        instances = self.order(guide_nodes.find_instances(scope, document))
        # From the *document*: a pass that deleted its guides is invisible to a
        # scene scan, which is exactly when a later pass needs its outputs.
        self._keys_to_ids = {}
        for entry in document.modules if document is not None else []:
            if entry.key in self._keys_to_ids:
                raise BuildError(
                    f"two modules share the display key '{entry.key}': "
                    f"{self._keys_to_ids[entry.key]} and {entry.instance_id}. "
                    "Rename one.",
                    instance_id=entry.instance_id,
                    module_type=entry.module_type,
                )
            self._keys_to_ids[entry.key] = entry.instance_id
        total = len(instances)
        if not total:
            self.events.log("No module guides found to build.", level="warning")
            return report

        with guide_nodes.undo_chunk("Trigger build"), self._rig_scope():
            report.scaffold = (
                ensure_test_rig(self.events) if test else ensure_rig(self.events)
            )
            self._root_path = report.scaffold.root.long_name

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
                with self._module_scope(instance, report.scaffold):
                    ctx = self._build_one(instance, report.scaffold, bind_parent)
                    report.rigs[instance.instance_id] = ctx
                    report.built.append(instance.instance_id)
                    by_key[instance.key] = instance
                    self._connect_one(instance, module_cls, inputs, by_key, report)
            self._connect_spaces(instances, report, by_key)
            apply_afterlife(instances, afterlife)
        self.events.log(f"Built {total} module(s).")
        return report

    # ---------------------------------------------------------- test rig
    def _prepare_test_scope(self, scope, document, report: BuildReport):
        """Clear or tear down the test rig, and return the scope to build.

        ``"scene"`` is Build All: the whole test rig goes, because rebuilding
        everything is exactly what wiping it leaves behind. A picked scope is
        expanded first -- downstream to repair consumers that are already
        built, upstream to fill in producers that are not -- and only those
        modules are torn down.
        """
        from . import sandbox

        if scope in ("scene", "selection") or document is None:
            sandbox.clear()
            return scope
        scope = expand_build_scope(
            document.modules, list(scope), sandbox.built_instance_ids()
        )
        report.torn_down = sandbox.teardown(scope)
        return scope

    @contextmanager
    def _rig_scope(self):
        """Create this build's nodes in the test rig's namespace, if it is one.

        The namespace is not decoration. tik.maya resolves nodes through short
        names in several places, so a test rig sharing short names with a built
        real rig makes them ambiguous and the build dies with "Object does not
        exist". The namespace makes them unique by construction.
        """
        if not self._test:
            yield
            return
        from . import sandbox

        with sandbox.namespace(sandbox.TEST_NAMESPACE):
            yield

    @contextmanager
    def _module_scope(self, instance, scaffold):
        """Build this module inside its own container, on a test build.

        The connect wiring belongs inside the block deliberately: an attach
        constraint belongs to the *consumer*, so tearing the consumer down
        takes it too. On a real build this does nothing at all.
        """
        if not self._test:
            yield
            return
        from . import sandbox

        container = sandbox.module_container(
            instance.instance_id, instance.key, scaffold.trigger
        )
        with sandbox.current(container):
            yield

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
        if key is None:
            return None
        if key not in by_key:
            # Built in an earlier pass: found in the scene so this module's
            # bind joints are still created in their final position.
            return self._earlier_pass_output(key, output)
        producer_ctx = report.rigs.get(by_key[key].instance_id)
        if producer_ctx is None:
            return None
        return producer_ctx.outputs.get(output)

    def _connect_one(self, instance, module_cls, inputs, by_key, report) -> None:
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
            with self._module_scope(instance, report.scaffold):
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
                            f"{instance.key}.{control}_{label}: "
                            "no source connected; skipped.",
                            level="warning",
                        )
                        continue
                    node = self.resolve(source, by_key, report, strict=False)
                    if node is None:
                        self.events.log(
                            f"{instance.key}.{control}_{label}: "
                            f"source '{source}' was not found; skipped.",
                            level="warning",
                        )
                        continue
                    targets, labels = groups.setdefault((control, mode), ([], []))
                    targets.append(node)
                    labels.append(label)
                    report.spaces.append((f"{instance.key}.{control}_{label}", source))
                for (control, mode), (targets, labels) in groups.items():
                    if not connect_space(ctx, control, mode, targets, labels):
                        self.events.log(
                            f"{instance.key}: no controller with role '{control}'; "
                            f"its {mode} space was skipped.",
                            level="warning",
                        )

    def _earlier_pass_output(self, key: Optional[str], output: str):
        """The scene node for ``key``.``output`` when an earlier pass built it."""
        if not key:
            return None
        instance_id = self._keys_to_ids.get(key)
        if instance_id is None:
            return None
        return guide_nodes.find_output(
            instance_id, output, under=self._root_path or None
        )

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
                    "(available outputs: "
                    f"{sorted(producer.outputs) if producer else []}).",
                    instance_id=instance.instance_id if instance else None,
                    module_type=instance.module_type if instance else None,
                )
            return node
        earlier = self._earlier_pass_output(key, output)
        if earlier is not None:
            return earlier
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
    def _build_one(self, instance: ModuleInstance, scaffold, bind_parent=None):
        module_cls = registry.get_module(instance.module_type)
        module = module_cls.from_instance(instance)
        problems = module.validate()
        if problems:
            raise BuildError(
                f"'{instance.name}' cannot build: " + "; ".join(problems),
                instance_id=instance.instance_id,
                module_type=instance.module_type,
            )
        for warning in module.warnings():
            self.events.log(f"{instance.key}: {warning}", level="warning")
        try:
            ctx = build_context(module, instance, scaffold, bind_parent)
            module.build(ctx)
            missing = [
                name
                for name in module_cls.output_names(instance.settings)
                if name not in ctx.outputs
            ]
            if missing:
                raise BuildError(
                    f"module '{instance.module_type}' did not produce "
                    f"output(s) {missing}",
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

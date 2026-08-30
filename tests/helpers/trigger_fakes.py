"""In-memory fake backend and toy modules for DCC-free trigger tests."""

from __future__ import annotations

import contextlib
from typing import Optional, Sequence

from tik.trigger.core import Guides, Input, IntField, Module, RigGroups
from tik.trigger.core.schemas import GuidePose, ModuleInstance, ParentRef


class FakeGuideContext:
    def __init__(self, module, backend):
        self.module = module
        self.side = module.side
        self.side_mult = module.side.multiplier
        self.backend = backend
        self.joints: list[tuple[str, int, tuple]] = []

    def joint(self, role, position, *, index=0, parent=None, radius=1.0):
        self.joints.append((role, index, tuple(position)))
        return f"{self.module.name}_{role}_{index}"


class FakeBuildContext:
    def __init__(self, module, instance, rig_root):
        self.module = module
        self.instance = instance
        self.side = module.side
        self.side_mult = module.side.multiplier
        self.groups = RigGroups(
            limb=f"{module.name}_grp",
            socket=f"{module.name}_socket_grp",
            control=f"{module.name}_control_grp",
            rig=f"{module.name}_rig_grp",
            bind=f"{module.name}_bind_grp",
        )
        self.rig_root = rig_root
        self.outputs: dict = {}
        self.attachments: dict = {}
        self.controllers: list = []
        self.deform_joints: list = []
        self.calls: list = []
        self.bind_parent = self.groups.bind

    def guide(self, role, index=0):
        return f"{self.module.name}_{role}_{index}"

    def guides(self, role):
        return [self.guide(role, index) for r, index in self.instance.guide_pairs if r == role]

    def name(self, *tokens, suffix=None):
        parts = [self.side.value, self.module.name, *map(str, tokens)]
        if suffix:
            parts.append(suffix)
        return "_".join(parts)

    def controller(self, name, **kwargs):
        self.controllers.append(name)
        return name

    def tweak_control(self, main, *, size=None, shape="Circle"):
        name = f"{main}_tweak"
        self.controllers.append(name)
        return name

    def bind_joint(self, name, *, parent=None, match=None, radius=1.0):
        node = f"{self.module.name}_{name}_jnt"
        return self.deform_joint(node)

    def controller_by_role(self, role):
        return next((item for item in self.controllers if item.endswith(role)), None)

    def deform_joint(self, node):
        self.deform_joints.append(node)
        return node

    def output(self, name, node):
        self.outputs[name] = node

    def attach(self, name, node):
        self.attachments[name] = node


class FakeBackend:
    """Records everything; instances live in ``self.instances``."""

    name = "fake"

    def __init__(self):
        self.instances: list[ModuleInstance] = []
        self.calls: list[tuple] = []
        self.settings: dict[str, dict] = {}
        self.connections: list[tuple[str, str, str]] = []
        self.space_connections: list = []
        self.scene_nodes: set[str] = set()
        self.afterlife_mode: Optional[str] = None
        self.fail_on: Optional[str] = None
        self.selection = None  # ParentRef returned by selected_guide()
        self.layout: dict = {}

    def new_scene(self):
        self.calls.append(("new_scene",))
        self.instances = []

    @contextlib.contextmanager
    def undo_chunk(self, label):
        self.calls.append(("undo_open", label))
        yield
        self.calls.append(("undo_close", label))

    def find_instances(self, scope="scene"):
        if scope == "scene":
            return list(self.instances)
        return [item for item in self.instances if item.instance_id in scope]

    def create_guides(self, module, parent=None, poses: Optional[Sequence[GuidePose]] = None, inputs=None):
        ctx = FakeGuideContext(module, self)
        module.draw_guides(ctx)
        guides = list(poses) if poses else [
            GuidePose(role, index, position) for role, index, position in ctx.joints
        ]
        resolved = dict(inputs or {})
        if not resolved and parent is not None and module.primary_input() is not None:
            parent_instance = next((item for item in self.instances if item.instance_id == parent.instance_id), None)
            if parent_instance is not None:
                from tik.trigger.core import registry as _registry

                output = _registry.get_module(parent_instance.module_type).output_at_role(parent.role)
                if output:
                    resolved = {module.primary_input().name: f"{parent_instance.key}.{output}"}
        instance = module.to_instance(guides=guides, parent=parent, inputs=resolved)
        self.instances.append(instance)
        self.calls.append(("create_guides", instance.instance_id))
        return instance

    def read_layout(self):
        return dict(self.layout)

    def write_layout(self, layout):
        self.layout = dict(layout)
        self.calls.append(("write_layout",))

    def delete_guides(self, instance_id):
        self.instances = [item for item in self.instances if item.instance_id != instance_id]
        self.calls.append(("delete_guides", instance_id))

    def write_settings(self, instance_id, settings):
        self.settings[instance_id] = dict(settings)
        # find_instances hands back these objects, so they carry the settings
        # too - the Maya backend writes to guide meta and re-reads it.
        for item in self.instances:
            if item.instance_id == instance_id:
                item.settings = dict(settings)

    def read_settings(self, instance_id):
        return dict(self.settings.get(instance_id, {}))

    def guide_node(self, instance_id, role, index=0):
        return f"{instance_id}_{role}_{index}"

    def reparent_guides(self, instance_id, parent):
        for item in self.instances:
            if item.instance_id == instance_id:
                item.parent = parent
        self.calls.append(("reparent", instance_id, parent.instance_id if parent else None))

    def settings_plug(self, instance_id, field_name):
        return f"{instance_id}.{field_name}"

    def install_scene_job(self, event, callback):
        self.scene_jobs = getattr(self, "scene_jobs", {})
        self.scene_jobs[event] = callback
        return len(self.scene_jobs)

    def kill_scene_job(self, job):
        pass

    def fire(self, event):
        callback = getattr(self, "scene_jobs", {}).get(event)
        if callback:
            callback()

    def make_observer(self, callback):
        self.observer_callback = callback

        class _Observer:
            active = False
            muted = False

            def start(self_inner):
                self_inner.active = True

            def stop(self_inner):
                self_inner.active = False

        return _Observer()

    def rename_instance(self, instance_id, name):
        for item in self.instances:
            if item.instance_id == instance_id:
                item.name = name

    def selected_guide(self):
        return self.selection

    def select_guides(self, instance_id):
        self.calls.append(("select", instance_id))

    def selected_node_names(self):
        return list(getattr(self, "selected_names", []))

    def select_nodes(self, nodes):
        self.calls.append(("select_nodes", [str(n) for n in nodes]))

    def selected_node_name(self):
        return "picked_node"

    def ensure_rig_root(self, rig_name):
        self.calls.append(("rig_root", rig_name))
        return rig_name

    def build_context(self, module, instance, rig_root, bind_parent=None):
        if self.fail_on == instance.name:
            raise RuntimeError("boom")
        ctx = FakeBuildContext(module, instance, rig_root)
        if bind_parent is not None:
            ctx.bind_parent = bind_parent
        return ctx

    def finalize(self, ctx):
        self.calls.append(("finalize", ctx.instance.instance_id))

    def connect(self, ctx, input_name, source_node):
        self.connections.append((ctx.instance.key, input_name, source_node))

    def scene_node(self, name):
        return name if name in self.scene_nodes else None

    def set_inputs(self, instance_id, inputs):
        for item in self.instances:
            if item.instance_id == instance_id:
                item.inputs = {key: value for key, value in inputs.items() if value}

    def connect_space(self, ctx, control, mode, targets, labels):
        self.space_connections.append((ctx.instance.key, control, mode, list(labels)))

    def afterlife(self, instances, mode):
        self.afterlife_mode = mode


class ToyRoot(Module):
    label = "Toy Root"
    sided = False
    guides = Guides("root")
    inputs = ()
    outputs = ("root",)
    space_controls = ("root",)

    def draw_guides(self, ctx):
        ctx.joint("root", (0, 0, 0))

    def build(self, ctx):
        ctx.controller("root")
        ctx.output("root", ctx.name("root", suffix="jnt"))


class ToyChain(Module):
    label = "Toy Chain"
    guides = Guides("root", multi="segment", min=1)
    inputs = (Input("root", primary=True), Input("space", optional=True))
    outputs = ("root", "end")
    segments = IntField(2, min=1)

    def guide_count(self):
        return self.segments

    def draw_guides(self, ctx):
        ctx.joint("root", (0, 0, 0))
        for index in range(self.segments):
            ctx.joint("segment", (index + 1, 0, 0), index=index)

    def build(self, ctx):
        ctx.attach("root", ctx.name("root", suffix="grp"))
        ctx.attach("space", ctx.name("space", suffix="grp"))
        ctx.output("root", ctx.guide("root"))
        ctx.output("end", ctx.guides("segment")[-1])
        for joint in ctx.guides("segment"):
            ctx.deform_joint(joint)

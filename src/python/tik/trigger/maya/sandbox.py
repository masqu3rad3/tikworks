"""The Guide Designer's throwaway rig, and the containers that make it tidy.

Spec: docs/superpowers/specs/2026-09-07-test-rig-sandbox-design.md

A test build is a mock-up: the rigger changes a setting, looks, and changes it
again. That needs two things the real build path does not give -- somewhere to
build that is not the real rig, and a teardown so pressing Build twice does not
stack a second copy.

Both come from one Maya feature. A ``dagContainer`` is a transform that also
*owns* the nodes created while it is current, DG nodes included, so a module's
``multMatrix`` chain is as much a member as its joints are. Teardown of one
module is deleting its container; teardown of the whole rig is deleting the
root, which owns the module containers in turn.

Named ``sandbox`` rather than ``test_rig`` so that no file under ``src/``
carries a ``test_`` prefix that pytest might collect.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterable, Optional

from maya import cmds

import tik.maya as tm

from . import tags
from .scaffold import TEST_NAMESPACE, TEST_ROOT, find_test_rig, namespace

__all__ = [
    "TEST_NAMESPACE",
    "TEST_ROOT",
    "namespace",
    "module_container",
    "find_module_container",
    "built_instance_ids",
    "current",
    "teardown",
    "clear",
]


def _containers() -> list:
    """Every ``dagContainer`` in the scene, by long name.

    ``ls(type="container")`` does not list a ``dagContainer`` -- it is its own
    node type -- so this asks for that type by name.
    """
    return cmds.ls(type="dagContainer", long=True) or []


def module_container(instance_id: str, key: str, parent) -> Any:
    """The container one module builds into, created if it is not there yet.

    Found by the instance uuid rather than by name, so renaming a module cannot
    strand its container.
    """
    found = find_module_container(instance_id)
    if found is not None:
        return found
    name = cmds.container(type="dagContainer", name=f"{key}_con")
    node = tm.resolve(cmds.parent(name, parent.long_name)[0])
    # The display key is tagged, not parsed back off the container's name: a
    # rename changes the name, and the tier enum is addressed by the key.
    tags.tag(
        node,
        **{tags.KIND: tags.RIG, tags.INSTANCE: instance_id, tags.NAME: key},
    )
    return node


def find_module_container(instance_id: str) -> Optional[Any]:
    """The container tagged with ``instance_id``, or None."""
    for name in _containers():
        node = tm.resolve(name)
        if node.meta.get(tags.INSTANCE) == instance_id:
            return node
    return None


def built_instance_ids() -> set:
    """The instance ids that currently have a container in the test rig.

    A fact about the scene, read fresh: the alternative is a cached list that
    drifts the moment anyone deletes a group by hand.
    """
    prefix = f"|{TEST_ROOT}|"
    found = set()
    for name in _containers():
        if not name.startswith(prefix):
            continue
        instance_id = tm.resolve(name).meta.get(tags.INSTANCE)
        if instance_id:
            found.add(instance_id)
    return found


@contextmanager
def current(container):
    """Make ``container`` the current one for the duration of the block.

    Maya does not restore an outer container when an inner one is cleared -- it
    sets the current container to nothing -- so the previous value is saved and
    put back by hand. The ``finally`` matters: a build that raises must not
    leave a container current for whatever runs next.
    """
    previous = cmds.container(q=True, current=True) or ""
    cmds.container(container.long_name, edit=True, current=True)
    try:
        yield container
    finally:
        if previous and cmds.objExists(previous):
            cmds.container(previous, edit=True, current=True)
        else:
            cmds.container(container.long_name, edit=True, current=False)


def teardown(instance_ids: Iterable, scaffold=None) -> list:
    """Remove each module's container from the test rig; report what went.

    The container takes the module's nodes, DG ones included. Its tier enum
    lives on the test rig's ``visibilities_ctrl`` -- an attribute on the
    scaffold, not a node in the container -- so that is removed separately.
    """
    from .build import tier_attr_name

    scaffold = scaffold if scaffold is not None else find_test_rig()
    removed = []
    for instance_id in instance_ids:
        container = find_module_container(instance_id)
        if container is None:
            continue
        key = container.meta.get(tags.NAME)
        if scaffold is not None and key:
            plug = scaffold.visibilities.transform[tier_attr_name(key)]
            if plug.exists():
                plug.locked = False
                plug.delete()
        cmds.delete(container.long_name)
        removed.append(instance_id)
    return removed


def clear() -> bool:
    """Delete the whole test rig. True when there was one to delete.

    Removing the namespace and its contents is the completest sweep there is:
    it takes the scaffold, the module containers and every DG node any of them
    created, with nothing left to hunt for.
    """
    if not cmds.namespace(exists=TEST_NAMESPACE):
        return False
    active = cmds.namespaceInfo(currentNamespace=True, absoluteName=True)
    if active == f":{TEST_NAMESPACE}":
        # Removing the current namespace is an error; step out of it first.
        cmds.namespace(set=":")
    cmds.namespace(
        removeNamespace=f":{TEST_NAMESPACE}", deleteNamespaceContent=True
    )
    return True

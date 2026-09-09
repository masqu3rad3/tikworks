"""The Guide Designer's throwaway rig, and the record that makes it tidy.

Spec: docs/superpowers/specs/2026-09-07-test-rig-sandbox-design.md

A test build is a mock-up: the rigger changes a setting, looks, and changes it
again. That needs two things the real build path does not give -- somewhere to
build that is not the real rig, and a teardown so pressing Build twice does not
stack a second copy.

Teardown needs a record of every node a module made, DG utility nodes included.
Maya's ``dagContainer`` is the obvious way to collect those -- it owns whatever
is created while it is current -- and it is the wrong one. The Channel Box
shows the owning container in place of any node inside it, so a controller in a
container shows the container's translate/rotate/scale where the rig's
attributes should be; they are built, they are simply never displayed. So the
record is kept the plain way instead: a uuid census either side of a module's
build, and an ``objectSet`` to hold the difference. A set is a DG node no part
of the UI treats specially.

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
    "module_record",
    "find_module_record",
    "built_instance_ids",
    "capturing",
    "members",
    "teardown",
    "clear",
]


def _absolute(name: str) -> str:
    """``name`` as an unambiguous path, whatever namespace is current.

    Capture happens *inside* the test namespace, and Maya reads a bare
    ``trigger_test:foo`` there as a child of the current namespace -- it looks
    for ``trigger_test:trigger_test:foo`` and reports the node as missing. A
    leading colon roots the name; a DAG long name is already rooted by its
    leading pipe.
    """
    return name if name.startswith(("|", ":")) else f":{name}"


def _resolve(names) -> list:
    """``names`` as unambiguous long paths, dropping any node already gone."""
    found = cmds.ls([_absolute(name) for name in names], long=True) or []
    # ls hands a DG node back bare, so the rooting has to be re-applied.
    return [_absolute(name) for name in found]


#: Node types Maya shares across the whole scene. It makes one on demand, on
#: whichever build first needs it, and every ``ikHandle`` in the scene points
#: at the same one. A census cannot tell that from a node the module made, so
#: it is named here: recording a solver against the module that happened to
#: trigger it lets that module's teardown take every other module's IK with
#: it. Matching is by inheritance, so the four solver subtypes are covered.
SHARED_TYPES = ("ikSolver",)


def _module_owned(names: list) -> list:
    """``names`` without the scene-wide singletons the module merely woke up."""
    shared = {_absolute(name) for name in (cmds.ls(names, type=SHARED_TYPES) or [])}
    return [name for name in names if name not in shared]


def _records() -> list:
    """Every module record set in the test rig's namespace, by name."""
    return cmds.ls(f":{TEST_NAMESPACE}:*", type="objectSet") or []


def module_record(instance_id: str, key: str) -> Any:
    """The set one module's nodes are recorded in, created if it is not there.

    Found by the instance uuid rather than by name, so renaming a module cannot
    strand its record.
    """
    found = find_module_record(instance_id)
    if found is not None:
        return found
    node = tm.resolve(cmds.sets(empty=True, name=f"{key}_set"))
    # The display key is tagged, not parsed back off the set's name: a rename
    # changes the name, and the tier enum is addressed by the key.
    tags.tag(
        node,
        **{tags.KIND: tags.RIG, tags.INSTANCE: instance_id, tags.NAME: key},
    )
    return node


def find_module_record(instance_id: str) -> Optional[Any]:
    """The record set tagged with ``instance_id``, or None."""
    for name in _records():
        node = tm.resolve(name)
        if node.meta.get(tags.INSTANCE) == instance_id:
            return node
    return None


def members(record) -> list:
    """The nodes ``record`` holds, by long name, skipping any already gone."""
    return _resolve(cmds.sets(_absolute(record.partial_name), query=True) or [])


def built_instance_ids() -> set:
    """The instance ids that currently have a record in the test rig.

    A fact about the scene, read fresh: the alternative is a cached list that
    drifts the moment anyone deletes a group by hand.
    """
    found = set()
    for name in _records():
        instance_id = tm.resolve(name).meta.get(tags.INSTANCE)
        if instance_id:
            found.add(instance_id)
    return found


@contextmanager
def capturing(instance_id: str, key: str):
    """Record every node created in the block against ``instance_id``.

    What the scene gained is the whole answer, so the block is bracketed by a
    uuid census and the difference is the module's. Uuids rather than names
    because a build renames as it goes, and the census rather than a
    ``dagContainer`` -- which is the obvious way to catch a DG node made
    through an ``MDGModifier``, and carries three habits a rig cannot live
    with. It takes over the Channel Box for every node inside it, so a
    controller shows the container's translate/rotate/scale in place of the
    rig's attributes. It adopts an unparented DAG node as a child. And letting
    go of it deletes any member that is not connected to something.

    A build that raises still gets what it made recorded, so the next Build
    can tear it down.
    """
    record = module_record(instance_id, key)
    before = set(cmds.ls(uuid=True) or [])
    try:
        yield record
    finally:
        made = [uuid for uuid in (cmds.ls(uuid=True) or []) if uuid not in before]
        caught = _module_owned(_resolve(cmds.ls(made) or [])) if made else []
        if caught:
            cmds.sets(caught, addElement=_absolute(record.partial_name))


def teardown(instance_ids: Iterable, scaffold=None) -> list:
    """Remove each module's nodes from the test rig; report what went.

    The record holds the module's nodes, DG ones included. Its tier enum lives
    on the test rig's ``visibilities_ctrl`` -- an attribute on the scaffold,
    not a node in the record -- so that is removed separately.
    """
    from .build import tier_attr_name

    scaffold = scaffold if scaffold is not None else find_test_rig()
    removed = []
    for instance_id in instance_ids:
        record = find_module_record(instance_id)
        if record is None:
            continue
        key = record.meta.get(tags.NAME)
        if scaffold is not None and key:
            plug = scaffold.visibilities.transform[tier_attr_name(key)]
            if plug.exists():
                plug.locked = False
                plug.delete()
        held = members(record)
        # The set goes first. Maya deletes a set that its own members' removal
        # empties, so deleting the nodes first leaves nothing to delete after.
        cmds.delete(_absolute(record.partial_name))
        # One at a time, checking first: deleting a parent takes its children
        # with it, and handing Maya a path that went with them is an error.
        for name in held:
            if cmds.objExists(name):
                cmds.delete(name)
        removed.append(instance_id)
    return removed


def clear() -> bool:
    """Delete the whole test rig. True when there was one to delete.

    Removing the namespace and its contents is the completest sweep there is:
    it takes the scaffold, the module records and every DG node any of them
    created, with nothing left to hunt for.
    """
    if not cmds.namespace(exists=TEST_NAMESPACE):
        return False
    active = cmds.namespaceInfo(currentNamespace=True, absoluteName=True)
    if active == f":{TEST_NAMESPACE}":
        # Removing the current namespace is an error; step out of it first.
        cmds.namespace(set=":")
    cmds.namespace(removeNamespace=f":{TEST_NAMESPACE}", deleteNamespaceContent=True)
    return True

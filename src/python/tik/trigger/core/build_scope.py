"""Which modules a scoped test build must tear down and rebuild.

Spec: docs/superpowers/specs/2026-09-07-test-rig-sandbox-design.md
Amended by: docs/superpowers/specs/2026-09-09-modules-without-required-inputs-design.md

Pure Python over the guide document's inputs, so it is unit-testable with no
Maya. Cross-module parenting is stored *as the primary input*, which makes
``ModuleEntry.inputs`` the whole graph.

Space inputs are excluded, exactly as ``Builder.build``'s ``structural_inputs``
excludes them: an arm in head space while the head sits in arm space is a
normal rig, and letting that reach the traversal would drag half the rig into
scope.
"""

from __future__ import annotations

from typing import Iterable

from . import registry
from .exceptions import NotFoundError
from .schemas import split_source


def _structural_producers(entry) -> list:
    """The instance ids ``entry`` structurally consumes."""
    skip: set = set()
    try:
        module_cls = registry.get_module(entry.module_type)
    except NotFoundError:
        # Unregistered: it cannot build either, but refusing to compute a
        # scope would turn a build error into an unrelated crash here.
        module_cls = None
    if module_cls is not None:
        skip = {item.name for item in module_cls.space_inputs(entry.settings)}
    found = []
    for name, source in (entry.inputs or {}).items():
        if name in skip or not source:
            continue
        producer, _output = split_source(source)
        if producer:
            found.append(producer)
    return found


def expand_build_scope(
    entries: Iterable, ids: Iterable, already_built: Iterable = ()
) -> list:
    """The instance ids a scoped test build must tear down and rebuild.

    Downstream, to repair: a consumer that is **already built** is rebuilt, so
    the test rig never holds an attach pointing at deleted nodes. A consumer
    that is not built has nothing to dangle and is left alone rather than built
    behind the rigger's back.

    Nothing upstream: an unbuilt producer is left alone and the consumer's
    socket simply stands free at its guide, which is a legal build since
    2026-09-09. Build the producer later and the downstream half rebuilds the
    consumer, which attaches then. This is the ``kinematics`` rule -- a pass
    builds only the modules it names.

    Args:
        entries: The guide document's modules, in document order.
        ids: The instance ids the rigger picked.
        already_built: Instance ids that currently have a record set in the
            test rig.

    Returns:
        The instance ids to build, in document order.
    """
    entries = list(entries)
    order = [entry.instance_id for entry in entries]
    known = set(order)
    producers: dict = {}
    consumers: dict = {}
    for entry in entries:
        sources = [
            producer
            for producer in _structural_producers(entry)
            if producer in known and producer != entry.instance_id
        ]
        producers[entry.instance_id] = sources
        for producer in sources:
            consumers.setdefault(producer, []).append(entry.instance_id)

    built = set(already_built)
    wanted = {instance_id for instance_id in ids if instance_id in known}

    stack = list(wanted)
    while stack:  # downstream: built consumers only
        for consumer in consumers.get(stack.pop(), ()):
            if consumer in wanted or consumer not in built:
                continue
            wanted.add(consumer)
            stack.append(consumer)

    return [instance_id for instance_id in order if instance_id in wanted]

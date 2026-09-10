"""Module groups: many copies of one module, drawn as one node.

A group is a set of same-type module instances the Guide Designer draws as a
single node and edits through a single panel. It is a document-and-UI fact and
nothing else: **grouping never changes the rig**. No group id, label or
membership reaches ``build()``, a guide joint, the bind skeleton or a node
name, and given the same members the build is identical grouped or ungrouped.

Members stay ordinary :class:`~.guide_document.ModuleEntry` objects. Nothing
about a member is special because it is a member, which is what keeps build,
guides, shapes, anim spaces, pivot presets, reconcile and the publish set out
of the feature entirely.

Membership is stored on the group, never on the entry. A ``group_id`` field on
``ModuleEntry`` would be a second copy of the same fact, and the entry is the
thing that gets serialized, diffed against a reference source and copied by
``duplicate`` -- three chances for the two copies to disagree.

Spec: ``docs/superpowers/specs/2026-09-10-module-groups-and-tabs-design.md``
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional

from .exceptions import TriggerError
from .manifest import instance_key


@dataclass
class ModuleGroup:
    """A set of same-type module instances the Designer treats as one.

    ``module_type`` and ``side`` are deliberately absent: both are properties
    of the members, enforced homogeneous when a module joins, so there is no
    second copy of either to fall out of step.
    """

    group_id: str
    label: str
    #: instance_ids, in tab order.
    members: list = field(default_factory=list)

    def key(self, side: str) -> str:
        """Display key: ``L_fingers`` / ``fingers``.

        The same function ``ModuleEntry.key`` uses, so a group and a module
        name themselves by one rule.
        """
        return instance_key(self.label, side)

    def to_dict(self) -> dict:
        """The JSON form stored in the document."""
        return {
            "group_id": self.group_id,
            "label": self.label,
            "members": list(self.members),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ModuleGroup":
        """Rebuild a group from its JSON form."""
        return cls(
            group_id=data["group_id"],
            label=data.get("label", data["group_id"]),
            members=list(data.get("members") or []),
        )


class GroupError(TriggerError):
    """A group operation the document refuses."""


def _entries(document, member_ids) -> list:
    """The entries for ``member_ids``, refusing any id the document lacks."""
    found = []
    for instance_id in member_ids:
        entry = document.module(instance_id)
        if entry is None:
            raise GroupError(f"No module '{instance_id}' to group.")
        found.append(entry)
    return found


def _check_homogeneous(entries) -> None:
    """Same type, same side, wholly local or wholly borrowed."""
    types = {entry.module_type for entry in entries}
    if len(types) > 1:
        raise GroupError(
            f"A group holds modules of the same type; got {sorted(types)}."
        )
    sides = {entry.side for entry in entries}
    if len(sides) > 1:
        raise GroupError(
            f"A group holds modules of the same side; got {sorted(sides)}. "
            "Mirror the group instead."
        )
    origins = {entry.origin for entry in entries}
    if len(origins) > 1:
        raise GroupError(
            "A group is wholly local or wholly referenced. Mixing them would "
            "leave a membership list that is partly this file's word and "
            "partly upstream's, with no answer when upstream drops a member."
        )


def _check_free(document, member_ids) -> None:
    """Refuse a module that some other group already holds."""
    for instance_id in member_ids:
        existing = document.group_of(instance_id)
        if existing is not None:
            raise GroupError(f"'{instance_id}' is already in group '{existing.label}'.")


def make_group(document, label: str, member_ids) -> ModuleGroup:
    """Group ``member_ids`` under ``label``. Mutates ``document`` in place.

    Two members is the minimum, because a group of one is a module -- the same
    rule that makes :func:`leave_group` dissolve on the way down.
    """
    member_ids = list(member_ids)
    if len(member_ids) < 2:
        raise GroupError("A group needs at least two modules.")
    _check_free(document, member_ids)
    _check_homogeneous(_entries(document, member_ids))
    group = ModuleGroup(group_id=uuid.uuid4().hex, label=label, members=member_ids)
    document.module_groups.append(group)
    return group


def join_group(document, group_id: str, instance_id: str) -> None:
    """Append ``instance_id`` to the group, at the end of the tab order."""
    group = document.module_group(group_id)
    if group is None:
        raise GroupError(f"No group '{group_id}'.")
    _check_free(document, [instance_id])
    _check_homogeneous(_entries(document, group.members + [instance_id]))
    group.members.append(instance_id)


def leave_group(document, instance_id: str) -> Optional[str]:
    """Remove ``instance_id`` from whatever group holds it.

    Returns the group id it left, or None when it was in none. A group that
    drops to one member dissolves: a group of one is a module.
    """
    group = document.group_of(instance_id)
    if group is None:
        return None
    group.members = [member for member in group.members if member != instance_id]
    if len(group.members) < 2:
        dissolve_group(document, group.group_id)
    return group.group_id


def dissolve_group(document, group_id: str) -> None:
    """Drop the group and its frame. The modules themselves are untouched.

    The list is edited **in place** rather than rebound. Rebinding works on a
    real ``GuideDocument``, which owns the attribute, but it silently breaks
    any holder of the same list -- and there is one: the Qt test double hands
    its own list to the document so these operations run for real against it.
    An in-place edit is correct for both and costs nothing.
    """
    document.module_groups[:] = [
        group for group in document.module_groups if group.group_id != group_id
    ]
    document.frames.pop(group_id, None)


#: Prefix that folds an input's source into the same table as the settings, so
#: one function answers "is this shared?" for both. A settings key can never
#: collide with it: ``@`` is not a legal Python identifier character, and
#: settings keys are field names.
INPUT_PREFIX = "@input:"


def _declared_inputs(entry) -> list:
    """Every input this entry's module declares, wired or not.

    An unwired input is absent from ``entry.inputs`` -- the document stores
    connections, not the absence of them -- but leaving one unwired is an
    ordinary state, not a missing value (*attachment is a connection, not a
    precondition*). Two members that have both left ``root`` alone agree
    about it, and the panel must be able to say so.
    """
    from .registry import get_module

    try:
        module_cls = get_module(entry.module_type)
    except Exception:  # noqa: BLE001 - an unregistered type has nothing to declare
        return list(entry.inputs)
    return list(module_cls.input_names(entry.settings))


def _value_table(entry) -> dict:
    """One entry's settings and inputs, in a single flat mapping."""
    table = dict(entry.settings)
    names = list(dict.fromkeys(_declared_inputs(entry) + list(entry.inputs)))
    table.update(
        {f"{INPUT_PREFIX}{name}": entry.inputs.get(name, "") for name in names}
    )
    return table


def shared_values(entries) -> dict:
    """Values every entry carries and agrees on.

    Sharing is *derived*, never declared. Nothing in a module class, a manifest
    or the group record says which settings are common -- which is what makes
    the feature land on every module, the ones that ship and the ones written
    afterwards, with no module author doing anything.

    A key missing from any entry is not shared: the members do not agree about
    it, they do not even agree that it exists.
    """
    tables = [_value_table(entry) for entry in entries]
    if not tables:
        return {}
    common = set(tables[0])
    for table in tables[1:]:
        common &= set(table)
    first = tables[0]
    return {
        name: first[name]
        for name in common
        if all(table[name] == first[name] for table in tables)
    }


def varying_names(entries) -> set:
    """Keys some entry has that are not shared -- the fields the tabs own."""
    tables = [_value_table(entry) for entry in entries]
    every = set().union(*tables) if tables else set()
    return every - set(shared_values(entries))

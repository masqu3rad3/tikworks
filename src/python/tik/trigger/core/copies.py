"""The copy list: one module, N repeats of itself.

Pure data. A copy is a row: a slug that keys its guides, a name that reaches
the rig, and a value for every field the module declares ``per_copy``.

The slug and the name are deliberately different things. The slug keys the
guide records; the name is the rigger's and is what the built nodes are
called. Keeping them apart is what lets a rigger rename a copy, or drag its
tab, without orphaning a pose -- the same trap the pivot-preset spec called
out and avoided the same way.

**The first slug is the empty string**, so its roles are ``root``/``segment``
exactly as every module writes today. That is what makes every existing
``.tr`` already a valid one-copy module: no migration, no schema bump, and
adding a second copy cannot disturb the first.

Spec: ``docs/superpowers/specs/2026-09-10-module-copies-design.md``
"""

from __future__ import annotations

from typing import Iterable, Optional

from .exceptions import TriggerError

#: The first copy carries no prefix, so a one-copy module is today's module.
EMPTY_SLUG = ""


class CopyError(TriggerError):
    """A copy-list operation the module refuses."""


def new_slug(existing: Iterable[str]) -> str:
    """The lowest ``cN`` no current copy holds.

    Unique among the copies that exist, which is all that is needed: removing
    a copy also removes its guide records (the module's expected pairs no
    longer contain them, and ``expand_guides`` keeps the entry matched to
    those pairs), so a later copy reusing the slug cannot inherit anything.
    """
    taken = set(existing)
    index = 1
    while f"c{index}" in taken:
        index += 1
    return f"c{index}"


def normalise(rows, per_copy_defaults: dict, module_name: str) -> list[dict]:
    """Return well-formed copy rows: at least one, each fully populated.

    Values for keys that are no longer ``per_copy`` are dropped rather than
    carried, so a module that stops declaring a field does not leave stale
    data behind in every ``.tr`` that ever used it.
    """
    found = []
    for row in rows or [{"slug": EMPTY_SLUG, "name": ""}]:
        clean = {
            "slug": str(row.get("slug", EMPTY_SLUG)),
            "name": row.get("name", ""),
        }
        for key, default in per_copy_defaults.items():
            clean[key] = row[key] if key in row else default
        found.append(clean)
    return found


def row_for(rows, slug: str) -> Optional[dict]:
    """The row with ``slug``, or None."""
    return next((row for row in rows if row.get("slug") == slug), None)


def copy_name(row, module_name: str) -> str:
    """The name this copy builds under.

    A blank name falls back to the module's own, which is what keeps a module
    nobody has added copies to named exactly as it is today.
    """
    return row.get("name") or module_name


def duplicate_row(
    rows, slug: str, per_copy_defaults: dict, taken_names, base: str = ""
) -> dict:
    """The ``[+]`` verb: a new row carrying ``slug``'s values.

    Its *values*, not the field defaults -- a fifth finger wants the fourth
    finger's settings. Its guides are copied by the caller, which is what
    lands the new copy stacked on the one it came from: an unplaced thing
    should look unplaced.

    Its *name*, though, comes from ``base`` -- the module's name -- and is
    numbered up from there: ``arm``, ``arm1``, ``arm2``. The numbering
    belongs to the module rather than to whichever copy was showing, which
    is how Maya names a duplicate and what a rigger expects to see.
    """
    source = row_for(rows, slug)
    if source is None:
        raise CopyError(f"There is no copy '{slug}' to duplicate.")
    made = dict(source)
    made["slug"] = new_slug(row.get("slug", "") for row in rows)
    made["name"] = free_name(base or source.get("name") or "copy", taken_names)
    return made


def free_name(name: str, taken) -> str:
    """``index`` -> ``index1`` -> ``index2`` until it is free."""
    taken = set(taken)
    base = name.rstrip("0123456789") or name
    candidate, index = name, 1
    while candidate in taken:
        candidate = f"{base}{index}"
        index += 1
    return candidate

# Integrating a version control system with Trigger

This guide is for a pipeline developer who wants Trigger to talk to a version
control system — Tik Manager, ShotGrid, Perforce, a folder tree on a server —
and who has never opened Trigger's source.

Everything here is implemented **outside** this repository. You write a Python
package, put its folder on `TRIGGER_PLUGIN_PATH`, and Trigger picks it up. You
never edit Trigger to add a VCS.

Reference implementation: `src/python/tik/trigger/vcs/folder.py`, quoted whole
in section 7. The design record is
`docs/superpowers/specs/2026-09-08-version-control-scaffold-design.md`.

---

## 1. What Trigger asks of a version control system

Trigger is a rigging framework. A session is a `.tr` file: the guides, a build
action list and a publish action list. There are exactly three places a
version control system meets it.

**Rig publish.** The publish list runs as the tail of **Build & Publish**, in
the same run as the build, with the freshly built rig in the scene. A publish
action there saves that scene, exports the guides, collects everything the
session depends on into a `PublishSet`, and hands the set to its own
`deliver()`. You write `deliver()`; everything before it is done for you.
Section 5.

**Element publish.** A rigger publishes one *file* — a script, a weights file,
the guides — without building anything, from the second button on a file field
("Publish `hero_arm.py` to Tik Manager…") or from the right-click menu on a
pipeline action ("Publish to Tik Manager" with one entry per file). Both land
on `provider.publish_file(kind, path, host)`. Trigger stages the file and gets
out of the way: task and category choices belong to your own dialog, and
Trigger records nothing about the result.

**Loading.** Every file field, **File > \<your label\>** and the Guide
Designer's Import/Export Guides can pick a file through your picker instead of
a plain file dialog, and the window's status strip shows a chip saying which
work and version the open session is.

One guarantee holds above all of this:

> **A `.tr` builds identically with or without a version control system
> installed.**

Fields store plain file paths, relative to the session folder where possible.
Nothing on the build path — `trigger/core`, the modules, the systems, the
guides, the runner, the ordinary actions — imports `tik.trigger.vcs` at all;
`tests/unit/test_import_boundaries.py` fails the build if it does. Only
`tik.trigger.ui`, `tik.trigger.actions.publish` and external plugins may. A
rigger without your plugin installed opens the same file and gets the same rig,
minus the buttons.

---

## 2. Getting your code loaded

A Trigger plugin is a folder holding a same-named Python file:

```
<root>/
  tik_manager/
    tik_manager.py        @register_provider("tik_manager")
    tik_manager.png       the icon, beside the file
  tik_publish/
    tik_publish.py        @register_action("tik_publish", scope="publish")
    tik_publish.svg
    defaults.json         optional: overrides field defaults, values only
```

`<root>` goes on `sys.path` and each folder is imported as a top-level package,
so `tik_manager/tik_manager.py` is imported as `tik_manager.tik_manager`. It is
exactly the layout Trigger's own built-in actions use (`script/script.py`).
Folders starting with `_` are skipped, and a plugin that raises on import is
logged and skipped without stopping the others.

Trigger finds `<root>` two ways:

- **`TRIGGER_PLUGIN_PATH`**, an `os.pathsep`-separated list of roots.
- **`tik.trigger.add_plugin_path(path)`**, at runtime, before plugins load.

`tik.trigger.load_plugins()` imports the built-ins and then every external
root. `tik.trigger.ui.main.show()` calls it, so opening the Trigger window is
enough; a headless script calls it itself.

```python
# userSetup.py
import os

import tik.trigger as trigger

os.environ["TRIGGER_PLUGIN_PATH"] = os.pathsep.join(
    [
        "C:/studio/pipeline/trigger_plugins",
        "C:/studio/tik_manager4/tik_manager4/dcc/trigger3/plugins",
    ]
)

# or, without touching the environment:
trigger.add_plugin_path("C:/studio/pipeline/trigger_plugins")

# the Trigger window calls this too; calling it early is harmless
trigger.load_plugins()
```

Two decorators register what a plugin file defines:

- `@register_provider("tik_manager")` from `tik.trigger.vcs`, on a
  `VersionControl` subclass. The name is stamped onto the class as `name`.
- `@register_action("tik_publish", category="finish", icon="tik_publish",
  scope="publish")` from `tik.trigger.core`, on an `Action` subclass. `scope`
  is `"build"`, `"publish"` or `"both"`, and decides which of a session's two
  action lists the action may live in.

Registering the same name twice with a different class raises
`DuplicateRegistrationError`, so pick a name nobody else will use.

---

## 3. The provider contract

`tik/trigger/vcs/provider.py` defines `VersionControl`. **Every verb has a
working default**, so you implement only what your system supports, and the UI
shows only what you answered. `VersionControl.supports("browse")` is how the UI
asks: it is true when your class overrides that method and false when it did
not.

```python
# studio_plugins/vault/vault.py
"""The shape of a provider: every verb, with its signature and its default."""

from typing import Optional

from tik.trigger.vcs import register_provider
from tik.trigger.vcs.provider import Context, VersionControl


@register_provider("vault")
class VaultProvider(VersionControl):
    """A provider is instantiated once; the instance is reused."""

    label = "Vault"        # menu text and button tooltips
    icon = "vault"         # <icon>.png or <icon>.svg beside this file

    def available(self) -> bool:
        """Installed and configured? Called often -- keep it cheap."""
        return True

    def context(self, session_path: str) -> Optional[Context]:
        """What this path is; None when it is not one of your works."""
        return Context(label="hero / rig_main", version=7, is_latest=True,
                       detail=session_path)

    def browse(self, kind: str, extensions: list, mode: str) -> str:
        """Your own picker. The chosen path, or "" when cancelled."""
        return ""

    def new_version(self, host) -> str:
        """Save the host's session as the next version; the new path."""
        return str(host.save_as("//server/hero/rig_main_v008.tr"))

    def open(self, host) -> str:
        """Pick a session and open it through the host; the path."""
        picked = self.browse("session", [".tr"], "open")
        if picked:
            host.open(picked)
        return picked

    def publish_file(self, kind: str, path, host) -> None:
        """Hand one file to your own publish/ingest dialog."""

    def launch(self, host) -> None:
        """Open your main window."""
```

What each verb buys you in the UI:

| Verb | Default | Left alone | Implemented |
|---|---|---|---|
| `available()` | `False` | your provider is never used | it can be picked as the active one |
| `context(session_path)` | `None` | the status chip reads "Not a \<label\> work" in amber | the chip reads `label · v###`, green when `is_latest`, amber when not, with `detail` as its tooltip |
| `browse(kind, extensions, mode)` | `""` | file fields show no "Browse \<label\>…" entry, and the guide Import/Export picker goes straight to the plain dialog | fields and the guide picker offer your browser beside the plain one |
| `new_version(host)` | `""` | no **Save New Version** in the File submenu | the entry appears |
| `open(host)` | `""` | no **Open from \<label\>…** | the entry appears |
| `publish_file(kind, path, host)` | does nothing | no "Publish … to \<label\>" on file fields or in the pipeline's right-click menu | both appear, one entry per existing file the action names |
| `launch(host)` | does nothing | no **Open \<label\>** entry, and clicking the status chip does nothing | both open your window |

One entry does not depend on a verb: **File > \<label\> > Publish…** is always
there, runs Build & Publish, and is enabled only while the open session's
publish list has something in it.

Two more helpers you rarely override: `display_label()` returns `label`, else
the registered name title-cased, else the class name; `icon_path()` finds
`<icon>.png` or `<icon>.svg` beside your provider's own file, the same rule
actions and modules follow.

`Context` is a frozen dataclass with four fields and no behaviour:

```python
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Context:
    label: str                    # "hero / rig_main"
    version: Optional[int] = None
    is_latest: bool = True
    detail: str = ""              # the chip's tooltip
```

### The host

A provider never imports Trigger's window. It receives `host`, the single
object Trigger exposes outward — `tik.trigger.vcs.host`. The window attaches
itself when it opens; a headless script attaches a `Session`. Both look
identical from a provider:

```python
from tik.trigger.session import Session
from tik.trigger.vcs import host

host.attach(session=Session("C:/shows/hero/rig_main.tr"))

host.session        # the active Session, or None
host.session_path   # its file with forward slashes, or ""
host.is_modified    # unsaved changes?
host.open(path)     # open a .tr in the window, or in the headless session
host.save_as(path)  # save the active session there; returns where it went
host.refresh()      # tell the window the VCS context changed (repaints the chip)
host.feedback       # a correctly parented Feedback for your own dialogs
host.detach()       # forget everything
```

`host.feedback` is Trigger's one dialog surface (`tik.shared.ui.feedback`):
message boxes, file browsers and text prompts, already parented to the right
window. Use it for your own questions rather than raw Qt dialogs.

### Which provider is active

`tik.trigger.vcs.active()` returns the provider in use, or `None`:

- the only registered provider whose `available()` is true;
- when several are available, the one named by `vcs.set_preferred(name)`;
- otherwise the first by name, with a log line saying which was picked and why.

A provider whose `available()` raises is logged and treated as unavailable —
your bug must not stop Trigger from opening. `vcs.require()` is `active()` or a
`VersionControlError`. With no provider, every entry point above is simply
absent.

`tik.trigger.vcs` never imports the preferences packages; the window reads the
`vcs.provider` preference and calls `set_preferred` for you. That keeps the
preferences guarantee intact: a preference can never change what a rig builds.

### Headless verbs

The same four operations the menu runs, callable from a script, each one line
into the active provider and the host:

```python
from tik.trigger import vcs

vcs.open()                          # pick and open a session; the path or ""
vcs.new_version()                   # save the session as its next version
vcs.publish_file("script", path)    # hand one file to your dialog
vcs.launch()                        # open your main window

vcs.active()                        # the provider, or None
vcs.provider_names()                # every registered name
vcs.set_preferred("vault")          # break a tie between available providers
```

---

## 4. Kinds

A *kind* is a plain string saying what a file **is**, so a provider can map it
onto its own element types without parsing paths. It is passed to `browse` and
to `publish_file`, and it labels every artifact in a publish set.

`tik/trigger/core/kinds.py` (re-exported as `tik.trigger.vcs.kinds`) holds the
vocabulary:

| Constant | Value | Extensions |
|---|---|---|
| `SESSION` | `"session"` | `.tr` |
| `GUIDES` | `"guides"` | `.trg` |
| `SCRIPT` | `"script"` | `.py` |
| `MODEL` | `"model"` | `.ma` `.mb` `.fbx` `.obj` `.abc` `.usd` |
| `RIG` | `"rig"` | `.ma` `.mb` |
| `FILE` | `"file"` | anything else |

`ORDER` is the resolution order when an extension belongs to more than one
kind: a bare `.mb` field is more likely a model an action imports than a built
rig. `kind_for(extensions, declared="")` returns `declared` when a field states
one, else the first kind sharing an extension, else `FILE`.

The vocabulary is **open**. An action may use any string — `"weights"`,
`"corrective"` — and a provider that does not recognise a kind treats it as a
generic file.

A field declares its kind with `FileField(kind=)`; a field without one falls
back to the extension mapping:

```python
from tik.trigger.core import Action, FileField
from tik.trigger.core.kinds import EXTENSIONS, GUIDES, kind_for


class Example(Action):
    guide_file = FileField("", extensions=[".trg"])                 # -> "guides"
    weights = FileField("", extensions=[".json"], kind="weights")   # -> "weights"


assert kind_for([".trg"]) == GUIDES
assert kind_for([".json"], declared="weights") == "weights"
assert EXTENSIONS[GUIDES] == (".trg",)
```

---

## 5. Writing a publish action

Publishing splits in two: **collecting** what to publish, which is the same
everywhere and Trigger does it; and **delivering** it, which is yours.

### `PublishAction`

`tik.trigger.actions.publish.publish.PublishAction` is an `Action` with a fixed
`run(ctx)`. Subclass it, register with `scope="publish"`, and implement one
method:

```python
def deliver(self, publish_set: PublishSet, ctx: ActionContext) -> None: ...
```

`run()` does the rest, in this order:

1. Refuses to start unless the session is saved (`validate` says
   "save the session first", so the failure is reported before the build).
2. Saves the current Maya scene as `<session folder>/_publish_tmp/<name>_rig.mb`.
   The runner guarantees a publish action only ever runs as the tail of a full
   Build & Publish, so the scene is the clean, freshly built rig.
3. Exports the guides to `<name>.trg` beside it, when `include_guides` is on.
4. Builds the `PublishSet`, asking every enabled build action that overrides
   `products()` for the files it wrote, when `include_products` is on.
5. Calls `self.deliver(publish_set, ctx)`.
6. Deletes the temporary folder.

Everything `deliver` needs is already on disk by the time it is called, and it
is a *delivery*: copy, upload, register. It must not edit the session — the
`PublishSet` carries the document so the bundle writer can rewrite a copy of
it, not so a destination can change what the rigger has open. Anything `deliver`
raises becomes an `ActionExecutionError` carrying your action's label, and the
temporary folder is left in place for inspection.

On top of the `notes` field every action has, the base adds `include_guides`
and `include_products`, both on by default.

### `PublishSet`

`tik/trigger/core/publish_set.py` is pure Python — no Maya, no Qt, no provider.

```python
from pathlib import Path

from tik.trigger.core.publish_set import Artifact, Dependency, PublishSet


def describe(publish_set: PublishSet) -> None:
    publish_set.name          # "hero", the session stem
    publish_set.session       # Path to the .tr
    publish_set.base_dir      # the session's folder; every relative path resolves here
    publish_set.document      # the in-memory Document (guides + both action lists)
    publish_set.artifacts     # list[Artifact]: the session, the .trg, the rig, products
    publish_set.dependencies  # list[Dependency]: every file the session needs to build

    for artifact in publish_set.artifacts:
        artifact.kind         # "session" | "guides" | "rig" | whatever a product says
        artifact.path         # Path
        artifact.label        # optional display name

    for dependency in publish_set.dependencies:
        dependency.path       # absolute Path
        dependency.original   # the value written in the document
        dependency.owner      # the action path that named it, e.g. "arms/load_weights"
        dependency.external   # an absolute path outside the session folder


assert Artifact("rig", Path("hero_rig.mb")).label == ""
assert Dependency(Path("a.py"), "a.py", "script", False).external is False
```

Dependencies are gathered recursively: a `reference` action's `.tr` is loaded
and its own dependencies collected too, as are the guide document's module
references. Disabled actions are skipped, and an unknown action type is
warned about, not guessed at.

### The bundle

`write_bundle(publish_set, target, store_root=None)` writes one self-contained
version:

```
<target>/
  hero.tr             the session with every file path rewritten into the store
  hero.trg
  hero_rig.mb
  manifest.json
  <products…>
<target>/../_store/   default when store_root is not given
  <sha1>_<name>       one file per distinct content
  index.json          the (size, mtime) -> hash cache
```

The store is **flat and content-addressed**: SHA-1 over the file's content,
prefixed to its original name. Publishing forty versions of a rig whose weights
file never changed stores that file once, and every version still opens on its
own because its `.tr` points into the store. Hashing is skipped when the
store's `index.json` already has a matching `(size, mtime)` entry.

Two rules about paths. A **relative** value belongs to the session however many
`..` it climbs, so it is bundled — otherwise the copy could not open. An
**absolute** path pointing outside the session folder (a studio model library)
is left exactly as the rigger wrote it and flagged `external` in the manifest:
the publisher may warn, never guess. A referenced `.tr` is rewritten and stored
too, and its `version` setting is pinned.

`manifest.json`:

```json
{
  "session": "hero.tr",
  "artifacts": [
    {"kind": "session", "path": "hero.tr", "label": ""},
    {"kind": "guides", "path": "hero.trg", "label": ""},
    {"kind": "rig", "path": "hero_rig.mb", "label": ""}
  ],
  "dependencies": [
    {
      "owner": "arms/load_weights",
      "original": "weights/arm.json",
      "hash": "1f0a…",
      "size": 20480,
      "store": "../_store/1f0a…_arm.json",
      "external": false
    }
  ]
}
```

Every `store` value is relative to the **bundle folder the manifest sits in**,
whatever document named the file, so reading a manifest never requires knowing
where anything came from.

`Store(root)` is the store's API — `hash_file(path)`, `put(path)`,
`put_bytes(data, name)`, `files()` — and
`clean(store_root, bundle_roots)` deletes every stored file no manifest under
`bundle_roots` names, returning what it removed. Nothing calls `clean`
automatically; it is a tool a rigger runs.

### A minimal publish action

This is the whole of a second destination. It writes the same bundle the
generic `publish` action writes, into a studio vault:

```python
# studio_plugins/vault_publish/vault_publish.py
"""Publish the built rig into the studio vault."""

from tik.trigger.actions.publish.publish import PublishAction
from tik.trigger.core import FileField, register_action, versioning
from tik.trigger.core.action import ActionContext
from tik.trigger.core.publish_set import STORE_DIR, PublishSet, write_bundle


@register_action(
    "vault_publish", category="finish", icon="vault_publish", scope="publish"
)
class VaultPublish(PublishAction):
    """Write one versioned bundle per publish into a vault folder."""

    label = "Vault Publish"

    vault = FileField(
        "", mode="dir", label="Vault folder", help="Where versions go."
    )

    def summary(self) -> str:
        return self.vault

    def validate(self, ctx: ActionContext) -> list:
        problems = super().validate(ctx)
        if not self.vault:
            problems.append("vault_publish: pick a vault folder")
        return problems

    def deliver(self, publish_set: PublishSet, ctx: ActionContext) -> None:
        root = ctx.resolve(self.vault)
        store_root = root / STORE_DIR
        store_root.mkdir(parents=True, exist_ok=True)
        target = versioning.next_version(root / publish_set.name)
        write_bundle(publish_set, target, store_root=store_root)
        ctx.log(f"Bundle written: {target}")
```

A delivery that talks to a real VCS does the same collection and then hands the
paths to its own API instead of `write_bundle`; see section 8.

---

## 6. Making an action publishable

An action is *publishable on its own* — its files appear in the right-click
publish submenu, and they are carried into every bundle — when it declares
them. There are three declarations, and the same ones drive both.

**`FileField`.** Every non-directory `FileField` on an action is a dependency
by default; `Action.file_fields()` returns them, and `mode="dir"` fields are
excluded because a folder is not a file to publish. Add `kind=` when the
extension does not say enough.

**`dependencies(ctx)`** returns absolute `Path`s the action needs **to build**.
The default is every non-empty file field resolved against the session folder.
Override it when the files are not fields — a script's siblings, a folder of
per-joint weights.

**`products(ctx)`** returns `Artifact`s the action **wrote during this run** and
wants published as their own elements. Empty by default. `PublishSet` calls it
only on actions that override it (`Action.has_products()` is how it checks), so
an action that captures scene data writes it here and returns what it wrote.

A weights action is the shape of a fully version-controlled action: a field, a
`dependencies` that adds its side files, a `products` that writes and returns.

```python
# studio_plugins/skinweights/skinweights.py
"""Skin weights: read at build time, published as their own element."""

from studio.weights import apply_weights, save_weights

from tik.trigger.core import Action, FileField, register_action
from tik.trigger.core.action import ActionContext
from tik.trigger.core.publish_set import Artifact

WEIGHTS = "weights"


@register_action("skinweights", category="deform", icon="skinweights")
class SkinWeights(Action):
    """Apply a weights file, plus the per-mesh files beside it."""

    label = "Skin Weights"

    file_path = FileField(
        "", extensions=[".json"], kind=WEIGHTS, label="Weights File"
    )

    def run(self, ctx: ActionContext) -> None:
        for path in self.dependencies(ctx):
            apply_weights(path)

    def dependencies(self, ctx: ActionContext) -> list:
        """The field, plus every per-mesh file in the folder it names."""
        found = super().dependencies(ctx)
        if self.file_path:
            folder = ctx.resolve(self.file_path).parent / "meshes"
            found.extend(sorted(folder.glob("*.json")))
        return found

    def products(self, ctx: ActionContext) -> list:
        """Capture what the scene has now and publish it as a "weights" element."""
        target = ctx.resolve(self.file_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        save_weights(target)
        return [Artifact(WEIGHTS, target, label="skin weights")]

    @classmethod
    def pin_settings(cls, settings: dict) -> dict:
        """Freeze anything derived from the file's name before it is rewritten."""
        return {}
```

The last hook, **`pin_settings(settings)`**, is a classmethod returning settings
the bundle must write down before it rewrites paths. A bundled file lands in
the store under a hashed name, so a setting that *defaulted* from the file's
name would quietly mean something else in the published copy. The built-in
`script` action uses it to freeze `import_as` to the original file's stem. If
nothing on your action derives from a file name, return `{}` — which is the
default, so you need not write it at all.

---

## 7. A complete minimal provider

`tik/trigger/vcs/folder.py` ships with Trigger: a version control system that is
only a folder tree, implementing every verb in the simplest form that works.
Point `TRIGGER_FOLDER_VCS` at a folder and it versions sessions under
`sessions/` and published files under `<kind>/`. Copy it and replace the bodies.

```python
# src/python/tik/trigger/vcs/folder.py
"""A version control system that is only a folder tree.

The reference provider: every verb of the contract in the simplest form that
works, and the file the integrator's guide quotes. Point ``TRIGGER_FOLDER_VCS``
at a folder and Trigger versions sessions under ``sessions/`` and published
files under ``<kind>/``, ``_v###`` style.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

from tik.trigger.core import versioning
from tik.trigger.vcs import kinds, register_provider
from tik.trigger.vcs.provider import Context, VersionControl

ROOT_VAR = "TRIGGER_FOLDER_VCS"


@register_provider("folder")
class FolderProvider(VersionControl):
    """Versioned folders, no server, no dialogs of its own."""

    label = "Folder"

    def __init__(self, root=None) -> None:
        self.root = Path(root or os.environ.get(ROOT_VAR, ""))

    def available(self) -> bool:
        return bool(str(self.root) != ".") and self.root.is_dir()

    def context(self, session_path: str) -> Optional[Context]:
        path = Path(session_path)
        if not session_path or self.root.resolve() not in path.resolve().parents:
            return None
        stem, version, _suffix = versioning.parse(path)
        latest = versioning.latest_version(path)
        latest_number = versioning.parse(latest)[1] if latest else version
        return Context(
            label=stem,
            version=version,
            is_latest=version is None or version >= (latest_number or 0),
            detail=str(path),
        )

    def browse(self, kind: str, extensions: list, mode: str) -> str:
        from tik.trigger.vcs import host

        folder = self.root / ("sessions" if kind == kinds.SESSION else kind)
        return host.feedback.browse_open("Pick a file", str(folder), tuple(extensions))

    def new_version(self, host) -> str:
        session = host.session
        if session is None:
            return ""
        folder = self.root / "sessions"
        folder.mkdir(parents=True, exist_ok=True)
        target = versioning.next_version(folder / session.name)
        return str(host.save_as(target)).replace("\\", "/")

    def open(self, host) -> str:
        picked = self.browse(kinds.SESSION, [".tr"], "open")
        if picked:
            host.open(picked)
        return picked

    def publish_file(self, kind: str, path, host) -> None:
        source = Path(path)
        folder = self.root / kind
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, versioning.next_version(folder / source.name))

    def launch(self, host) -> None:
        from tik.shared.io import open_external

        open_external(self.root)
```

---

## 8. The tik_manager4 integration

[tik_manager4](https://github.com/masqu3rad3/tik_manager4) is the first real
implementation, and it follows exactly the path above: an external plugin root,
no changes to Trigger. It lives in tik_manager4's own repository under
`tik_manager4/dcc/trigger3` (the older `dcc/trigger` integration is untouched),
and it is worth reading as the worked example.

tik_manager4 models every host application as a *DCC*, with folders of
`extract` plugins (publish one element), `ingest` plugins (load one element),
`validate` and `extension`. `trigger3` makes Trigger one of those hosts **and**
registers a Trigger provider, which is the same host object seen from both
sides.

| File | What it implements |
|---|---|
| `_host.py` | the single import site for `tik.trigger.vcs.host`, so the whole integration reaches Trigger through one file. |
| `main.py` | the `Dcc(MainCore)` adapter — `name = "trigger3"`, `formats = [".tr"]` — forwarding `save_scene`, `save_as`, `open`, `get_scene_file`, `is_modified` and `get_main_window` to the host verbs of section 3, with `post_save`/`post_publish` calling `host.refresh()`. |
| `extract/source.py` | the `.tr` bundle element: builds the `PublishSet` of section 5 from the host session and writes it into the version folder. |
| `extract/rig.py` | the built scene element: builds through `host.session` and saves the `.mb`. |
| `extract/guides.py` | the guides element: exports the session's `.trg`. |
| `ingest/source.py` | the other direction — opens a published bundle's `.tr` through `host.open`. |
| `ingest/guides.py` | imports a published `.trg` into the active session's guides. |
| `plugins/tik_manager/tik_manager.py` | the provider: `@register_provider("tik_manager")`, label "Tik Manager". `context` is a work lookup by absolute path, `new_version` is a new work version saved through the host, `open` and `browse` run the picker, `publish_file` opens tik_manager's ingest dialog with the file preselected, `launch` opens its main window. |
| `picker.py` | the dialog behind `browse` and `open`: tik_manager's own subproject, task, category and version widgets, returning the chosen version's file (or an element's path, filtered by the field's extensions). |
| `plugins/tik_publish/tik_publish.py` | the `PublishAction` subclass of section 5. Its `deliver` reserves a version, hands the already-collected `PublishSet` to the resolved extractors and publishes with the action's notes; its `validate` performs the same work lookup, so "the session is not saved in a Tik Manager work" stops the build before it starts rather than at the end. |
| `setup/how-to-install.txt` | the two lines a studio needs: put `dcc/trigger3/plugins` on `TRIGGER_PLUGIN_PATH`, and list `source`, `rig` and `guides` in the project's category definition for rig works. |

The one thing to copy from it: the extractors serve **two** callers. Driven by
tik_manager's own publish dialog they collect for themselves; driven by
`tik_publish` at the tail of a build the set already exists, so the action
assigns it to each resolved extractor and they write from it. One code path per
element, and no rebuild at the end of a build.

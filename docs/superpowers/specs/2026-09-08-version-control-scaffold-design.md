# Version Control Scaffold — Design

**Date:** 2026-09-08
**Status:** Approved, pending implementation plan
**Scope:** `tik/trigger/core/publish_set.py`, `tik/trigger/vcs`,
`tik/trigger/actions/publish`, `tik/trigger/core/discovery.py`,
`tik/shared/ui/fields.py`, `tik/trigger/ui`, `docs/trigger/`; and, in the
tik_manager4 repository, `tik_manager4/dcc/trigger3`

---

## 1. Purpose

Trigger has no way to talk to a version control system. The old Trigger had
one, but it was two unrelated things glued together: tik_manager4 buttons
injected into Trigger's header through a global handle onto the main window,
and a ShotGrid class with hardcoded path templates. Neither side had a
contract the other could implement, so every new VCS meant editing Trigger.

This design gives Trigger a small, documented contract that any version
control system implements from **outside** the repository, and uses
tik_manager4 as the first, worked implementation. It carries one guarantee
that follows from the preferences guarantee:

> **A `.tr` builds identically with or without a version control system
> installed.** The document stores plain file paths, and nothing on the build
> path reads the provider.

Three flows are covered:

1. **Rig publish.** The tail of Build & Publish bundles the built scene, the
   session, the guides and every file the session depends on, and delivers
   the bundle to a folder or to a VCS.
2. **Element publish.** A rigger publishes one action's file (a script, a
   weights file, the guides) on its own, through the VCS's own dialog.
3. **Loading.** Every file field, the Open menu and the Designer's guide
   import can pick a file from the VCS, and the window shows which work and
   version the session is.

---

## 2. What exists today

| Piece | Location | Relevance |
|---|---|---|
| Headless `Session` | `trigger/session.py` | open, save, increment, build, `is_modified` — the API a VCS drives |
| `Feedback.set_browser` | `shared/ui/feedback.py` | replaces every file picker repo-wide; stays as the pipeline seam |
| `FileField` | `core/fields.py` | `extensions`, `mode`; the natural place for a *kind* |
| `Action.save_from_scene` | `trigger/core/action.py` | an unused stub for side files; folded into `products` |
| Publish list, `scope` | `core/document.py`, `core/registry.py` | publish actions run only as the tail of a full build |
| `versioning` | `core/versioning.py` | `_v###` on disk; the generic publish reuses it |
| Plugin discovery | `core/discovery.py` | scans only Trigger's own packages; no external plugins |
| tik_manager4 `dcc/trigger` | tik_manager4 repo | the **old** integration; must keep working untouched |

tik_manager4 treats each host as a "DCC": a `Dcc(MainCore)` with
`save_scene`, `save_as`, `open`, `get_scene_file`, `is_modified`, and folders
of `extract` (publish elements), `ingest` (load elements), `validate` and
`extension` plugins. Its publisher resolves the current work from the DCC's
scene file, picks extractors from the work's category definition, reserves a
`.tpub`, runs each extractor into the version folder and finalises with notes.

---

## 3. Decisions

Each of these was a fork in the design; the choice and the reason are
recorded so they are not relitigated.

1. **Trigger owns the contract; the VCS implements it.** A provider interface
   in Trigger, implemented from outside. tik_manager4's DCC adapter is a
   consumer of the same headless API, not a second design.
2. **Fields store plain paths.** No URIs resolved at build time. The on-disk
   `version: latest | pinned | v###` mechanism keeps working and the build
   never touches the VCS.
3. **One `PublishAction` base, concrete actions per destination.** The shared
   part of publishing is *collecting what to publish*, not delivering it.
   `publish` writes a versioned folder with no VCS; `tik_publish` is a
   subclass in tik_manager4's repo; a studio's `shotgrid_publish` is a third,
   like a custom HDA. There is no generic provider-driven publish action.
4. **Element publish hands off to the VCS's own dialog.** Trigger stages the
   file and calls `provider.publish_file`; task and category choices are the
   VCS's business. Trigger records nothing about the result.
5. **The tik_manager4 side lives in tik_manager4**, as an external Trigger
   plugin under `dcc/trigger3`, discovered through a plugin path. That is the
   same path a studio follows, so tik_manager4 is the worked example rather
   than a special case. The old `dcc/trigger` stays byte-identical until it is
   deprecated.
6. **Bundles deduplicate through a content-addressed store.** Copying every
   dependency into every version would replicate an unchanged weights file
   forty times. The store holds one copy per distinct content; each version
   stays self-contained and immutable.
7. **The VCS is additive in the UI.** Plain browsing stays; a provider adds a
   second button on file fields, a File submenu, a status chip and a
   right-click entry on actions.

---

## 4. Packages and boundaries

```
tik/trigger/core/publish_set.py     pure: PublishSet, Artifact, manifest, hashing, path rewriting
tik/trigger/vcs/__init__.py         registry, active(), the host, headless verbs
tik/trigger/vcs/provider.py         VersionControl base class, Context
tik/trigger/vcs/kinds.py            the kind vocabulary and extension mapping
tik/trigger/vcs/folder.py           FolderProvider: reference implementation, quoted in the guide
tik/trigger/actions/publish/        PublishAction base + the generic `publish` action (+ .svg)
tik/trigger/config/pages/vcs.py     one preference: the active provider when several are installed
docs/trigger/integrating-version-control.md
```

Boundaries, enforced by extending `tests/unit/test_import_boundaries.py`:

- `core` stays pure. `publish_set` knows files and hashes; never Maya, Qt or
  a provider.
- `tik.trigger.vcs` may be imported only by `tik.trigger.ui`,
  `tik.trigger.actions.publish` (and its subclasses) and external plugins.
  Modules, systems, guides, the runner and every other action never see it.
  `PublishAction` and the generic `publish` action do not import it either;
  only a subclass that talks to a VCS does.
- `tik.trigger.vcs` never imports `tik.trigger.config` or `tik.shared.prefs`
  (section 7, Activation), so the preferences guarantee holds transitively.
- Nothing in tikworks imports `tik_manager4`.

### External plugins

`discover()` gains a second source. `TRIGGER_PLUGIN_PATH` (`os.pathsep`
separated) and `trigger.add_plugin_path(path)` each name a folder in the same
`<name>/<name>.py` layout as the built-ins, so `tik_publish/tik_publish.py`
there registers like `script/script.py` here. Providers register with
`@register_provider("tik_manager")` in the same or a sibling file, and
`load_plugins()` imports them all. A plugin that fails to import is logged
and skipped, as today.

---

## 5. The publish set

`PublishSet` is the one thing every publish shares: a pure object describing
what a session needs, assembled at the tail of Build & Publish.

### Contents

1. **Core artifacts**, always present, each an `Artifact(kind, path, label)`:
   the `.tr` (`session`), the guides export (`guides`, a `.trg` written from
   the session's guide document) and the built scene (`rig`, saved from the
   current Maya scene by the publish action).
2. **Dependencies**: every file the session needs to build. The default comes
   from the schema: every `FileField` value on every enabled action,
   recursively through `reference` actions and module references, resolved
   against its own session folder. An action overrides
   `dependencies(ctx) -> list[Path]` when its files are not fields: the
   script action's `scripts/` siblings its file imports, a future weights
   action's per-joint files.
3. **Products**: files an action wrote during this run and wants published as
   their own element, from `Action.products(ctx) -> list[Artifact]`. Empty by
   default. `save_from_scene` is folded into this: an action that writes
   scene data does it inside `products` and returns what it wrote.
4. **Pins**: `Action.pin_settings(settings) -> dict` returns settings the
   bundle must freeze because a rewritten path changes a derived value; the
   script action pins `import_as` to the original stem, since its file is
   renamed to its hash in the store. Applied by the rewrite to every
   document, nested ones included.

### The bundle

```
<target>/
  hero.tr              dependency paths rewritten
  hero.trg
  hero_rig.mb
  manifest.json        every dependency: original relative path, hash, size, store path, external flag
  <products...>
<target>/../_store/<sha1>_<name>
```

- Each dependency path in the copied `.tr` is rewritten to its store path
  relative to the bundle. Every version therefore opens and builds on its
  own, and byte-identical content exists once, whatever the version count.
- Absolute paths outside the session folder (a studio model library) are left
  untouched and listed in the manifest as `external`; the publisher may warn,
  never guess.
- A referenced `.tr` is bundled recursively; its own dependencies land in the
  same store.
- Hashing is SHA-1 over content, skipped when a `(size, mtime)` entry in the
  store's cache matches.
- `PublishSet.clean(store_root, bundle_roots)` deletes store files no manifest
  under `bundle_roots` names. It is a tool a rigger runs; nothing runs it
  automatically.

The store is flat: a nested referenced `.tr` is rewritten and stored too, and
with every stored file a sibling its own paths are deterministic before its
hash is known.

### Publishable actions

An action is *publishable on its own* when `dependencies(ctx)` or
`products(ctx)` returns anything. The same declaration drives the bundle and
the element publish. A future skinweights action needs three things to be
fully version controlled: a `FileField` for where its file lives, a
`products(ctx)` that writes it, and nothing else.

---

## 6. The publish actions

**`PublishAction`** is an `Action` with `scope="publish"` and a fixed
`run(ctx)`:

1. Save the current Maya scene to a temporary `<name>_rig.mb` beside the
   session. The runner already guarantees this runs only as the tail of a
   full Build & Publish, so the scene is the clean rig.
2. Export the guides to a temporary `.trg` beside it.
3. Build the `PublishSet`.
4. Call `self.deliver(publish_set, ctx)` — the only method a subclass writes.
5. Remove the temporaries.

Its own fields, on top of `notes`: `include_guides` (default on) and
`include_products` (default on). Two rules the base enforces: `deliver`
receives the `PublishSet`, which carries a **copy** of the document, so a
subclass cannot mutate the session; `ctx` stays for logging, path resolution
and the identity check a VCS subclass makes against the host; and a failure
inside `deliver` becomes an `ActionExecutionError` carrying the subclass's
message, with the temporaries left in place for inspection.

**`publish`**, the generic action, adds `folder` (a `FileField` with
`mode="dir"`, relative to the session when possible). Its `deliver` writes
`<folder>/<name>_v###/` as the bundle above, `_store/` beside the version
folders, the version number from `versioning.next_version`. No provider, no
dialog, no network. It is what a solo rigger uses and what the tests exercise.

**`tik_publish`** lives in tik_manager4 (section 9). If a subclass's
prerequisites are missing (no provider, no work), its `validate` says so and
the build refuses to start rather than failing at the end.

---

## 7. The provider contract

`tik/trigger/vcs/provider.py` defines `VersionControl`. Every method has a
working default, so a provider implements only what it supports, and the UI
shows only what the provider answers.

```python
@register_provider("tik_manager")
class TikManagerProvider(VersionControl):
    label = "Tik Manager"          # menu text, button tooltip
    icon = "tik_manager"           # svg/png beside the file, same rule as actions

    def available(self) -> bool                        # installed and configured?
    def context(self, session_path) -> Context | None  # what work/version a path is; None = not a work
    def browse(self, kind, extensions, mode) -> str    # the VCS's own picker; "" when cancelled
    def new_version(self, host) -> str                 # save the session as the next version; the new path
    def open(self, host) -> str                        # pick and open a session through the VCS; the path
    def publish_file(self, kind, path, host) -> None   # element publish: hand one file to the VCS dialog
    def launch(self, host) -> None                     # open the VCS's main window
```

`Context` is a frozen dataclass: `label` ("hero / rig_main"), `version`,
`is_latest`, `detail` for the tooltip. The status chip renders it and nothing
else.

### The host

Providers never import the window. They receive `host`, the one object
Trigger exposes outward, defined in `vcs/__init__.py` and usable headless:

```python
host.session        # the active Session, or None
host.session_path   # its file, or ""
host.is_modified
host.open(path)     # open a .tr in the window, or replace the headless session
host.save_as(path)  # save the active session there
host.refresh()      # re-read context; the window updates its chip
host.feedback       # a Feedback parented correctly, for the provider's own questions
```

The window installs itself as the host when it opens; a headless script sets
one over a `Session`. This replaces the old `ApiHandler`, and it is also what
tik_manager4's `Dcc` class calls, so Trigger-as-a-DCC and provider-in-Trigger
are two faces of one object.

### Activation

`load_plugins()` imports providers with actions. `vcs.active()` returns the
provider in use: the only registered one whose `available()` is true; when
several are, the one named by `vcs.set_preferred(name)`, else the first
registered, with a log line saying which was picked and why. No provider
means every VCS entry point is absent from the UI.

`tik.trigger.vcs` never imports the preferences packages. The window reads
the `vcs.provider` preference and calls `set_preferred`; headless callers do
the same or leave it unset. This keeps the boundary in section 4 clean: a
publish action may import `vcs` without preferences reaching the build path.

### Kinds

A plain string vocabulary shared by `browse`, `publish_file` and the publish
set: `session`, `guides`, `rig`, `script`, `model`, open for actions to add
(`weights`). `vcs/kinds.py` lists each with the extensions it usually
carries, so a provider maps by kind or by extension; an unknown kind is a
generic file. `FileField` gains an optional `kind=` keyword; fields without
one fall back to the extension mapping.

### Headless verbs

`tik.trigger.vcs` exposes `open()`, `new_version()`, `publish_file(kind,
path)` and `launch()` as one-line calls into the active provider and host, so
scripts and the menu share one path.

---

## 8. The UI surface

Everything below appears only when `vcs.active()` returns a provider, labelled
with its `label` and `icon`: a rigger reads "from Tik Manager…", never "from
VCS".

- **File fields.** `_FileEditor` in `tik/shared/ui/fields.py` gains an
  optional `vcs` callable slot beside its `browser` slot and shows a second
  small button after Browse when it is set. `FormBuilder` fills the slot when
  a provider is active. Browse mode calls `provider.browse(kind, extensions,
  mode)` and writes the returned path into the field. When the field already
  holds a file and its action declares it publishable, the button offers a
  two-item menu: browse, and "Publish <name> to Tik Manager…". The shared
  editor only knows it has a second button; deciding the kind and offering
  the publish entry live in `tik/trigger/ui`.
- **Pipeline list.** Right-click on an action adds a "Publish to Tik Manager"
  submenu with one entry per file from `dependencies` and `products`. Actions
  with none show nothing.
- **Menu.** **File › Tik Manager** (the provider's label): Open from Tik
  Manager…, Save New Version, Publish… (runs Build & Publish when the session
  has a publish action, otherwise disabled with a tooltip saying why), Open
  Tik Manager.
- **Status chip.** A fourth field in the status strip from
  `provider.context(session_path)`, refreshed when the active tab or its path
  changes and on `host.refresh()`: work label and version, green when latest,
  amber when older, "Not a Tik Manager work" in amber when `None`. Clicking
  it calls `provider.launch(host)`.
- **Guide Designer.** Import Guides… and Export Guides… replace their bare
  `browse_open` / `browse_save` calls with the same file picker the fields
  use, so they get the provider button for free.

---

## 9. The tik_manager4 side (`dcc/trigger3`)

All new files; `dcc/trigger` untouched.

```
tik_manager4/dcc/__init__.py          + "trigger3": [".tr"] in EXTENSION_DICT, + one elif
tik_manager4/dcc/trigger3/
  main.py                             Dcc(MainCore): name "trigger3", formats [".tr"]
  extract/source.py                   the .tr bundle (section 5), element "source"
  extract/rig.py                      the built scene as .mb, element "rig"
  extract/guides.py                   the .trg, element "guides"
  ingest/source.py                    open a published .tr through the host
  ingest/guides.py                    import a .trg into the active session's guides
  plugins/tik_publish/tik_publish.py  the PublishAction subclass (+ .svg)
  plugins/tik_manager/tik_manager.py  @register_provider("tik_manager") (+ .svg)
  picker.py                           the version picker dialog behind provider.browse and open
  setup/how-to-install.txt, icons/
```

- **`Dcc`** forwards `save_scene`, `save_as`, `open`, `get_scene_file`,
  `is_modified`, `get_dcc_version` and `get_main_window` to
  `tik.trigger.vcs.host`. `post_save` and `post_publish` call
  `host.refresh()`.
- **The extractors serve two callers.** Driven by tik_manager's own publish
  dialog, `source` builds the `PublishSet` from the host session, `rig` runs
  `host.session.build()` and saves the scene, `guides` exports the `.trg`.
  Driven by `tik_publish`, the set already exists, so the action assigns it
  to each resolved extractor (`extractor.publish_set = ...`) and they write
  from it. One code path per element, no rebuild at the tail of a build.
- **`tik_publish.deliver`**: initialise tik_manager4 for `trigger3`, create a
  `Publisher`, `resolve()`; no work found raises "the session is not saved in
  a Tik Manager work"; `reserve()`, hand the set to the resolved extractors,
  `extract()`, `publish(notes=self.notes)`. `validate` performs the same work
  lookup so the failure is reported before the build. The project's category
  definition for rig works must list `source`, `rig` and `guides`; the install
  notes say so.
- **The provider.** `context` is `project.find_work_by_absolute_path`.
  `new_version` is `work.new_version()` with the host saving. `open` and
  `browse` share the **picker**: a dialog assembled from the subproject,
  task, category and version widgets `MainUI` already uses, with a Use button
  returning the chosen version's file, or an element's path when browsing for
  a kind, filtered by the field's extensions. `publish_file` opens
  tik_manager's ingest dialog with the file preselected. `launch` opens
  `MainUI`.
- **Known wart, kept.** `tik_manager4.initialize` sets the global DCC and
  reloads `objects.main`, so inside a Maya that also runs tik_manager's Maya
  integration the provider re-initialises for `trigger3` before each
  operation, as the old code did. Fixing that belongs to tik_manager4.
- **Registration.** `how-to-install.txt`: put `dcc/trigger3/plugins` on
  `TRIGGER_PLUGIN_PATH`, or call `trigger.add_plugin_path()` from a
  userSetup.

---

## 10. The integrator's guide

`docs/trigger/integrating-version-control.md`, written for a pipeline
developer who has never opened Trigger's source. A deliverable of the
implementation, checked by a test. Contents, in order:

1. What Trigger asks of a VCS: the three flows, and that a `.tr` stores paths
   and builds without any VCS present.
2. Getting code loaded: the plugin layout, `TRIGGER_PLUGIN_PATH`,
   `add_plugin_path`, `@register_provider`, `@register_action`.
3. The provider contract verb by verb, what the UI does when a verb is left
   at its default, `Context` and `host`.
4. Kinds: the vocabulary, the extension mapping, how an action adds one.
5. Writing a publish action: `PublishAction`, what `deliver` receives, the
   bundle layout, the manifest schema, the store and its dedup guarantee.
6. Making an action publishable: `FileField(kind=)`, `dependencies`,
   `products`.
7. A complete minimal provider: `FolderProvider` from `vcs/folder.py`, quoted
   verbatim so the sample and the shipped code cannot drift.
8. The tik_manager4 integration as the worked example, pointing at each piece
   of the contract in `dcc/trigger3`.

---

## 11. Testing

No fake backends, as elsewhere in the repo; but only the scene save needs
Maya, so most of this is pure or Qt-offscreen.

- `tests/unit/test_publish_set_trigger.py`, pure: dependencies gathered from
  fields, recursive references, `dependencies`/`products` overrides, external
  paths flagged not copied, path rewriting in the copied `.tr`, the store
  deduplicating byte-identical content across two bundles, the size-and-mtime
  hash cache, `clean` removing only unreferenced store files.
- `tests/unit/test_vcs_trigger.py`, pure: the provider registry; `active()`
  with none, one and several providers plus the preference; the headless host
  over a `Session`; the kind vocabulary and extension fallback; every
  provider default being a no-op the UI can detect.
- `tests/unit/test_plugin_path_trigger.py`: an external folder on
  `TRIGGER_PLUGIN_PATH` registering an action and a provider; a broken plugin
  not stopping the others.
- `tests/integration/trigger/test_publish_action_trigger.py`, Maya: Build &
  Publish with the generic `publish` action writes a versioned bundle whose
  `.tr` reopens and builds again from the bundle alone; a second publish
  reuses the store; a partial build refuses to publish, as today.
- `tests/ui/test_vcs_ui.py`, offscreen with a stub provider: the field button
  appears only with a provider; browse mode writes the picked path; publish
  mode calls `publish_file` with the right kind; the menu and status chip
  follow the provider's `context`; the right-click submenu lists exactly the
  action's files.
- `tests/unit/test_import_boundaries.py` extended: `tik.trigger.vcs`
  importable only from `ui`, `actions.publish` and plugins; `core.publish_set`
  imports no Maya, Qt or vcs; nothing in tikworks imports `tik_manager4`.
- `tests/unit/test_integration_guide.py`: every fenced Python block in the
  guide compiles; the quoted `FolderProvider` matches the shipped file.
- In tik_manager4's own `tests/`: the `trigger3` Dcc adapter over a headless
  host; the extractors given a prebuilt `PublishSet`; `tik_publish.deliver`
  against a temporary project; the picker driven offscreen.

---

## 12. Out of scope

- Deprecating or altering tik_manager4's old `dcc/trigger` integration.
- VCS references stored in the `.tr` (URIs resolved at build time). Decision 2
  leaves room to add a path-plus-URI form later if plain paths prove brittle.
- A generic provider-driven publish action (decision 3).
- Fixing tik_manager4's global DCC initialisation.
- Automatic store clean-up; `clean` is a tool.
- Any VCS other than the folder reference and tik_manager4.

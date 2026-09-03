# Plug-ins

Maya plug-ins shipped with tikworks.

- `python/` — Python plug-ins, deployed as-is. Version and platform agnostic.
- `cpp/` — C++ plug-ins, built per Maya version by `package/package.py`.

The generated `.mod` puts both on `MAYA_PLUG_IN_PATH`, so Maya resolves them
**by name** (`cmds.loadPlugin("tik_undo.py")`). Loading a plug-in by absolute
path from anywhere else is what makes Maya ask the user to approve an
untrusted location — so never load one by path, and never deploy one outside
this area.

A plug-in here is a file Maya loads, not a module Python imports. Nothing in
`src/python/tik` should be a plug-in, and nothing here should be imported.
Where a plug-in needs a Python-side API, split it: the plug-in half lives here,
the importable half in the `tik` package, and the two meet through a module
parked in `sys.modules`. See `python/tik_undo.py` and
`tik/maya/core/undo.py` for the pattern.

## What belongs here

Plug-ins that **help build** a rig — they do their work during construction
and leave nothing behind. The undo command is the canonical case.

A delivered rig should be vanilla Maya nodes. A plug-in that survives into the
result becomes a dependency of every scene that references the rig, and of
every machine that opens one. That is an exception to argue for case by case,
not a default.

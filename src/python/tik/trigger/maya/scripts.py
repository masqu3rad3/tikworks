"""The per-run module namespace that script actions share.

``trigger_build`` is a real module registered in ``sys.modules`` for the
duration of a run. Script files are loaded into it under an alias with
``importlib``; inline code execs in its globals. This touches ``sys.modules``
and ``sys.path`` -- process state, not Maya state -- and sits in the Maya
layer because the runner is its only client.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any, Optional


class ScriptError(Exception):
    """A script file or alias cannot be loaded."""


class ScriptSpace:
    """The modules and globals script actions share for one run.

    Enter it around a run. ``build``-lifetime aliases vanish on exit;
    ``keep`` marks an alias as ``maya``-lifetime, which leaves it and the
    ``trigger_build`` module importable until the next run tears them down
    on enter. Last run wins.
    """

    name = "trigger_build"

    def __init__(self) -> None:
        self.module: Optional[types.ModuleType] = None
        self.aliases: set[str] = set()
        self._paths: list[str] = []
        self._kept: set[str] = set()

    # ------------------------------------------------------------ lifetime
    def __enter__(self) -> "ScriptSpace":
        self._teardown_previous()
        self.module = types.ModuleType(self.name)
        self.module.ctx = None
        self.module._trigger_aliases = ()
        self.module._trigger_paths = ()
        sys.modules[self.name] = self.module
        return self

    def __exit__(self, *_exc) -> None:
        module = self.module
        if module is None:
            return
        module.ctx = None
        for alias in sorted(self.aliases - self._kept):
            sys.modules.pop(alias, None)
            module.__dict__.pop(alias, None)
        if self._kept:
            module._trigger_aliases = tuple(sorted(self._kept))
            module._trigger_paths = tuple(self._paths)
        else:
            for entry in self._paths:
                _remove_path(entry)
            sys.modules.pop(self.name, None)
        self.module = None

    @classmethod
    def _teardown_previous(cls) -> None:
        previous = sys.modules.pop(cls.name, None)
        if previous is None:
            return
        for alias in getattr(previous, "_trigger_aliases", ()):
            sys.modules.pop(alias, None)
        for entry in getattr(previous, "_trigger_paths", ()):
            _remove_path(entry)

    # ---------------------------------------------------------------- paths
    def add_path(self, scripts_dir) -> None:
        """Put ``scripts_dir`` first on ``sys.path`` for the run, once."""
        folder = Path(scripts_dir)
        if not folder.is_dir():
            return
        entry = str(folder)
        if entry in self._paths:
            return
        self._paths.append(entry)
        if entry not in sys.path:
            sys.path.insert(0, entry)

    # -------------------------------------------------------------- loading
    def is_reserved(self, alias: str) -> bool:
        """True when ``alias`` names a module Trigger did not load."""
        return alias in sys.modules and alias not in self.aliases

    def load(self, path, alias: str) -> types.ModuleType:
        """Execute ``path`` as module ``alias`` and register it."""
        if self.module is None:
            raise ScriptError("ScriptSpace is not entered.")
        if self.is_reserved(alias):
            raise ScriptError(
                f"'{alias}' is already a module in this Maya; pick another Import As."
            )
        path = Path(path)
        spec = importlib.util.spec_from_file_location(alias, str(path))
        if spec is None or spec.loader is None:
            raise ScriptError(f"Cannot load {path} as a module.")
        module = importlib.util.module_from_spec(spec)
        sys.modules.pop(alias, None)  # a previous load this run: reload fresh
        sys.modules[alias] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(alias, None)
            self.module.__dict__.pop(alias, None)
            self.aliases.discard(alias)
            raise
        self.aliases.add(alias)
        setattr(self.module, alias, module)
        return module

    def globals(self, ctx: Any) -> dict:
        """The exec namespace for inline code: aliases, ``ctx``, ``__name__``."""
        if self.module is None:
            raise ScriptError("ScriptSpace is not entered.")
        self.module.ctx = ctx
        return self.module.__dict__

    def keep(self, alias: str) -> None:
        """Mark ``alias`` as ``maya``-lifetime."""
        if alias in self.aliases:
            self._kept.add(alias)

    def hint_for(self, error: ImportError) -> str:
        """An ordering hint when an alias is missing, else ``""``."""
        name = getattr(error, "name", None)
        if not name or name in sys.modules:
            return ""
        top = name.split(".")[0]
        for entry in self._paths:
            if any(Path(entry).glob(f"{top}*.py")):
                return ""
        return (
            f"{top} is not loaded yet; a script action that loads it must run "
            "before this one."
        )


def _remove_path(entry: str) -> None:
    while entry in sys.path:
        sys.path.remove(entry)

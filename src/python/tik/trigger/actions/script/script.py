"""Load a Python file as a named module, then run inline code.

A script file is a library: it is executed as a real module under an alias
(``import_as``, default the file stem) and registered in ``sys.modules``, so
later files can ``import`` it and later actions call into it. Inline code runs
in the shared ``trigger_build`` namespace where every alias loaded so far is a
global, next to ``ctx``. Pipeline order is the dependency order.
"""

from __future__ import annotations

import keyword
import re
from pathlib import Path
from string import Template

from tik.trigger.core import (
    Action,
    ChoiceField,
    FileField,
    StringField,
    TextField,
    register_action,
    versioning,
)
from tik.trigger.core.action import ActionContext
from tik.trigger.core.exceptions import ActionExecutionError

BUILD_LIFETIME = "build"
MAYA_LIFETIME = "maya"

_TEMPLATE = Path(__file__).with_name("stub.py.tmpl")


@register_action("script", category="structure", icon="script", scope="both")
class Script(Action):
    """Load a Python file as a named module, then run inline code.

    Either half is optional. Files loaded earlier in the pipeline are
    importable by alias; inline code sees them as globals next to ``ctx``.
    With ``lifetime`` ``maya`` the module stays importable from the Script
    Editor (``import trigger_build``) until the next run replaces it.
    """

    label = "Script"

    file_path = FileField("", extensions=[".py"], label="Script File")
    import_as = StringField(
        "", label="Import As", help="Module name for the file; defaults to its stem"
    )
    code = TextField(
        "",
        label="Code",
        language="python",
        help="Runs after the file, with every loaded module and ctx in scope",
    )
    lifetime = ChoiceField(
        BUILD_LIFETIME,
        choices=[BUILD_LIFETIME, MAYA_LIFETIME],
        help="build: names vanish when the run ends. "
        "maya: they stay importable until the next run (last run wins)",
    )

    # ------------------------------------------------------------ helpers
    def alias(self) -> str:
        """The module name the file loads under."""
        if self.import_as:
            return self.import_as
        if self.file_path:
            return versioning.parse(self.file_path)[0]
        return ""

    def summary(self) -> str:
        """``name.py`` or ``name.py as alias`` when the alias is not the stem."""
        if not self.file_path:
            return ""
        name = Path(self.file_path).name
        alias = self.alias()
        if alias and alias != versioning.parse(self.file_path)[0]:
            return f"{name} as {alias}"
        return name

    @classmethod
    def migrate_settings(cls, settings: dict) -> dict:
        """Accept the legacy ``script_file_path`` / ``commands`` keys."""
        data = dict(settings)
        legacy_path = data.pop("script_file_path", None)
        if legacy_path and not data.get("file_path"):
            data["file_path"] = legacy_path
        commands = data.pop("commands", None)
        if isinstance(commands, list) and commands and not data.get("code"):
            data["code"] = "\n".join(str(line) for line in commands)
        return data

    # --------------------------------------------------------------- steps
    def validate(self, ctx: ActionContext) -> list[str]:
        """Missing file (inherited), bad alias, reserved alias."""
        problems = super().validate(ctx)
        if not self.file_path:
            return problems
        alias = self.alias()
        if not alias.isidentifier() or keyword.iskeyword(alias):
            problems.append(f"import_as: '{alias}' is not a valid module name")
            return problems
        from tik.trigger.maya.scripts import ScriptSpace

        space = ctx.scripts if ctx.scripts is not None else ScriptSpace()
        if space.is_reserved(alias):
            problems.append(
                f"import_as: '{alias}' is already a module in this Maya; "
                "pick another name"
            )
        return problems

    def run(self, ctx: ActionContext) -> None:
        """Load the file under its alias, then exec the inline code."""
        from tik.trigger.maya.scripts import ScriptSpace

        if ctx.scripts is not None:
            self._run_in(ctx.scripts, ctx)
            return
        # run outside a Runner (tests, tools): a private build-lifetime space
        with ScriptSpace() as space:
            if ctx.base_dir:
                space.add_path(Path(ctx.base_dir) / "scripts")
            self._run_in(space, ctx)

    def _run_in(self, space, ctx: ActionContext) -> None:
        if self.file_path:
            path = ctx.resolve(self.file_path)
            if not path.exists():
                raise ActionExecutionError(f"Script not found: {path}")
            alias = self.alias()
            try:
                space.load(path, alias)
            except ImportError as error:
                raise ActionExecutionError(
                    self._import_message(space, error)
                ) from error
            ctx.log(f"Loaded {path.name} as {alias}")
            if self.lifetime == MAYA_LIFETIME:
                space.keep(alias)
        if self.code:
            namespace = space.globals(ctx)
            try:
                exec(  # noqa: S102 - running the rigger's code is the action
                    compile(self.code, f"<{ctx.path or 'script'}>", "exec"), namespace
                )
            except ImportError as error:
                raise ActionExecutionError(
                    self._import_message(space, error)
                ) from error

    @staticmethod
    def _import_message(space, error: ImportError) -> str:
        hint = space.hint_for(error)
        return f"{error}. {hint}" if hint else str(error)


def editor_command() -> str:
    """The user's ``external_editor`` command, or ``""`` for the OS default.

    Read lazily: ``tik.trigger.config`` builds its settings singleton at
    import time and writes a file into the process's working directory, which
    under Maya is not writable. A settings store that cannot be reached must
    not stop a script from opening.
    """
    try:
        from tik.trigger.config import trigger_settings

        return str(trigger_settings.get("external_editor") or "")
    except Exception:  # noqa: BLE001 - any store failure means "OS default"
        return ""


def create_script_file(session_dir, name: str) -> Path:
    """Write a versioned stub into ``<session_dir>/scripts`` and return it.

    ``name`` is slugged to an identifier (spaces and dashes become
    underscores). The one place Trigger writes a ``.py`` file.
    """
    slug = re.sub(r"[^0-9A-Za-z_]+", "_", name.strip()).strip("_").lower()
    if not slug.isidentifier() or keyword.iskeyword(slug):
        raise ValueError(f"'{name}' is not a valid script name")
    folder = Path(session_dir) / "scripts"
    folder.mkdir(parents=True, exist_ok=True)
    target = versioning.next_version(folder / f"{slug}.py")
    text = Template(_TEMPLATE.read_text(encoding="utf-8")).substitute(
        name=target.stem, alias=slug
    )
    target.write_text(text, encoding="utf-8")
    return target

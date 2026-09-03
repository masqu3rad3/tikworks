"""Reference another session: its actions run here, with local overrides."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from tik.core.fields import DictField, FieldGroup, FileField, ListField, StringField
from tik.trigger.core import Action, register_action, versioning
from tik.trigger.core.document import ActionNode, Document
from tik.trigger.core.exceptions import SessionError

SCOPE = FieldGroup("Scope", collapsed=True)


@register_action("reference", category="structure", icon="reference")
class Reference(Action):
    """Run the actions of another .tr file as part of this session.

    Ticking/unticking or editing a referenced action stores an override here;
    the referenced file is never modified.
    """

    label = "Reference"

    file = FileField("", extensions=[".tr"], label="Session file")
    version = StringField("latest", help="'latest', 'pinned' or an explicit v###")
    include = ListField(
        item_type=str, help="Action paths to include; empty = all", group=SCOPE
    )
    overrides = DictField(
        help="{action path: {enabled: bool, settings: {...}}}", hidden=True
    )

    def run(self, ctx) -> None:  # expanded by the runner; nothing to do here
        """Nothing: the runner expands a reference into its actions."""
        return None

    # ------------------------------------------------------------ expansion
    @staticmethod
    def resolve_file(node: ActionNode, base_dir: str) -> Path:
        """The referenced ``.tr`` path, made absolute against ``base_dir``."""
        file_value = node.settings.get("file", "")
        if not file_value:
            raise SessionError("reference has no file.")
        path = Path(file_value)
        if not path.is_absolute() and base_dir:
            path = Path(base_dir) / path
        path = versioning.resolve(path, node.settings.get("version", "latest"))
        if not path.exists():
            raise SessionError(f"referenced session not found: {path}")
        return path

    @staticmethod
    def expand(
        node: ActionNode,
        base_dir: str,
        loader: Callable = Document.load,
        chain: tuple = (),
    ) -> tuple[Document, str, str]:
        """Return ``(document with overrides applied, its directory, its file)``."""
        path = Reference.resolve_file(node, base_dir)
        key = str(path.resolve())
        if key in chain:
            raise SessionError(
                "reference cycle: "
                f"{' > '.join(Path(item).name for item in chain)} > {path.name}"
            )
        document = loader(path)
        Reference.apply_overrides(
            document,
            node.settings.get("include") or [],
            node.settings.get("overrides") or {},
        )
        return document, str(path.parent), key

    @staticmethod
    def apply_overrides(
        document: Document, include: list, overrides: dict
    ) -> list[str]:
        """Apply the include list and overrides; return unresolved override paths."""
        if include:
            wanted = set(include)
            for path, item, _parent in document.walk():
                if (
                    path not in wanted
                    and not any(want.startswith(path + "/") for want in wanted)
                    and not any(path.startswith(want + "/") for want in wanted)
                ):
                    item.enabled = False
        missing = []
        for path, override in overrides.items():
            target = document.find(path)
            if target is None:
                missing.append(path)
                continue
            if "enabled" in override:
                target.enabled = bool(override["enabled"])
            for key, value in (override.get("settings") or {}).items():
                target.settings[key] = value
        return missing

    # --------------------------------------------------------------- summary
    def summary(self) -> str:
        """The referenced file name, for the pipeline list."""
        return Path(self.file).name if self.file else ""

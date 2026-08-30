"""Declarative, typed settings fields.

A ``Field`` is a descriptor that stores a validated value per instance and
describes itself (type, default, limits, label) so UIs and serializers can be
generated from the class rather than from a parallel JSON file.

Example:
    class Arm(Schema):
        segments = IntField(3, min=1, max=20, label="Segments")
        local = BoolField(False)

    arm = Arm()
    arm.segments = 5
    arm.values()            # {"segments": 5, "local": False}
    Arm.schema()            # JSON-serializable description
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Iterable, Optional, Sequence


class FieldValidationError(ValueError):
    """Raised when a value does not satisfy a field's constraints."""

    def __init__(self, field_name: str, value: Any, reason: str) -> None:
        self.field_name = field_name
        self.value = value
        self.reason = reason
        super().__init__(f"{field_name}: {reason} (got {value!r})")


class Field:
    """Base descriptor. Subclasses set ``type_name`` and override ``coerce``."""

    type_name = "any"

    def __init__(
        self,
        default: Any = None,
        *,
        label: Optional[str] = None,
        help: str = "",  # noqa: A002
        min: Any = None,  # noqa: A002
        max: Any = None,  # noqa: A002
        choices: Optional[Sequence[Any]] = None,
        hidden: bool = False,
        group: Optional[str] = None,
    ) -> None:
        self.default = default
        self.label = label
        self.help = help
        self.min = min
        self.max = max
        self.choices = list(choices) if choices is not None else None
        self.hidden = hidden
        self.group = group
        self.name = ""

    # --- descriptor protocol -------------------------------------------------
    def __set_name__(self, owner, name: str) -> None:
        self.name = name
        if self.label is None:
            self.label = name.replace("_", " ").title()

    def _key(self) -> str:
        return f"_field_{self.name}"

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        key = self._key()
        if key not in instance.__dict__:
            instance.__dict__[key] = copy.deepcopy(self.default)
        return instance.__dict__[key]

    def __set__(self, instance, value) -> None:
        instance.__dict__[self._key()] = self.validate(value)

    # --- validation ----------------------------------------------------------
    def coerce(self, value: Any) -> Any:
        """Convert ``value`` to the field type or raise ``FieldValidationError``."""
        return value

    def validate(self, value: Any) -> Any:
        value = self.coerce(value)
        if self.choices is not None and value not in self.choices:
            raise FieldValidationError(
                self.name, value, f"must be one of {self.choices}"
            )
        if self.min is not None and value < self.min:
            raise FieldValidationError(self.name, value, f"must be >= {self.min}")
        if self.max is not None and value > self.max:
            raise FieldValidationError(self.name, value, f"must be <= {self.max}")
        return value

    def to_schema(self) -> dict:
        """Return a JSON-serializable description of the field."""
        return {
            "type": self.type_name,
            "default": copy.deepcopy(self.default),
            "label": self.label,
            "help": self.help,
            "min": self.min,
            "max": self.max,
            "choices": list(self.choices) if self.choices is not None else None,
            "hidden": self.hidden,
            "group": self.group,
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.name!r}, default={self.default!r})"


class IntField(Field):
    type_name = "int"

    def coerce(self, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise FieldValidationError(self.name, value, "must be a number")
        if isinstance(value, float) and not value.is_integer():
            raise FieldValidationError(self.name, value, "must be an integer")
        return int(value)


class FloatField(Field):
    type_name = "float"

    def coerce(self, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise FieldValidationError(self.name, value, "must be a number")
        return float(value)


class BoolField(Field):
    type_name = "bool"

    def coerce(self, value):
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in (0, 1):
            return bool(value)
        raise FieldValidationError(self.name, value, "must be a boolean")


class StringField(Field):
    type_name = "string"

    def coerce(self, value):
        if not isinstance(value, str):
            raise FieldValidationError(self.name, value, "must be a string")
        return value


class ChoiceField(Field):
    """A value restricted to ``choices``."""

    type_name = "choice"

    def __init__(self, default, choices: Sequence[Any], **kwargs) -> None:
        super().__init__(default, choices=choices, **kwargs)


class VectorField(Field):
    """A fixed-size tuple of floats (default size 3)."""

    type_name = "vector"

    def __init__(self, default=(0.0, 0.0, 0.0), *, size: int = 3, **kwargs) -> None:
        self.size = size
        super().__init__(tuple(float(item) for item in default), **kwargs)

    def coerce(self, value):
        try:
            items = tuple(float(item) for item in value)
        except (TypeError, ValueError):
            raise FieldValidationError(self.name, value, "must be a sequence of numbers")
        if len(items) != self.size:
            raise FieldValidationError(self.name, value, f"must have {self.size} items")
        return items

    def validate(self, value):
        # min/max apply per component
        items = self.coerce(value)
        for item in items:
            if self.min is not None and item < self.min:
                raise FieldValidationError(self.name, value, f"components must be >= {self.min}")
            if self.max is not None and item > self.max:
                raise FieldValidationError(self.name, value, f"components must be <= {self.max}")
        return items

    def to_schema(self) -> dict:
        data = super().to_schema()
        data["default"] = list(self.default)
        data["size"] = self.size
        return data


class ListField(Field):
    """A list, optionally with an ``item_type`` (a python type) enforced."""

    type_name = "list"

    def __init__(self, default=None, *, item_type: Optional[type] = None, **kwargs) -> None:
        self.item_type = item_type
        super().__init__(list(default) if default else [], **kwargs)

    def coerce(self, value):
        if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
            raise FieldValidationError(self.name, value, "must be a list")
        items = list(value)
        if self.item_type is not None:
            for item in items:
                if not isinstance(item, self.item_type):
                    raise FieldValidationError(
                        self.name, value, f"items must be {self.item_type.__name__}"
                    )
        return items

    def validate(self, value):
        return self.coerce(value)

    def to_schema(self) -> dict:
        data = super().to_schema()
        data["item_type"] = self.item_type.__name__ if self.item_type else None
        return data


class NodeRefField(Field):
    """A reference to a DCC node by name/path (string, may be empty)."""

    type_name = "node"

    def __init__(self, default: str = "", *, node_types: Sequence[str] = (), **kwargs) -> None:
        self.node_types = list(node_types)
        super().__init__(default, **kwargs)

    def coerce(self, value):
        if value is None:
            return ""
        if not isinstance(value, str):
            value = str(value)
        return value

    def to_schema(self) -> dict:
        data = super().to_schema()
        data["node_types"] = list(self.node_types)
        return data


class FileField(Field):
    """A file or directory path (string). Stored relative to a session when possible."""

    type_name = "file"

    def __init__(
        self,
        default: str = "",
        *,
        extensions: Sequence[str] = (),
        mode: str = "open",
        **kwargs,
    ) -> None:
        if mode not in ("open", "save", "dir"):
            raise ValueError("mode must be 'open', 'save' or 'dir'")
        self.extensions = [ext if ext.startswith(".") else f".{ext}" for ext in extensions]
        self.mode = mode
        super().__init__(default, **kwargs)

    def coerce(self, value):
        if value is None:
            return ""
        if not isinstance(value, str):
            raise FieldValidationError(self.name, value, "must be a path string")
        return value.replace("\\", "/")

    def to_schema(self) -> dict:
        data = super().to_schema()
        data["extensions"] = list(self.extensions)
        data["mode"] = self.mode
        return data


@dataclass(frozen=True)
class Column:
    """One column of a :class:`TableField`.

    ``choices_from`` names an attribute on the *target object* supplying the
    options. A field is a class attribute and cannot know the subclass it will
    be edited on, so a column whose options vary per module resolves them at
    render time instead.
    """

    name: str
    kind: str = "string"  # "string" | "choice"
    choices: tuple = ()
    choices_from: str = ""
    label: str = ""

    def display(self) -> str:
        return self.label or self.name.replace("_", " ").title()


class TableField(Field):
    """A list of records, rendered as a table with add/remove rows.

    The value is a list of plain dicts, so it serialises with no special
    handling.
    """

    type_name = "table"

    def __init__(self, default=None, *, columns: Sequence[Column] = (), **kwargs) -> None:
        self.columns = tuple(columns)
        super().__init__([dict(row) for row in default] if default else [], **kwargs)

    def coerce(self, value):
        if value is None:
            return []
        if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
            raise FieldValidationError(self.name, value, "must be a list of rows")
        known = {column.name for column in self.columns}
        rows = []
        for row in value:
            if not isinstance(row, dict):
                raise FieldValidationError(self.name, value, "each row must be a mapping")
            unknown = set(row) - known
            if unknown:
                raise FieldValidationError(
                    self.name, value, f"unknown column(s): {sorted(unknown)}"
                )
            filled = {}
            for column in self.columns:
                entry = row.get(column.name, "")
                if column.kind == "choice" and column.choices and entry:
                    if entry not in column.choices:
                        raise FieldValidationError(
                            self.name, value,
                            f"'{column.name}' must be one of {list(column.choices)}",
                        )
                filled[column.name] = entry
            rows.append(filled)
        return rows

    def validate(self, value):
        return self.coerce(value)

    def to_schema(self) -> dict:
        schema = super().to_schema()
        schema["columns"] = [
            {
                "name": column.name,
                "kind": column.kind,
                "choices": list(column.choices),
                "choices_from": column.choices_from,
                "label": column.display(),
            }
            for column in self.columns
        ]
        return schema


class DictField(Field):
    """A JSON-like mapping (str keys)."""

    type_name = "dict"

    def __init__(self, default=None, **kwargs) -> None:
        super().__init__(dict(default) if default else {}, **kwargs)

    def coerce(self, value):
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise FieldValidationError(self.name, value, "must be a mapping")
        return copy.deepcopy(value)

    def validate(self, value):
        return self.coerce(value)


class Schema:
    """Mixin for classes that declare ``Field`` attributes."""

    @classmethod
    def fields(cls) -> dict[str, Field]:
        """Return fields in definition order, base classes first."""
        collected: dict[str, Field] = {}
        for klass in reversed(cls.__mro__):
            for name, attr in vars(klass).items():
                if isinstance(attr, Field):
                    collected[name] = attr
        return collected

    @classmethod
    def schema(cls) -> dict:
        """Return a JSON-serializable description of every field."""
        return {name: field.to_schema() for name, field in cls.fields().items()}

    def values(self) -> dict:
        """Return the current field values."""
        return {name: copy.deepcopy(getattr(self, name)) for name in self.fields()}

    def apply(self, mapping: dict, strict: bool = True) -> None:
        """Set several fields at once.

        Args:
            mapping: ``{field_name: value}``.
            strict: Raise ``KeyError`` on unknown names; otherwise ignore them.
        """
        fields = self.fields()
        for name, value in mapping.items():
            if name not in fields:
                if strict:
                    raise KeyError(f"Unknown field '{name}' for {type(self).__name__}")
                continue
            setattr(self, name, value)

    def reset(self) -> None:
        """Restore every field to its default."""
        for name, field in self.fields().items():
            self.__dict__.pop(field._key(), None)

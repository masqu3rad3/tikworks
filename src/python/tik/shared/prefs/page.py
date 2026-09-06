"""A preferences page: a ``Schema`` with a name, a label and a sort order."""

from __future__ import annotations

from tik.core.fields import Schema


class PrefPage(Schema):
    """One page in the preferences dialog.

    Subclasses declare ``Field`` attributes exactly as a module declares its
    settings, so adding a preference is one line and the dialog needs no
    changes at all. Every field must carry ``help=``: it is the tooltip and
    the text that search matches against.
    """

    #: Stable key used in the stored file and in ``prefs.<name>``.
    name: str = ""
    #: What the category list shows.
    label: str = ""
    #: Sort order in the category list; ties break on ``name``.
    order: int = 100

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.name!r})"

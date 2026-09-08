"""Version control preferences: which provider to use when several are installed."""

from __future__ import annotations

from tik.core.fields import FieldGroup, StringField
from tik.shared.prefs import PrefPage, register_page


@register_page
class VcsPrefs(PrefPage):
    """Which version control system Trigger talks to."""

    name, label, order = "vcs", "Version Control", 50

    PROVIDER = FieldGroup("Provider")

    provider = StringField(
        "",
        group=PROVIDER,
        label="Preferred provider",
        help=(
            "The registered provider name to use when more than one is "
            "available (for example tik_manager). Empty picks the first."
        ),
    )

"""Session management for tik.trigger.

This module provides session management for both guide sessions and action sessions:

- GuideSession: Manages guide creation and persistence
- ActionSession: Manages the action build pipeline

Example:
    # Guide workflow
    guide_session = GuideSession()
    guide_session.create_guides("bipedArm", side="L")
    guide_session.save("character.trg")

    # Action workflow
    action_session = ActionSession()
    action_session.add_action("jointify", order=1)
    action_session.add_action("skinweights", order=2)
    action_session.run_all()
    action_session.save("pipeline.tra")
"""

from __future__ import annotations

from tik.trigger.core.io import IO, GUIDE_SESSION_EXT, ACTION_SESSION_EXT
from tik.shared.io import ensure_extension
from .guide_session import GuideSession
from .action_session import ActionSession

__all__ = [
    # IO utilities
    "IO",
    "GUIDE_SESSION_EXT",
    "ACTION_SESSION_EXT",
    "ensure_extension",
    # Session classes
    "GuideSession",
    "ActionSession",
]

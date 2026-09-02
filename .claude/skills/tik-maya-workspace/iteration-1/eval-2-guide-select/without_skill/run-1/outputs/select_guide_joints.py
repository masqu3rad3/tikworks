"""Select every joint in the scene whose meta 'kind' is 'guide'.

Run inside Maya (script editor or shelf):

    import select_guide_joints
    select_guide_joints.select_guide_joints()

Uses the tik.maya wrapper only -- no direct maya.cmds calls.
"""

import logging

import tik.maya as tm

LOG = logging.getLogger(__name__)

META_ATTR = "kind"
META_VALUE = "guide"


def _read_meta(joint, attr):
    """Read a meta attribute value from a joint, or None if unreadable.

    Prefers the Plug interface; falls back to the cmds proxy with the long
    name because Plug currently resolves attributes by short name, which
    fails on nodes with duplicate (ambiguous) short names.
    """
    try:
        return joint[attr].value
    except RuntimeError:
        pass
    try:
        return tm.getAttr(f"{joint.long_name}.{attr}")
    except (RuntimeError, ValueError):
        LOG.warning("Could not read %s.%s -- skipping.", joint.long_name, attr)
        return None


def find_guide_joints():
    """Return all Joint wrappers whose 'kind' meta attribute equals 'guide'.

    Returns:
        list: tik.maya Joint instances tagged as guides.
    """
    guide_joints = []
    for joint in tm.ls(type="joint", long=True):
        if not joint.has_attr(META_ATTR):
            continue
        if _read_meta(joint, META_ATTR) == META_VALUE:
            guide_joints.append(joint)
    return guide_joints


def select_guide_joints():
    """Select all guide joints in the scene.

    Clears the selection if no guide joints are found.

    Returns:
        list: The selected Joint instances (may be empty).
    """
    guide_joints = find_guide_joints()
    if guide_joints:
        # Select by long name to stay unambiguous with duplicate short names.
        tm.select([joint.long_name for joint in guide_joints], replace=True)
        LOG.info("Selected %d guide joint(s).", len(guide_joints))
    else:
        tm.select(clear=True)
        LOG.info("No guide joints found -- selection cleared.")
    return guide_joints


if __name__ == "__main__":
    select_guide_joints()

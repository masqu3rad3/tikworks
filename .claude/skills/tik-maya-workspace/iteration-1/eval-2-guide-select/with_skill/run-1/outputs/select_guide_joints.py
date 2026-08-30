"""Select every joint in the scene whose meta 'kind' is 'guide'.

Quick utility script. Run it in a Maya session with ``src/python`` on
``sys.path``, or execute it directly::

    import select_guide_joints
    select_guide_joints.select_guide_joints()
"""

import tik.maya as tm


def select_guide_joints() -> list:
    """Select all joints tagged with meta ``kind == "guide"``.

    Returns:
        list: The wrapped Joint nodes that were selected (empty if none —
            in that case the selection is cleared).
    """
    guide_joints = tm.find_by_meta("kind", "guide", node_type="joint")
    if guide_joints:
        tm.select_nodes(guide_joints, replace=True)
    else:
        tm.select_nodes(clear=True)
    return guide_joints


if __name__ == "__main__":
    selected = select_guide_joints()
    print(f"Selected {len(selected)} guide joint(s).")

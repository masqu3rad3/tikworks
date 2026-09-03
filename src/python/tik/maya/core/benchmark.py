from __future__ import annotations

from functools import wraps
from tik.core.benchmark import Benchmark
from maya import cmds


class MayaBenchmark(Benchmark):
    """
    A Maya-specific benchmark that disables Undo and Viewport
    to ensure fair testing of the code, not the UI.
    """

    def measure(self, name, iterations=10, warmup=2, new_scene=False):
        context = super().measure(name, iterations, warmup)
        context._new_scene = new_scene  # Store it on the context object
        original_run = context.run

        def maya_wrapped_run(func, *args, **kwargs):
            # Store Maya State
            undo_state = cmds.undoInfo(q=True, state=True)

            # Turn off some heavy Maya features
            cmds.undoInfo(state=False)
            # cmds.refresh(suspend=True) # Optional: Be careful with this one

            try:
                # Wrap the function to handle the scene reset
                # This lets us keep the parent's timing logic intact.

                @wraps(func)
                def scene_resetting_func(*f_args, **f_kwargs):
                    if context._new_scene:
                        # Force new scene without saving
                        cmds.file(new=True, force=True)
                    return func(*f_args, **f_kwargs)

                # Execute the benchmark with our wrapped function
                return original_run(scene_resetting_func, *args, **kwargs)

            finally:
                # Restore State
                cmds.undoInfo(state=undo_state)
                # cmds.refresh(suspend=False)

                # In case we messed with the scene...
                if context._new_scene:
                    cmds.file(new=True, force=True)

        context.run = maya_wrapped_run
        return context


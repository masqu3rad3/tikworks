"""Decorator functions for Tikmaya core functionalities."""
import sys
from functools import wraps

from maya import cmds

def add_aliases(aliases):
    """Attach alias properties to a class.

    Example Usage:
        @add_aliases({
            "alias_name": "original_property_name",
            ...
        })
        class MyClass:
            ...

    Args:
        aliases: A mapping of alias_name -> original_property_name.

    """

    def decorator(cls):
        """Attach aliases to the provided class."""
        for original, alias in aliases.items():
            setattr(cls, alias, getattr(cls, original))
        return cls
    return decorator


def alias(alias_name):
    """
    Available as a decorator for loose functions.
    It injects 'alias_name' into the module's global scope pointing to the function.
    """

    def decorator(func):
        # 1. Identify the module where the function is defined
        module = sys.modules[func.__module__]

        # 2. Inject the alias into that module
        setattr(module, alias_name, func)

        return func

    return decorator

def undo(func):
    """Puts the wrapped `func` into a single Maya Undo action, then
    undoes it when the function enters the finally: block"""

    @wraps(func)
    def _undofunc(*args, **kwargs):
        cmds.undoInfo(openChunk=True)
        try:
            result = func(*args, **kwargs)
        except Exception as exc:
            cmds.undoInfo(closeChunk=True)
            raise exc
        finally:
            # after calling the func, end the undo chunk and undo
            cmds.undoInfo(closeChunk=True)
            return result
    return _undofunc

def keepselection(func):
    """Decorator method to keep the current selection. Useful where
    the wrapped method messes with the current selection"""

    @wraps(func)
    def _keepfunc(*args, **kwargs):
        original_selection = cmds.ls(selection=True)
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            raise exc
        finally:
            # after calling the func, end the undo chunk and undo
            cmds.select(original_selection)

    return _keepfunc
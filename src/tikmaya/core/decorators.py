"""Decorator functions for Tikmaya core functionalities."""
import sys

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

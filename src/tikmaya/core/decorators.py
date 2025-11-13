"""Decorator functions for Tikmaya core functionalities."""

import functools

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
        for original, alias in aliases.items():
            setattr(cls, alias, getattr(cls, original))
        return cls
    return decorator

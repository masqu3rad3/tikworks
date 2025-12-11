"""Decorate classes with aliases."""


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

    Returns:
        Callable: Decorator that assigns aliases on the class.
    """

    def decorator(cls):
        """Assign alias attributes to the decorated class.

        Args:
            cls (type): Class to augment with alias attributes.

        Returns:
            type: The class with aliases applied.
        """
        for original, alias in aliases.items():
            setattr(cls, alias, getattr(cls, original))
        return cls

    return decorator

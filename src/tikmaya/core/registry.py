import maya.cmds as cmds

_NODE_TYPES = {}
_DEFAULT_FACTORY = None  # set by set_default_factory(Node)

def register(node_type):
    """Decorator for registering Maya node wrappers."""
    def inner(cls):
        _NODE_TYPES[node_type] = cls
        return cls
    return inner

def set_default_factory(factory):
    """Set the fallback factory (e.g., Node) without importing it here."""
    global _DEFAULT_FACTORY
    _DEFAULT_FACTORY = factory

def get_node(name):
    """Return an instance of the correct Node subclass based on Maya node type."""
    if not cmds.objExists(name):
        raise ValueError(f"Node '{name}' does not exist.")

    node_type = cmds.nodeType(name)
    cls = _NODE_TYPES.get(node_type)
    if cls:
        return cls(name)

    # Try inherited types (e.g., 'dagNode', 'dependNode', etc.)
    for t in (cmds.nodeType(name, inherited=True) or []):
        cls = _NODE_TYPES.get(t)
        if cls:
            return cls(name)

    if _DEFAULT_FACTORY is not None:
        return _DEFAULT_FACTORY(name)

    raise LookupError(f"No wrapper registered for '{node_type}' and no default factory set.")

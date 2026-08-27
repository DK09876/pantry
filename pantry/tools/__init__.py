"""Tool registry.

A tool is a plain Python function with type hints and a docstring; the model
reads both to decide when to call it. Apps register their own set, and a mode
decides which sets are in scope.

Keeping the registry separate from any one app is the point: adding a second
app means adding a module here, not touching the voice loop.
"""

from . import lifeos

# Tools grouped by the app that owns them.
REGISTRY = {
    "lifeos": lifeos.TOOLS,
}


def for_names(names):
    """Flatten the tool sets a mode asks for into one list."""
    tools = []
    for name in names:
        tools.extend(REGISTRY.get(name, ()))
    return tools


__all__ = ["REGISTRY", "for_names"]

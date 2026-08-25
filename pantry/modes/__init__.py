"""Mode registry.

One entry today. The lookup exists so the second mode is a registration
rather than a rewrite of the loop.
"""

from .base import Mode
from .general import GENERAL

REGISTRY = {GENERAL.name: GENERAL}
DEFAULT = GENERAL


def resolve(text):
    """Return the mode a spoken phrase switches into, or None."""
    lowered = text.lower()
    for mode in REGISTRY.values():
        if any(phrase in lowered for phrase in mode.enter_phrases):
            return mode
    return None


__all__ = ["Mode", "REGISTRY", "DEFAULT", "resolve"]

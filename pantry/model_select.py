"""Pick a Gemini model that actually works with this API key.

Google retires models without removing them from models.list(), so a name can
be listed and still 404 on generate_content. Probe at startup and cache.
"""

import os

# Newest first. gemini-flash-latest floats to whatever is current, so it sits
# last as a safety net rather than first where it could shift under us.
CANDIDATES = [
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-flash-latest",
]

_cached = None


def pick_model(client, candidates=None, verbose=True):
    """Return the first candidate that responds to a real request."""
    global _cached
    if _cached:
        return _cached

    override = os.environ.get("GEMINI_MODEL")
    if override:
        _cached = override
        if verbose:
            print(f"[ model: {override} (from GEMINI_MODEL) ]")
        return _cached

    for name in candidates or CANDIDATES:
        try:
            client.models.generate_content(model=name, contents="ping")
            _cached = name
            if verbose:
                print(f"[ model: {name} ]")
            return name
        except Exception as e:
            if verbose:
                code = "404" if "404" in str(e) else "429" if "429" in str(e) else "err"
                print(f"[ {name} unavailable ({code}), trying next ]")

    raise RuntimeError(
        "No usable Gemini model. Run tools/check_models.py to see what your key allows."
    )

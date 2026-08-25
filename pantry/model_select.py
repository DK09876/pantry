"""Pick a Gemini model that actually works with this API key.

Google retires models without removing them from models.list(), so a name can
be listed and still 404 on generate_content. Probe at startup and cache.
"""

import logging
import os

# Ordered for a voice assistant, where time-to-first-token dominates the felt
# latency and answers are one or two sentences.
#
# Measured on this Pi, first token:
#   gemini-flash-lite-latest  0.33-0.71s
#   gemini-3.5-flash-lite     0.43-0.78s
#   gemini-3.7-flash          1.89-2.44s
#   gemini-3.6-flash          2.66-22.48s   (wildly variable)
#
# The lite models are 3-5x faster to speak and the quality gap is negligible
# at this length. Set GEMINI_MODEL in .env to override - use a full flash
# model if you start asking it harder questions.
CANDIDATES = [
    "gemini-flash-lite-latest",
    "gemini-3.5-flash-lite",
    "gemini-3.7-flash",
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

    # The probe uses models.generate_content, which logs an advisory about
    # automatic function calling. Irrelevant here - we send no tools.
    genai_log = logging.getLogger("google_genai.models")
    previous = genai_log.level
    genai_log.setLevel(logging.ERROR)
    try:
        return _probe(client, candidates or CANDIDATES, verbose)
    finally:
        genai_log.setLevel(previous)


def _probe(client, candidates, verbose):
    global _cached
    for name in candidates:
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

#!/usr/bin/env python
"""Which models does this key work with, and how fast are they right now?

    tools/check_models.py            probe the candidate list
    tools/check_models.py --all      probe every model the key can see

Doubles as a health check: latency here is what the assistant will feel.
"""

import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Importing config loads .env, which must happen before genai.Client() looks
# for GEMINI_API_KEY.
from pantry import config  # noqa: F401
from pantry.model_select import CANDIDATES

from google import genai
from google.genai import types

ROUNDS = 3


def probe(client, name):
    times = []
    for _ in range(ROUNDS):
        started = time.monotonic()
        try:
            client.models.generate_content(model=name, contents="say ok")
            times.append(time.monotonic() - started)
        except Exception as exc:
            return None, f"{type(exc).__name__}: {str(exc)[:60]}"
    return times, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true",
                        help="probe every visible model, not just candidates")
    args = parser.parse_args()

    # Generous ceiling: this tool is measuring latency, not enforcing it.
    client = genai.Client(http_options=types.HttpOptions(timeout=60000))

    if args.all:
        names = [m.name.replace("models/", "") for m in client.models.list()]
        names = [n for n in names if "gemini" in n and "embedding" not in n]
    else:
        names = CANDIDATES

    print(f"Probing {len(names)} model(s), {ROUNDS} requests each.\n")
    healthy = []
    for name in names:
        times, error = probe(client, name)
        if error:
            print(f"  {name:<32} FAIL  {error}")
            continue
        median = statistics.median(times)
        spread = f"{min(times):.2f}-{max(times):.2f}s"
        flag = "" if median < 2 else "   << slow"
        print(f"  {name:<32} ok    median {median:5.2f}s  ({spread}){flag}")
        healthy.append((median, name))

    print()
    if not healthy:
        print("Nothing responded. Either the key is wrong or the API is down.")
        return 1

    healthy.sort()
    best_median = healthy[0][0]
    print(f"Fastest: {healthy[0][1]} at {best_median:.2f}s median")
    if best_median > 2:
        print("The API is degraded right now - normal here is well under 1s.")
        print("The assistant will hit its 20s timeout often until this clears.")
    else:
        print("Latency looks normal.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

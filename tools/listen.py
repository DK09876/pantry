#!/usr/bin/env python
"""Phase 1 acceptance test: wake word -> endpointed utterance -> wav file.

    tools/listen.py            wait for the wake word, capture one utterance
    tools/listen.py --monitor  print live wake scores, to tune the threshold
    tools/listen.py --loop     keep going until Ctrl-C

No speech recognition and no LLM here on purpose. This exercises only the
input path, so a failure points at exactly one place.
"""

import argparse
import sys
import time
import wave
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pantry import config
from pantry.audio import open_stream
from pantry.vad import Endpointer
from pantry.wake import WakeDetector

REC_DIR = Path(__file__).resolve().parent.parent / "recordings"


def save(audio, tag="utterance"):
    REC_DIR.mkdir(exist_ok=True)
    path = REC_DIR / f"{tag}_{datetime.now():%Y%m%d_%H%M%S}.wav"
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(config.TARGET_RATE)
        w.writeframes(audio.tobytes())
    return path


def dbfs(audio):
    if len(audio) == 0:
        return float("-inf")
    rms = float(np.sqrt((audio.astype(np.float64) ** 2).mean()))
    return 20 * np.log10(max(rms, 1e-9) / 32768)


def monitor(blocks, wake):
    print(f"Live scores. Say '{config.WAKE_MODEL}'. Ctrl-C to stop.\n")
    peak = 0.0
    while True:
        wake.process(next(blocks))
        peak = max(peak, wake.last_score)
        bar = "#" * int(wake.last_score * 40)
        print(f"\r  {wake.last_score:5.3f} peak {peak:5.3f} |{bar:<40}|", end="", flush=True)


def capture(blocks, wake, quiet=False):
    if not quiet:
        print(f"\nListening for wake word ({config.WAKE_MODEL})...")
    t_start = time.monotonic()
    while not wake.process(next(blocks)):
        pass
    t_wake = time.monotonic()
    print(f"  [wake] score {wake.last_score:.3f} after {t_wake - t_start:.1f}s idle")
    print("  [listening] speak now")

    ep = Endpointer()
    audio = None
    while audio is None:
        audio = ep.process(next(blocks))
    t_end = time.monotonic()

    if len(audio) == 0:
        print(f"  [timeout] no speech within {config.UTTERANCE_TIMEOUT_S:.0f}s")
        return None

    seconds = len(audio) / config.TARGET_RATE
    path = save(audio)
    # Report the phases separately: your reaction time is not system latency.
    reaction = (ep.speech_started_at - t_wake) if ep.speech_started_at else 0.0
    endpoint = (t_end - ep.speech_ended_at) if ep.speech_ended_at else 0.0
    print(f"  [captured] {seconds:.1f}s of audio, {dbfs(audio):.1f} dBFS")
    print(f"  [timing] you started after {reaction:.1f}s | "
          f"endpoint fired {endpoint * 1000:.0f}ms after you stopped "
          f"(target {config.VAD_SILENCE_MS}ms)")
    print(f"  [saved] {path}")
    print(f"  play: aplay -D plughw:2,0 {path}")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--monitor", action="store_true", help="live wake scores")
    ap.add_argument("--loop", action="store_true", help="repeat until Ctrl-C")
    args = ap.parse_args()

    wake = WakeDetector()
    print(f"[config] threshold {config.WAKE_THRESHOLD} | "
          f"silence {config.VAD_SILENCE_MS}ms | capture {config.CAPTURE_RATE}Hz -> 16kHz")

    with open_stream() as blocks:
        try:
            if args.monitor:
                monitor(blocks, wake)
            elif args.loop:
                while True:
                    capture(blocks, wake)
            else:
                capture(blocks, wake)
        except KeyboardInterrupt:
            print("\nstopped")


if __name__ == "__main__":
    main()

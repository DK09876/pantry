"""Settings, read from .env with defaults that work on this Pi."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _f(key, default):
    return float(os.environ.get(key, default))


def _i(key, default):
    return int(os.environ.get(key, default))


# --- Audio ---------------------------------------------------------------
# The USB mic rejects 16 kHz outright, so capture at 48 kHz and decimate 3:1.
# Card numbers move between boots, so the device is matched by name.
MIC_MATCH = os.environ.get("PANTRY_MIC_MATCH", "USB")
CAPTURE_RATE = _i("PANTRY_CAPTURE_RATE", 48000)
TARGET_RATE = 16000
DECIMATION = CAPTURE_RATE // TARGET_RATE

# 512 samples at 16 kHz is Silero's native chunk; openWakeWord buffers to 1280.
BLOCK_SAMPLES = 512
BLOCK_MS = BLOCK_SAMPLES / TARGET_RATE * 1000

# --- Wake word -----------------------------------------------------------
WAKE_MODEL = os.environ.get("PANTRY_WAKE_MODEL", "hey_jarvis_v0.1")
WAKE_THRESHOLD = _f("PANTRY_WAKE_THRESHOLD", 0.5)
# Ignore repeat fires for this long after a trigger.
WAKE_REFRACTORY_S = _f("PANTRY_WAKE_REFRACTORY_S", 2.0)

# --- Endpointing ---------------------------------------------------------
VAD_THRESHOLD = _f("PANTRY_VAD_THRESHOLD", 0.5)
# Speech must persist this long before we call it the start of an utterance.
VAD_START_MS = _i("PANTRY_VAD_START_MS", 160)
# Silence this long ends the utterance. Too short clips you off mid-sentence;
# too long and the assistant feels slow to respond.
VAD_SILENCE_MS = _i("PANTRY_VAD_SILENCE_MS", 700)
# Hard ceiling on one utterance.
UTTERANCE_MAX_S = _f("PANTRY_UTTERANCE_MAX_S", 15.0)
# Give up if no speech starts at all after the wake word.
UTTERANCE_TIMEOUT_S = _f("PANTRY_UTTERANCE_TIMEOUT_S", 6.0)

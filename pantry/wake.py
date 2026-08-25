"""Wake word detection with openWakeWord.

Runs fully on-device. The previous prototype detected the wake word by sending
every 4 seconds of room audio to Google's speech API, which meant the mic was
streaming to the cloud around the clock.
"""

import os
import time

import numpy as np
import openwakeword
from openwakeword.model import Model

from . import config

MODEL_DIR = os.path.join(os.path.dirname(openwakeword.__file__), "resources", "models")

# openWakeWord consumes 1280-sample frames; audio arrives in 512-sample blocks.
FRAME_SAMPLES = 1280


def model_path(name=config.WAKE_MODEL):
    path = os.path.join(MODEL_DIR, f"{name}.onnx")
    if not os.path.exists(path):
        available = sorted(
            f[:-5] for f in os.listdir(MODEL_DIR)
            if f.endswith(".onnx") and "melspectrogram" not in f
            and "embedding" not in f and "silero" not in f
        )
        raise FileNotFoundError(f"No wake model {name!r}. Available: {available}")
    return path


class WakeDetector:
    """Feed it audio blocks; it reports when the wake word fires.

    Scores are only produced on full 1280-sample frames, so blocks are buffered
    until a frame is available.
    """

    def __init__(self, name=config.WAKE_MODEL, threshold=config.WAKE_THRESHOLD,
                 refractory_s=config.WAKE_REFRACTORY_S):
        self.name = name
        self.threshold = threshold
        self.refractory_s = refractory_s
        self.model = Model(wakeword_model_paths=[model_path(name)])
        self._buffer = np.empty(0, dtype=np.int16)
        self._last_fire = 0.0
        self.last_score = 0.0

    def reset(self):
        self.model.reset()
        self._buffer = np.empty(0, dtype=np.int16)

    def process(self, block):
        """Return True if the wake word fired in this block."""
        self._buffer = np.concatenate([self._buffer, block])
        fired = False

        while len(self._buffer) >= FRAME_SAMPLES:
            frame = self._buffer[:FRAME_SAMPLES]
            self._buffer = self._buffer[FRAME_SAMPLES:]
            scores = self.model.predict(frame)
            self.last_score = float(scores.get(self.name, 0.0))

            if self.last_score >= self.threshold:
                now = time.monotonic()
                # One utterance can score above threshold on several consecutive
                # frames; the refractory window collapses those into one trigger.
                if now - self._last_fire > self.refractory_s:
                    self._last_fire = now
                    fired = True
                    self.reset()
                    break
        return fired

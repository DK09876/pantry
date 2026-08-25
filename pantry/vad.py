"""Utterance endpointing with Silero VAD.

Replaces SpeechRecognition's energy-threshold endpointing, which is close to
guessing on a mic whose noise floor sits around -40 dBFS.
"""

import time

import numpy as np
from pysilero_vad import SileroVoiceActivityDetector

from . import config

CHUNK_SAMPLES = 512  # Silero's native chunk at 16 kHz


class Endpointer:
    """Collects one utterance: waits for speech, then for the silence after it.

    Feed blocks in; when it returns audio, the utterance is complete.
    """

    WAITING = "waiting"
    SPEAKING = "speaking"
    DONE = "done"

    def __init__(self, threshold=config.VAD_THRESHOLD,
                 start_ms=config.VAD_START_MS,
                 silence_ms=config.VAD_SILENCE_MS,
                 max_s=config.UTTERANCE_MAX_S,
                 timeout_s=config.UTTERANCE_TIMEOUT_S):
        self.vad = SileroVoiceActivityDetector()
        self.threshold = threshold
        self.start_chunks = max(1, int(start_ms / 32))
        self.silence_chunks = max(1, int(silence_ms / 32))
        self.max_s = max_s
        self.timeout_s = timeout_s
        self.reset()

    def reset(self):
        self.vad.reset()
        self.state = self.WAITING
        self._audio = []
        self._pending = np.empty(0, dtype=np.int16)
        self._speech_run = 0
        self._silence_run = 0
        self._started = time.monotonic()
        self.last_prob = 0.0

    def process(self, block):
        """Return the utterance as int16 audio once complete, else None.

        Returns an empty array if it timed out with no speech.
        """
        if self.state == self.DONE:
            return None

        elapsed = time.monotonic() - self._started
        if self.state == self.WAITING and elapsed > self.timeout_s:
            self.state = self.DONE
            return np.empty(0, dtype=np.int16)
        if self.state == self.SPEAKING and elapsed > self.max_s:
            self.state = self.DONE
            return self._collected()

        self._pending = np.concatenate([self._pending, block])

        while len(self._pending) >= CHUNK_SAMPLES:
            chunk = self._pending[:CHUNK_SAMPLES]
            self._pending = self._pending[CHUNK_SAMPLES:]
            self.last_prob = float(self.vad(chunk.tobytes()))
            speech = self.last_prob >= self.threshold

            if self.state == self.WAITING:
                # Keep a little audio before speech starts so the first
                # phoneme is not clipped off the front.
                self._audio.append(chunk)
                if len(self._audio) > self.start_chunks + 8:
                    self._audio.pop(0)
                self._speech_run = self._speech_run + 1 if speech else 0
                if self._speech_run >= self.start_chunks:
                    self.state = self.SPEAKING
                    self._silence_run = 0
            else:
                self._audio.append(chunk)
                self._silence_run = 0 if speech else self._silence_run + 1
                if self._silence_run >= self.silence_chunks:
                    self.state = self.DONE
                    return self._collected()
        return None

    def _collected(self):
        return np.concatenate(self._audio) if self._audio else np.empty(0, dtype=np.int16)

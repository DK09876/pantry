"""Microphone capture.

One 16 kHz mono stream that every consumer shares. The mic only supports
44.1/48 kHz, so audio is captured at 48 kHz and decimated 3:1.

The decimation filter is stateful on purpose. Resampling each block
independently leaves a discontinuity at every block boundary, which shows up
as broadband noise the wake word model has to see through.
"""

import contextlib
import os
import sys

import numpy as np
import pyaudio
from scipy.signal import firwin, lfilter, lfilter_zi

from . import config


@contextlib.contextmanager
def suppress_c_stderr():
    """Hide the ALSA/JACK chatter PortAudio emits at C level on startup."""
    saved = os.dup(2)
    devnull = os.open(os.devnull, os.O_RDWR)
    try:
        os.dup2(devnull, 2)
        yield
    finally:
        os.dup2(saved, 2)
        os.close(devnull)
        os.close(saved)


class Decimator:
    """48 kHz -> 16 kHz with an anti-alias filter that keeps state.

    Without the low-pass, everything above 8 kHz folds back into the speech
    band. The mic hiss is broadband, so that would land right on top of speech.
    """

    def __init__(self, factor=config.DECIMATION, rate=config.CAPTURE_RATE):
        self.factor = factor
        nyquist_out = rate / factor / 2
        self.taps = firwin(63, nyquist_out * 0.9, fs=rate)
        self.state = lfilter_zi(self.taps, 1.0) * 0.0
        self._phase = 0

    def __call__(self, samples):
        filtered, self.state = lfilter(self.taps, 1.0, samples, zi=self.state)
        # Keep phase continuous across blocks so we never drop or repeat a sample.
        out = filtered[self._phase :: self.factor]
        consumed = len(samples) - self._phase
        self._phase = (-consumed) % self.factor
        return out.astype(np.int16)


def find_input_device(pa, match=config.MIC_MATCH):
    """Locate the mic by name. Card indices shift between boots and USB ports."""
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        if info["maxInputChannels"] > 0 and match.lower() in info["name"].lower():
            return i, info["name"]
    raise RuntimeError(
        f"No input device matching {match!r}. Check 'arecord -l' and PANTRY_MIC_MATCH."
    )


@contextlib.contextmanager
def open_stream(block_samples=config.BLOCK_SAMPLES):
    """Yield a generator of 16 kHz mono int16 blocks of `block_samples` each."""
    with suppress_c_stderr():
        pa = pyaudio.PyAudio()
    try:
        index, name = find_input_device(pa)
        print(f"[audio] {name}", file=sys.stderr)

        capture_block = block_samples * config.DECIMATION
        with suppress_c_stderr():
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=config.CAPTURE_RATE,
                input=True,
                input_device_index=index,
                frames_per_buffer=capture_block,
            )
        decimate = Decimator()

        def blocks():
            while True:
                raw = stream.read(capture_block, exception_on_overflow=False)
                yield decimate(np.frombuffer(raw, dtype=np.int16).astype(np.float64))

        try:
            yield blocks()
        finally:
            stream.stop_stream()
            stream.close()
    finally:
        pa.terminate()

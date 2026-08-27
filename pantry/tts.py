"""Speech output.

Sentences are synthesised and played on a worker thread while the language
model is still generating, so the first words are spoken before the last ones
exist. That overlap is most of the difference between feeling responsive and
feeling slow.

Speech is synthesised on-device by Piper. The model is loaded once at
startup, which takes a few seconds; doing it lazily would put that delay in
front of the first thing the assistant ever says.
"""

import os
import queue
import re
import subprocess
import sys
import tempfile
import time
import threading
import wave
from pathlib import Path

import numpy as np
from piper import PiperVoice, SynthesisConfig

from . import config

# Split after . ! ? when followed by a space, so decimals and abbreviations
# mostly survive intact.
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

# Piper reads a thousands separator aloud: 29,031 becomes "twenty-nine
# thousand, oh three one". Strip the commas and it says the number.
THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")

# Markdown emphasis reads as stray punctuation if the model slips any in.
MARKDOWN = re.compile(r"[*_`#]+")


def for_speech(text):
    """Tidy model output into something a speech engine reads correctly."""
    text = THOUSANDS.sub("", text)
    text = MARKDOWN.sub("", text)
    return text.strip()

# Don't fire a network round trip for a two-word fragment; wait for more.
MIN_SENTENCE_CHARS = 25


def find_output_card(match=None):
    """Resolve the speaker's ALSA card by name.

    Card numbers move when devices are plugged or unplugged, so the device is
    matched by name. A USB speaker is preferred over the Pi's own 3.5mm jack:
    the onboard DAC is noisy, and if a USB speaker is present it is almost
    certainly the one that is connected to something.

    PANTRY_SPEAKER_MATCH overrides the search entirely.
    """
    try:
        listing = subprocess.run(["aplay", "-l"], capture_output=True, text=True).stdout
    except FileNotFoundError:
        return None

    cards = []
    for line in listing.splitlines():
        if line.startswith("card"):
            cards.append((line.split(":")[0].split()[1], line))

    override = match or os.environ.get("PANTRY_SPEAKER_MATCH")
    if override:
        for number, line in cards:
            if override.lower() in line.lower():
                return number
        return None

    # HDMI is almost never what is wanted on a headless box.
    candidates = [(n, l) for n, l in cards if "hdmi" not in l.lower()]
    for wanted in ("usb", "headphones"):
        for number, line in candidates:
            if wanted in line.lower():
                return number
    return candidates[0][0] if candidates else None


class Speaker:
    def __init__(self, card=None, voice_path=None):
        self.card = card or find_output_card()
        self.device = f"plughw:{self.card},0" if self.card else "default"
        print(f"[audio] out {self.device}", file=sys.stderr)
        self._tmp = Path(tempfile.mkdtemp(prefix="pantry-tts-"))
        self._chime = self._make_chime()

        path = voice_path or config.PIPER_VOICE
        if not Path(path).exists():
            raise FileNotFoundError(
                f"No Piper voice at {path}. Run scripts/get_voice.sh, or set "
                "PANTRY_PIPER_VOICE."
            )
        started = time.monotonic()
        self._voice = PiperVoice.load(path)
        self._synthesis = SynthesisConfig(
            length_scale=config.PIPER_LENGTH_SCALE,
            noise_scale=config.PIPER_NOISE_SCALE,
            noise_w_scale=config.PIPER_NOISE_W_SCALE,
        )
        print(f"[audio] voice {Path(path).stem} "
              f"({time.monotonic() - started:.1f}s)", file=sys.stderr)

    # --- playback --------------------------------------------------------
    def _play_wav(self, path):
        subprocess.run(["aplay", "-q", "-D", self.device, str(path)],
                       stderr=subprocess.DEVNULL)

    def _make_chime(self):
        """A short two-tone chime. Acknowledging the wake word with speech
        would cost a network round trip; this is instant."""
        path = self._tmp / "chime.wav"
        sr = 16000
        tone = []
        for freq, ms in ((880, 120), (1320, 160)):
            n = int(sr * ms / 1000)
            t = np.arange(n) / sr
            env = np.minimum(1.0, np.minimum(t * 60, (ms / 1000 - t) * 60))
            tone.append(np.sin(2 * np.pi * freq * t) * env * 0.5)
        lead = np.zeros(int(sr * config.LEAD_SILENCE_MS / 1000))
        samples = (np.concatenate([lead] + tone) * 32767).astype(np.int16)
        with wave.open(str(path), "w") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(samples.tobytes())
        return path

    @staticmethod
    def _pad(path):
        """Prepend silence so the amp is awake before the words begin."""
        with wave.open(str(path)) as w:
            params = w.getparams()
            frames = w.readframes(w.getnframes())
        n = int(params.framerate * config.LEAD_SILENCE_MS / 1000)
        lead = bytes(n * params.sampwidth * params.nchannels)
        with wave.open(str(path), "w") as w:
            w.setparams(params)
            w.writeframes(lead + frames)
        return path

    def chime(self):
        self._play_wav(self._chime)

    # --- synthesis -------------------------------------------------------
    def _synthesise(self, text, index):
        """Render text to a playable wav, on-device."""
        wav_path = self._tmp / f"seg{index}.wav"
        with wave.open(str(wav_path), "wb") as wav:
            self._voice.synthesize_wav(for_speech(text), wav,
                                       syn_config=self._synthesis)
        return self._pad(wav_path)

    def say(self, text):
        """Speak one string, blocking until finished."""
        text = text.strip()
        if not text:
            return
        try:
            wav = self._synthesise(text, 0)
            self._play_wav(wav)
            wav.unlink(missing_ok=True)
        except Exception as exc:
            print(f"[tts] failed: {exc}")

    def stream(self):
        return _SpeechStream(self)


class _SpeechStream:
    """Accepts text as it arrives; speaks complete sentences as they form."""

    def __init__(self, speaker):
        self.speaker = speaker
        self._queue = queue.Queue()
        self._buffer = ""
        self._index = 0
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def _run(self):
        while True:
            item = self._queue.get()
            if item is None:
                break
            index, text = item
            try:
                wav = self.speaker._synthesise(text, index)
                self.speaker._play_wav(wav)
                wav.unlink(missing_ok=True)
            except Exception as exc:
                print(f"[tts] segment failed: {exc}")

    def feed(self, chunk):
        self._buffer += chunk
        while True:
            parts = SENTENCE_END.split(self._buffer, maxsplit=1)
            if len(parts) < 2 or len(parts[0]) < MIN_SENTENCE_CHARS:
                break
            self._emit(parts[0])
            self._buffer = parts[1]

    def _emit(self, text):
        text = text.strip()
        if text:
            self._index += 1
            self._queue.put((self._index, text))

    def close(self):
        """Flush the tail and wait for playback to finish."""
        self._emit(self._buffer)
        self._buffer = ""
        self._queue.put(None)
        self._worker.join()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

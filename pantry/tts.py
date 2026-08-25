"""Speech output.

Sentences are synthesised and played on a worker thread while the language
model is still generating, so the first words are spoken before the last ones
exist. That overlap is most of the difference between feeling responsive and
feeling slow.

gTTS is a placeholder. Piper replaces it in phase 3 and slots in behind the
same Speaker interface - only `_synthesise` changes.
"""

import queue
import re
import subprocess
import sys
import tempfile
import threading
import wave
from pathlib import Path

import numpy as np
from gtts import gTTS

# Split after . ! ? when followed by a space, so decimals and abbreviations
# mostly survive intact.
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

# Don't fire a network round trip for a two-word fragment; wait for more.
MIN_SENTENCE_CHARS = 25


def find_output_card(match="Headphones"):
    """Resolve the speaker's ALSA card by name; indices move between boots."""
    try:
        out = subprocess.run(["aplay", "-l"], capture_output=True, text=True).stdout
    except FileNotFoundError:
        return None
    for line in out.splitlines():
        if line.startswith("card") and match.lower() in line.lower():
            return line.split(":")[0].split()[1]
    return None


class Speaker:
    def __init__(self, card=None):
        self.card = card or find_output_card()
        self.device = f"plughw:{self.card},0" if self.card else "default"
        print(f"[audio] out {self.device}", file=sys.stderr)
        self._tmp = Path(tempfile.mkdtemp(prefix="pantry-tts-"))
        self._chime = self._make_chime()

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
        for freq, ms in ((880, 90), (1320, 110)):
            n = int(sr * ms / 1000)
            t = np.arange(n) / sr
            env = np.minimum(1.0, np.minimum(t * 60, (ms / 1000 - t) * 60))
            tone.append(np.sin(2 * np.pi * freq * t) * env * 0.25)
        samples = (np.concatenate(tone) * 32767).astype(np.int16)
        with wave.open(str(path), "w") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(samples.tobytes())
        return path

    def chime(self):
        self._play_wav(self._chime)

    # --- synthesis -------------------------------------------------------
    def _synthesise(self, text, index):
        """Render text to a playable wav. Piper replaces this in phase 3."""
        mp3 = self._tmp / f"seg{index}.mp3"
        wav = self._tmp / f"seg{index}.wav"
        gTTS(text=text, lang="en").save(str(mp3))
        subprocess.run(["mpg123", "-q", "-w", str(wav), str(mp3)],
                       stderr=subprocess.DEVNULL)
        mp3.unlink(missing_ok=True)
        return wav

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

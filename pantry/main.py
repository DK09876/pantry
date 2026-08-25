"""The voice loop.

    sleep -> wake word -> listen -> transcribe -> reason -> speak -> repeat

Structured as a dispatcher with one mode registered. Adding coding or
task-tracker modes means registering them, not reworking this file.
"""

import os
import sys
import time

from . import config
from .audio import open_stream
from .brain import Brain
from .modes import DEFAULT, resolve
from .stt import Transcriber
from .tts import Speaker
from .vad import Endpointer
from .wake import WakeDetector

# Spoken phrases that end the exchange and go back to sleep.
SLEEP_PHRASES = ("goodbye", "good bye", "never mind", "nevermind",
                 "go to sleep", "that's all", "thats all", "stop listening")

# How long to keep listening for a follow-up before going back to sleep.
FOLLOWUP_TIMEOUT_S = float(os.environ.get("PANTRY_FOLLOWUP_TIMEOUT_S", 8))


def _wants_sleep(text):
    lowered = text.lower().strip(" .!?")
    return any(phrase in lowered for phrase in SLEEP_PHRASES)


class Assistant:
    def __init__(self):
        self.speaker = Speaker()
        self.wake = WakeDetector()
        self.stt = Transcriber()
        self.brain = Brain()
        self.mode = DEFAULT
        self.chat = self.brain.session(self.mode)

    def _await_wake(self, audio):
        print(f"\n[sleeping] say '{self.wake.label}'")
        for block in audio.blocks():
            if self.wake.process(block):
                return

    def _listen(self, audio, timeout_s=None):
        """Capture one utterance and transcribe it. None if nothing usable."""
        endpointer = Endpointer(
            timeout_s=timeout_s or config.UTTERANCE_TIMEOUT_S)
        captured = None
        for block in audio.blocks():
            captured = endpointer.process(block)
            if captured is not None:
                break
        if captured is None or len(captured) == 0:
            return None

        started = time.monotonic()
        text = self.stt.transcribe(captured)
        if text:
            print(f"[heard] {text}   ({time.monotonic() - started:.1f}s stt)")
        return text

    def _respond(self, text):
        """Stream the reply into speech, sentence by sentence."""
        started = time.monotonic()
        spoken = []
        try:
            with self.speaker.stream() as speech:
                for chunk in self.brain.stream(self.chat, text):
                    spoken.append(chunk)
                    speech.feed(chunk)
        except Exception as exc:
            print(f"[brain] {type(exc).__name__}: {exc}")
            self.speaker.say("Sorry, I could not reach the model just now.")
            return
        print(f"[said] {''.join(spoken).strip()}   "
              f"({time.monotonic() - started:.1f}s)")

    def _exchange(self, audio):
        """One wake-to-sleep conversation."""
        self.speaker.chime()
        audio.drain()

        timeout = None
        while True:
            print("[listening]")
            text = self._listen(audio, timeout_s=timeout)
            if not text:
                # Silence after a reply just means the conversation is over.
                if timeout is not None:
                    return
                self.speaker.say("I didn't catch that.")
                audio.drain()
                return

            if _wants_sleep(text):
                self.speaker.say("Okay.")
                audio.drain()
                return

            switched = resolve(text)
            if switched and switched is not self.mode:
                self.mode = switched
                self.chat = self.brain.session(self.mode)
                self.speaker.say(f"{switched.name} mode.")
                audio.drain()
                continue

            self._respond(text)
            audio.drain()
            timeout = FOLLOWUP_TIMEOUT_S

    def run(self):
        print(f"[ready] model {self.brain.model} | mode {self.mode.name} | "
              f"wake '{self.wake.label}' at {config.WAKE_THRESHOLD}")
        with open_stream() as audio:
            while True:
                self._await_wake(audio)
                self._exchange(audio)


def main():
    try:
        Assistant().run()
    except KeyboardInterrupt:
        print("\n[stopped]")
        return 0
    except Exception as exc:
        print(f"[fatal] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

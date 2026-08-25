"""Speech to text.

Google's free Web Speech endpoint, reached through SpeechRecognition. It is
undocumented and carries no SLA, so every failure mode here has to be handled
rather than raised - a transcription failure should cost you one turn, not the
whole session.
"""

import speech_recognition as sr

from . import config


class Transcriber:
    def __init__(self):
        self._recognizer = sr.Recognizer()

    def transcribe(self, audio):
        """Return recognised text, or None if nothing usable came back."""
        if len(audio) == 0:
            return None
        data = sr.AudioData(audio.tobytes(), config.TARGET_RATE, 2)
        try:
            return self._recognizer.recognize_google(data).strip() or None
        except sr.UnknownValueError:
            return None
        except sr.RequestError as exc:
            print(f"[stt] service error: {exc}")
            return None

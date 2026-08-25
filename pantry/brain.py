"""The reasoning stage.

Gemini, streamed. Streaming is not cosmetic here: it lets speech synthesis
start on the first sentence while the rest is still being written.
"""

import time

from google import genai
from google.genai.errors import APIError

# Importing config loads .env, which must happen before genai.Client() looks
# for GEMINI_API_KEY.
from . import config  # noqa: F401
from .model_select import pick_model


class Brain:
    def __init__(self, temperature=0.7):
        self.client = genai.Client()
        self.model = pick_model(self.client)
        self.temperature = temperature

    def session(self, mode):
        """Start a conversation scoped to a mode."""
        return self.client.chats.create(
            model=self.model,
            config={
                "temperature": self.temperature,
                "system_instruction": mode.system_prompt,
            },
        )

    def stream(self, chat, text, max_retries=3):
        """Yield reply text as it arrives.

        Retries 503s, which Gemini returns under load. Anything else is
        surfaced to the caller so one bad turn does not kill the session.
        """
        for attempt in range(max_retries):
            try:
                for chunk in chat.send_message_stream(text):
                    if chunk.text:
                        yield chunk.text
                return
            except APIError as exc:
                retryable = getattr(exc, "code", None) == 503
                if retryable and attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise

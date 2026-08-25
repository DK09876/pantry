"""The reasoning stage.

Gemini, streamed. Streaming is not cosmetic here: it lets speech synthesis
start on the first sentence while the rest is still being written.
"""

import time

from google import genai
from google.genai import types
from google.genai.errors import APIError, ServerError

# Importing config loads .env, which must happen before genai.Client() looks
# for GEMINI_API_KEY.
from . import config  # noqa: F401
from .model_select import pick_model


class Brain:
    def __init__(self, temperature=0.7):
        # Without a timeout a stalled request hangs the whole assistant.
        # Measured: 1 in 3 requests took 29s unbounded. Must be the typed
        # HttpOptions - passing a plain dict here is unreliable.
        self.client = genai.Client(
            http_options=types.HttpOptions(
                timeout=int(config.LLM_TIMEOUT_S * 1000)
            )
        )
        # Startup probing gets a longer leash: one slow response should not
        # disqualify an otherwise good model for the whole session.
        self._probe_client = genai.Client(
            http_options=types.HttpOptions(timeout=45000)
        )
        self.model = pick_model(self._probe_client)
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
            except (APIError, ServerError) as exc:
                # 503 means overloaded, 504 means our own deadline fired.
                # Both are worth one more attempt.
                code = getattr(exc, "code", None)
                if code in (503, 504) and attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise

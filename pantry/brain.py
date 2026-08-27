"""The reasoning stage.

Gemini, streamed. Streaming is not cosmetic here: it lets speech synthesis
start on the first sentence while the rest is still being written.
"""

import time

import httpx

from google import genai
from google.genai import types
from google.genai.errors import APIError, ServerError

# Importing config loads .env, which must happen before genai.Client() looks
# for GEMINI_API_KEY.
from . import config  # noqa: F401
from .model_select import pick_model
from .tools import for_names


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
        """Start a conversation scoped to a mode.

        A mode's tools are handed to the model as plain Python functions; the
        SDK derives the parameter schema from their type hints and reads the
        docstrings to decide when to call them. Calls are executed
        automatically and the result fed back, so send_message returns text
        that already reflects whatever the tools did.
        """
        config = {
            "temperature": self.temperature,
            "system_instruction": mode.system_prompt,
        }
        tools = for_names(mode.tools)
        if tools:
            config["tools"] = tools
        return self.client.chats.create(model=self.model, config=config)

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
            except httpx.TimeoutException:
                # The deadline fired inside the transport, so this never
                # became an APIError. Same situation as a 504 and worth the
                # same retry.
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise
            except (APIError, ServerError) as exc:
                # 503 means overloaded, 504 means our own deadline fired.
                # Both are worth one more attempt.
                code = getattr(exc, "code", None)
                if code in (503, 504) and attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise

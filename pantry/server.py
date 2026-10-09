"""Pantry without a microphone: text in, spoken reply out.

This is what Siri talks to. An iOS Shortcut takes what you said, LifeOS's
/api/voice forwards it here over the Pi's loopback, and the reply comes back
for Siri to speak - so Pantry works from an iPhone, Apple Watch, AirPods or
CarPlay, not only within earshot of the Pi.

Same brain and tools as the voice loop. Each device keeps its own short
conversation, so "...and move it to tomorrow" works as a follow-up, and it
forgets after a few idle minutes.

    python -m pantry.server          # listens on 127.0.0.1:8790
"""

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .modes import DEFAULT

HOST = os.environ.get("PANTRY_API_HOST", "127.0.0.1")
PORT = int(os.environ.get("PANTRY_API_PORT", 8790))
SESSION_IDLE_S = float(os.environ.get("PANTRY_SESSION_IDLE_S", 300))


class Conversations:
    """One chat per device, dropped after a few idle minutes."""

    def __init__(self, brain, idle_s=SESSION_IDLE_S, clock=time.monotonic):
        self.brain = brain
        self.idle_s = idle_s
        self.clock = clock
        self._chats = {}
        # One model call at a time: chats are not thread-safe, and this is a
        # single-person assistant - queuing a second request costs nothing.
        self._lock = threading.Lock()

    def ask(self, device, text):
        with self._lock:
            now = self.clock()
            chat, last = self._chats.get(device, (None, 0.0))
            if chat is None or now - last > self.idle_s:
                chat = self.brain.session(DEFAULT)
            self._chats[device] = (chat, now)
            try:
                reply = self.brain.send(chat, text)
            except Exception as exc:  # noqa: BLE001 - any failure is one spoken sentence
                print(f"[server] {type(exc).__name__}: {exc}", flush=True)
                return "Sorry, I couldn't reach the model just now."
            return reply or "Done."


def make_handler(conversations):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 - http.server's naming
            if self.path.rstrip("/") != "/ask":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                self._reply(400, {"reply": "I didn't get that."})
                return
            text = str(body.get("text", "")).strip()
            if not text:
                self._reply(200, {"reply": "I didn't hear anything."})
                return
            device = str(body.get("device") or "siri")[:40]
            started = time.monotonic()
            reply = conversations.ask(device, text)
            print(f"[{device}] {text!r} -> {reply!r} ({time.monotonic() - started:.1f}s)", flush=True)
            self._reply(200, {"reply": reply})

        def do_GET(self):  # noqa: N802
            self._reply(200, {"ok": True}) if self.path == "/health" else self.send_error(404)

        def _reply(self, status, payload):
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass  # requests are logged above, once, with what was said

    return Handler


def main():
    from .brain import Brain  # loads the model client; kept out of tests

    conversations = Conversations(Brain())
    server = ThreadingHTTPServer((HOST, PORT), make_handler(conversations))
    print(f"[server] listening on {HOST}:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

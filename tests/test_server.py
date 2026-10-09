"""Tests for the text endpoint Siri talks to. The model is stubbed - no
paid API calls in tests."""

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from pantry.clock import with_now
from pantry.server import Conversations, make_handler


class FakeBrain:
    def __init__(self):
        self.sessions = 0
        self.sent = []

    def session(self, mode):
        self.sessions += 1
        return f"chat-{self.sessions}"

    def send(self, chat, text):
        self.sent.append((chat, text))
        return f"heard {text} on {chat}"


def test_a_device_keeps_its_conversation_until_idle():
    clock = [0.0]
    brain = FakeBrain()
    convo = Conversations(brain, idle_s=300, clock=lambda: clock[0])
    convo.ask("iphone", "add dishes to today")
    clock[0] = 60
    convo.ask("iphone", "and move it to tomorrow")
    assert [c for c, _ in brain.sent] == ["chat-1", "chat-1"]
    clock[0] = 60 + 301
    convo.ask("iphone", "what's on today")
    assert brain.sent[-1][0] == "chat-2"


def test_devices_do_not_share_a_conversation():
    brain = FakeBrain()
    convo = Conversations(brain)
    convo.ask("iphone", "a")
    convo.ask("watch", "b")
    assert brain.sessions == 2


def test_a_model_failure_is_a_sentence():
    class Broken(FakeBrain):
        def send(self, chat, text):
            raise RuntimeError("boom")
    assert "couldn't reach the model" in Conversations(Broken()).ask("x", "hi")


def test_http_round_trip():
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(Conversations(FakeBrain())))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/ask"
        req = urllib.request.Request(url, data=json.dumps({"text": "hello", "device": "iphone"}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        reply = json.loads(urllib.request.urlopen(req, timeout=5).read())
        assert reply == {"reply": "heard hello on chat-1"}
    finally:
        server.shutdown()


def test_every_request_carries_the_date():
    from datetime import datetime
    stamped = with_now("what's on friday", datetime(2026, 10, 9, 10, 5))
    assert stamped == "[It is Friday 9 October 2026, 10:05 AM.] what's on friday"

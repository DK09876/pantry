"""Shared fixtures.

The LifeOS tools talk to a real HTTP API. These tests stand a fake in its
place so they exercise the tool logic - name resolution, date parsing, the
shape of what gets written - without needing the server running.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class FakeAssistant:
    """Stands in for LifeOS's /api/assistant, recording what the tools ask."""

    def __init__(self):
        self.calls = []
        self.reply = "ok"
        self.fail = False

    def request(self, intent, args):
        if self.fail:
            raise OSError("connection refused")
        self.calls.append((intent, args))
        return {"ok": True, "say": self.reply}

    @property
    def last(self):
        return self.calls[-1]


@pytest.fixture
def lifeos(monkeypatch):
    """The lifeos tool module, wired to a fake assistant API."""
    from pantry.tools import lifeos as module

    fake = FakeAssistant()
    monkeypatch.setattr(module, "_request", fake.request)
    module.fake = fake
    return module

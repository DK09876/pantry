"""Shared fixtures.

The LifeOS tools talk to a real HTTP API. These tests stand a fake in its
place so they exercise the tool logic - name resolution, date parsing, the
shape of what gets written - without needing the server running.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class FakeLifeOS:
    """Stands in for the LifeOS API, recording what the tools send it."""

    def __init__(self):
        self.data = {
            "tasks": [], "domains": [], "habits": [],
            "events": [], "projects": [], "filterPresets": [],
            "preferences": {},
        }
        self.writes = []

    def request(self, method, path, payload=None):
        if method == "GET":
            return self.data
        self.writes.append((path, payload))
        collection = payload["collection"]
        for record in payload["records"]:
            existing = next(
                (i for i, r in enumerate(self.data[collection])
                 if r["id"] == record["id"]), None)
            if existing is None:
                self.data[collection].append(record)
            else:
                self.data[collection][existing] = record
        return {"ok": True}

    # --- helpers for arranging state --------------------------------------
    def add_domain(self, name, domain_id=None, priority="2 - Important"):
        row = {"id": domain_id or f"dom-{name.lower()}", "name": name,
               "priority": priority, "deletedAt": None}
        self.data["domains"].append(row)
        return row

    def add_task(self, name, task_id=None, status="Backlog", **extra):
        row = {"id": task_id or f"task-{len(self.data['tasks'])}",
               "taskName": name, "status": status, "taskScore": 0,
               "dueDate": None, "deletedAt": None}
        row.update(extra)
        self.data["tasks"].append(row)
        return row

    @property
    def tasks(self):
        return [t for t in self.data["tasks"] if not t.get("deletedAt")]


@pytest.fixture
def lifeos(monkeypatch):
    """The lifeos tool module, wired to a fake server."""
    from pantry.tools import lifeos as module

    fake = FakeLifeOS()
    monkeypatch.setattr(module, "_request", fake.request)
    module.fake = fake
    return module

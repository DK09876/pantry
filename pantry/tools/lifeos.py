"""Tools backed by LifeOS.

LifeOS runs on this same Pi, so these talk to it over localhost rather than
out through Tailscale.

Every function here is handed to the model as-is: the type hints become the
parameter schema and the docstring is what the model reads to decide whether
to call it. The wording of these docstrings is functional, not decoration.
"""

import json
import os
import urllib.request
import uuid
from datetime import date, datetime, timedelta

BASE_URL = os.environ.get("PANTRY_LIFEOS_URL", "http://localhost:3000")
PROFILE = os.environ.get("PANTRY_LIFEOS_PROFILE", "dk")
TIMEOUT = float(os.environ.get("PANTRY_LIFEOS_TIMEOUT_S", 8))


def _request(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(BASE_URL + path, data=data, method=method)
    if data:
        request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        body = response.read().decode()
    return json.loads(body) if body else {}


def _read():
    return _request("GET", "/api/data?profile=" + PROFILE)


def _write(collection, records):
    return _request("POST", "/api/data?profile=" + PROFILE,
                    {"collection": collection, "records": records})


def _live(rows):
    return [row for row in rows if not row.get("deletedAt")]


def _resolve_domain(name, domains):
    """Match a spoken domain name loosely - speech gives a name, not an id."""
    if not name:
        return None
    wanted = name.strip().lower()
    for domain in domains:
        if domain.get("name", "").lower() == wanted:
            return domain
    for domain in domains:
        if wanted in domain.get("name", "").lower():
            return domain
    return None


def _resolve_due(due_date):
    if not due_date:
        return ""
    lowered = due_date.strip().lower()
    if lowered == "today":
        return date.today().isoformat()
    if lowered == "tomorrow":
        return (date.today() + timedelta(days=1)).isoformat()
    return due_date.strip()


def add_task(task_name: str, due_date: str = "", domain: str = "",
             priority: str = "3 - Normal") -> str:
    """Add a task to the user's LifeOS task list.

    Args:
        task_name: What the task is, in the user's own words.
        due_date: Optional. YYYY-MM-DD, or the words today or tomorrow.
        domain: Optional life area such as Work, Health, Personal.
        priority: One of 1 - Urgent, 2 - High, 3 - Normal, 4 - Low,
            5 - Optional. Defaults to Normal when the user does not say.
    """
    payload = _read()
    matched = _resolve_domain(domain, _live(payload.get("domains", [])))
    resolved_due = _resolve_due(due_date)
    now = datetime.utcnow().isoformat() + "Z"

    _write("tasks", [{
        "id": str(uuid.uuid4()),
        "taskName": task_name,
        "status": "Backlog",
        "taskPriority": priority,
        "urgency": "3 - Normal",
        "taskScore": 0,
        "importanceScore": 0,
        "urgencyScore": 0,
        "dueDate": resolved_due or None,
        "plannedDate": None,
        "recurrence": "None",
        "lastCompleted": None,
        "doneDate": None,
        "actionPoints": None,
        "notes": "",
        "domainId": matched["id"] if matched else None,
        "projectId": None,
        "blockedBy": [],
        "createdAt": now,
        "updatedAt": now,
        "deletedAt": None,
    }])

    where = " in " + matched["name"] if matched else ""
    when = ", due " + resolved_due if resolved_due else ""
    return "Added " + task_name + where + when + "."


def list_tasks(when: str = "all", limit: int = 5) -> str:
    """List the user's current LifeOS tasks.

    Args:
        when: today for tasks due today or overdue, week for the next seven
            days, or all for everything not yet done.
        limit: How many to return. Keep it small; this is read aloud.
    """
    tasks = _live(_read().get("tasks", []))
    open_tasks = [t for t in tasks if t.get("status") not in ("Done", "Archived")]

    scope = (when or "all").strip().lower()
    if scope in ("today", "week"):
        horizon = date.today() + timedelta(days=7 if scope == "week" else 0)
        open_tasks = [t for t in open_tasks if t.get("dueDate")
                      and date.fromisoformat(t["dueDate"]) <= horizon]

    if not open_tasks:
        return "No tasks." if scope == "all" else "Nothing due " + scope + "."

    open_tasks.sort(key=lambda t: t.get("taskScore") or 0, reverse=True)
    names = [t.get("taskName", "untitled") for t in open_tasks[:limit]]
    return str(len(open_tasks)) + " open. Top: " + "; ".join(names) + "."


def complete_task(task_name: str) -> str:
    """Mark a LifeOS task as done.

    Args:
        task_name: The task to complete. Matched loosely, so a partial name
            is fine.
    """
    tasks = _live(_read().get("tasks", []))
    wanted = task_name.strip().lower()

    match = next((t for t in tasks if t.get("taskName", "").lower() == wanted), None)
    if match is None:
        match = next((t for t in tasks if wanted in t.get("taskName", "").lower()), None)
    if match is None:
        return "I could not find a task matching " + task_name + "."

    match["status"] = "Done"
    match["doneDate"] = date.today().isoformat()
    match["updatedAt"] = datetime.utcnow().isoformat() + "Z"
    _write("tasks", [match])
    return "Marked " + match["taskName"] + " as done."


def add_domain(name: str, priority: str = "2 - Important") -> str:
    """Create a life area (domain) in LifeOS, such as Work or Health.

    Args:
        name: What to call the area.
        priority: 1 - Critical, 2 - Important, or 3 - Maintenance.
    """
    now = datetime.utcnow().isoformat() + "Z"
    _write("domains", [{
        "id": str(uuid.uuid4()),
        "name": name,
        "icon": None,
        "priority": priority,
        "createdAt": now,
        "updatedAt": now,
        "deletedAt": None,
    }])
    return "Created the " + name + " area."


def list_domains() -> str:
    """List the user's life areas (domains) in LifeOS."""
    domains = _live(_read().get("domains", []))
    if not domains:
        return "No areas set up yet."
    return "Areas: " + ", ".join(d.get("name", "unnamed") for d in domains) + "."


TOOLS = (add_task, list_tasks, complete_task, add_domain, list_domains)

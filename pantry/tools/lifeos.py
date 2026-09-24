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
from datetime import UTC, date, datetime, timedelta

# Importing config loads .env. These module-level settings read os.environ at
# import time, so without this they depend on some other module having loaded
# .env first - which happened to be true, but silently.
from .. import config  # noqa: F401

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


def _task_status(task):
    """Mirror of isTaskComplete in LifeOS lib/hooks.ts.

    The web app promotes a task out of Needs Details only once priority,
    urgency, domain and action points are all set. Hard-coding "Backlog" here
    let voice-added tasks skip that triage, so they arrived scored as if they
    had been thought about when they had not.
    """
    ready = all((
        (task.get("taskName") or "").strip(),
        task.get("taskPriority"),
        task.get("urgency"),
        task.get("domainId"),
        task.get("actionPoints"),
    ))
    if not ready:
        return "Needs Details"
    return "Planned" if task.get("plannedDate") else "Backlog"


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
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    task = {
        "id": str(uuid.uuid4()),
        "taskName": task_name,
        "taskPriority": priority or None,
        # Not inferable from a spoken request; left unset so the task shows up
        # for triage rather than claiming a judgement nobody made.
        "urgency": None,
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
    }
    task["status"] = _task_status(task)
    _write("tasks", [task])

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
        # Planned for the day counts as much as due on it - "what do I have
        # today" means the plan, not only the deadlines. Blocked work is not
        # the user's to do, so it is left out, as the app does.
        def on(field):
            return lambda t: t.get(field) and date.fromisoformat(t[field]) <= horizon
        open_tasks = [t for t in open_tasks if t.get("status") != "Blocked"
                      and (on("dueDate")(t) or on("plannedDate")(t))]

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

    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    match["status"] = "Done"
    # A full timestamp, not date.today(): the app reads a bare YYYY-MM-DD as
    # UTC midnight, which is the previous evening here, so a task finished
    # today was reported as finished yesterday.
    match["doneDate"] = now
    # Recurrence keys off lastCompleted; without it a recurring task completed
    # by voice never came back.
    match["lastCompleted"] = now
    # The app keeps a log of completion days, which is what survives a
    # recurring task coming back for its next occurrence.
    today = date.today().isoformat()
    match["completions"] = sorted(set((match.get("completions") or []) + [today]))
    match["updatedAt"] = now
    _write("tasks", [match])
    return "Marked " + match["taskName"] + " as done."


def add_domain(name: str, priority: str = "2 - Important") -> str:
    """Create a life area (domain) in LifeOS, such as Work or Health.

    Args:
        name: What to call the area.
        priority: 1 - Critical, 2 - Important, or 3 - Maintenance.
    """
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
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


def _find_list(notes, name):
    wanted = (name or "").strip().lower()
    lists = [n for n in notes if n.get("kind") == "list"]
    exact = next((n for n in lists if n.get("title", "").lower() == wanted), None)
    return exact or next((n for n in lists if wanted and wanted in n.get("title", "").lower()), None)


def add_to_list(item: str, list_name: str = "Shopping") -> str:
    """Add an item to a checklist in LifeOS, such as the shopping list.

    Use this, not add_task, for shopping and other simple lists: they have no
    deadline or priority. The list is created if it does not exist yet.

    Args:
        item: The thing to add, e.g. "milk". Several can be comma-separated.
        list_name: Which list. Defaults to Shopping.
    """
    notes = _live(_read().get("notes", []))
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    target = _find_list(notes, list_name)
    items = [part.strip() for part in item.split(",") if part.strip()]
    if not items:
        return "Nothing to add."
    if target is None:
        target = {
            "id": str(uuid.uuid4()), "title": (list_name or "Shopping").strip().title(),
            "kind": "list", "body": "", "items": [], "pinned": False, "domainId": None,
            "createdAt": now, "deletedAt": None,
        }
    target["items"] = list(target.get("items") or []) + [
        {"id": str(uuid.uuid4()), "text": text, "done": False} for text in items]
    target["updatedAt"] = now
    _write("notes", [target])
    return "Added " + ", ".join(items) + " to " + target["title"] + "."


def read_list(list_name: str = "Shopping") -> str:
    """Read out what is still unticked on a LifeOS list.

    Args:
        list_name: Which list. Defaults to Shopping.
    """
    target = _find_list(_live(_read().get("notes", [])), list_name)
    if target is None:
        return "There is no " + list_name + " list."
    left = [i["text"] for i in target.get("items") or [] if not i.get("done")]
    if not left:
        return target["title"] + " is empty."
    return target["title"] + ": " + ", ".join(left) + "."


def add_note(text: str, title: str = "") -> str:
    """Save something to remember in LifeOS - a fact, an idea, a code.

    Use this, not add_task, for anything that is not work to be done.

    Args:
        text: What to remember, in the user's words.
        title: Optional short title. Defaults to the start of the text.
    """
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    heading = (title or text).strip()
    if len(heading) > 40:
        heading = heading[:40].rsplit(" ", 1)[0] + "…"
    _write("notes", [{
        "id": str(uuid.uuid4()), "title": heading, "kind": "note", "body": text,
        "items": [], "pinned": False, "domainId": None,
        "createdAt": now, "updatedAt": now, "deletedAt": None,
    }])
    return "Noted."


TOOLS = (add_task, list_tasks, complete_task, add_domain, list_domains,
         add_to_list, read_list, add_note)

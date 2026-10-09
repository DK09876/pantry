"""Tools backed by LifeOS.

LifeOS runs on this same Pi. Every tool here is a thin call to its assistant
API (/api/assistant), which runs the app's own actions - so "I did laundry"
said aloud does exactly what ticking it in the app does. Keeping the rules in
one place is the point: an earlier version re-implemented some of them in
Python, and the two copies were bound to drift apart.

Every function is handed to the model as-is: the type hints become the
parameter schema and the docstring is what the model reads to decide whether
to call it. The wording of these docstrings is functional, not decoration.

Each returns one short sentence from LifeOS, written to be spoken.
"""

import json
import os
import urllib.error
import urllib.request

# Importing config loads .env. These module-level settings read os.environ at
# import time, so without this they depend on some other module having loaded
# .env first - which happened to be true, but silently.
from .. import config  # noqa: F401

BASE_URL = os.environ.get("PANTRY_LIFEOS_URL", "http://localhost:3000")
PROFILE = os.environ.get("PANTRY_LIFEOS_PROFILE", "dk")
TIMEOUT = float(os.environ.get("PANTRY_LIFEOS_TIMEOUT_S", 8))

UNREACHABLE = "LifeOS isn't answering right now, so I couldn't do that."


def _request(intent, args):
    payload = json.dumps({"intent": intent, "args": args}).encode()
    request = urllib.request.Request(
        f"{BASE_URL}/api/assistant?profile={PROFILE}", data=payload, method="POST",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read().decode())


def _ask(intent, **args):
    """Run one LifeOS intent and return what it says.

    Never raises: a tool that throws surfaces to the user as "I could not
    reach the model", which is wrong when the model was fine and LifeOS was
    not. Saying what actually happened is more useful.
    """
    clean = {k: v for k, v in args.items() if v not in (None, "")}
    try:
        return _request(intent, clean).get("say") or "Done."
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return UNREACHABLE


# --- what's on ---------------------------------------------------------------

def whats_on(day: str = "today") -> str:
    """What is planned for a day: tasks, habits still to do, events, and how
    much energy (AP) is planned against the day's budget.

    Args:
        day: today (the default), tomorrow, a weekday such as Saturday,
            "next friday", or a date YYYY-MM-DD.
    """
    if (day or "today").strip().lower() == "today":
        return _ask("today")
    return _ask("day", day=day)


def whats_next() -> str:
    """The single best thing to do next today, within the energy left."""
    return _ask("next")


def this_week() -> str:
    """How many things are planned on each remaining day of this week."""
    return _ask("week")


def whats_overdue() -> str:
    """Tasks past their due date, and plans whose day went by undone."""
    return _ask("overdue")


def morning_brief() -> str:
    """A spoken summary of today plus anything overdue. Use for "brief me"."""
    return _ask("brief")


# --- capture -------------------------------------------------------------------

def add_task(task_name: str, day: str = "", due: str = "", domain: str = "",
             priority: str = "", urgency: str = "", effort: int = -1) -> str:
    """Add a new task to LifeOS. Only pass what the user actually said;
    anything left out stays unset and the task waits for the user to fill it
    in. Never invent a priority, urgency, domain or effort.

    Args:
        task_name: What the task is, in the user's words.
        day: The day they plan to do it, e.g. today, tomorrow, Saturday.
        due: The day it is due, if they said one.
        domain: Life area such as Home, Work, Finance, if said.
        priority: essential, high, normal, low or optional, if said.
        urgency: critical, high, normal, low or someday, if said.
        effort: 1 (tiny) to 5 (big), if said; -1 when not.
    """
    return _ask("add_task", name=task_name, day=day, due=due, domain=domain,
                priority=priority, urgency=urgency, effort=effort if effort >= 0 else None)


def add_to_list(items: str, list_name: str = "Shopping") -> str:
    """Add items to a checklist such as the shopping list. Use this, not
    add_task, for shopping and other simple lists.

    Args:
        items: The thing or things to add, comma-separated, e.g. "eggs, milk".
        list_name: Which list. Defaults to Shopping.
    """
    return _ask("list_add", items=items, list=list_name)


def read_list(list_name: str = "Shopping") -> str:
    """Read out what is still unticked on a list.

    Args:
        list_name: Which list. Defaults to Shopping.
    """
    return _ask("list_read", list=list_name)


def tick_off_list(item: str, list_name: str = "") -> str:
    """Tick an item off a list, e.g. "got the eggs".

    Args:
        item: The item that was got or done.
        list_name: The list, if the user said which.
    """
    return _ask("list_tick", item=item, list=list_name)


def add_note(text: str, title: str = "") -> str:
    """Save something to remember - a fact, an idea, a code. Use this, not
    add_task, for anything that is not work to be done.

    Args:
        text: What to remember, in the user's words.
        title: Optional short title.
    """
    return _ask("add_note", text=text, title=title)


def find_note(query: str) -> str:
    """Look up something the user saved, e.g. "what's the wifi code".

    Args:
        query: The words to look for.
    """
    return _ask("find_note", query=query)


# --- planning ------------------------------------------------------------------

def plan_task(task_name: str, day: str = "today") -> str:
    """Put an existing task on a day, or move it to another day. Also brings
    back a finished chore if that is what was named.

    Args:
        task_name: The task, loosely - "laundry" finds "Do laundry".
        day: today, tomorrow, a weekday, "next friday", or YYYY-MM-DD.
    """
    return _ask("plan", name=task_name, day=day)


def push_to_tomorrow(task_name: str) -> str:
    """Move a task to tomorrow, e.g. "I won't get to the taxes today".

    Args:
        task_name: The task.
    """
    return _ask("push", name=task_name)


def do_again(task_name: str, today: bool = True) -> str:
    """Bring back a finished chore that gets done regularly, such as the
    dishes or laundry, instead of creating a new task.

    Args:
        task_name: The chore.
        today: True to plan it for today (the default), False to just put it
            back on the list.
    """
    return _ask("do_again", name=task_name, today=today)


# --- doing ---------------------------------------------------------------------

def mark_done(name: str, day: str = "today") -> str:
    """Mark a task or a habit as done, e.g. "I did laundry", "I meditated".
    Use day="yesterday" for something done yesterday.

    Args:
        name: The task or habit, loosely.
        day: today (default) or yesterday.
    """
    return _ask("complete", name=name, day=day)


def log_progress(amount: float, goal: str = "", day: str = "today") -> str:
    """Log progress towards a goal, e.g. "I read 12 pages" or "ran 5 km".

    Args:
        amount: How much was done.
        goal: The goal or its unit (e.g. "pages", "Read a Book"), if said.
        day: today (default) or yesterday.
    """
    return _ask("log_progress", amount=amount, goal=goal, day=day)


def undo_last() -> str:
    """Undo the last change made by voice, e.g. "undo that", "no, cancel that"."""
    return _ask("undo")


# --- energy --------------------------------------------------------------------

def energy_today() -> str:
    """How much energy (AP) today has used, has planned, and has left."""
    return _ask("energy")


def set_today_energy(ap: int) -> str:
    """Change today's energy budget only, e.g. "I'm wiped, make today a 5".

    Args:
        ap: The new budget for today in AP.
    """
    return _ask("set_energy", ap=ap)


# --- waiting -------------------------------------------------------------------

def mark_waiting(task_name: str, waiting_on: str = "", chase_day: str = "") -> str:
    """Mark a task as blocked, waiting on someone or something, with a day to
    chase it up, e.g. "tax docs is waiting on the accountant, chase Thursday".

    Args:
        task_name: The task that is waiting.
        waiting_on: Who or what it is waiting on.
        chase_day: When to follow up; defaults to in 3 days.
    """
    return _ask("block", name=task_name, waiting_on=waiting_on, chase=chase_day)


def whats_waiting() -> str:
    """Everything blocked, what it is waiting on, and when to chase it."""
    return _ask("waiting")


# --- looking back -----------------------------------------------------------------

def week_review() -> str:
    """How this week has gone: things done, energy, backlog, habits."""
    return _ask("review")


def habit_streak(habit_name: str) -> str:
    """The current and best streak for a habit.

    Args:
        habit_name: The habit, loosely.
    """
    return _ask("streak", name=habit_name)


TOOLS = (
    whats_on, whats_next, this_week, whats_overdue, morning_brief,
    add_task, add_to_list, read_list, tick_off_list, add_note, find_note,
    plan_task, push_to_tomorrow, do_again,
    mark_done, log_progress, undo_last,
    energy_today, set_today_energy,
    mark_waiting, whats_waiting,
    week_review, habit_streak,
)

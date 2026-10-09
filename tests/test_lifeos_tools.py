"""Tests for the LifeOS tools.

The tools are thin: LifeOS's assistant API does the work and has its own
tests (lib/server/assistant.test.ts). What matters here is that each tool
asks for the right thing with only what the user said, and that a LifeOS
outage comes back as a sentence rather than an exception.
"""

import pytest


@pytest.mark.parametrize("call, expected", [
    (lambda t: t.whats_on(), ("today", {})),
    (lambda t: t.whats_on("Saturday"), ("day", {"day": "Saturday"})),
    (lambda t: t.whats_next(), ("next", {})),
    (lambda t: t.this_week(), ("week", {})),
    (lambda t: t.whats_overdue(), ("overdue", {})),
    (lambda t: t.morning_brief(), ("brief", {})),
    (lambda t: t.plan_task("laundry", "saturday"), ("plan", {"name": "laundry", "day": "saturday"})),
    (lambda t: t.push_to_tomorrow("taxes"), ("push", {"name": "taxes"})),
    (lambda t: t.do_again("dishes"), ("do_again", {"name": "dishes", "today": True})),
    (lambda t: t.do_again("dishes", today=False), ("do_again", {"name": "dishes", "today": False})),
    (lambda t: t.mark_done("laundry", "yesterday"), ("complete", {"name": "laundry", "day": "yesterday"})),
    (lambda t: t.log_progress(12, "pages"), ("log_progress", {"amount": 12, "goal": "pages", "day": "today"})),
    (lambda t: t.undo_last(), ("undo", {})),
    (lambda t: t.energy_today(), ("energy", {})),
    (lambda t: t.set_today_energy(5), ("set_energy", {"ap": 5})),
    (lambda t: t.mark_waiting("tax docs", "the accountant", "thursday"),
     ("block", {"name": "tax docs", "waiting_on": "the accountant", "chase": "thursday"})),
    (lambda t: t.whats_waiting(), ("waiting", {})),
    (lambda t: t.week_review(), ("review", {})),
    (lambda t: t.habit_streak("meditate"), ("streak", {"name": "meditate"})),
    (lambda t: t.add_to_list("eggs, milk"), ("list_add", {"items": "eggs, milk", "list": "Shopping"})),
    (lambda t: t.read_list(), ("list_read", {"list": "Shopping"})),
    (lambda t: t.tick_off_list("eggs"), ("list_tick", {"item": "eggs"})),
    (lambda t: t.add_note("wifi is 4471"), ("add_note", {"text": "wifi is 4471"})),
    (lambda t: t.find_note("wifi"), ("find_note", {"query": "wifi"})),
])
def test_each_tool_asks_for_the_right_intent(lifeos, call, expected):
    call(lifeos)
    assert lifeos.fake.last == expected


def test_add_task_sends_only_what_was_said(lifeos):
    # Voice is a capture inbox: nothing the user did not say is invented.
    lifeos.add_task("call mom", day="tomorrow")
    assert lifeos.fake.last == ("add_task", {"name": "call mom", "day": "tomorrow"})


def test_add_task_passes_everything_when_given(lifeos):
    lifeos.add_task("taxes", due="the 30th", domain="Finance", priority="high", urgency="high", effort=3)
    intent, args = lifeos.fake.last
    assert args == {"name": "taxes", "due": "the 30th", "domain": "Finance",
                    "priority": "high", "urgency": "high", "effort": 3}


def test_effort_zero_is_kept(lifeos):
    lifeos.add_task("brush teeth", effort=0)
    assert lifeos.fake.last[1]["effort"] == 0


def test_returns_what_lifeos_says(lifeos):
    lifeos.fake.reply = "Laundry is on Saturday."
    assert lifeos.plan_task("laundry", "saturday") == "Laundry is on Saturday."


def test_an_outage_is_a_sentence_not_an_exception(lifeos):
    lifeos.fake.fail = True
    assert lifeos.whats_on() == lifeos.UNREACHABLE


def test_every_tool_is_documented_for_the_model(lifeos):
    for tool in lifeos.TOOLS:
        assert tool.__doc__ and len(tool.__doc__.strip()) > 20, tool.__name__

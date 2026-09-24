"""Tests for the LifeOS tools.

These are the functions the model calls, so their arguments arrive as spoken
language rather than clean data: a domain name instead of an id, "tomorrow"
instead of a date, half a task title instead of the whole one. Almost all the
logic here is absorbing that, which is exactly the kind of code that breaks
quietly.
"""

from datetime import date, timedelta


def test_adds_a_task_with_only_a_name(lifeos):
    reply = lifeos.add_task("buy milk")

    assert len(lifeos.fake.tasks) == 1
    task = lifeos.fake.tasks[0]
    assert task["taskName"] == "buy milk"
    # A name alone is not enough to act on, so it lands in triage rather than
    # the backlog - the same rule the web app applies. Claiming "Backlog" here
    # put unexamined tasks straight into the planning board.
    assert task["status"] == "Needs Details"
    assert task["dueDate"] is None
    assert task["domainId"] is None
    assert "buy milk" in reply


def test_a_fully_specified_task_goes_straight_to_the_backlog(lifeos):
    lifeos.fake.add_domain("Health")
    lifeos.add_task("buy milk", domain="Health", priority="2 - High")
    task = lifeos.fake.tasks[0]
    # Voice cannot supply urgency or action points, so even this stays in
    # triage; the assertion records which fields are still missing.
    assert task["taskPriority"] == "2 - High"
    assert task["domainId"] is not None
    assert task["urgency"] is None
    assert task["actionPoints"] is None
    assert task["status"] == "Needs Details"


class TestDueDates:
    """Speech gives words, not ISO strings."""

    def test_today_and_tomorrow_resolve(self, lifeos):
        lifeos.add_task("a", due_date="today")
        lifeos.add_task("b", due_date="tomorrow")

        due = [t["dueDate"] for t in lifeos.fake.tasks]
        assert due == [date.today().isoformat(),
                       (date.today() + timedelta(days=1)).isoformat()]

    def test_word_matching_is_case_insensitive(self, lifeos):
        lifeos.add_task("a", due_date="Tomorrow")
        assert lifeos.fake.tasks[0]["dueDate"] == (
            date.today() + timedelta(days=1)).isoformat()

    def test_an_explicit_date_passes_through(self, lifeos):
        lifeos.add_task("a", due_date="2026-12-25")
        assert lifeos.fake.tasks[0]["dueDate"] == "2026-12-25"

    def test_no_due_date_is_null_not_empty_string(self, lifeos):
        lifeos.add_task("a")
        assert lifeos.fake.tasks[0]["dueDate"] is None


class TestDomainResolution:
    """The model passes a spoken name; the record needs an id."""

    def test_exact_name_matches(self, lifeos):
        health = lifeos.fake.add_domain("Health")
        lifeos.add_task("a", domain="Health")
        assert lifeos.fake.tasks[0]["domainId"] == health["id"]

    def test_matching_ignores_case(self, lifeos):
        health = lifeos.fake.add_domain("Health")
        lifeos.add_task("a", domain="health")
        assert lifeos.fake.tasks[0]["domainId"] == health["id"]

    def test_partial_name_matches(self, lifeos):
        work = lifeos.fake.add_domain("Work and Career")
        lifeos.add_task("a", domain="work")
        assert lifeos.fake.tasks[0]["domainId"] == work["id"]

    def test_exact_wins_over_partial(self, lifeos):
        lifeos.fake.add_domain("Work and Career")
        exact = lifeos.fake.add_domain("Work")
        lifeos.add_task("a", domain="Work")
        assert lifeos.fake.tasks[0]["domainId"] == exact["id"]

    def test_unknown_domain_still_creates_the_task(self, lifeos):
        lifeos.fake.add_domain("Health")
        reply = lifeos.add_task("a", domain="Fitness")
        assert len(lifeos.fake.tasks) == 1
        assert lifeos.fake.tasks[0]["domainId"] is None
        assert "Fitness" not in reply

    def test_deleted_domains_are_not_matched(self, lifeos):
        gone = lifeos.fake.add_domain("Health")
        gone["deletedAt"] = "2026-01-01T00:00:00Z"
        lifeos.add_task("a", domain="Health")
        assert lifeos.fake.tasks[0]["domainId"] is None


class TestListTasks:
    def test_says_so_when_there_is_nothing(self, lifeos):
        assert "No tasks" in lifeos.list_tasks()

    def test_done_and_archived_are_excluded(self, lifeos):
        lifeos.fake.add_task("open one")
        lifeos.fake.add_task("finished", status="Done")
        lifeos.fake.add_task("filed", status="Archived")

        reply = lifeos.list_tasks()
        assert "open one" in reply
        assert "finished" not in reply
        assert "filed" not in reply

    def test_highest_scoring_first(self, lifeos):
        lifeos.fake.add_task("minor", taskScore=10)
        lifeos.fake.add_task("urgent", taskScore=90)
        reply = lifeos.list_tasks()
        assert reply.index("urgent") < reply.index("minor")

    def test_limit_caps_what_is_read_aloud(self, lifeos):
        for i in range(10):
            lifeos.fake.add_task("task " + str(i), taskScore=i)
        reply = lifeos.list_tasks(limit=3)
        assert "10 open" in reply
        assert reply.count(";") == 2

    def test_today_covers_overdue_as_well(self, lifeos):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        lifeos.fake.add_task("overdue", dueDate=yesterday)
        lifeos.fake.add_task("next month",
                             dueDate=(date.today() + timedelta(days=30)).isoformat())

        reply = lifeos.list_tasks(when="today")
        assert "overdue" in reply
        assert "next month" not in reply

    def test_week_reaches_seven_days_out(self, lifeos):
        lifeos.fake.add_task("in three days",
                             dueDate=(date.today() + timedelta(days=3)).isoformat())
        lifeos.fake.add_task("in twenty days",
                             dueDate=(date.today() + timedelta(days=20)).isoformat())

        reply = lifeos.list_tasks(when="week")
        assert "in three days" in reply
        assert "in twenty days" not in reply

    def test_undated_tasks_are_left_out_of_a_dated_scope(self, lifeos):
        lifeos.fake.add_task("someday")
        assert "someday" not in lifeos.list_tasks(when="today")
        assert "someday" in lifeos.list_tasks(when="all")


class TestCompleteTask:
    def test_exact_name(self, lifeos):
        lifeos.fake.add_task("buy milk")
        reply = lifeos.complete_task("buy milk")
        assert lifeos.fake.tasks[0]["status"] == "Done"
        # A full timestamp, not a bare date: the app parses a 10-character
        # value as UTC midnight, which reads as the previous day here, so a
        # task finished today was reported as finished yesterday.
        done = lifeos.fake.tasks[0]["doneDate"]
        assert done.startswith(date.today().isoformat())
        assert done.endswith("Z") and len(done) > 10
        # Recurrence keys off lastCompleted; without it a recurring task
        # completed by voice never came back.
        assert lifeos.fake.tasks[0]["lastCompleted"] == done
        assert "buy milk" in reply

    def test_partial_name(self, lifeos):
        lifeos.fake.add_task("book a dentist appointment")
        lifeos.complete_task("dentist")
        assert lifeos.fake.tasks[0]["status"] == "Done"

    def test_case_insensitive(self, lifeos):
        lifeos.fake.add_task("Buy Milk")
        lifeos.complete_task("buy milk")
        assert lifeos.fake.tasks[0]["status"] == "Done"

    def test_exact_match_wins_over_partial(self, lifeos):
        lifeos.fake.add_task("milk run", task_id="partial")
        lifeos.fake.add_task("milk", task_id="exact")
        lifeos.complete_task("milk")

        by_id = {t["id"]: t for t in lifeos.fake.tasks}
        assert by_id["exact"]["status"] == "Done"
        assert by_id["partial"]["status"] == "Backlog"

    def test_says_so_when_nothing_matches(self, lifeos):
        lifeos.fake.add_task("buy milk")
        reply = lifeos.complete_task("wash the car")
        assert "could not find" in reply.lower()
        assert lifeos.fake.tasks[0]["status"] == "Backlog"

    def test_nothing_is_written_when_nothing_matches(self, lifeos):
        lifeos.fake.add_task("buy milk")
        lifeos.complete_task("nonsense")
        assert lifeos.fake.writes == []


class TestDomains:
    def test_add_and_list(self, lifeos):
        lifeos.add_domain("Fitness")
        assert lifeos.fake.data["domains"][0]["name"] == "Fitness"
        assert "Fitness" in lifeos.list_domains()

    def test_list_says_so_when_empty(self, lifeos):
        assert "No areas" in lifeos.list_domains()

    def test_deleted_domains_are_not_listed(self, lifeos):
        gone = lifeos.fake.add_domain("Old")
        gone["deletedAt"] = "2026-01-01T00:00:00Z"
        assert "Old" not in lifeos.list_domains()


def test_every_tool_returns_a_nonempty_string(lifeos):
    """A tool result is fed back to the model and then spoken aloud, so one
    returning a dict or None would surface as gibberish."""
    lifeos.fake.add_domain("Health")
    lifeos.fake.add_task("something")

    for result in (
        lifeos.add_task("x"),
        lifeos.list_tasks(),
        lifeos.complete_task("something"),
        lifeos.add_domain("New"),
        lifeos.list_domains(),
    ):
        assert isinstance(result, str) and result


class TestListsAndNotes:
    """Shopping lists and things to remember are not tasks."""

    def test_creates_the_shopping_list_on_first_use(self, lifeos):
        reply = lifeos.add_to_list("milk, eggs")
        [note] = lifeos.fake.data["notes"]
        assert note["kind"] == "list" and note["title"] == "Shopping"
        assert [i["text"] for i in note["items"]] == ["milk", "eggs"]
        assert lifeos.fake.tasks == []
        assert "milk" in reply

    def test_adds_to_an_existing_list_by_loose_name(self, lifeos):
        lifeos.add_to_list("milk", list_name="Groceries")
        lifeos.add_to_list("bread", list_name="grocer")
        [note] = lifeos.fake.data["notes"]
        assert [i["text"] for i in note["items"]] == ["milk", "bread"]

    def test_reads_only_unticked_items(self, lifeos):
        lifeos.add_to_list("milk, eggs")
        lifeos.fake.data["notes"][0]["items"][0]["done"] = True
        assert lifeos.read_list() == "Shopping: eggs."

    def test_saves_a_note(self, lifeos):
        lifeos.add_note("The boiler code is 4471")
        [note] = lifeos.fake.data["notes"]
        assert note["kind"] == "note" and note["body"] == "The boiler code is 4471"


def test_completing_logs_the_day(lifeos):
    lifeos.fake.add_task("water plants", recurrence="Biweekly", completions=["2026-01-01"])
    lifeos.complete_task("water plants")
    assert lifeos.fake.tasks[0]["completions"] == ["2026-01-01", date.today().isoformat()]


def test_today_includes_planned_work_and_skips_blocked(lifeos):
    today = date.today().isoformat()
    lifeos.fake.add_task("planned", plannedDate=today)
    lifeos.fake.add_task("blocked", status="Blocked", dueDate=today)
    reply = lifeos.list_tasks("today")
    assert "planned" in reply and "blocked" not in reply

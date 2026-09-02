"""Tests for recognising a dismissal.

Getting this wrong in either direction is bad: miss a dismissal and it keeps
listening, over-match and an ordinary question ends the conversation. Single
words only count as the whole utterance for that reason.
"""

import pytest

from pantry.main import _wants_sleep


@pytest.mark.parametrize("phrase", [
    "exit", "quit", "stop", "bye", "goodbye", "cancel",
    "go away", "never mind", "nevermind", "that's all",
    "okay stop", "stop listening", "go to sleep",
])
def test_dismissals(phrase):
    assert _wants_sleep(phrase) is True


@pytest.mark.parametrize("phrase", [
    "how do I stop a docker container",
    "what is a bye week",
    "tell me about exit codes",
    "why did my container stop running",
    "whats the weather in phoenix",
    "add a task to cancel my subscription",
    "remind me to quit the gym",
])
def test_questions_that_merely_contain_the_words(phrase):
    assert _wants_sleep(phrase) is False


def test_punctuation_and_case_are_ignored():
    assert _wants_sleep("Goodbye!") is True
    assert _wants_sleep("  STOP.  ") is True


def test_apostrophes_do_not_matter():
    # Speech recognition is inconsistent about them.
    assert _wants_sleep("that's all") is True
    assert _wants_sleep("thats all") is True

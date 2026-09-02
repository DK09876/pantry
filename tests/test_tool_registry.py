"""Tests for the tool registry.

The registry is keyed by application so a mode can scope which sets are live.
That indirection is the whole extensibility claim, so it is worth pinning.
"""

from pantry.modes import DEFAULT, REGISTRY as MODES, resolve
from pantry.tools import REGISTRY, for_names


def test_lifeos_tools_are_registered():
    assert "lifeos" in REGISTRY
    names = {fn.__name__ for fn in REGISTRY["lifeos"]}
    assert names == {"add_task", "list_tasks", "complete_task",
                     "add_domain", "list_domains"}


def test_for_names_flattens_requested_sets():
    assert len(for_names(["lifeos"])) == len(REGISTRY["lifeos"])


def test_an_unknown_set_is_ignored_rather_than_raising():
    # A mode naming a toolset that has not been built yet should degrade,
    # not crash the assistant at startup.
    assert for_names(["lifeos", "does-not-exist"]) == list(REGISTRY["lifeos"])


def test_asking_for_nothing_gives_nothing():
    assert for_names([]) == []


def test_general_mode_has_the_lifeos_tools():
    assert DEFAULT.tools == ("lifeos",)
    assert len(for_names(DEFAULT.tools)) == 5


def test_every_tool_is_describable_to_the_model():
    """The SDK builds the schema from type hints and the docstring, so a tool
    missing either is invisible or misused."""
    for tools in REGISTRY.values():
        for fn in tools:
            assert fn.__doc__, f"{fn.__name__} has no docstring"
            assert fn.__annotations__, f"{fn.__name__} has no type hints"
            assert "return" in fn.__annotations__, f"{fn.__name__} has no return type"


def test_mode_phrases_resolve():
    assert resolve("switch to general mode") is DEFAULT
    assert resolve("what is the weather") is None

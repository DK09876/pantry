"""What a mode is.

A mode is scoped context, not a separate program: a system prompt, the phrases
that switch into it, and later a toolset. General is mode zero. Adding coding
or task-tracker modes means adding entries here, not touching the voice loop.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Mode:
    name: str
    system_prompt: str
    # Spoken phrases that switch into this mode.
    enter_phrases: tuple = ()
    # Tool names this mode exposes. Empty for now; this is the hook that
    # makes modes tool filters over one agent rather than separate stacks.
    tools: tuple = field(default_factory=tuple)

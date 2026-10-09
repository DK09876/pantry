"""The one thing the model cannot know: what time it is."""

from datetime import datetime


def with_now(text, now=None):
    """Prefix a request with the local date and time.

    The model has no clock. Without this, "put laundry on Saturday" or "what's
    on Friday" had nothing to count from, and the old prompt even told it to
    refuse questions about the date.
    """
    now = now or datetime.now()
    return f"[It is {now:%A %-d %B %Y, %-I:%M %p}.] {text}"

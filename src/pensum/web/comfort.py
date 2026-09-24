"""The comfort profile: how the site behaves for the person using it.

Calm motion, bigger targets, a voice for the prompts. These change how a page
looks and moves, never what is asked or how it is marked, so they belong to the
device rather than to a result -- and they live in a cookie rather than in
`localStorage` for one reason: the server has to know them before it sends the
first byte. A setting read by a script after the page has painted is a page
that animates once and then stops, which is exactly what "calm" exists to
prevent.

The cookie is first-party, holds only the settings below, and is read back by
nobody but this site. It is not signed, because there is nothing to protect: a
forged value can only choose a setting its owner could have chosen on the
settings page. What it can do is be garbage, so every read is forgiving -- an
unreadable key falls back to its default, an unknown key is ignored, and a
cookie that is entirely nonsense reads as a first visit.

Account storage comes later. Until then a pupil who switches device sets it
again, which is the cost of not keeping anything server-side.
"""

from __future__ import annotations

from typing import Literal, get_args

from fastapi import Request
from pydantic import BaseModel, ConfigDict

COMFORT_COOKIE = "pensum_comfort"

# A year. Long enough that a family tablet keeps a child's settings through the
# school year, and it is renewed every time the settings page is saved.
COMFORT_MAX_AGE = 365 * 24 * 60 * 60

Theme = Literal["plain", "animals", "vehicles", "space", "blocks"]
THEMES: tuple[str, ...] = get_args(Theme)

# The on-the-wire alphabet is deliberately narrow: letters, digits, `_`, `:` and
# `|` are all legal in a cookie value unquoted, so the value reaches the browser
# exactly as written here instead of wrapped in quotes and escapes by whichever
# cookie library is in the middle.
_PAIR = "|"
_KV = ":"


class ComfortProfile(BaseModel):
    """What one device has asked for. Every default is the first-visit state."""

    model_config = ConfigDict(frozen=True)

    # The only setting that defaults to on: nobody should have to turn motion
    # off, and anyone who wants it can turn it on (principles.md, rule 9).
    calm: bool = True
    read_aloud: bool = False
    bigger_targets: bool = False
    # Stored, not yet drawn: the primitives that take a theme come later.
    theme: Theme = "plain"
    # Stored, not yet acted on: the break card comes with the run shape.
    break_reminder: bool = False

    @classmethod
    def parse(cls, raw: str | None) -> ComfortProfile:
        """Read a cookie value. Never raises: anything unreadable is a default."""
        if not raw:
            return cls()
        values: dict[str, object] = {}
        for pair in raw.split(_PAIR):
            key, sep, value = pair.partition(_KV)
            if not sep:
                continue
            if key in _FLAGS and value in ("0", "1"):
                values[key] = value == "1"
            elif key == "theme" and value in THEMES:
                values[key] = value
        return cls.model_validate(values)

    def serialise(self) -> str:
        """The cookie value. Every key is written, so a default changing later
        does not silently flip a setting someone chose."""
        parts = [f"{flag}{_KV}{int(getattr(self, flag))}" for flag in _FLAGS]
        parts.append(f"theme{_KV}{self.theme}")
        return _PAIR.join(parts)


_FLAGS = ("calm", "read_aloud", "bigger_targets", "break_reminder")


def comfort_of(request: Request) -> ComfortProfile:
    """The one place the cookie is read."""
    return ComfortProfile.parse(request.cookies.get(COMFORT_COOKIE))

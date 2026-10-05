"""An Arkade round in progress, and how a finished one is marked.

Held in memory, like a quiz session: a round that is never finished leaves no
trace, and a restart losing one in flight costs a pupil a few balloons. The
page gets the items when the round starts and plays them without the server;
the server marks the picks it is sent at the end, against its own copy.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from pensum.arkade.items import Item

# Long enough for a round played slowly with breaks, short enough that the store
# does not grow with every round anyone ever started.
ROUND_LIFETIME = timedelta(hours=2)


@dataclass(frozen=True)
class Round:
    id: str
    game: str
    subject: str
    items: tuple[Item, ...]
    timed: bool
    created_at: datetime
    user_sub: str | None = None


@dataclass(frozen=True)
class Marked:
    """One item's outcome. `correct` is None when time ran out (rule 4)."""

    item: Item
    correct: bool | None


@dataclass
class RoundStore:
    _rounds: dict[str, Round] = field(default_factory=dict)

    def create(
        self,
        game: str,
        subject: str,
        items: list[Item],
        *,
        timed: bool,
        now: datetime,
        user_sub: str | None,
    ) -> Round:
        self._sweep(now)
        played = Round(
            id=secrets.token_urlsafe(16),
            game=game,
            subject=subject,
            items=tuple(items),
            timed=timed,
            created_at=now,
            user_sub=user_sub,
        )
        self._rounds[played.id] = played
        return played

    def finish(self, round_id: str, user_sub: str | None, now: datetime) -> Round | None:
        """Take a round out of the store, so it can be marked once and only once.

        None for an unknown or expired round, or one another pupil started.
        """
        self._sweep(now)
        played = self._rounds.get(round_id)
        if played is None or played.user_sub != user_sub:
            return None
        del self._rounds[round_id]
        return played

    def __len__(self) -> int:
        return len(self._rounds)

    def _sweep(self, now: datetime) -> None:
        expired = [k for k, r in self._rounds.items() if now - r.created_at > ROUND_LIFETIME]
        for key in expired:
            del self._rounds[key]


def mark(played: Round, picks: list[int | None]) -> list[Marked]:
    """Each item's outcome from the candidate the pupil picked.

    No pick is not an answer: time ran out, or the page sent fewer picks than
    there were items. Either way it is neither right nor wrong.
    """
    out = []
    for index, item in enumerate(played.items):
        pick = picks[index] if index < len(picks) else None
        out.append(Marked(item, None if pick is None else item.is_match(pick)))
    return out

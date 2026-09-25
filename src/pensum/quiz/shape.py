"""The shape of a trinntest run: warm-up, core, finish.

docs/design/architecture.md, "Session engine", draws a run as three parts:

  * **Warm-up** -- one task the pupil can do, before anything new (principle 8).
    An item they already got right in an earlier sitting, if we know of one;
    otherwise the easiest item the goal set has. The warm-up may come from any
    goal: it is the one place a run mixes skills (principle 14).
  * **Core** -- the rest, *blocked*: every item for one goal together, then the
    next goal, rather than goals interleaved. Within a goal the items go
    concrete before pictorial before abstract, and easy before hard.
  * **Finish** -- a choice between two tasks, made by the pupil (principle 11).

**The length does not change.** A trinntest has always been `DEFAULT_LENGTH`
questions, spread across goals by `scoring.select`, and the result page's
threshold and per-goal breakdown are calibrated on that. So the run asks
`select` for exactly as many items as it did before -- one warm-up plus
`DEFAULT_LENGTH - 1` -- and the finish's second option is the only item drawn
beyond that. The option the pupil does not pick is never asked and never
scored, so a finished run is still `DEFAULT_LENGTH` answers graded exactly as
before. A bank too thin to spare that extra item gets a finish with no choice
rather than a shorter run.

The one way a run grows is stage stepping (`pensum.quiz.stages`), by at most one task,
and the pupil is told before it happens.

Pure functions of what they are given: no I/O, no clock, and randomness only
through the seed `select` already takes.
"""

from __future__ import annotations

import random
from collections.abc import Iterable
from dataclasses import dataclass

from pensum.items.schema import QuizItem
from pensum.quiz.scoring import select
from pensum.quiz.session import DEFAULT_LENGTH
from pensum.quiz.stages import STAGE_RANK

# How many options the finish offers. Two is a choice; more is a menu.
FINISH_OPTIONS = 2


@dataclass(frozen=True)
class Plan:
    """A run before it starts. `finish` is empty or exactly two options."""

    warm_up: QuizItem | None
    core: tuple[QuizItem, ...]
    finish: tuple[QuizItem, ...] = ()

    @property
    def items(self) -> list[QuizItem]:
        """The run in order, with the finish's first option holding its slot.

        The slot has to be in the list for the length to be right before the
        pupil reaches it; which option fills it is settled when they choose.
        """
        head = [self.warm_up] if self.warm_up else []
        return [*head, *self.core, *self.finish[:1]]


def plan(
    pool: list[QuizItem],
    *,
    length: int = DEFAULT_LENGTH,
    known_right: Iterable[str] = (),
    seed: int | None = None,
) -> Plan:
    """Lay out a run from a goal set's items."""
    if not pool:
        return Plan(warm_up=None, core=())

    warm = warm_up(pool, known_right, seed)
    rest = [item for item in pool if item.id != warm.id]
    # One more than the slots left, so the finish can offer a second option.
    drawn = select(rest, length, seed)
    if len(drawn) == length and length >= FINISH_OPTIONS + 1:
        core, finish = drawn[:-FINISH_OPTIONS], tuple(drawn[-FINISH_OPTIONS:])
    else:
        # Too few to spare one. Every item is asked, the last one is the finish
        # without a choice, and the run is as long as the bank allows.
        core, finish = drawn[: length - 1], ()
    return Plan(warm_up=warm, core=tuple(block(core)), finish=finish)


def warm_up(pool: list[QuizItem], known_right: Iterable[str], seed: int | None) -> QuizItem:
    """Something the pupil can do: known right before, else the easiest there is.

    Ties are broken at random rather than by id, so the same pupil does not
    open every sitting with the same question.
    """
    rng = random.Random(seed)  # noqa: S311 -- variety, not cryptography
    known = set(known_right)
    candidates = [item for item in pool if item.id in known] or pool
    easiest = min(item.difficulty for item in candidates)
    return rng.choice(sorted((i for i in candidates if i.difficulty == easiest), key=_id))


def block(items: list[QuizItem]) -> list[QuizItem]:
    """Group by goal, easier goals first; within a goal, concrete and easy first.

    Blocking is what principle 14 asks of the core: one skill at a time, so a
    pupil is not switching what they are thinking about on every screen.
    """
    by_goal: dict[str, list[QuizItem]] = {}
    for item in items:
        by_goal.setdefault(item.goal, []).append(item)
    for group in by_goal.values():
        group.sort(key=lambda i: (_rank(i), i.difficulty, i.id))

    def goal_key(goal: str) -> tuple[float, str]:
        group = by_goal[goal]
        return (sum(i.difficulty for i in group) / len(group), goal)

    return [item for goal in sorted(by_goal, key=goal_key) for item in by_goal[goal]]


def _rank(item: QuizItem) -> int:
    # An item with no declared stage sorts with the abstract ones: it is a
    # plain question, which is the abstract stage by default.
    return STAGE_RANK[item.stage] if item.stage else STAGE_RANK["abstract"]


def _id(item: QuizItem) -> str:
    return item.id

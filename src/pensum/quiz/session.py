"""Quiz sessions.

Held in memory for the length of a sitting and then discarded. Pensum is used by
children, so the default is that there is nothing to leak: no account, no
identifier that outlives the quiz. The cost is that an in-flight quiz does not
survive a restart, which is the right trade for a practice tool.

A session records who started it only when they were signed in. That attribution
is the one thing that can outlive the sitting -- and only as a summary, only when
score history is configured; see `pensum.scores.store`.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol, runtime_checkable

from pensum.auth.models import User
from pensum.items.schema import QuizItem
from pensum.quiz import stages
from pensum.quiz.hints import Revealed, Step, next_step, reveal

# Long enough that a 7-year-old is not rushed, short enough that abandoned
# sessions do not accumulate.
SESSION_TTL = timedelta(hours=2)
DEFAULT_LENGTH = 10


# After this many tasks, a pupil who asked for break reminders is offered one.
BREAK_EVERY = 4


@dataclass(frozen=True)
class AnswerRecord:
    """One answer as the session knows it, including how much help it took.

    `hints_used` is the number of hint-ladder steps revealed on this task before
    it was answered, carried over if the task was swapped for a lower-stage one.
    It is recorded, not scored: `scoring.score` never reads it, so a hinted
    answer counts exactly as an unhinted one on the pupil's result.
    """

    item_id: str
    goal: str
    response: str
    correct: bool
    hints_used: int


@dataclass(frozen=True)
class Stones:
    """The run's length, drawn as stones: one per task, filled as they finish.

    Never a clock and never a percentage (principle 3). `marks` is what the
    template draws; `done` and `total` are what it says to a screen reader.
    """

    done: int
    total: int

    def marks(self) -> tuple[str, ...]:
        return tuple(
            "done" if i < self.done else "current" if i == self.done else "todo"
            for i in range(self.total)
        )


@dataclass
class QuizSession:
    """One pupil's attempt at one checkpoint.

    `items` is the run in order -- warm-up, core, and the finish slot -- laid out
    by `pensum.quiz.shape`. It changes in three ways only, each one the pupil
    asked for or is told about: the finish slot takes whichever of
    `finish_options` they choose, a wrong answer can insert one lower-stage task
    (at most once per run, announced before it appears), and the hint ladder
    can swap the current task for its lower-stage version without changing the
    length.
    """

    id: str
    subject: str
    goal_set: str
    grade: int
    items: list[QuizItem]
    created_at: datetime
    answers: dict[str, str] = field(default_factory=dict)

    # Set only if the pupil was signed in when they started. Captured at start
    # rather than read at the end, so signing in mid-quiz cannot retroactively
    # attribute an attempt somebody else began.
    user_sub: str | None = None
    user_name: str | None = None

    # The goal set's whole bank, which stage stepping draws from.
    pool: tuple[QuizItem, ...] = ()
    # Two options for the last slot, or none when the bank could not spare one.
    finish_options: tuple[QuizItem, ...] = ()
    finish_chosen: bool = False
    # The id of the answer that added a stone, once one has.
    grown_after: str | None = None
    # Hint steps revealed per task, and the answer as it stood at the last
    # press, which the ladder's "show" step compares.
    hint_steps: dict[str, tuple[Step, ...]] = field(default_factory=dict)
    held: dict[str, str] = field(default_factory=dict)
    # Answers counted when the pupil last chose to carry on past a break card.
    rested_at: int = 0

    @property
    def attributed(self) -> bool:
        return self.user_sub is not None

    @property
    def answered(self) -> int:
        return len(self.answers)

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def finished(self) -> bool:
        return self.answered >= self.total

    def current(self) -> QuizItem | None:
        """The first unanswered item, or None when the quiz is done."""
        return next((item for item in self.items if item.id not in self.answers), None)

    def upcoming(self) -> QuizItem | None:
        """The task after the current one, for "show what's next"."""
        waiting = [item for item in self.items if item.id not in self.answers]
        return waiting[1] if len(waiting) > 1 else None

    # --- the finish ---------------------------------------------------------

    @property
    def choosing(self) -> bool:
        """True when the pupil has reached the finish and not yet picked."""
        return (
            bool(self.finish_options)
            and not self.finish_chosen
            and self.current() is self.items[-1]
        )

    def next_is_choice(self) -> bool:
        """True when the task after this one is the finish choice."""
        upcoming = self.upcoming()
        return bool(self.finish_options) and not self.finish_chosen and upcoming is self.items[-1]

    def choose(self, item_id: str) -> QuizItem | None:
        """Fill the finish slot with the option picked. None if it is not one."""
        if self.finish_chosen or not self.finish_options:
            return None
        picked = next((i for i in self.finish_options if i.id == item_id), None)
        if picked is None or self.items[-1].id in self.answers:
            return None
        self.items[-1] = picked
        self.finish_chosen = True
        return picked

    # --- answering ----------------------------------------------------------

    def answer(self, item_id: str, response: str) -> QuizItem | None:
        """Record a response. Returns the item answered, or None if unknown.

        Re-answering is refused rather than overwritten: the score should reflect
        the first attempt, not the one after the explanation was read.

        An answer to either finish option is taken as choosing it: a client that
        never showed the two cards has still asked one of them.
        """
        if item_id in self.answers:
            return None
        if not self.finish_chosen and any(i.id == item_id for i in self.finish_options):
            self.choose(item_id)
        item = next((i for i in self.items if i.id == item_id), None)
        if item is None:
            return None
        self.answers[item_id] = response
        if not item.is_correct(response):
            self._step_down_after(item)
        return item

    def _step_down_after(self, item: QuizItem) -> None:
        """After a wrong answer, put the same goal one stage lower next.

        At most once per run, never after the last task (the end the pupil was
        shown stays the end), and only where the bank has such an item.
        """
        if self.grown_after is not None:
            return
        index = self.items.index(item)
        if index >= len(self.items) - 1:
            return
        lower = self.lower_stage(item)
        if lower is None:
            return
        self.items.insert(index + 1, lower)
        self.grown_after = item.id

    def just_grew(self, item: QuizItem) -> bool:
        """Whether answering `item` is what added a stone -- said once, on its feedback."""
        return self.grown_after == item.id

    def stones(self, *, announcing: bool = False) -> Stones:
        """The stones to draw. While a new stone is being announced it is not
        drawn yet: the pupil reads that it is coming before it appears."""
        return Stones(done=self.answered, total=self.total - (1 if announcing else 0))

    # --- stage stepping and the hint ladder -----------------------------------

    def lower_stage(self, item: QuizItem) -> QuizItem | None:
        spent = {i.id for i in self.items} | {i.id for i in self.finish_options}
        return stages.lower_stage(item, self.pool, spent)

    def hint(self, item_id: str, held: str) -> Step | None:
        """Reveal the next step of the current task's ladder. None if there is none.

        Only the task on screen takes hints; a stale form for an earlier one is
        ignored rather than recorded against an answer already given.
        """
        item = self.current()
        if item is None or item.id != item_id:
            return None
        self.held[item_id] = held
        revealed = self.hint_steps.get(item_id, ())
        step = next_step(
            item, revealed, can_step_down=self.lower_stage(item) is not None, held=held
        )
        if step is not None:
            self.hint_steps[item_id] = (*revealed, step)
        return step

    def revealed(self, item: QuizItem, locale: str) -> tuple[Revealed, ...]:
        return reveal(
            item,
            self.hint_steps.get(item.id, ()),
            lower=self.lower_stage(item),
            held=self.held.get(item.id, ""),
            locale=locale,
        )

    def more_help(self, item: QuizItem) -> bool:
        """Whether one more press would reveal anything.

        Judged on the answer as last held. With the script running that is
        always a board state, so it is exact; before the first press there is
        always a restatement to give.
        """
        return (
            next_step(
                item,
                self.hint_steps.get(item.id, ()),
                can_step_down=self.lower_stage(item) is not None,
                held=self.held.get(item.id, ""),
            )
            is not None
        )

    def swap_down(self, item_id: str) -> QuizItem | None:
        """Hint step 3: replace the current task with its lower-stage version.

        The run keeps its length -- this is the same task shown differently, not
        an extra one -- and the hints already used come along, since they were
        spent on this task.
        """
        item = self.current()
        if item is None or item.id != item_id:
            return None
        if "step_down" not in self.hint_steps.get(item_id, ()):
            return None
        lower = self.lower_stage(item)
        if lower is None:
            return None
        index = self.items.index(item)
        self.items[index] = lower
        if index == len(self.items) - 1 and self.finish_options:
            # Swapping the finish is still the pupil's choice, just made twice.
            self.finish_chosen = True
        self.hint_steps[lower.id] = self.hint_steps.pop(item_id)
        self.held.pop(item_id, None)
        return lower

    def hints_used(self, item_id: str) -> int:
        return len(self.hint_steps.get(item_id, ()))

    def records(self) -> tuple[AnswerRecord, ...]:
        """Every answer, in run order, with the help it took."""
        return tuple(
            AnswerRecord(
                item_id=item.id,
                goal=item.goal,
                response=self.answers[item.id],
                correct=item.is_correct(self.answers[item.id]),
                hints_used=self.hints_used(item.id),
            )
            for item in self.items
            if item.id in self.answers
        )

    # --- breaks ---------------------------------------------------------------

    def break_due(self) -> bool:
        """Whether a break card belongs before the next task.

        Only between tasks, only every `BREAK_EVERY`, and only once per stop: a
        pupil who chose to carry on is not asked again until four more are done.
        The comfort setting is the caller's to check; the session does not know
        which device it is on.
        """
        return (
            not self.finished
            and self.answered > 0
            and self.answered % BREAK_EVERY == 0
            and self.rested_at != self.answered
        )

    def carry_on(self) -> None:
        self.rested_at = self.answered

    def expired(self, now: datetime) -> bool:
        return now - self.created_at > SESSION_TTL


@runtime_checkable
class Expiring(Protocol):
    """What the store needs of a session, and nothing more.

    A nivåtest session is a different shape from a trinntest one -- it draws its
    questions a block at a time instead of holding a fixed list -- but the part
    that must not be implemented twice is the expiry sweep, since that is what
    keeps abandoned attempts from accumulating. So the store is defined against
    this instead of against a concrete class, and `pensum.quiz.run` can put its
    own session type in without either module importing the other.
    """

    @property
    def id(self) -> str: ...

    def expired(self, now: datetime) -> bool: ...


class SessionStore:
    """In-memory session storage, swept lazily.

    Deliberately process-local. A restart loses in-flight quizzes, and an
    unfinished quiz leaves no trace anywhere.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, Expiring] = {}

    def create(
        self,
        subject: str,
        goal_set: str,
        grade: int,
        items: list[QuizItem],
        now: datetime,
        user: User | None = None,
        *,
        pool: tuple[QuizItem, ...] = (),
        finish_options: tuple[QuizItem, ...] = (),
    ) -> QuizSession:
        self._sweep(now)
        session = QuizSession(
            # Opaque and unguessable, so a session id reveals nothing and cannot
            # be enumerated.
            id=secrets.token_urlsafe(16),
            subject=subject,
            goal_set=goal_set,
            grade=grade,
            items=items,
            created_at=now,
            user_sub=user.sub if user else None,
            user_name=user.name if user else None,
            pool=pool,
            finish_options=finish_options,
        )
        self._sessions[session.id] = session
        return session

    def known_right(self, user_sub: str | None, goal_set: str, now: datetime) -> set[str]:
        """Items this pupil answered right in an earlier sitting still held here.

        What the warm-up prefers (`pensum.quiz.shape.warm_up`). Only for a
        signed-in pupil, since nothing else ties two sittings to one child, and
        only as far back as sessions live: this reads the store, not the score
        history, which keeps summaries and never item ids.
        """
        if user_sub is None:
            return set()
        self._sweep(now)
        return {
            item.id
            for session in self._sessions.values()
            if isinstance(session, QuizSession)
            and session.user_sub == user_sub
            and session.goal_set == goal_set
            for item in session.items
            if item.id in session.answers and item.is_correct(session.answers[item.id])
        }

    def put(self, session: Expiring, now: datetime) -> Expiring:
        """Store a session built elsewhere, sweeping first.

        The trinntest flow has `create` because the store knows how to build
        that session. A nivåtest session needs a ladder and a way to draw items,
        neither of which belongs here.
        """
        self._sweep(now)
        self._sessions[session.id] = session
        return session

    def get(self, session_id: str, now: datetime) -> Expiring | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.expired(now):
            del self._sessions[session_id]
            return None
        return session

    def _sweep(self, now: datetime) -> None:
        for key in [k for k, s in self._sessions.items() if s.expired(now)]:
            del self._sessions[key]

    def __len__(self) -> int:
        return len(self._sessions)

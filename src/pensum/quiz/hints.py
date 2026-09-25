"""The hint ladder: fixed steps, walked one per press of Help.

docs/design/activities.md, "Hint ladder", fixes the steps and their order for
every subject, so that help is worded the same way everywhere and a pupil learns
what pressing Help will do:

  1. **restate** -- the task in fewer words (read aloud when that is on). An
     item's `hints.restate` if the author wrote one, else the prompt again.
  2. **show** -- what the pupil has built so far beside what was asked. Only a
     hands-on primitive with a board state has a "so far"; everything else,
     including a primitive answered by typing, skips it.
  3. **step_down** -- swap this task for the same goal one stage more concrete
     (`pensum.quiz.stages`). Skipped when the bank has no such item.
  4. **partial** -- the first step done for them: `hints.partial`.
  5. **worked** -- a parallel task, solved: `hints.worked`.

A step with nothing to show is skipped, not padded: a ladder that says "no hint
here" on the way up is one more thing to read for nothing. Each press reveals
the next step that exists, and earlier ones stay on screen.

Using help costs nothing. The number of steps revealed is recorded with the
answer (`QuizSession.records`) as information for whoever reads evidence later,
and the score a pupil is shown never looks at it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pensum.items.primitives import primitive_for
from pensum.items.primitives.base import Comparison
from pensum.items.schema import QuizItem

Step = Literal["restate", "show", "step_down", "partial", "worked"]
LADDER: tuple[Step, ...] = ("restate", "show", "step_down", "partial", "worked")


@dataclass(frozen=True)
class Revealed:
    """One step on screen: its words, and for `show` and `step_down` its extra."""

    step: Step
    text: str = ""
    comparison: Comparison | None = None
    # The item a `step_down` swaps to.
    target: QuizItem | None = None


def next_step(
    item: QuizItem, revealed: tuple[Step, ...], *, can_step_down: bool, held: str
) -> Step | None:
    """The step one more press of Help reveals, or None at the top of the ladder.

    Always further up than anything already revealed, so a step once shown is
    never shown twice and the ladder never goes back down. What is available is
    judged now, at the press: the board may have something on it this time that
    it did not the last.
    """
    hints = item.hints
    available: dict[Step, bool] = {
        # Always there: with no authored restatement it is the prompt again,
        # which is still the thing read aloud for a pupil who asked.
        "restate": True,
        "show": _built(item, held),
        "step_down": can_step_down,
        "partial": hints is not None and hints.partial is not None,
        "worked": hints is not None and hints.worked is not None,
    }
    after = LADDER.index(revealed[-1]) + 1 if revealed else 0
    return next((step for step in LADDER[after:] if available[step]), None)


def reveal(
    item: QuizItem,
    steps: tuple[Step, ...],
    *,
    lower: QuizItem | None,
    held: str,
    locale: str,
) -> tuple[Revealed, ...]:
    """The revealed steps, filled in for display.

    `held` is the answer as it stood at the last press -- the board's state for
    a primitive -- so `show` compares what the pupil has now, not what the task
    opened with. A step whose content has since gone (the lower-stage item was
    used elsewhere in the run) is left off rather than drawn empty.
    """
    shown: list[Revealed] = []
    for step in steps:
        if step == "restate":
            text = item.hints.restate if item.hints and item.hints.restate else item.prompt
            shown.append(Revealed(step, text.get(locale)))
        elif step == "show" and _built(item, held):
            primitive = primitive_for(item)
            comparison = primitive.compare(item, held, locale) if primitive else None
            shown.append(Revealed(step, comparison=comparison))
        elif step == "step_down" and lower is not None:
            shown.append(Revealed(step, target=lower))
        elif step == "partial" and item.hints and item.hints.partial:
            shown.append(Revealed(step, item.hints.partial.get(locale)))
        elif step == "worked" and item.hints and item.hints.worked:
            shown.append(Revealed(step, item.hints.worked.get(locale)))
    return tuple(shown)


def _built(item: QuizItem, held: str) -> bool:
    """Whether there is a built board to put beside the task.

    Only a hands-on primitive has one, and only once the page has sent its
    state: the no-script road sends a typed number, and "you wrote 12, the
    answer is 34" is not a hint but the answer. The number line is on the seam
    but draws no comparison, so it has nothing to show either.
    """
    primitive = primitive_for(item)
    if primitive is None or primitive.config is None or item.activity is None:
        return False
    return held.strip().startswith("{") and item.activity.read(held) is not None

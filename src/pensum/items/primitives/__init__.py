"""Item kinds a pupil answers with their hands, and the seam they plug into.

`docs/design/activities.md` lists some thirty primitives -- counters, ten-frames,
base-ten blocks, balances, sorting bins -- and every one is a piece of
interaction code with its own tests, keyboard model and no-JavaScript fallback.
If each of them were a new `elif` in `schema.py`, `question.html`, the feedback
partial and the routes, the thirtieth would be written into five files that
already hold twenty-nine others, and the one that forgets a branch fails quietly.

**So an interactive item kind is one module and one registration line.** The
module provides a `Primitive`:

  * `config` -- a frozen pydantic model, the item's `activity:` block. Declared
    parameters, never paths or markup, for the reason `figures.py` gives: a
    reviewer can check `target: 34` against the prompt, and nobody can check an
    SVG path. It subclasses `base.ActivityConfig`, which supplies the state
    parsing, the typed fallback and the feedback comparison.
  * `grade(item, response)` -- a pure function of the declared config and the
    one serialised state the page submits. Never raises: a malformed state is
    a wrong answer.
  * `template` -- the partial that draws the question's answer area. For an
    `ActivityConfig` primitive it extends `partials/primitives/_activity.html`,
    which already provides the board, the hidden state field, undo and the
    no-script fallback, so the partial only lists the primitive's buttons.
  * `script` -- optionally, a file under `static/` that registers the
    primitive's pure state functions with `static/primitives/core.js`. The core
    does the pointer and keyboard plumbing, tap-tap and drag, undo and the
    live status line; the primitive's own file says what a move does.

Registering is adding it to `PRIMITIVES` below. The item schema, the question
and feedback partials, the pages that load scripts and the review page all read
the registry, so none of them changes when a primitive is added.

What stays outside the seam: `multiple_choice`, `numeric` and `short_text`.
They are the abstract stage and every primitive's fallback, their grading is
three lines each, and moving them would be churn for its own sake.
`number_line` is on the seam, as a `Primitive` whose config is the item's
existing `figure` and `answer`, so its YAML did not change.

Two properties every primitive keeps, and the tests hold them to:

  * grading is a pure function of the final state, never of time or process;
  * the question is answerable with no script at all, by typing a number into
    the same form, and that number is graded against the same target. The
    card primitives (sort, sequence, match, label, highlight) have no number,
    so theirs is a choice between whole arrangements, each one a state graded
    by the same rule as a built one (`cards.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any, Union

from pydantic import Field

from pensum.items.primitives import base
from pensum.items.primitives.array import ArrayActivity
from pensum.items.primitives.balance import BalanceActivity
from pensum.items.primitives.base_ten import BaseTenActivity
from pensum.items.primitives.blend import BlendActivity
from pensum.items.primitives.counters import CountersActivity
from pensum.items.primitives.dialogue import DialogueActivity
from pensum.items.primitives.explore_sim import ExploreSimActivity
from pensum.items.primitives.highlight import HighlightActivity
from pensum.items.primitives.label import LabelActivity
from pensum.items.primitives.match import MatchActivity
from pensum.items.primitives.sentence_build import SentenceBuildActivity
from pensum.items.primitives.sequence import SequenceActivity
from pensum.items.primitives.sort import SortActivity
from pensum.items.primitives.sound_boxes import SoundBoxesActivity
from pensum.items.primitives.step_code import StepCodeActivity
from pensum.items.primitives.ten_frame import TenFrameActivity
from pensum.items.primitives.trials import TrialsActivity
from pensum.items.primitives.word_build import WordBuildActivity

if TYPE_CHECKING:
    from pensum.items.schema import QuizItem

__all__ = [
    "PRIMITIVES",
    "Activity",
    "Primitive",
    "primitive_for",
    "scripts",
]


@dataclass(frozen=True)
class Primitive:
    """One interactive item kind, as the rest of the code sees it.

    The defaults implement everything for a primitive whose rules live in an
    `ActivityConfig`; `number_line` overrides them because its declaration
    predates the seam and lives in `figure` and `answer`.
    """

    kind: str
    template: str
    script: str | None = None
    config: type[base.ActivityConfig] | None = None
    # A number_line draws the item's figure itself, as the thing answered on,
    # so the generic figure above the answers stands down for it.
    owns_figure: bool = False

    def check(self, item: QuizItem) -> None:
        """Raise ValueError if the item is not a well-formed one of these."""
        activity = item.activity
        if activity is None or activity.kind != self.kind:
            raise ValueError(f"{item.id}: a {self.kind} item needs an activity of that kind")
        if item.choices or item.answer is not None or item.accept:
            raise ValueError(
                f"{item.id}: a {self.kind} item is graded from its activity, "
                "so choices, answer and accept would never be read"
            )
        # The config must agree with itself: its own solution, serialised the
        # way the page sends it, grades right, and the starting board is a
        # state it admits. A declaration that fails this is a typo, and it
        # fails at load rather than in front of a child.
        if not base.grade(activity, activity.serialise(activity.solution())):
            raise ValueError(f"{item.id}: the {self.kind} activity cannot be answered")
        if activity.read(activity.serialise(activity.initial())) is None:
            raise ValueError(f"{item.id}: the {self.kind} activity cannot start as declared")
        if activity.fallback is None and not base.grade(activity, activity.typed_example()):
            raise ValueError(f"{item.id}: the no-script answer does not grade as right")

    def grade(self, item: QuizItem, response: str) -> bool:
        return base.grade(item.activity, response) if item.activity is not None else False

    def compare(self, item: QuizItem, response: str, locale: str) -> base.Comparison | None:
        """Feedback that shows, then says. None for kinds that do not draw it."""
        if item.activity is None:
            return None
        return base.compare(item.activity, response, locale)

    def correct_text(self, item: QuizItem, locale: str) -> str:
        if item.activity is None:
            return ""
        return item.activity.describe(item.activity.solution(), locale)

    def response_text(self, item: QuizItem, response: str, locale: str) -> str:
        comparison = self.compare(item, response, locale)
        return comparison.made if comparison else response.strip()

    def board(self, item: QuizItem, locale: str) -> base.Board | None:
        """The board as the question opens."""
        if item.activity is None:
            return None
        return item.activity.board(item.activity.initial(), locale)


# Imported after `Primitive` exists: the number line's adapter subclasses it.
from pensum.items.primitives.number_line import NUMBER_LINE  # noqa: E402

# The registry. One line per primitive; order is the order scripts load in.
PRIMITIVES: dict[str, Primitive] = {
    p.kind: p
    for p in (
        NUMBER_LINE,
        Primitive(
            "counters",
            "partials/primitives/counters.html",
            "primitives/counters.js",
            CountersActivity,
        ),
        Primitive(
            "ten_frame",
            "partials/primitives/ten_frame.html",
            "primitives/ten-frame.js",
            TenFrameActivity,
        ),
        Primitive(
            "base_ten",
            "partials/primitives/base_ten.html",
            "primitives/base-ten.js",
            BaseTenActivity,
        ),
        Primitive("array", "partials/primitives/array.html", "primitives/array.js", ArrayActivity),
        Primitive(
            "balance", "partials/primitives/balance.html", "primitives/balance.js", BalanceActivity
        ),
        # The language primitives.
        Primitive(
            "sound_boxes",
            "partials/primitives/sound_boxes.html",
            "primitives/sound-boxes.js",
            SoundBoxesActivity,
        ),
        Primitive("blend", "partials/primitives/blend.html", "primitives/blend.js", BlendActivity),
        Primitive(
            "word_build",
            "partials/primitives/word_build.html",
            "primitives/word-build.js",
            WordBuildActivity,
        ),
        Primitive(
            "sentence_build",
            "partials/primitives/sentence_build.html",
            "primitives/sentence-build.js",
            SentenceBuildActivity,
        ),
        Primitive(
            "dialogue",
            "partials/primitives/dialogue.html",
            "primitives/dialogue.js",
            DialogueActivity,
        ),
        # The card primitives: the knowledge-and-reasoning boards every subject
        # uses. Their no-script road is a choice between arrangements (`cards.py`).
        Primitive("sort", "partials/primitives/sort.html", "primitives/sort.js", SortActivity),
        Primitive(
            "sequence",
            "partials/primitives/sequence.html",
            "primitives/sequence.js",
            SequenceActivity,
        ),
        Primitive("match", "partials/primitives/match.html", "primitives/match.js", MatchActivity),
        Primitive("label", "partials/primitives/label.html", "primitives/label.js", LabelActivity),
        Primitive(
            "highlight",
            "partials/primitives/highlight.html",
            "primitives/highlight.js",
            HighlightActivity,
        ),
        # The simulations: something runs, and the page shows it.
        Primitive(
            "trials", "partials/primitives/trials.html", "primitives/trials.js", TrialsActivity
        ),
        Primitive(
            "step_code",
            "partials/primitives/step_code.html",
            "primitives/step-code.js",
            StepCodeActivity,
        ),
        Primitive(
            "explore_sim",
            "partials/primitives/explore_sim.html",
            "primitives/explore-sim.js",
            ExploreSimActivity,
        ),
    )
}

# Every `activity:` block an item can carry, told apart by `kind`. Built from
# the registry so a new primitive's config is accepted without editing the
# schema.
_CONFIGS = tuple(p.config for p in PRIMITIVES.values() if p.config is not None)
Activity = Annotated[Union[_CONFIGS], Field(discriminator="kind")]  # noqa: UP007

# The script every activity primitive's own file registers with. Listed apart
# from the primitives because it has to load first.
CORE_SCRIPT = "primitives/core.js"


def primitive_for(item: Any) -> Primitive | None:
    """The primitive an item is answered with, or None for the plain kinds."""
    return PRIMITIVES.get(getattr(item, "type", ""))


def scripts() -> list[str]:
    """Every script a page showing questions should load, core first."""
    return [CORE_SCRIPT] + [p.script for p in PRIMITIVES.values() if p.script]

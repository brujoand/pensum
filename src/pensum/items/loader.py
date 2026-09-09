"""Loading authored quiz items from disk."""

from __future__ import annotations

from functools import cached_property
from pathlib import Path

import yaml

from pensum.domain.models import GoalSet
from pensum.items.coverage import Coverage, coverage
from pensum.items.schema import ItemSet, QuizItem
from pensum.review.store import ReviewLedger

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ITEMS_DIR = REPO_ROOT / "data" / "items"

# What a decision about a quiz item is filed under.
KIND = "item"


class ItemBank:
    """Every authored item, indexed by goal set."""

    def __init__(self, item_sets: list[ItemSet], *, include_unreviewed: bool = False) -> None:
        self._sets = {item_set.goal_set: item_set for item_set in item_sets}
        self._include_unreviewed = include_unreviewed
        self._ledger: ReviewLedger | None = None

    def with_ledger(self, ledger: ReviewLedger | None) -> ItemBank:
        """Consult recorded review decisions from now on.

        Attached after construction rather than passed in: the bank is built in
        a dozen places, most of which have no database, and every one of them
        would otherwise have to name a collaborator it does not use. None -- no
        history configured -- leaves the file's own flag deciding, which is the
        behaviour every instance had before decisions existed.
        """
        self._ledger = ledger
        return self

    def _publishes(self, item: QuizItem) -> bool:
        if self._ledger is None:
            return item.reviewed
        return self._ledger.publishes(KIND, item.id, item.reviewed)

    @classmethod
    def load(cls, items_dir: Path | None = None, *, include_unreviewed: bool = False) -> ItemBank:
        directory = items_dir or DEFAULT_ITEMS_DIR
        item_sets = [
            ItemSet.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
            for path in sorted(directory.glob("*/*.yaml"))
        ]
        return cls(item_sets, include_unreviewed=include_unreviewed)

    @property
    def item_sets(self) -> list[ItemSet]:
        return list(self._sets.values())

    def for_goal_set(self, code: str, *, unreviewed: bool = False) -> list[QuizItem]:
        """Servable items for a goal set.

        Unreviewed items are withheld unless something explicitly asks for them.
        Generation writes them as unreviewed, so this is what keeps a draft
        question from reaching a child on the strength of a merge alone.

        Two things can ask. `include_unreviewed` on the bank is the
        deployment-wide switch, which is what a local review session uses.
        `unreviewed=True` per call is for a request that has established it may
        see them -- an administrator, who needs to read a draft in place before
        deciding whether to mark it reviewed.

        The default is False at every layer. A caller that forgets the argument
        gets the safe answer, which is the only acceptable direction for this
        particular mistake.

        A recorded review decision overrides the file's flag -- see
        `ReviewLedger.publishes` -- so an item approved on the review page is
        served without a release, and one rejected there is withheld even though
        the file still says otherwise.
        """
        item_set = self._sets.get(code)
        if item_set is None:
            return []
        widened = self._include_unreviewed or unreviewed
        return [item for item in item_set.items if widened or self._publishes(item)]

    def has_quiz(self, code: str, *, unreviewed: bool = False) -> bool:
        return bool(self.for_goal_set(code, unreviewed=unreviewed))

    def tested_goals(self, code: str, *, unreviewed: bool = False) -> set[str]:
        """Goal codes a served item actually tests, for the given goal set."""
        return {item.goal for item in self.for_goal_set(code, unreviewed=unreviewed)}

    def coverage(self, goal_set: GoalSet, *, unreviewed: bool = False) -> Coverage:
        """How much of `goal_set` its quiz reaches, goal by goal.

        Follows whatever the caller can see, so an administrator reading drafts
        is shown the coverage those drafts actually produce rather than the
        coverage a pupil would get.
        """
        return coverage(goal_set, self.tested_goals(goal_set.code, unreviewed=unreviewed))

    @cached_property
    def goal_codes(self) -> set[str]:
        """Every goal referenced by an item or excused as not assessable."""
        return {
            code
            for item_set in self._sets.values()
            for code in item_set.goals_covered | item_set.goals_excused
        }

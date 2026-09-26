"""Loading authored quiz items from disk."""

from __future__ import annotations

import random
from collections.abc import Collection
from functools import cached_property
from pathlib import Path

import yaml

from pensum.domain.models import GoalSet
from pensum.items.coverage import Coverage, coverage
from pensum.items.schema import QuizItem
from pensum.items.sets import ItemSet
from pensum.items.template import ItemTemplate
from pensum.review.gate import ReviewGate
from pensum.review.store import ReviewLedger, State

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ITEMS_DIR = REPO_ROOT / "data" / "items"

# What a decision about a quiz item is filed under.
KIND = "item"


class ItemBank:
    """Every authored item, indexed by goal set."""

    def __init__(self, item_sets: list[ItemSet]) -> None:
        self._sets = {item_set.goal_set: item_set for item_set in item_sets}
        self._items = {item.id: item for s in item_sets for item in s.items}
        self._templates = {template.id: template for s in item_sets for template in s.templates}
        self._gate = ReviewGate(KIND)

    def with_ledger(self, ledger: ReviewLedger | None) -> ItemBank:
        """Consult this instance's review decisions from now on.

        Attached after construction rather than passed in: the bank is built in
        a dozen places, most of which serve nothing to anybody, and every one of
        them would otherwise have to name a collaborator it does not use. With
        no ledger nothing is approved, so a bank that was never given one
        serves no pupil anything -- see `pensum.review.gate`.
        """
        self._gate.ledger = ledger
        return self

    def _publishes(self, item: QuizItem) -> bool:
        return self._gate.publishes(item.id, item)

    def _publishes_template(self, template: ItemTemplate) -> bool:
        """Whether a template's questions may be served.

        Decided on the template, never on the instance: a reviewer approves the
        family, because the family is what the domain check proved sound and
        what the review page shows, and an instance id nobody has ever seen is
        not something to record a decision against. The fingerprint is the
        template's own, so changing a range or a sentence returns every
        instance to pending together.
        """
        return self._gate.publishes(template.id, template)

    def review_state(self, content_id: str) -> State:
        """Where one item or template stands on this instance.

        A template instance (`template#3-4`) answers for its template, because
        that is what was decided. An id nothing was authored under is pending,
        which withholds it -- the answer that is safe to be wrong with.
        """
        if content_id in self._items:
            return self._gate.state(content_id, self._items[content_id])
        template = self._templates.get(content_id.split("#", 1)[0])
        if template is not None:
            return self._gate.state(template.id, template)
        return "pending"

    def fingerprint(self, content_id: str) -> str | None:
        """The fingerprint of a hand-written item or a template, if one exists."""
        if content_id in self._items:
            return self._gate.fingerprint(content_id, self._items[content_id])
        if content_id in self._templates:
            return self._gate.fingerprint(content_id, self._templates[content_id])
        return None

    def item(self, content_id: str) -> QuizItem | None:
        """One question by id, whatever its state: a hand-written item, or one
        instance of a template (`template#3-4`). For the review page, which
        lets an administrator answer a question before deciding about it."""
        if content_id in self._items:
            return self._items[content_id]
        template = self._templates.get(content_id.split("#", 1)[0])
        if template is None:
            return None
        return next((i for i in template.instances() if i.id == content_id), None)

    def has_authored(self, code: str) -> bool:
        """Whether anything at all was written for this goal set, approved or not.

        For the page that has to say "questions exist here, and none of them
        has been approved on this site yet" rather than "there are none".
        """
        item_set = self._sets.get(code)
        return item_set is not None and bool(item_set.items or item_set.templates)

    @classmethod
    def load(cls, items_dir: Path | None = None) -> ItemBank:
        directory = items_dir or DEFAULT_ITEMS_DIR
        item_sets = [
            ItemSet.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
            for path in sorted(directory.glob("*/*.yaml"))
        ]
        return cls(item_sets)

    @property
    def item_sets(self) -> list[ItemSet]:
        return list(self._sets.values())

    def for_goal_set(
        self,
        code: str,
        *,
        unreviewed: bool = False,
        seed: int | None = None,
        exclude: Collection[str] = (),
    ) -> list[QuizItem]:
        """Servable items for a goal set.

        Approved items only, unless the caller asks for everything. Approval is
        this instance's, recorded on its review page; nothing in a file can
        make an item servable, so a merge alone never puts a question in front
        of a child.

        `unreviewed=True` is for a request that has established it may see
        everything -- an administrator, who needs to meet a question in place,
        labelled with its state, before deciding about it. The default is False
        at every layer. A caller that forgets the argument gets the safe
        answer, which is the only acceptable direction for this mistake.

        `exclude` names ids this caller has already served. It belongs here
        rather than in a filter the caller applies afterwards, and the
        difference only shows up once templates exist: a template offers one
        instance out of a domain of hundreds, so a caller that draws first and
        filters second discards the whole template whenever its single instance
        happens to be one already asked. Excluding before the draw picks a
        different question instead, and a template only falls silent when the
        run really has seen every question it has.
        """
        item_set = self._sets.get(code)
        if item_set is None:
            return []
        widened = unreviewed
        spent = frozenset(exclude)
        served = [
            item
            for item in item_set.items
            if (widened or self._publishes(item)) and item.id not in spent
        ]

        # A template contributes one question, not its whole domain: a quiz of
        # ten drawn from a bank where one template had supplied two hundred
        # would be that template ten times over. Which one is the caller's
        # choice, and `seed` is how a test or a session asks for the same
        # question twice.
        rng = random.Random(seed)  # noqa: S311 -- quiz variety, not cryptography
        for template in item_set.templates:
            if not (widened or self._publishes_template(template)):
                continue
            fresh = [item for item in template.instances() if item.id not in spent]
            if fresh:
                served.append(rng.choice(fresh))
        return served

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

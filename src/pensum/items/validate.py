"""Validate authored items against the curriculum catalogue.

Runs as a pre-commit hook and in CI, offline. Schema validity is only half of
it: an item can be perfectly well-formed and still reference a competence goal
that no longer exists, which is exactly what a curriculum revision produces.
That failure is silent at runtime -- the item simply never gets selected -- so it
is made loud here instead.

A template is checked harder than an item, and it has to be. `reviewed: true`
on a hand-written item says a human read the sentence a child will see; on a
template it says a human read a *rule* that produces sentences nobody has read.
What closes that gap is enumeration: every question in the domain is built here,
and every one of them has to be a question worth asking. A domain that can
produce a fraction of a sheep, or an answer of nought, fails the build rather
than surprising a ten-year-old.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml
from pydantic import ValidationError

from pensum.catalogue.loader import Catalogue
from pensum.items.loader import DEFAULT_ITEMS_DIR
from pensum.items.sets import ItemSet
from pensum.items.template import ItemTemplate


def validate(items_dir: Path | None = None) -> list[str]:
    """Return a problem per line. Empty means everything checks out."""
    directory = items_dir or DEFAULT_ITEMS_DIR
    catalogue = Catalogue.load()
    problems: list[str] = []
    item_sets: list[ItemSet] = []

    for path in sorted(directory.glob("*/*.yaml")):
        where = path.relative_to(directory.parent)
        try:
            item_sets.append(
                ItemSet.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
            )
        except (ValidationError, yaml.YAMLError) as exc:
            problems.append(f"{where}: {exc}")

    for item_set in item_sets:
        subject = catalogue.subject(item_set.subject)
        if subject is None:
            problems.append(f"{item_set.goal_set}: unknown subject {item_set.subject}")
            continue

        goal_set = subject.goal_set(item_set.goal_set)
        if goal_set is None:
            problems.append(
                f"{item_set.goal_set}: not a goal set of {item_set.subject}; "
                "the curriculum may have been revised"
            )
            continue

        # The check that matters: a renumbered goal orphans its items.
        known = {goal.code for goal in goal_set.goals}
        for item in item_set.items:
            if item.goal not in known:
                problems.append(
                    f"{item.id}: goal {item.goal} is not in {item_set.goal_set}; "
                    "it may have been renumbered by a curriculum revision"
                )
        for template in item_set.templates:
            if template.goal not in known:
                problems.append(
                    f"{template.id}: goal {template.goal} is not in {item_set.goal_set}; "
                    "it may have been renumbered by a curriculum revision"
                )
            problems.extend(_domain_problems(template))

        for excused in item_set.not_assessable:
            if excused.goal not in known:
                problems.append(
                    f"{item_set.goal_set}: not_assessable names {excused.goal}, "
                    "which is not in this goal set"
                )

        # Every goal should be either tested or explicitly excused. Silence
        # about a goal is indistinguishable from forgetting it.
        unaccounted = sorted(known - item_set.goals_covered - item_set.goals_excused)
        if unaccounted:
            problems.append(
                f"{item_set.goal_set}: {len(unaccounted)} goal(s) neither tested nor "
                f"marked not_assessable: {', '.join(unaccounted)}"
            )

    return problems


# The smallest answer worth asking a pupil for. Zero is a legitimate number and
# a terrible generated answer: "how many sauer" answered by "none" reads as a
# trick, and an author who wanted it would say so in `require`.
MIN_ANSWER = 1


def _domain_problems(template: ItemTemplate) -> list[str]:
    """Walk every question a template can ask, and judge each one.

    This is what a template has instead of a human reading its questions. The
    schema already proved each instance is a valid `QuizItem`; what is left is
    whether it is a *sensible* one, and that is arithmetic nobody can eyeball
    across two hundred flocks.
    """
    problems: list[str] = []
    instances = template.instances()

    for item in instances:
        answer = float(item.answer)
        if not answer.is_integer():
            problems.append(
                f"{item.id}: the answer is {answer}, and a question phrased for a whole "
                "number should not produce a fraction"
            )
        elif answer < MIN_ANSWER:
            problems.append(f"{item.id}: the answer is {int(answer)}, which reads as a trick")

    # Two instances that read identically are one question wearing two ids: the
    # pupil meets the same flock twice and the domain is smaller than it looks.
    prompts = [item.prompt.nb for item in instances]
    if len(set(prompts)) != len(prompts):
        repeated = sorted({p for p in prompts if prompts.count(p) > 1})
        problems.append(
            f"{template.id}: {len(repeated)} prompt(s) are produced by more than one "
            "combination, so the domain is smaller than it looks"
        )

    return problems


def main() -> int:
    problems = validate()
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print(f"\n{len(problems)} problem(s) found in authored items.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

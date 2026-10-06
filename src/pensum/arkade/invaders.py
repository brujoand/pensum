"""Invaders: one rule for the round, and targets that match it or do not.

"Shoot the numbers you can divide by 3", "shoot the consonants". Each target is
a yes-or-no item: shooting it says it matches. About half of them do, so
holding fire is never a safe plan.

The answer shown after a wrong call ("9 kan deles på 3") is language, so the
page's own wording is passed in as `describe` rather than written here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from random import Random

from pensum.arkade.items import TARGET_CHOICES, Item, balloon

# (rule, token, matches, rule parameters) -> the sentence that says which it was.
Describe = Callable[[str, str, bool, dict[str, int]], str]

# A target per draw is enough nearly always; this bounds the loop when a pool
# is small, as the vowels are.
MAX_DRAWS = 200

# Even numbers are the only rule here that a skill names on its own.
EVEN_SKILL = "mat.counting.odd-even"

VOWELS = {"nb": "AEIOUYÆØÅ", "nn": "AEIOUYÆØÅ", "en": "AEIOU"}
# English Y is a vowel in some words and a consonant in others, so it is left
# out rather than marked wrong for a pupil who knows that.
CONSONANTS = {
    "nb": "BCDFGHJKLMNPQRSTVWXZ",
    "nn": "BCDFGHJKLMNPQRSTVWXZ",
    "en": "BCDFGHJKLMNPQRSTVWXZ",
}


@dataclass(frozen=True)
class Targets:
    """A round of targets: the rule, as an i18n key and its parameters, and the items."""

    rule: str
    items: list[Item]
    params: dict[str, int] = field(default_factory=dict)


def _target(
    targets: Targets, key: str, token: str, matches: bool, describe: Describe, skill: str | None
) -> Item:
    return balloon(
        f"{key}:{token}",
        "target",
        token,
        true=matches,
        answer=describe(targets.rule, token, matches, targets.params),
        skill=skill,
        choices=TARGET_CHOICES,
    )


def _draw(rng: Random, count: int, matching: list[str], other: list[str]) -> list[tuple[str, bool]]:
    """`count` distinct tokens, about half from `matching`, in a random order."""
    picked: dict[str, bool] = {}
    for _ in range(MAX_DRAWS):
        if len(picked) == count:
            break
        matches = rng.random() < 0.5
        pool = matching if matches else other
        token = rng.choice(pool)
        picked.setdefault(token, matches)
    return list(picked.items())


def number_targets(grade: int, rng: Random, count: int, describe: Describe) -> Targets:
    """Numbers for `grade`: even numbers first, then dividing by ever larger numbers."""
    if grade <= 2:
        top, divisor, rule = 20, 2, "even"
    elif grade == 3:
        top, divisor, rule = 60, rng.choice((2, 5, 10)), "divisible"
    elif grade <= 7:
        top, divisor, rule = 100, rng.choice((3, 4, 5, 6, 9)), "divisible"
    else:
        top, divisor, rule = 150, rng.choice((3, 4, 6, 7, 8, 9, 11, 12)), "divisible"

    numbers = range(1, top + 1)
    matching = [str(n) for n in numbers if n % divisor == 0]
    other = [str(n) for n in numbers if n % divisor != 0]
    skill = EVEN_SKILL if rule == "even" else None
    targets = Targets(rule=rule, items=[], params={} if rule == "even" else {"n": divisor})
    targets.items.extend(
        _target(targets, f"{rule}{divisor}", token, matches, describe, skill)
        for token, matches in _draw(rng, count, matching, other)
    )
    return targets


def letter_targets(language: str, rng: Random, count: int, describe: Describe) -> Targets:
    """Letters of `language`: shoot the consonants, or shoot the vowels."""
    vowels = list(VOWELS.get(language, VOWELS["nb"]))
    consonants = list(CONSONANTS.get(language, CONSONANTS["nb"]))
    rule = rng.choice(("consonants", "vowels"))
    matching, other = (consonants, vowels) if rule == "consonants" else (vowels, consonants)
    targets = Targets(rule=rule, items=[])
    targets.items.extend(
        _target(targets, rule, token, matches, describe, None)
        for token, matches in _draw(rng, count, matching, other)
    )
    return targets

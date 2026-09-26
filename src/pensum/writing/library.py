"""Loading letterforms and prompts from disk.

Same shape as `pensum.items.loader` and `pensum.reading.library`, deliberately:
one YAML file per checkpoint, loaded once at startup, immutable afterwards, and
a prompt no administrator of this instance has approved is withheld from pupils,
exactly as an unapproved quiz item is.

The alphabet sits beside them rather than inside them. It is one file for the
whole application because a letter is not owned by a subject.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from pensum.review.gate import ReviewGate
from pensum.review.store import ReviewLedger, State
from pensum.writing.schema import Alphabet, WritingPrompt, WritingSet

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_WRITING_DIR = REPO_ROOT / "data" / "writing"
ALPHABET_FILE = "alphabet.yaml"

# What a decision about a writing prompt is filed under.
KIND = "writing"


def load_alphabet(writing_dir: Path | None = None) -> Alphabet:
    path = (writing_dir or DEFAULT_WRITING_DIR) / ALPHABET_FILE
    return Alphabet.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


class WritingLibrary:
    """Every authored prompt, indexed by goal set, plus the letterforms."""

    def __init__(
        self,
        writing_sets: list[WritingSet],
        alphabet: Alphabet,
    ) -> None:
        self._sets = {writing_set.goal_set: writing_set for writing_set in writing_sets}
        self._alphabet = alphabet
        self._prompts = {prompt.id: prompt for ws in writing_sets for prompt in ws.prompts}
        self._gate = ReviewGate(KIND)

    def with_ledger(self, ledger: ReviewLedger | None) -> WritingLibrary:
        """Consult recorded review decisions from now on.

        Same contract as `ItemBank.with_ledger`, including that None approves
        nothing.
        """
        self._gate.ledger = ledger
        return self

    def _publishes(self, prompt: WritingPrompt) -> bool:
        return self._gate.publishes(prompt.id, prompt)

    def review_state(self, content_id: str) -> State:
        prompt = self._prompts.get(content_id)
        return self._gate.state(content_id, prompt) if prompt is not None else "pending"

    def fingerprint(self, content_id: str) -> str | None:
        prompt = self._prompts.get(content_id)
        return self._gate.fingerprint(content_id, prompt) if prompt is not None else None

    def has_authored(self, code: str) -> bool:
        writing_set = self._sets.get(code)
        return writing_set is not None and bool(writing_set.prompts)

    @classmethod
    def load(cls, writing_dir: Path | None = None) -> WritingLibrary:
        directory = writing_dir or DEFAULT_WRITING_DIR
        writing_sets = [
            WritingSet.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
            for path in sorted(directory.glob("*/*.yaml"))
        ]
        return cls(writing_sets, load_alphabet(directory))

    @property
    def alphabet(self) -> Alphabet:
        return self._alphabet

    @property
    def writing_sets(self) -> list[WritingSet]:
        return list(self._sets.values())

    def for_goal_set(self, code: str, *, unreviewed: bool = False) -> list[WritingPrompt]:
        """Servable prompts for a goal set.

        Same contract as `ItemBank.for_goal_set`: approved prompts only,
        widened only by a request that has established it may see everything.
        False at every layer, so a forgotten argument fails closed.

        A prompt whose characters the alphabet cannot draw is dropped rather
        than served: the page would otherwise show a blank box and ask a child
        to trace it. The data test is what makes this never fire in practice.

        The alphabet check is not overridable: a letter Pensum cannot draw
        stays undrawable however many humans approve the prompt.
        """
        writing_set = self._sets.get(code)
        if writing_set is None:
            return []
        return [
            prompt
            for prompt in writing_set.prompts
            if (unreviewed or self._publishes(prompt)) and self._alphabet.covers(prompt.text)
        ]

    def has_writing(self, code: str, *, unreviewed: bool = False) -> bool:
        return bool(self.for_goal_set(code, unreviewed=unreviewed))

    def prompt(
        self, goal_set: str, prompt_id: str, *, unreviewed: bool = False
    ) -> WritingPrompt | None:
        return next(
            (p for p in self.for_goal_set(goal_set, unreviewed=unreviewed) if p.id == prompt_id),
            None,
        )

    @property
    def goal_codes(self) -> set[str]:
        """Every goal a prompt claims to exercise, for the orphan check."""
        return {prompt.goal for ws in self._sets.values() for prompt in ws.prompts}

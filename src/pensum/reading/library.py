"""Loading reading passages and speed bands from disk.

Same shape as `pensum.items.loader`, deliberately: one YAML file per checkpoint,
loaded once at startup, immutable afterwards. A passage that has not been read
by an administrator of this instance is withheld from pupils, exactly as an
unapproved quiz item is.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from pensum.reading.schema import NormTable, ReadingNorm, ReadingSet, ReadingText
from pensum.review.gate import ReviewGate
from pensum.review.store import ReviewLedger, State

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_READING_DIR = REPO_ROOT / "data" / "reading"
NORMS_FILE = "norms.yaml"

# What a decision about a reading passage is filed under.
KIND = "reading"


class ReadingLibrary:
    """Every authored passage, indexed by goal set, plus the speed bands."""

    def __init__(
        self,
        reading_sets: list[ReadingSet],
        norms: NormTable,
    ) -> None:
        self._sets = {reading_set.goal_set: reading_set for reading_set in reading_sets}
        self._norms = norms
        self._texts = {text.id: text for rs in reading_sets for text in rs.texts}
        self._gate = ReviewGate(KIND)

    def with_ledger(self, ledger: ReviewLedger | None) -> ReadingLibrary:
        """Consult recorded review decisions from now on.

        Same contract as `ItemBank.with_ledger`, including that None approves
        nothing.
        """
        self._gate.ledger = ledger
        return self

    def _publishes(self, text: ReadingText) -> bool:
        return self._gate.publishes(text.id, text)

    def review_state(self, content_id: str) -> State:
        text = self._texts.get(content_id)
        return self._gate.state(content_id, text) if text is not None else "pending"

    def fingerprint(self, content_id: str) -> str | None:
        text = self._texts.get(content_id)
        return self._gate.fingerprint(content_id, text) if text is not None else None

    def has_authored(self, code: str) -> bool:
        reading_set = self._sets.get(code)
        return reading_set is not None and bool(reading_set.texts)

    @classmethod
    def load(cls, reading_dir: Path | None = None) -> ReadingLibrary:
        directory = reading_dir or DEFAULT_READING_DIR
        reading_sets = [
            ReadingSet.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
            for path in sorted(directory.glob("*/*.yaml"))
        ]
        norms_path = directory / NORMS_FILE
        norms = (
            NormTable.model_validate(yaml.safe_load(norms_path.read_text(encoding="utf-8")))
            if norms_path.exists()
            else NormTable()
        )
        return cls(reading_sets, norms)

    @property
    def norms(self) -> NormTable:
        return self._norms

    @property
    def reading_sets(self) -> list[ReadingSet]:
        return list(self._sets.values())

    def for_goal_set(self, code: str, *, unreviewed: bool = False) -> list[ReadingText]:
        """Servable passages for a goal set.

        Same contract as `ItemBank.for_goal_set`: approved passages only,
        widened only by a request that has established it may see everything.
        False at every layer, so a forgotten argument fails closed.
        """
        reading_set = self._sets.get(code)
        if reading_set is None:
            return []
        return [t for t in reading_set.texts if unreviewed or self._publishes(t)]

    def has_reading(self, code: str, *, unreviewed: bool = False) -> bool:
        return bool(self.for_goal_set(code, unreviewed=unreviewed))

    def text(self, goal_set: str, text_id: str, *, unreviewed: bool = False) -> ReadingText | None:
        return next(
            (t for t in self.for_goal_set(goal_set, unreviewed=unreviewed) if t.id == text_id),
            None,
        )

    def band(self, subject: str, after_year: int) -> ReadingNorm | None:
        return self._norms.band(subject, after_year)

    @property
    def goal_codes(self) -> set[str]:
        """Every goal a passage claims to exercise, for the orphan check."""
        return {text.goal for rs in self._sets.values() for text in rs.texts}

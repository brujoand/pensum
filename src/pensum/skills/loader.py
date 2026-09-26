"""Loading skills files from disk.

A subject with no file is an ordinary state, not an error: skills are authored
subject by subject, and the page that shows them is offered exactly where a file
exists.

Skills are reviewed like every other piece of content: on the instance, by an
administrator. The progression guide is a teacher's page and shows every skill
with its state; the pupil's map shows approved skills only (`approved_file`).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from pensum.review.gate import ReviewGate
from pensum.review.store import ReviewLedger, State
from pensum.skills.schema import Skill, SkillFile

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SKILLS_DIR = REPO_ROOT / "data" / "skills"

# What a decision about a skill is filed under.
KIND = "skill"


def read(path: Path) -> SkillFile:
    """Parse one file. Raises on YAML or schema errors; the validator reports them."""
    return SkillFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


class SkillLibrary:
    """Every subject's skills file, indexed by subject code."""

    def __init__(self, files: list[SkillFile]) -> None:
        self._by_subject = {f.subject: f for f in files}
        self._skills = {skill.id: skill for f in files for skill in f.skills}
        self._gate = ReviewGate(KIND)

    def with_ledger(self, ledger: ReviewLedger | None) -> SkillLibrary:
        """Same contract as `ItemBank.with_ledger`: None approves nothing."""
        self._gate.ledger = ledger
        return self

    def publishes(self, skill: Skill) -> bool:
        return self._gate.publishes(skill.id, skill)

    def review_state(self, content_id: str) -> State:
        skill = self._skills.get(content_id)
        return self._gate.state(content_id, skill) if skill is not None else "pending"

    def fingerprint(self, content_id: str) -> str | None:
        skill = self._skills.get(content_id)
        return self._gate.fingerprint(content_id, skill) if skill is not None else None

    def approved_file(self, subject_code: str) -> SkillFile | None:
        """One subject's file with only the skills approved on this instance.

        What a pupil-facing page reads. The strands stay, so the page keeps the
        file's order; a strand left with no skill is the page's to leave out.
        None where no file exists; a file whose skills are all pending comes
        back with none, which the page says plainly.
        """
        skill_file = self.for_subject(subject_code)
        if skill_file is None:
            return None
        approved = tuple(skill for skill in skill_file.skills if self.publishes(skill))
        return skill_file.model_copy(update={"skills": approved})

    @classmethod
    def load(cls, skills_dir: Path | None = None) -> SkillLibrary:
        directory = skills_dir or DEFAULT_SKILLS_DIR
        return cls([read(path) for path in sorted(directory.glob("*.yaml"))])

    def for_subject(self, subject_code: str) -> SkillFile | None:
        return self._by_subject.get(subject_code)

    def has(self, subject_code: str) -> bool:
        return subject_code in self._by_subject

    @property
    def subjects(self) -> list[str]:
        return sorted(self._by_subject)

"""Loading skills files from disk.

A subject with no file is an ordinary state, not an error: skills are authored
subject by subject, and the page that shows them is offered exactly where a file
exists.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from pensum.skills.schema import SkillFile

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SKILLS_DIR = REPO_ROOT / "data" / "skills"


def read(path: Path) -> SkillFile:
    """Parse one file. Raises on YAML or schema errors; the validator reports them."""
    return SkillFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


class SkillLibrary:
    """Every subject's skills file, indexed by subject code."""

    def __init__(self, files: list[SkillFile]) -> None:
        self._by_subject = {f.subject: f for f in files}

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

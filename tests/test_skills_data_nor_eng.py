"""Stop-gap checks on the committed norsk and engelsk skill files.

The skill validator is being written in a separate change and is not on main
yet, so these check the same contract directly against the YAML and the
ingested curriculum JSON, with nothing from `pensum` imported. Once the real
validator lands and runs over `data/skills/`, this file duplicates it and can
be deleted.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
SUBJECTS = ["NOR01-08", "ENG01-06"]

# A pupil-facing line is read aloud to a seven-year-old; past this length it
# stops being one thought.
MAX_I_CAN_WORDS = 12


def _load(code: str) -> tuple[dict, dict[str, int]]:
    skills = yaml.safe_load((ROOT / "data/skills" / f"{code}.yaml").read_text(encoding="utf-8"))
    curriculum = json.loads(
        (ROOT / "data/curriculum/subjects" / f"{code}.json").read_text(encoding="utf-8")
    )
    goal_year = {g["code"]: gs["after_year"] for gs in curriculum["goal_sets"] for g in gs["goals"]}
    return skills, goal_year


@pytest.mark.parametrize("code", SUBJECTS)
def test_every_goal_is_covered(code: str) -> None:
    doc, goal_year = _load(code)
    referenced = {ref for skill in doc["skills"] for ref in skill["refs"]}
    assert set(goal_year) - referenced == set()


@pytest.mark.parametrize("code", SUBJECTS)
def test_refs_exist_and_match_checkpoint(code: str) -> None:
    doc, goal_year = _load(code)
    wrong = [
        (skill["id"], ref)
        for skill in doc["skills"]
        for ref in skill["refs"]
        if goal_year.get(ref) != skill["checkpoint"]
    ]
    assert wrong == []
    assert all(skill["refs"] for skill in doc["skills"])


@pytest.mark.parametrize("code", SUBJECTS)
def test_ids_strands_and_needs(code: str) -> None:
    doc, _ = _load(code)
    ids = [skill["id"] for skill in doc["skills"]]
    strands = {strand["id"] for strand in doc["strands"]}
    assert len(ids) == len(set(ids))
    assert {skill["strand"] for skill in doc["skills"]} <= strands
    graph = {skill["id"]: skill["needs"] for skill in doc["skills"]}
    assert {n for needs in graph.values() for n in needs} <= set(ids)

    # Acyclic: repeatedly remove skills whose needs are all removed already.
    done: set[str] = set()
    while len(done) < len(graph):
        ready = {sid for sid, needs in graph.items() if sid not in done and set(needs) <= done}
        assert ready, f"cycle among {sorted(set(graph) - done)}"
        done |= ready


@pytest.mark.parametrize("code", SUBJECTS)
def test_i_can_is_short_and_bilingual(code: str) -> None:
    doc, _ = _load(code)
    for skill in doc["skills"]:
        for field in ("i_can", "teacher"):
            assert set(skill[field]) == {"nob", "eng"}, skill["id"]
            assert all(text.strip() for text in skill[field].values()), skill["id"]
        for text in skill["i_can"].values():
            assert len(text.split()) <= MAX_I_CAN_WORDS, (skill["id"], text)


@pytest.mark.parametrize("code", SUBJECTS)
def test_stages_ordered_and_unreviewed(code: str) -> None:
    order = ["concrete", "pictorial", "abstract"]
    doc, _ = _load(code)
    for skill in doc["skills"]:
        stages = skill["stages"]
        assert stages and stages == sorted(set(stages), key=order.index), skill["id"]
        assert skill["reviewed"] is False, skill["id"]

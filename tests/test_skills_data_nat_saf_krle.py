"""Assertions about the committed naturfag, samfunnsfag and KRLE skills.

The skills validator is written in a separate change and is not on main yet, so
these files would otherwise land with nothing checking them. This is a
self-contained stand-in for the contract's five rules, read straight from
`data/curriculum/subjects/`. It may be removed once the validator lands and
covers these subjects.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SUBJECTS = {"NAT01-05": "nat", "SAF01-05": "saf", "RLE01-04": "krle"}
STAGES = ["concrete", "pictorial", "abstract"]


def load(code: str) -> tuple[dict, dict[str, int]]:
    doc = yaml.safe_load((ROOT / "data" / "skills" / f"{code}.yaml").read_text(encoding="utf-8"))
    curriculum = json.loads(
        (ROOT / "data" / "curriculum" / "subjects" / f"{code}.json").read_text(encoding="utf-8")
    )
    goal_year = {g["code"]: gs["after_year"] for gs in curriculum["goal_sets"] for g in gs["goals"]}
    return doc, goal_year


@pytest.mark.parametrize("code", SUBJECTS)
def test_every_goal_is_covered_by_a_skill(code: str) -> None:
    doc, goal_year = load(code)
    covered = {ref for skill in doc["skills"] for ref in skill["refs"]}
    assert sorted(set(goal_year) - covered) == []


@pytest.mark.parametrize("code", SUBJECTS)
def test_refs_exist_and_match_the_checkpoint(code: str) -> None:
    doc, goal_year = load(code)
    wrong = [
        (skill["id"], ref)
        for skill in doc["skills"]
        for ref in skill["refs"]
        if goal_year.get(ref) != skill["checkpoint"]
    ]
    assert all(skill["refs"] for skill in doc["skills"])
    assert wrong == []


@pytest.mark.parametrize("code", SUBJECTS)
def test_needs_exist_and_form_a_dag(code: str) -> None:
    doc, _ = load(code)
    needs = {skill["id"]: skill["needs"] for skill in doc["skills"]}
    assert [(s, n) for s, ns in needs.items() for n in ns if n not in needs] == []

    done: set[str] = set()

    def visit(node: str, path: tuple[str, ...]) -> None:
        assert node not in path, f"cycle: {' -> '.join((*path, node))}"
        if node in done:
            return
        for dep in needs[node]:
            visit(dep, (*path, node))
        done.add(node)

    for node in needs:
        visit(node, ())


@pytest.mark.parametrize("code", SUBJECTS)
def test_i_can_is_at_most_twelve_words(code: str) -> None:
    doc, _ = load(code)
    long = [
        (skill["id"], lang)
        for skill in doc["skills"]
        for lang, text in skill["i_can"].items()
        if len(text.split()) > 12
    ]
    assert long == []


@pytest.mark.parametrize("code", SUBJECTS)
def test_ids_strands_stages_and_text_are_well_formed(code: str) -> None:
    doc, _ = load(code)
    assert doc["subject"] == code
    strands = [strand["id"] for strand in doc["strands"]]
    ids = [skill["id"] for skill in doc["skills"]]
    assert len(set(strands)) == len(strands)
    assert len(set(ids)) == len(ids)

    texts = [strand["title"] for strand in doc["strands"]]
    for skill in doc["skills"]:
        prefix, strand, _slug = skill["id"].split(".")
        assert (prefix, strand) == (SUBJECTS[code], skill["strand"]), skill["id"]
        assert skill["strand"] in strands, skill["id"]
        stages = skill["stages"]
        assert stages and stages == [s for s in STAGES if s in stages], skill["id"]
        assert skill["reviewed"] is False, skill["id"]
        texts += [skill["i_can"], skill["teacher"]]
    for text in texts:
        assert set(text) == {"nob", "eng"} and all(v.strip() for v in text.values()), text

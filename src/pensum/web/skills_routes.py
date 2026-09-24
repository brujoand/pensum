"""The progression guide: a subject's skills, strands down and checkpoints across.

The first of the teacher views in `docs/design/architecture.md`, and the one
that needs nothing but data: no accounts, no evidence, no JavaScript. It is
meant to be read and printed.

Two voices share the page and must never be confused. The skills are Pensum's
reading of the curriculum; the goals they cite are Udir's wording, quoted
verbatim beside them under the same `.curriculum` treatment the subject page
uses. The page says which is which before it shows either.

Unreviewed skills are shown, and labelled. Nothing a pupil sees depends on them
yet, and a teacher judging a draft needs to be able to read it.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from pensum.domain.models import Goal, Subject
from pensum.skills.loader import SkillLibrary
from pensum.skills.schema import Skill, SkillFile, Strand
from pensum.web.rendering import context, templates, validate_locale

router = APIRouter()


@dataclass(frozen=True)
class Cell:
    """The skills of one strand at one checkpoint, with the goals they cite."""

    checkpoint: int
    skills: tuple[tuple[Skill, tuple[Goal, ...]], ...]


@dataclass(frozen=True)
class Row:
    strand: Strand
    cells: tuple[Cell, ...]


def _skills(request: Request) -> SkillLibrary:
    return request.app.state.skills


def grid(skill_file: SkillFile, subject: Subject) -> tuple[list[int], list[Row]]:
    """Checkpoints across, strands down, in the file's own strand order.

    The columns are every checkpoint the curriculum has, not only the ones with
    skills: an empty cell is information (this strand has not started yet, or
    has ended), and a column that appears and disappears between subjects would
    hide it.
    """
    goals = {goal.code: goal for goal_set in subject.goal_sets for goal in goal_set.goals}
    checkpoints = sorted({goal_set.after_year for goal_set in subject.goal_sets})
    rows = []
    for strand in skill_file.strands:
        cells = []
        for checkpoint in checkpoints:
            skills = tuple(
                (skill, tuple(goals[ref] for ref in skill.refs if ref in goals))
                for skill in skill_file.skills
                if skill.strand == strand.id and skill.checkpoint == checkpoint
            )
            cells.append(Cell(checkpoint=checkpoint, skills=skills))
        rows.append(Row(strand=strand, cells=tuple(cells)))
    return checkpoints, rows


@router.get("/{locale}/progresjon/{subject_code}", response_class=HTMLResponse)
async def progression_page(request: Request, locale: str, subject_code: str) -> HTMLResponse:
    validate_locale(locale)
    subject = request.app.state.catalogue.subject(subject_code)
    if subject is None:
        raise HTTPException(status_code=404, detail="unknown subject")
    skill_file = _skills(request).for_subject(subject.code)
    if skill_file is None:
        raise HTTPException(status_code=404, detail="no skills authored for this subject")

    checkpoints, rows = grid(skill_file, subject)
    return templates.TemplateResponse(
        request,
        "pages/progression.html",
        context(
            request,
            locale,
            subject=subject,
            checkpoints=checkpoints,
            rows=rows,
            skill_count=len(skill_file.skills),
            draft_count=sum(1 for skill in skill_file.skills if not skill.reviewed),
        ),
    )

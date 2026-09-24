"""The pupil's map and the teacher's class grid: two readings of the same evidence.

The map is for the pupil, and shows only their own skills growing: seed, sprout,
plant, flower. It never shrinks (it shows `Mastery.shown`), it carries no
number, no percentage and nothing about anybody else. That is principles 4 and
8 and the gamification table in `docs/design/principles.md`, and the template
is built so there is nothing on it to compare.

The grid is for an adult in the admin group, and shows the truth: every pupil
on the roster against one strand's skills, each cell the state the evidence
supports now (`Mastery.current`), the furthest representation stage reached,
and whether the skill has slipped since it was secure. The cell a teacher wants
most -- practising, concrete only -- is marked.

Sensitive skills are on the map without a glyph and absent from the grid. So
are skills practised off screen (`assessable: false`): no quiz can grow them,
and an empty spot that can never fill is a promise the page cannot keep.

Both pages exist whatever the configuration. Without a database, or without
sign-in, they say plainly that nothing is stored and so there is nothing to
grow -- rather than 404ing, which would read as a broken link.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from pensum.domain.models import Subject
from pensum.mastery.rules import DEFAULT_RULES, NOT_STARTED, Mastery, MasteryRules, State, assess
from pensum.scores.evidence import Evidence
from pensum.skills.schema import Skill, SkillFile, Strand
from pensum.web.deps import current_user, get_evidence, get_store, require_admin
from pensum.web.rendering import context, templates, validate_locale

router = APIRouter(include_in_schema=False)

# Every state, in order, for the legend on the map.
GROWTH = tuple(State)


def _rules(request: Request) -> MasteryRules:
    return getattr(request.app.state, "mastery_rules", DEFAULT_RULES)


def _skill_file(request: Request, subject_code: str) -> tuple[Subject, SkillFile]:
    subject = request.app.state.catalogue.subject(subject_code)
    if subject is None:
        raise HTTPException(status_code=404, detail="unknown subject")
    skill_file = request.app.state.skills.for_subject(subject.code)
    if skill_file is None:
        raise HTTPException(status_code=404, detail="no skills authored for this subject")
    return subject, skill_file


def grows(skill: Skill) -> bool:
    """Whether a skill can have a glyph: assessable on screen, and not sensitive."""
    return skill.assessable and not skill.sensitive


# The pupil's map ------------------------------------------------------------


@dataclass(frozen=True)
class Spot:
    """One skill on the map. `state` is None where nothing grows by design."""

    skill: Skill
    state: State | None


@dataclass(frozen=True)
class MapStrand:
    strand: Strand
    spots: tuple[Spot, ...]


def checkpoints(skill_file: SkillFile) -> list[int]:
    return sorted({skill.checkpoint for skill in skill_file.skills})


def default_checkpoint(skill_file: SkillFile, evidence: Mapping[str, Sequence[Evidence]]) -> int:
    """Where the map opens: the checkpoint of the skill last practised, else the first.

    Opening on what the pupil was just doing is the least surprising page; the
    first checkpoint is right for a pupil with nothing recorded yet.
    """
    latest = max(
        ((rows[-1].recorded_at, skill_id) for skill_id, rows in evidence.items() if rows),
        default=None,
    )
    skill = skill_file.skill(latest[1]) if latest else None
    return skill.checkpoint if skill else checkpoints(skill_file)[0]


def pupil_map(
    skill_file: SkillFile,
    checkpoint: int,
    evidence: Mapping[str, Sequence[Evidence]],
    rules: MasteryRules = DEFAULT_RULES,
) -> list[MapStrand]:
    """Strands in file order, each with its skills at one checkpoint.

    Strands with no skill at the checkpoint are left out: a strand heading over
    nothing is a gap the pupil can do nothing about.
    """
    strands = []
    for strand in skill_file.strands:
        spots = tuple(
            Spot(
                skill=skill,
                state=assess(evidence.get(skill.id, ()), skill, rules).shown
                if grows(skill)
                else None,
            )
            for skill in skill_file.skills
            if skill.strand == strand.id and skill.checkpoint == checkpoint
        )
        if spots:
            strands.append(MapStrand(strand=strand, spots=spots))
    return strands


@router.get("/{locale}/kart/{subject_code}", response_class=HTMLResponse)
async def map_page(
    request: Request, locale: str, subject_code: str, trinn: int | None = None
) -> HTMLResponse:
    validate_locale(locale)
    subject, skill_file = _skill_file(request, subject_code)
    store = get_evidence(request)
    user = current_user(request)

    extra: dict[str, object] = {"subject": subject, "recording": store is not None}
    if store is not None and user is not None:
        evidence = {
            skill_id: rows
            for skill_id, rows in store.for_pupil(user.sub).items()
            if skill_file.skill(skill_id) is not None
        }
        available = checkpoints(skill_file)
        chosen = trinn if trinn in available else default_checkpoint(skill_file, evidence)
        extra |= {
            "checkpoints": available,
            "checkpoint": chosen,
            "strands": pupil_map(skill_file, chosen, evidence, _rules(request)),
            "legend": GROWTH,
        }

    return templates.TemplateResponse(
        request, "pages/growth_map.html", context(request, locale, **extra)
    )


# The class grid -------------------------------------------------------------


def skills_on(skill_file: SkillFile, strand_id: str) -> list[Skill]:
    """The grid's columns: a strand's skills that can grow, in checkpoint order."""
    return sorted(
        (s for s in skill_file.skills if s.strand == strand_id and grows(s)),
        key=lambda s: s.checkpoint,
    )


@dataclass(frozen=True)
class GridRow:
    name: str
    sub: str
    cells: tuple[Mastery, ...]


def class_grid(
    skill_file: SkillFile,
    strand_id: str,
    pupils: Sequence[tuple[str, str]],
    evidence: Mapping[str, Mapping[str, Sequence[Evidence]]],
    rules: MasteryRules = DEFAULT_RULES,
) -> tuple[list[Skill], list[GridRow]]:
    """Pupils down, the strand's skills across in checkpoint order.

    `pupils` is (sub, name) pairs, in the roster's order. Every pupil gets a row
    whether or not they have touched this strand: a row of "not started" is
    exactly what a teacher looking for who needs this strand wants to see.
    """
    skills = skills_on(skill_file, strand_id)
    rows = []
    for sub, name in pupils:
        theirs = evidence.get(sub, {})
        cells = tuple(
            assess(theirs[skill.id], skill, rules) if skill.id in theirs else NOT_STARTED
            for skill in skills
        )
        rows.append(GridRow(name=name, sub=sub, cells=cells))
    return skills, rows


@router.get("/{locale}/admin/klasse/{subject_code}", response_class=HTMLResponse)
async def class_page(
    request: Request, locale: str, subject_code: str, strand: str | None = None
) -> HTMLResponse:
    validate_locale(locale)
    require_admin(request)
    subject, skill_file = _skill_file(request, subject_code)

    # Strands with nothing that can grow (all sensitive, or all off screen)
    # have no grid to show and are not offered.
    strands = [s for s in skill_file.strands if skills_on(skill_file, s.id)]
    chosen = next((s for s in strands if s.id == strand), strands[0] if strands else None)

    store = get_evidence(request)
    attempts = get_store(request)
    extra: dict[str, object] = {
        "subject": subject,
        "recording": store is not None,
        "strands": strands,
        "strand": chosen,
    }
    if store is not None and attempts is not None and chosen is not None:
        pupils = [(user.sub, user.name) for user in attempts.users()]
        skills, rows = class_grid(
            skill_file,
            chosen.id,
            pupils,
            store.for_skills([s.id for s in skills_on(skill_file, chosen.id)]),
            _rules(request),
        )
        extra |= {"skills": skills, "rows": rows}

    return templates.TemplateResponse(
        request, "pages/admin_class.html", context(request, locale, **extra)
    )

"""Printable missions, the cards they use, and a teacher's list of them.

A mission page is made to leave the screen: large type, a checklist, the card
beneath it, one A4 page when printed. A pupil may also tick the steps in the
browser. The ticks are ordinary checkboxes, so they work with no script at all;
`missions.js` only remembers them in this browser's localStorage, and nothing
on these pages posts, fetches or stores anything on the server.

Confirmation by a teacher is evidence, and evidence belongs to the mastery
layer. These pages say who confirms a mission; they do not record that anyone
did.

Unreviewed missions are shown, and labelled, as unreviewed skills are on the
progression guide: they are teacher-handed paper, and a teacher judging a draft
needs to be able to read and print it.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from pensum.missions.cards import CARDS
from pensum.missions.loader import MissionLibrary
from pensum.missions.schema import Mission
from pensum.web.rendering import context, templates, validate_locale

router = APIRouter()


def library(request: Request) -> MissionLibrary:
    """The missions, loaded on first use and kept on the app.

    Loaded here rather than in the app's lifespan so that this router is the
    only place that knows missions exist; a test puts its own library on
    `app.state.missions` before the first request.
    """
    missions = getattr(request.app.state, "missions", None)
    if missions is None:
        missions = MissionLibrary.load()
        request.app.state.missions = missions
    return missions


def missions_by_skill(request: Request, subject_code: str) -> dict[str, tuple[Mission, ...]]:
    """For the progression guide: each off-screen skill's missions."""
    return library(request).by_skill(subject_code)


@router.get("/{locale}/progresjon/{subject_code}/oppdrag", response_class=HTMLResponse)
async def mission_list(request: Request, locale: str, subject_code: str) -> HTMLResponse:
    """Every off-screen skill of a subject, with its missions and cards."""
    validate_locale(locale)
    subject = request.app.state.catalogue.subject(subject_code)
    if subject is None:
        raise HTTPException(status_code=404, detail="unknown subject")
    skill_file = request.app.state.skills.for_subject(subject.code)
    mission_file = library(request).for_subject(subject.code)
    if skill_file is None or mission_file is None:
        raise HTTPException(status_code=404, detail="no missions authored for this subject")

    by_skill = library(request).by_skill(subject.code)
    # Every off-screen skill, missions or not: a skill with none is a gap a
    # teacher should see rather than a row that silently is not there.
    rows = [
        (skill, by_skill.get(skill.id, ()))
        for skill in sorted(skill_file.skills, key=lambda s: s.checkpoint)
        if not skill.assessable
    ]
    used = [kind for kind in CARDS if any(m.card == kind for m in mission_file.missions)]
    return templates.TemplateResponse(
        request,
        "pages/missions.html",
        context(
            request,
            locale,
            subject=subject,
            rows=rows,
            cards=used,
            mission_count=len(mission_file.missions),
            draft_count=sum(1 for m in mission_file.missions if not m.reviewed),
        ),
    )


@router.get("/{locale}/oppdrag/kort/{kind}", response_class=HTMLResponse)
async def card_page(request: Request, locale: str, kind: str) -> HTMLResponse:
    """One card on its own, to print and keep on the desk."""
    validate_locale(locale)
    card = CARDS.get(kind)
    if card is None:
        raise HTTPException(status_code=404, detail="unknown card")
    return templates.TemplateResponse(
        request, "pages/mission_card.html", context(request, locale, card=card, question=None)
    )


@router.get("/{locale}/oppdrag/{mission_id}", response_class=HTMLResponse)
async def mission_page(request: Request, locale: str, mission_id: str) -> HTMLResponse:
    validate_locale(locale)
    found = library(request).mission(mission_id)
    if found is None:
        raise HTTPException(status_code=404, detail="unknown mission")
    subject_code, mission = found
    subject = request.app.state.catalogue.subject(subject_code)
    skill_file = request.app.state.skills.for_subject(subject_code)
    skill = skill_file.skill(mission.skill) if skill_file is not None else None
    if subject is None or skill is None:
        # The validator refuses both; this is a library loaded without it.
        raise HTTPException(status_code=404, detail="mission has no skill")
    return templates.TemplateResponse(
        request,
        "pages/mission.html",
        context(
            request,
            locale,
            subject=subject,
            mission=mission,
            skill=skill,
            card=CARDS[mission.card] if mission.card else None,
            question=mission.question,
        ),
    )

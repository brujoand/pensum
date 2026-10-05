"""Arkade: the hub, the timer setting, and the balloon game.

The rules are `docs/design/arkade.md`. Arkade is reached only from its own
links, and every exercise rule outside it is unchanged. Behind the same
sign-in gate as the exercises, so a pupil arrives here with a year.

A round is built when the game page is opened and played in the browser. The
page sends back which balloon was popped for each item, or nothing where time
ran out, and the server marks that against its own copy of the round.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Body, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from pensum.arkade.arithmetic import statement_items
from pensum.arkade.items import Item
from pensum.arkade.rounds import Marked, Round, RoundStore, mark
from pensum.arkade.spelling import spoken_word_items
from pensum.domain.grades import FIRST_GRADE, LAST_GRADE, checkpoint_for
from pensum.scores.evidence import Evidence
from pensum.scores.store import attempt_key
from pensum.scores.xp import Award
from pensum.scores.xp import for_run as xp_for_run
from pensum.web.deps import (
    current_user,
    get_evidence,
    get_profiles,
    get_xp,
    pupil_grade,
    sees_unreviewed,
)
from pensum.web.rendering import context, templates, validate_locale

router = APIRouter()

# Rule 6: a fixed length, shown before the round starts.
ROUND_LENGTH = 8
# Fewer spelling items than this and there is not a round to play: the
# checkpoint's passages are too few, or not yet approved on this instance.
MIN_ROUND = 4
# Two balloons, side by side: one true and one false, or two spellings. More
# than two did not fit a phone in a row, and stacked balloons read as a list.
BALLOONS = 2
# How long a balloon grows before it pops, with the timer on.
BALLOON_SECONDS = 60
# The most picks a finished round can send. A round has ROUND_LENGTH; this only
# bounds what a malformed request can make the server read.
MAX_PICKS = 64

# The balloon games, by the slug in their address: the subject, and whether the
# items are spoken words or arithmetic statements.
GAMES: dict[str, tuple[str, str]] = {
    "matte": ("MAT01-06", "statements"),
    "norsk": ("NOR01-08", "spelling"),
    "engelsk": ("ENG01-06", "spelling"),
}


def _rounds(request: Request) -> RoundStore:
    return request.app.state.arkade_rounds


def _grade(request: Request) -> int | None:
    """The pupil's year, or the one picked on the hub where nobody is signed in."""
    known = pupil_grade(request)
    if known is not None:
        return known
    raw = request.query_params.get("trinn", "")
    if raw.isdigit() and FIRST_GRADE <= int(raw) <= LAST_GRADE:
        return int(raw)
    return None


def _timer_on(request: Request) -> bool:
    """The pupil's stored choice, or the hub's link where there is nowhere to store one."""
    profiles = get_profiles(request)
    user = current_user(request)
    if profiles is not None and user is not None:
        return profiles.timer_on(user.sub)
    return request.query_params.get("tidtaker") != "av"


def _rng() -> random.Random:
    return random.Random()  # noqa: S311 -- variety between rounds, not cryptography


def _items(request: Request, game: str, grade: int) -> list[Item]:
    subject_code, kind = GAMES[game]
    if kind == "statements":
        return statement_items(grade, _rng(), ROUND_LENGTH, BALLOONS)

    subject = request.app.state.catalogue.subject(subject_code)
    checkpoint = checkpoint_for(subject, grade) if subject is not None else None
    if checkpoint is None:
        return []
    texts = request.app.state.reading.for_goal_set(
        checkpoint.goal_set.code, unreviewed=sees_unreviewed(request)
    )
    if not texts:
        return []
    lexicon = request.app.state.listening.lexicon(texts[0].language)
    return spoken_word_items(texts, lexicon, checkpoint.goal_set.after_year, _rng(), ROUND_LENGTH)


@router.get("/{locale}/arkade", response_class=HTMLResponse)
async def hub(request: Request, locale: str) -> HTMLResponse:
    validate_locale(locale)
    profiles = get_profiles(request)
    return templates.TemplateResponse(
        request,
        "pages/arkade.html",
        context(
            request,
            locale,
            grade=_grade(request),
            grades=range(FIRST_GRADE, LAST_GRADE + 1),
            games=list(GAMES),
            timer_on=_timer_on(request),
            timer_stored=profiles is not None and current_user(request) is not None,
            round_length=ROUND_LENGTH,
        ),
    )


@router.post("/{locale}/arkade/tidtaker")
async def save_timer(
    request: Request, locale: str, timer: Annotated[str, Form()] = "av"
) -> RedirectResponse:
    validate_locale(locale)
    profiles = get_profiles(request)
    user = current_user(request)
    if profiles is None or user is None:
        raise HTTPException(status_code=404, detail="nowhere to keep the setting")
    profiles.set_timer(user.sub, timer == "på")
    return RedirectResponse(f"/{locale}/arkade", status_code=303)


@router.get("/{locale}/arkade/ballonger/{game}", response_class=HTMLResponse)
async def balloons(request: Request, locale: str, game: str) -> Response:
    validate_locale(locale)
    if game not in GAMES:
        raise HTTPException(status_code=404, detail="no such game")
    grade = _grade(request)
    if grade is None:
        return RedirectResponse(f"/{locale}/arkade", status_code=303)

    items = _items(request, game, grade)
    timed = _timer_on(request)
    user = current_user(request)
    played = None
    if len(items) >= MIN_ROUND:
        played = _rounds(request).create(
            game,
            GAMES[game][0],
            items,
            timed=timed,
            now=datetime.now(UTC),
            user_sub=user.sub if user else None,
        )
    return templates.TemplateResponse(
        request,
        "pages/balloons.html",
        context(
            request,
            locale,
            game=game,
            grade=grade,
            played=played,
            payload=_payload(played) if played else None,
            timed=timed,
            balloon_seconds=BALLOON_SECONDS,
        ),
    )


def _payload(played: Round) -> dict[str, object]:
    """What the page plays. It includes which balloon is right: the page says so
    the moment one is popped, and the server marks the picks again regardless."""
    return {
        "round": played.id,
        "timed": played.timed,
        "items": [
            {
                "rule": item.rule,
                "candidates": list(item.candidates),
                "matches": sorted(item.matches),
                "answer": item.answer,
                "spoken": item.spoken,
                "language": item.language,
            }
            for item in played.items
        ],
    }


@router.post("/{locale}/arkade/runde/{round_id}", response_class=HTMLResponse)
async def finish(
    request: Request,
    locale: str,
    round_id: str,
    picks: Annotated[list[int | None], Body(embed=True, max_length=MAX_PICKS)],
) -> HTMLResponse:
    validate_locale(locale)
    user = current_user(request)
    now = datetime.now(UTC)
    played = _rounds(request).finish(round_id, user.sub if user else None, now)
    if played is None:
        raise HTTPException(status_code=404, detail="no such round")

    marked = mark(played, picks)
    earned = _record(request, played, marked, now)
    ledger = get_xp(request)
    return templates.TemplateResponse(
        request,
        "partials/arkade_result.html",
        context(
            request,
            locale,
            game=played.game,
            correct=sum(1 for m in marked if m.correct),
            total=len(marked),
            xp_earned=earned,
            xp_total=ledger.total(played.user_sub) if ledger and played.user_sub else None,
        ),
    )


def _record(request: Request, played: Round, marked: list[Marked], now: datetime) -> int:
    """XP and evidence for a finished round, for a signed-in pupil. Returns the XP earned.

    Time running out is neither: it earns nothing and is not written as
    evidence (rule 4). An item on a sensitive skill earns nothing (rule 9).
    """
    if played.user_sub is None:
        return 0
    skill_file = request.app.state.skills.for_subject(played.subject)

    def sensitive(item: Item) -> bool:
        if skill_file is None or item.skill is None:
            return False
        named = skill_file.skill(item.skill)
        return named is not None and named.sensitive

    key = attempt_key(played.id)
    earned = 0
    ledger = get_xp(request)
    if ledger is not None:
        earned = xp_for_run((m.correct is True, sensitive(m.item)) for m in marked)
        ledger.record(
            Award(
                user_sub=played.user_sub,
                source="arkade",
                subject=played.subject,
                ref=key,
                amount=earned,
                recorded_at=now,
            )
        )

    evidence = get_evidence(request)
    if evidence is not None:
        evidence.record(
            Evidence(
                attempt=key,
                user_sub=played.user_sub,
                skill=m.item.skill,
                item=m.item.id,
                stage=None,
                correct=m.correct,
                hints=0,
                recorded_at=now,
            )
            for m in marked
            if m.item.skill is not None and m.correct is not None
        )
    return earned

"""The "which year are you in" page, shown once, at a pupil's first exercise.

`require_pupil` sends a signed-in pupil here when Pensum has no year for them,
and the answer sends them back to where they were going. The same page is how
they correct a wrong answer later, so it shows what they said last time.

Only where there is somewhere to keep the answer: a signed-in pupil and a
database. Anywhere else the page does not exist.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from pensum.auth.models import User
from pensum.domain.grades import FIRST_GRADE, LAST_GRADE
from pensum.scores.profile import ProfileStore
from pensum.web.deps import SignInRequired, current_user, get_profiles, safe_next
from pensum.web.rendering import context, templates, validate_locale

router = APIRouter()


def _pupil(request: Request) -> tuple[User, ProfileStore]:
    profiles = get_profiles(request)
    if profiles is None:
        raise HTTPException(status_code=404, detail="nowhere to keep a year")
    user = current_user(request)
    if user is None:
        raise SignInRequired(request.url.path)
    return user, profiles


@router.get("/{locale}/trinn", response_class=HTMLResponse)
async def year_page(request: Request, locale: str) -> HTMLResponse:
    validate_locale(locale)
    user, profiles = _pupil(request)
    return templates.TemplateResponse(
        request,
        "pages/year.html",
        context(
            request,
            locale,
            grades=range(FIRST_GRADE, LAST_GRADE + 1),
            current=profiles.grade(user.sub, datetime.now(UTC)),
            back=safe_next(request.query_params.get("next"), ""),
        ),
    )


@router.post("/{locale}/trinn")
async def save_year(
    request: Request,
    locale: str,
    grade: Annotated[int, Form()],
    next: Annotated[str | None, Form()] = None,  # noqa: A002 -- the form field's name
) -> RedirectResponse:
    validate_locale(locale)
    user, profiles = _pupil(request)
    if not FIRST_GRADE <= grade <= LAST_GRADE:
        raise HTTPException(status_code=422, detail="grade outside grunnskole")
    profiles.set_grade(user.sub, grade, datetime.now(UTC))
    # 303, so a reload of the page it lands on does not post the form again.
    return RedirectResponse(safe_next(next, f"/{locale}/klasse/{grade}"), status_code=303)

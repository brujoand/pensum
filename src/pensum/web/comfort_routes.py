"""The settings page: how the site moves, how big it is, whether it speaks.

A plain form that posts and redirects, so it works with JavaScript off -- the
setting most likely to be wanted by someone whose browser runs no scripts is
the one that makes pages quieter, and it must not depend on a script to be
turned on.

The wording never names a diagnosis. Every setting is described by what it
does, because that is what the person choosing it needs to know, and because a
child switching on bigger buttons should not be told what that says about them.
"""

from __future__ import annotations

from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from pensum.web.comfort import COMFORT_COOKIE, COMFORT_MAX_AGE, THEMES, ComfortProfile
from pensum.web.deps import is_secure, safe_next
from pensum.web.rendering import context, templates, validate_locale

router = APIRouter()


@router.get("/{locale}/innstillinger", response_class=HTMLResponse)
async def comfort_page(request: Request, locale: str) -> HTMLResponse:
    validate_locale(locale)
    back = request.query_params.get("next")
    return templates.TemplateResponse(
        request,
        "pages/comfort.html",
        context(
            request,
            locale,
            themes=THEMES,
            back=safe_next(back, "") or None,
            saved=request.query_params.get("saved") == "1",
        ),
    )


@router.post("/{locale}/innstillinger")
async def save_comfort(
    request: Request,
    locale: str,
    # A checkbox that is not ticked is not sent at all, so absence is "off" --
    # including for calm, whose default is on. The form always renders the box,
    # so an absent value here is always somebody unticking it.
    calm: Annotated[str | None, Form()] = None,
    read_aloud: Annotated[str | None, Form()] = None,
    bigger_targets: Annotated[str | None, Form()] = None,
    break_reminder: Annotated[str | None, Form()] = None,
    theme: Annotated[str, Form()] = "plain",
    next: Annotated[str | None, Form()] = None,  # noqa: A002 -- the form field's name
) -> RedirectResponse:
    validate_locale(locale)
    profile = ComfortProfile(
        calm=calm is not None,
        read_aloud=read_aloud is not None,
        bigger_targets=bigger_targets is not None,
        break_reminder=break_reminder is not None,
        theme=theme if theme in THEMES else "plain",
    )

    query = {"saved": "1"}
    if back := safe_next(next, ""):
        query["next"] = back
    # 303, so a reload of the page it lands on does not post the form again.
    response = RedirectResponse(f"/{locale}/innstillinger?{urlencode(query)}", status_code=303)
    response.set_cookie(
        COMFORT_COOKIE,
        profile.serialise(),
        max_age=COMFORT_MAX_AGE,
        path="/",
        # Nothing in the browser reads it: the server puts it on <html>, and the
        # scripts read that.
        httponly=True,
        secure=is_secure(request),
        samesite="lax",
    )
    return response

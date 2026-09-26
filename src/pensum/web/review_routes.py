"""The review page: meet a piece of content as a pupil would, then approve or reject it.

This page is how content becomes live. Nothing a pupil is served comes from a
flag in a file; it comes from a decision recorded here, in this instance's
database (`pensum.review`). Every route is behind `require_admin`.

Three things a reviewer can do, all as plain forms so the page works with no
script at all:

* **Decide one piece.** The form carries the fingerprint of the content the
  reviewer was looking at. If the file has changed since the page was rendered,
  nothing is saved and the page says so: an approval is for what was read.
* **Decide a whole filtered selection.** Every instance starts with several
  hundred pieces pending, so this has to exist. It takes two posts: the first
  only counts and asks, the second applies -- and only if the selection is
  still exactly what was counted (`queue.digest`).
* **Try a question.** An administrator can answer it and be told whether that
  was right, as a pupil would, before deciding.

What matters about ordering: the decision is written, then the ledger is
reloaded, and only then does the redirect go out. A reviewer who approves
something and immediately looks at it must see it live, not half a minute later.
"""

from __future__ import annotations

import math

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from pensum.catalogue.loader import Catalogue
from pensum.items.schema import QuizItem
from pensum.items.template import ItemTemplate
from pensum.review.queue import (
    ALL,
    Filters,
    Libraries,
    ReviewEntry,
    counts,
    decide,
    digest,
    entries,
    find,
    select,
)
from pensum.review.store import KINDS, STATES, ReviewLedger, ReviewStore
from pensum.web.deps import get_missions, get_review_store, get_reviews, require_admin
from pensum.web.rendering import context, templates, validate_locale

router = APIRouter(include_in_schema=False)

BASE = "/{locale}/admin/gjennomgang"

# Rows per page. Each row can carry a live board with its script, and a page of
# four hundred of those is a page nobody can scroll; bulk decisions act on the
# whole filtered selection, not on the page, so paging costs the reviewer
# nothing there.
PAGE_SIZE = 20

# How many other variants of a template to show with their answers.
TEMPLATE_EXAMPLES = 5


def _stores(request: Request) -> tuple[ReviewStore, ReviewLedger]:
    return get_review_store(request), get_reviews(request)


def _libraries(request: Request) -> Libraries:
    state = request.app.state
    return Libraries(
        items=state.items,
        reading=state.reading,
        writing=state.writing,
        skills=state.skills,
        missions=get_missions(request),
    )


def _all_entries(request: Request, ledger: ReviewLedger) -> list[ReviewEntry]:
    return entries(_libraries(request), ledger, request.app.state.catalogue)


def _describe(catalogue: Catalogue, entry: ReviewEntry, lang: str) -> dict[str, object]:
    """One row, with the curriculum resolved for display.

    Same approach as the score pages: codes are resolved at render time, so a
    curriculum revision that renumbers a goal leaves the row rendering with the
    bare code rather than failing the page.
    """
    subject = catalogue.subject(entry.subject)
    goal_set = subject.goal_set(entry.goal_set) if subject and entry.goal_set else None
    goals = {g.code: g for g in goal_set.goals} if goal_set else {}
    goal = goals.get(entry.goal) if entry.goal else None

    row: dict[str, object] = {
        "entry": entry,
        "subject_title": subject.display_title.get(lang) if subject else entry.subject,
        "after_year": goal_set.after_year if goal_set else None,
        "goal_text": goal.text.get(lang) if goal else (entry.goal or ""),
    }
    if isinstance(entry.content, ItemTemplate):
        instances = entry.content.instances()
        row |= {
            "sample": instances[0],
            "examples": instances[1 : 1 + TEMPLATE_EXAMPLES],
            "variant_count": len(instances),
        }
    elif isinstance(entry.content, QuizItem):
        row["sample"] = entry.content
    return row


def _choices(collected: list[ReviewEntry], filters: Filters) -> dict[str, list[str]]:
    """What the subject and goal-set filters can be set to, from what exists.

    Goal sets are narrowed to the chosen subject, so the list stays one a
    person can scan.
    """
    subjects = sorted({e.subject for e in collected})
    goal_sets = sorted(
        {
            e.goal_set
            for e in collected
            if e.goal_set and (filters.subject == ALL or e.subject == filters.subject)
        }
    )
    return {"subjects": subjects, "goal_sets": goal_sets}


def _redirect(locale: str, filters: Filters, anchor: str = "", **extra: str) -> RedirectResponse:
    fragment = f"#{anchor}" if anchor else ""
    url = f"{BASE.format(locale=locale)}?{filters.query(**extra)}{fragment}"
    return RedirectResponse(url, status_code=303)


@router.get("/{locale}/admin/gjennomgang", response_class=HTMLResponse)
async def queue(
    request: Request,
    locale: str,
    subject: str = ALL,
    goal_set: str = ALL,
    kind: str = ALL,
    state: str = "pending",
    page: int = 1,
    done: int | None = None,
    stale: str | None = None,
) -> HTMLResponse:
    validate_locale(locale)
    require_admin(request)
    _, ledger = _stores(request)

    filters = Filters.parse(subject, goal_set, kind, state)
    collected = _all_entries(request, ledger)
    shown = select(collected, filters)

    pages = max(1, math.ceil(len(shown) / PAGE_SIZE))
    page = min(max(page, 1), pages)
    window = shown[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]

    lang = str(context(request, locale)["lang"])
    catalogue = request.app.state.catalogue
    return templates.TemplateResponse(
        request,
        "pages/admin_review.html",
        context(
            request,
            locale,
            counts=counts(collected),
            filters=filters,
            kinds=KINDS,
            states=STATES,
            choices=_choices(collected, filters),
            selected=len(shown),
            page=page,
            pages=pages,
            rows=[_describe(catalogue, e, lang) for e in window],
            done=done,
            stale=stale,
        ),
    )


@router.post("/{locale}/admin/gjennomgang/samlet", response_class=HTMLResponse)
async def decide_selection(
    request: Request,
    locale: str,
    verdict: str = Form(...),
    subject: str = Form(ALL),
    goal_set: str = Form(ALL),
    kind: str = Form(ALL),
    state: str = Form("pending"),
    note: str = Form(""),
    confirm: str = Form(""),
    expected: str = Form(""),
) -> Response:
    """Approve or reject everything the current filters select.

    First post: count, and ask. Second post (`confirm=yes`): apply, if and only
    if the selection still has the digest the first post showed.
    """
    validate_locale(locale)
    user = require_admin(request)
    store, ledger = _stores(request)
    if verdict not in ("approved", "rejected"):
        raise HTTPException(status_code=422, detail="unknown verdict")

    filters = Filters.parse(subject, goal_set, kind, state)
    selected = select(_all_entries(request, ledger), filters)
    current = digest(selected)

    if confirm == "yes" and expected == current and selected:
        written = store.record_many(decide(selected, verdict, user, note.strip() or None))
        ledger.reload()
        return _redirect(locale, filters, done=str(written))

    return templates.TemplateResponse(
        request,
        "pages/admin_review_bulk.html",
        context(
            request,
            locale,
            verdict=verdict,
            filters=filters,
            count=len(selected),
            expected=current,
            note=note,
            # Asked to apply, but the selection moved underneath: say so, and
            # show the new count rather than writing the old one.
            changed=confirm == "yes",
        ),
    )


@router.post("/{locale}/admin/gjennomgang/proev", response_class=HTMLResponse)
async def try_item(
    request: Request,
    locale: str,
    item_id: str = Form(...),
    response: str = Form(""),
    back: str = Form(""),
) -> HTMLResponse:
    """Answer a question as a pupil would, and be told whether it was right.

    Nothing is recorded: this is the reviewer checking the question, not a
    pupil being assessed. Returned as a fragment to htmx and as a whole page to
    a browser without script.
    """
    validate_locale(locale)
    require_admin(request)
    item = request.app.state.items.item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="no such question")

    partial = request.headers.get("hx-request") == "true"
    return templates.TemplateResponse(
        request,
        "partials/review_try.html" if partial else "pages/admin_review_try.html",
        context(
            request,
            locale,
            item=item,
            correct=item.is_correct(response),
            # Only ever back to this page: `back` comes from the form.
            back=back if back.startswith(BASE.format(locale=locale)) else "",
        ),
    )


@router.post("/{locale}/admin/gjennomgang/{kind}/{content_id}")
async def decide_one(
    request: Request,
    locale: str,
    kind: str,
    content_id: str,
    verdict: str = Form(...),
    fingerprint: str = Form(""),
    note: str = Form(""),
    subject: str = Form(ALL),
    goal_set: str = Form(ALL),
    filter_kind: str = Form(ALL),
    state: str = Form("pending"),
    page: str = Form("1"),
) -> RedirectResponse:
    validate_locale(locale)
    user = require_admin(request)
    store, ledger = _stores(request)
    filters = Filters.parse(subject, goal_set, filter_kind, state)

    if kind not in KINDS:
        raise HTTPException(status_code=404, detail="unknown content kind")

    # The id has to name something real. Without this check the table would
    # happily accumulate decisions about content that does not exist, and the
    # queue -- which is built from the libraries, not from the table -- would
    # never show them again.
    entry = find(_all_entries(request, ledger), kind, content_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="no such content")

    if verdict not in ("approved", "rejected", "clear"):
        raise HTTPException(status_code=422, detail="unknown verdict")

    # What was on the reviewer's screen must still be what is served. If the
    # file changed in between, approving now would approve words nobody read.
    page_number = page if page.isdigit() else "1"
    if verdict != "clear" and fingerprint != entry.fingerprint:
        return _redirect(locale, filters, entry.anchor, page=page_number, stale=entry.anchor)

    if verdict == "clear":
        store.clear(entry.kind, entry.content_id)
    else:
        store.record_many(decide([entry], verdict, user, note.strip() or None))

    # Before the redirect, so the page the reviewer lands on reflects what they
    # just did rather than the snapshot from before it.
    ledger.reload()
    return _redirect(locale, filters, entry.anchor, page=page_number)

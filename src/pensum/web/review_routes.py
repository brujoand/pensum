"""The review page: read a draft, then publish or withhold it.

One page and one form target, both behind `require_admin`, and both 404 when
there is no database -- a review page that cannot record anything would be a
button that lies.

What a decision does is described in `pensum.review.store`. What matters here is
the ordering: the decision is written, then the ledger is reloaded, and only
then does the redirect go out. A reviewer who approves something and immediately
looks at it must see it published, not see it half a minute later.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from pensum.catalogue.loader import Catalogue
from pensum.review.queue import ReviewEntry, counts, entries, find
from pensum.review.store import KINDS, Decision, ReviewLedger, ReviewStore
from pensum.web.deps import get_review_store, get_reviews, require_admin
from pensum.web.rendering import context, templates, validate_locale

router = APIRouter(include_in_schema=False)

# What the page can be filtered down to. `pending` first because it is the
# working set: everything nobody has decided and no file has published.
FILTERS = ("pending", "published", "rejected", "all")


def _store_or_404(request: Request) -> tuple[ReviewStore, ReviewLedger]:
    store = get_review_store(request)
    ledger = get_reviews(request)
    if store is None or ledger is None:
        raise HTTPException(status_code=404, detail="review decisions are not configured")
    return store, ledger


def _all_entries(request: Request, ledger: ReviewLedger) -> list[ReviewEntry]:
    return entries(
        request.app.state.items,
        request.app.state.reading,
        request.app.state.writing,
        ledger,
    )


def _describe(catalogue: Catalogue, entry: ReviewEntry, lang: str) -> dict[str, object]:
    """One row, with the curriculum resolved for display.

    Same approach as the score pages: codes are resolved at render time, so a
    curriculum revision that renumbers a goal leaves the row rendering with the
    bare code rather than failing the page.
    """
    subject = catalogue.subject(entry.subject)
    goal_set = subject.goal_set(entry.goal_set) if subject else None
    goal = next((g for g in goal_set.goals if g.code == entry.goal), None) if goal_set else None

    return {
        "entry": entry,
        "subject_title": subject.display_title.get(lang) if subject else entry.subject,
        "after_year": goal_set.after_year if goal_set else None,
        "goal_text": goal.text.get(lang) if goal else entry.goal,
    }


@router.get("/{locale}/admin/gjennomgang", response_class=HTMLResponse)
async def queue(
    request: Request,
    locale: str,
    show: str = "pending",
    kind: str = "all",
) -> HTMLResponse:
    validate_locale(locale)
    require_admin(request)
    _, ledger = _store_or_404(request)

    if show not in FILTERS:
        show = "pending"
    if kind != "all" and kind not in KINDS:
        kind = "all"

    collected = _all_entries(request, ledger)
    tally = counts(collected)

    shown = [e for e in collected if show == "all" or e.state == show]
    if kind != "all":
        shown = [e for e in shown if e.kind == kind]

    lang = str(context(request, locale)["lang"])
    return templates.TemplateResponse(
        request,
        "pages/admin_review.html",
        context(
            request,
            locale,
            counts=tally,
            show=show,
            kind=kind,
            kinds=KINDS,
            filters=FILTERS,
            rows=[_describe(request.app.state.catalogue, e, lang) for e in shown],
        ),
    )


@router.post("/{locale}/admin/gjennomgang/{kind}/{content_id}")
async def decide(
    request: Request,
    locale: str,
    kind: str,
    content_id: str,
    verdict: str = Form(...),
    show: str = Form("pending"),
    filter_kind: str = Form("all"),
) -> RedirectResponse:
    validate_locale(locale)
    user = require_admin(request)
    store, ledger = _store_or_404(request)

    if kind not in KINDS:
        raise HTTPException(status_code=404, detail="unknown content kind")

    # The id has to name something real. Without this check the table would
    # happily accumulate decisions about content that does not exist, and the
    # queue -- which is built from the libraries, not from the table -- would
    # never show them again.
    if find(_all_entries(request, ledger), kind, content_id) is None:
        raise HTTPException(status_code=404, detail="no such content")

    if verdict == "clear":
        store.clear(kind, content_id)
    elif verdict in ("approved", "rejected"):
        store.record(
            Decision(
                kind=kind,
                content_id=content_id,
                verdict=verdict,
                by_sub=user.sub,
                by_name=user.name,
                decided_at=datetime.now(UTC),
            )
        )
    else:
        raise HTTPException(status_code=422, detail="unknown verdict")

    # Before the redirect, so the page the reviewer lands on reflects what they
    # just did rather than the snapshot from before it.
    ledger.reload()

    destination = f"/{locale}/admin/gjennomgang?show={show}&kind={filter_kind}#{kind}-{content_id}"
    return RedirectResponse(destination, status_code=303)

"""Quiz routes.

HTMX drives the question loop: each answer swaps in feedback, and the next
question replaces it. No page reloads, no JavaScript we wrote, and the whole
flow still works if the fragments are fetched as ordinary pages.

The run's own controls -- Help, the step-down swap, the finish choice and the
break card -- are plain forms that post and redirect back to the quiz page when
no script is running, and swap the question slot in place when htmx is. Each
changes the session and nothing else, so both roads land on the same screen.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from pensum.domain.grades import checkpoint_for
from pensum.i18n import translate
from pensum.items.loader import ItemBank
from pensum.items.schema import QuizItem
from pensum.mastery.attribution import evidence_for
from pensum.quiz.scoring import Result, score
from pensum.quiz.session import QuizSession, SessionStore
from pensum.quiz.shape import plan
from pensum.scores.store import Attempt, GoalTally, attempt_key
from pensum.web.comfort import comfort_of
from pensum.web.deps import current_user, get_evidence, get_store, sees_unreviewed
from pensum.web.rendering import context, flow, templates, validate_locale

router = APIRouter()


def _flow(request: Request, locale: str, session: QuizSession) -> dict[str, object]:
    """A trinntest knows its own length, so it says so -- as stones.

    `progress` stays for the pages that still read it as text; the question and
    feedback partials draw `stones` instead when they are given them, which only
    this flow does. The nivåtest has no length to draw.
    """
    number = min(session.answered + 1, session.total)
    return flow(
        locale,
        "quiz",
        session.id,
        progress=translate(locale, "quiz.progress", number=number, total=session.total),
        finished=session.finished,
    )


def _run(request: Request, locale: str, session: QuizSession) -> dict[str, object]:
    """What the question slot needs to draw a run: stones, preview, help, breaks.

    Built in one place because the quiz page, the question partial and every
    control's response all render the same slot, and a slot drawn from two
    different contexts is how one road ends up without the break card.
    """
    comfort = comfort_of(request)
    base = f"/{locale}/quiz/{session.id}"
    item = session.current()
    return {
        "run": session,
        "page_url": base,
        "help_url": f"{base}/help",
        "swap_url": f"{base}/swap",
        "choose_url": f"{base}/choose",
        "carry_on_url": f"{base}/carry-on",
        "stones": session.stones(),
        "hints": session.revealed(item, locale) if item else (),
        "more_help": session.more_help(item) if item else False,
        "held": session.held.get(item.id, "") if item else "",
        "break_card": comfort.break_reminder and session.break_due(),
        "preview": _preview(locale, session) if comfort.show_next else None,
    }


def _preview(locale: str, session: QuizSession, *, on_feedback: bool = False) -> str | None:
    """One line saying what comes next (comfort: show what's next).

    On a question, "next" is the task after this one. On the feedback that
    follows an answer it is the task the Next button opens.
    """
    if on_feedback:
        if session.finished:
            return None
        if session.choosing:
            return translate(locale, "run.next_choice")
        upcoming = session.current()
    else:
        if session.next_is_choice():
            return translate(locale, "run.next_choice")
        upcoming = session.upcoming()
    if upcoming is None:
        return translate(locale, "run.next_last")
    kind = kind_label(locale, upcoming)
    prompt = upcoming.prompt.get(locale)
    return translate(locale, "run.next", kind=kind, prompt=prompt) if kind else prompt


def kind_label(locale: str, item: QuizItem) -> str:
    """How a task is answered, in words: "Tellebrikker", "Velg et svar".

    Empty for a kind with no wording yet -- a primitive registered after this
    was written -- rather than showing the pupil an i18n key.
    """
    key = f"run.kind.{item.type}"
    text = translate(locale, key)
    return "" if text == key else text


# The finish cards name each option's kind too, so the template can ask.
templates.env.globals["kind_label"] = kind_label


def _bank(request: Request) -> ItemBank:
    return request.app.state.items


def _store(request: Request) -> SessionStore:
    return request.app.state.sessions


def _session_or_404(request: Request, session_id: str) -> QuizSession:
    session = _store(request).get(session_id, datetime.now(UTC))
    if not isinstance(session, QuizSession):
        # Expired, unknown, or a nivåtest id on a trinntest path. All ordinary --
        # a tab left open overnight is the common case, not an error worth
        # alarming a pupil about. The type check mirrors
        # `placement_routes._run_or_404`: the two flows share one store, so it is
        # what keeps the paths separate.
        raise HTTPException(status_code=404, detail="quiz session not found")
    return session


def _remember(request: Request, session: QuizSession, outcome: Result, now: datetime) -> None:
    """Record a finished attempt and its evidence, if there is anywhere and anyone.

    Three conditions, all of which must hold, and none of which is the default:
    a store is configured, the pupil was signed in when they started, and they
    actually finished. An abandoned quiz is not a result and is not kept.
    """
    store = get_store(request)
    if store is None or not session.attributed or not session.finished:
        return

    store.record(
        Attempt(
            key=attempt_key(session.id),
            user_sub=str(session.user_sub),
            user_name=session.user_name or str(session.user_sub),
            subject=session.subject,
            goal_set=session.goal_set,
            grade=session.grade,
            correct=outcome.correct,
            total=outcome.total,
            by_goal=tuple(
                GoalTally(goal=g.goal, correct=g.correct, total=g.total) for g in outcome.by_goal
            ),
            finished_at=now,
        )
    )

    # Evidence for the pupil's map, under the same three conditions and at the
    # same moment. A subject with no skills file has nothing to file it under.
    evidence = get_evidence(request)
    skill_file = request.app.state.skills.for_subject(session.subject)
    subject = request.app.state.catalogue.subject(session.subject)
    goal_set = subject.goal_set(session.goal_set) if subject else None
    if evidence is None or skill_file is None or goal_set is None:
        return
    # Hints come from the session's answer records, which cover answered items
    # only; an item without one is recorded with 0, as before.
    hints = {record.item_id: record.hints_used for record in session.records()}
    evidence.record(
        evidence_for(
            (
                (item, item.is_correct(session.answers.get(item.id, "")), hints.get(item.id, 0))
                for item in session.items
            ),
            attempt=attempt_key(session.id),
            user_sub=str(session.user_sub),
            checkpoint=goal_set.after_year,
            skill_file=skill_file,
            at=now,
        )
    )


def _slot(request: Request, locale: str, session: QuizSession) -> Response:
    """After a run control: the slot again for htmx, the page again without it.

    303 for the plain form, so a reload of the page it lands on does not post
    the control a second time.
    """
    if request.headers.get("HX-Request"):
        return _question(request, locale, session)
    return RedirectResponse(f"/{locale}/quiz/{session.id}", status_code=303)


def _question(request: Request, locale: str, session: QuizSession) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "partials/question.html",
        context(
            request,
            locale,
            session=session,
            item=session.current(),
            **_flow(request, locale, session),
            **_run(request, locale, session),
        ),
    )


@router.post("/{locale}/klasse/{grade}/{subject_code}/quiz")
async def start_quiz(
    request: Request, locale: str, grade: int, subject_code: str
) -> RedirectResponse:
    validate_locale(locale)
    subject = request.app.state.catalogue.subject(subject_code)
    if subject is None:
        raise HTTPException(status_code=404, detail="unknown subject")

    checkpoint = checkpoint_for(subject, grade)
    if checkpoint is None:
        raise HTTPException(status_code=404, detail="no goals for this grade")

    # An administrator gets the drafts too, because reading a question in the
    # quiz it belongs to is the only way to judge it.
    pool = _bank(request).for_goal_set(
        checkpoint.goal_set.code, unreviewed=sees_unreviewed(request)
    )
    user = current_user(request)
    now = datetime.now(UTC)
    shaped = plan(
        pool,
        known_right=_store(request).known_right(
            user.sub if user else None, checkpoint.goal_set.code, now
        ),
    )
    if not shaped.items:
        raise HTTPException(status_code=404, detail="no quiz available for this checkpoint")

    session = _store(request).create(
        subject=subject.code,
        goal_set=checkpoint.goal_set.code,
        grade=grade,
        items=shaped.items,
        now=now,
        user=user,
        pool=tuple(pool),
        finish_options=shaped.finish,
    )
    return RedirectResponse(f"/{locale}/quiz/{session.id}", status_code=303)


@router.get("/{locale}/quiz/{session_id}", response_class=HTMLResponse)
async def quiz_page(request: Request, locale: str, session_id: str) -> HTMLResponse:
    validate_locale(locale)
    session = _session_or_404(request, session_id)
    subject = request.app.state.catalogue.subject(session.subject)

    return templates.TemplateResponse(
        request,
        "pages/quiz.html",
        context(
            request,
            locale,
            session=session,
            subject=subject,
            item=session.current(),
            **_flow(request, locale, session),
            **_run(request, locale, session),
        ),
    )


@router.post("/{locale}/quiz/{session_id}/answer", response_class=HTMLResponse)
async def answer(
    request: Request,
    locale: str,
    session_id: str,
    item_id: str = Form(...),
    response: str = Form(""),
) -> HTMLResponse:
    validate_locale(locale)
    session = _session_or_404(request, session_id)

    item = session.answer(item_id, response)
    if item is None:
        raise HTTPException(status_code=409, detail="that question was already answered")

    announcing = session.just_grew(item)
    return templates.TemplateResponse(
        request,
        "partials/feedback.html",
        context(
            request,
            locale,
            session=session,
            item=item,
            given=response,
            correct=item.is_correct(response),
            **_flow(request, locale, session),
            **{
                **_run(request, locale, session),
                # The stone a wrong answer added is said before it is drawn.
                "stones": session.stones(announcing=announcing),
                "grew": announcing,
                "preview": _preview(locale, session, on_feedback=True)
                if comfort_of(request).show_next
                else None,
            },
        ),
    )


@router.get("/{locale}/quiz/{session_id}/question", response_class=HTMLResponse)
async def next_question(request: Request, locale: str, session_id: str) -> HTMLResponse:
    validate_locale(locale)
    return _question(request, locale, _session_or_404(request, session_id))


@router.post("/{locale}/quiz/{session_id}/help")
async def help_step(
    request: Request,
    locale: str,
    session_id: str,
    item_id: str = Form(...),
    response: str = Form(""),
) -> Response:
    """One press of Help: the next step of the hint ladder.

    The form is the question's own, so what arrives in `response` is the
    answer as it stands -- the board's state -- which the ladder's "show" step
    compares and the redrawn question puts back on the board.
    """
    validate_locale(locale)
    session = _session_or_404(request, session_id)
    session.hint(item_id, response)
    return _slot(request, locale, session)


@router.post("/{locale}/quiz/{session_id}/swap")
async def swap(
    request: Request, locale: str, session_id: str, item_id: str = Form(...)
) -> Response:
    """Hint step 3, taken: this task becomes its lower-stage version."""
    validate_locale(locale)
    session = _session_or_404(request, session_id)
    session.swap_down(item_id)
    return _slot(request, locale, session)


@router.post("/{locale}/quiz/{session_id}/choose")
async def choose(
    request: Request, locale: str, session_id: str, item_id: str = Form(...)
) -> Response:
    """The finish: the pupil picks one of two."""
    validate_locale(locale)
    session = _session_or_404(request, session_id)
    session.choose(item_id)
    return _slot(request, locale, session)


@router.post("/{locale}/quiz/{session_id}/carry-on")
async def carry_on(request: Request, locale: str, session_id: str) -> Response:
    """The break card's "keep going". Its "stop" is a link to the result."""
    validate_locale(locale)
    session = _session_or_404(request, session_id)
    session.carry_on()
    return _slot(request, locale, session)


@router.get("/{locale}/quiz/{session_id}/result", response_class=HTMLResponse)
async def result(request: Request, locale: str, session_id: str) -> HTMLResponse:
    validate_locale(locale)
    session = _session_or_404(request, session_id)
    subject = request.app.state.catalogue.subject(session.subject)
    goal_set = subject.goal_set(session.goal_set)

    outcome = score(session)
    _remember(request, session, outcome, datetime.now(UTC))

    # The per-goal breakdown is the useful half of the result, and it only reads
    # as useful if it shows the goal text rather than a KM code.
    goals = {goal.code: goal for goal in goal_set.goals}

    return templates.TemplateResponse(
        request,
        "pages/result.html",
        context(
            request,
            locale,
            session=session,
            subject=subject,
            result=outcome,
            goals=goals,
            # So a score reads against what the quiz actually reached, not the
            # whole checkpoint.
            coverage=_bank(request).coverage(goal_set, unreviewed=sees_unreviewed(request)),
        ),
    )

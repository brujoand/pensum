# Architecture

How the two deliverables fit together as data and as runtime:

1. **Guidance.** What a pupil needs to understand at each level, readable by a
   teacher and traceable to LK20.
2. **Activities.** Short, tactile, gamified tasks that practise and check those
   things.

This is a design. Nothing here is implemented yet, and every name below is a
proposal. Where it extends something Pensum already has, the existing module is
named.

## The layers

```
 Udir (verbatim, never edited)          Pensum (authored, reviewed)
 ─────────────────────────────          ──────────────────────────────────────────
 Subject     MAT01-06                    Strand     "Tall og plassverdi"
 └ GoalSet   etter 2. trinn        ◄──── └ Skill    "Kan bytte 10 enere mot 1 tier"
   └ Goal    KM13232                          │  refs: [KM13232]
                                              │  needs: [count-to-100]
                                              │  stages: concrete, pictorial, abstract
                                              │  misconceptions: [reads-digits-as-units]
                                              ▼
                                         Activity   base_ten, "vis 34 med blokker"
                                              │  primitive + content + stage
                                              ▼
                                         Evidence   attempt, stage, hints used, correct
                                              ▼
                                         Mastery    exploring → practising → secure → retained
                                              ▼
                        Teacher view: class × skill grid      Pupil view: the map fills in
```

Udir's three levels stay exactly as `pensum.domain.models` has them. Everything
to the right is new, and all of it is Pensum's own reading of the curriculum. It
must never be presented as official text, for the same reason `items/schema.py`
gives for quiz items.

## Strand

A strand is one thread of a subject that runs through every checkpoint:
*tall og plassverdi*, *brøk*, *lesing: avkoding*, *muntlig samhandling*. It is
the axis a teacher reads down to see progression, and the axis a pupil's map is
drawn along.

LK20 already names *kjerneelementer* per subject, and every goal carries their
codes (`core_elements` in the ingested JSON). Strands are finer than core
elements: matematikk's goals cite five core elements, and the subject needs
about nine strands before a progression becomes readable. Each strand therefore names the core elements
it draws on, so the mapping back is checkable.

## Skill

A skill is the unit of guidance and the unit of mastery. It is one thing a pupil
can or cannot yet do, stated so a teacher can observe it and a pupil can read it.

```yaml
# data/skills/MAT01-06.yaml  (proposed)
- id: mat.place-value.exchange-tens
  strand: place-value
  checkpoint: 2          # the GoalSet's after_year
  refs: [KM13232]        # at least one; every one must exist in the curriculum
  needs: [mat.counting.to-100]
  i_can:                 # pupil-facing, first person, one clause
    nob: Jeg kan bytte ti enere mot én tier.
    eng: I can swap ten ones for one ten.
  teacher:               # what it looks like when it is there, and when it is not
    nob: ...
    eng: >-
      Shows 34 as 3 rods and 4 cubes without counting all 34. Knows 2 rods 14
      cubes is also 34. Not yet: counts every cube one by one.
  stages: [concrete, pictorial, abstract]
  misconceptions: [reads-digits-as-units, zero-as-nothing]
  assessable: true       # false: practised off screen, see "Missions" below
```

Rules the validator enforces, in the style of `pensum.items.validate`:

- Every `refs` code exists in the current curriculum. A revision that renumbers
  goals fails CI loudly, exactly as orphaned items do today.
- `needs` forms a DAG within the subject. Cross-subject edges are allowed only
  to matematikk and norsk, which are the prerequisites other subjects actually
  lean on (reading the task, reading a table).
- Every goal is covered by at least one skill, or listed with a reason in a
  `not_modelled` block. Coverage is visible, as `items/coverage.py` makes it
  visible for items.
- `i_can` is at most 12 words and uses no term that is not introduced by an
  earlier skill. This keeps it readable aloud to a seven-year-old.

**Why a skill layer and not goals directly.** A single LK20 goal is often three
skills (*"use numerals, number words, drawings and tangible objects to represent
the positional system and translate between the representations"*), and several
goals share one skill. Mastery tracked per goal would be both too coarse to
teach from and duplicated across goals. The skill is the smallest thing a
teacher would write on a sticky note about a pupil.

**Why skills are authored, not generated.** Same policy as items: drafted with
an LLM if useful, and read by a human before anything is served. Whether a
skill, an activity or a mission is live is not a flag in its file: it is
decided per instance, by an administrator on that instance's review page, and
stored in its database with a fingerprint of what was approved, so an edit
returns it to pending (`pensum.review`; README, "Reviewing drafts").

## Activity

An activity is a **primitive** (engine code, a small fixed set) filled with
**content** (data). The catalogue of primitives is [activities.md](activities.md).

```yaml
# data/activities/MAT01-06/place-value.yaml  (proposed)
- id: mat.pv.build-34
  skill: mat.place-value.exchange-tens
  primitive: base_ten
  stage: concrete
  prompt: {nob: Vis 34 med blokker., eng: Show 34 with blocks.}
  start: {tens: 0, ones: 0}
  target: {value: 34}
  accept: any_equivalent        # 2 tens + 14 ones also counts
  hint_ladder: [show-a-ten-as-ten-ones, count-tens-first, worked-example]
```

This is the existing figure principle carried one step further: **an activity is
declared, not drawn.** `target: {value: 34}` is either right or a visible typo.
The primitive owns the geometry, the interaction, and the grading, and those are
tested in code, not per item.

Activities extend `QuizItem` rather than replace it. `multiple_choice`,
`numeric`, `short_text` and `number_line` become four primitives among the
others, and the existing `template.py` parameterisation applies to any primitive
whose target is a function of its numbers.

### Grading is a function of final state

Every primitive submits one serialised state, and grading is a pure function of
that state and the declared target. This is how `number_line` works already
(the marker snaps to a tick and the tick is graded), and it keeps three
properties the codebase already relies on:

- deterministic and offline, no model at request time;
- testable without a browser;
- a no-JavaScript fallback exists for every primitive: the same target asked as
  a `numeric` or `multiple_choice` item, rendered from the same declaration.

Process is recorded as evidence but never graded: how many hints, which
representation, whether the pupil undid. That feeds the teacher view, not the
score.

## Evidence and mastery

Each attempt writes one evidence row: skill, activity, stage, correct, hints
used, and a timestamp. No response content beyond the final state, no timing
used for scoring, no audio (reading aloud already keeps none).

Mastery is a rule over evidence, not a fitted model. The reasoning in
`quiz/placement.py` applies unchanged: there is no response data to fit item
parameters to, and a decimal-point ability estimate from guessed difficulties is
worse than a coarse state that is honest about being coarse.

| state | rule (defaults, per-deployment config) | shown to pupil as |
|---|---|---|
| not started | no evidence | an empty spot on the map |
| exploring | any attempt | a seed |
| practising | ≥1 correct without hints | a sprout |
| secure | 4 of the last 5 correct, across ≥2 sessions, at ≥2 stages including the skill's last | a plant |
| retained | secure, then correct on a spaced check ≥7 days later | a plant with a flower |

Rules deliberately chosen:

- **Secure needs two sessions.** One good run straight after a worked example is
  short-term memory. Two sessions is the cheapest guard against it.
- **Secure needs two representations.** A pupil who can do it with blocks but
  not with numerals, or the reverse, has not yet got it. This is the CRA
  principle stated as a rule.
- **States never go down on screen.** A retained skill that fails a later check
  is scheduled for review and marked for the teacher, but the pupil's plant does
  not wilt. Loss framing is exactly what the design is avoiding (see
  [principles.md](principles.md)). The teacher view shows the true state.
- **Hints do not fail an attempt.** A hinted correct answer counts as evidence
  of *practising*, not of *secure*. No penalty is shown.

## Session engine

A **run** is the unit a pupil experiences: a short, fixed-length sequence with
a visible end. It generalises `quiz/run.py`.

```
 ┌── warm-up ──┐┌──────── core ────────┐┌─ finish ─┐
 │ 1 secure    ││ 3-5 on the current   ││ 1 chosen │
 │ skill, easy ││ skill, stage-stepped ││ by pupil │
 └─────────────┘└──────────────────────┘└──────────┘
   ●  ●  ●  ○  ○  ○  ○      six stones, filled as tasks finish
```

- **Length is shown as stones, never as a clock.** The count is known before the
  first task. There is no timer in any activity, anywhere.
- **Warm-up is always something the pupil can do.** It sets up a success before
  anything new ([principles.md](principles.md), rule 8).
- **Core steps representation on error.** A wrong abstract answer is followed by
  the same target at the pictorial stage, not by a harder or a different one.
- **Finish is a choice between two.** Autonomy at the end, where it costs
  nothing.
- **Selection.** Current skill = the lowest unmet skill whose `needs` are all
  secure, on the strand the teacher assigned or the pupil picked. Spaced checks
  for retention are slotted into warm-up.

## Missions: goals a screen cannot check

`not_assessable` stays. Pensum should not invent a quiz for *samtale om*,
*utforske*, *delta i*. But a goal that is not assessable on screen can still be
**guided** on screen: a mission card is a short, concrete, off-screen task with
a checklist, which the pupil ticks and a teacher can confirm.

```yaml
- id: nat.weather-week
  skill: nat.inquiry.observe-and-record
  primitive: mission
  steps:
    - {eng: Look at the sky at the same time every day for 5 days.}
    - {eng: Draw what you see in the weather table.}
    - {eng: Tell someone which day was different, and why you think so.}
  confirm: teacher        # or: self
```

A mission produces evidence `confirmed_by: self|teacher`. Only a teacher
confirmation moves mastery past *practising*. Nothing is uploaded: no photo, no
recording, consistent with what Pensum already refuses to store.

## Comfort profile (accommodations)

Per pupil, settable by the pupil and by a teacher, stored with the account if
there is one and in `localStorage` if not. Every setting is off by default
except where noted; none of them is ever labelled with a diagnosis.

| setting | effect |
|---|---|
| calm (default **on**) | no animation beyond 150 ms state changes, no sound effects, no confetti |
| read everything aloud | prompts, choices and feedback spoken with the browser voice already used by listening |
| fewer choices | 3 options instead of 4; distractors removed nearest-first |
| show what's next | the next task's primitive and prompt previewed before the current one ends |
| step at a time | multi-step prompts shown one step per screen |
| bigger targets | 64 px minimum hit areas instead of 44 |
| literal feedback | feedback states the fact only (default wording is already literal; this removes praise lines too) |
| theme | cosmetic skin for counters and characters: animals, vehicles, space, blocks, plain |
| break reminder | after N tasks, a pause card with a choice to stop here; the run's progress is kept |

`prefers-reduced-motion` and `prefers-contrast` switch the matching settings on
automatically; the pupil can still see and change them.

## Teacher surface

Three views, all derived from the data above, none requiring new data from the
teacher beyond a class list (which the existing accounts feature already
gates):

1. **Progression guide.** Per subject: strands down, checkpoints across, skills
   in cells with `teacher` text and the verbatim LK20 goals they refer to. This
   is deliverable 1, and it works without any accounts at all. It is also
   printable.
2. **Class grid.** Pupils × skills on one strand, cells showing mastery state
   and the representation stage last reached. The cell a teacher cares about
   most is *practising, concrete only*: the pupil can do it with blocks and has
   not yet moved to numerals.
3. **Assign.** Pick a strand or a skill range and optionally lock the comfort
   profile for a pupil. That is the whole assignment model: no due dates, no
   minutes-per-week targets, both of which would reintroduce time pressure.

Printable worksheets are rendered from the same activity declarations at the
pictorial stage, so a teacher can hand the same task on paper.

## Where state lives

Unchanged from the current privacy stance in the README: nothing stored without
accounts; with accounts, evidence rows and mastery states only; no third-party
scripts; no analytics. The pupil-side map, personal bests and theme can live in
`localStorage` as reading's personal bests do today.

## Open decisions

1. **Strand granularity.** Nine strands in matematikk is a judgement. The test is
   whether a teacher reading one row sees a progression, not a list.
2. **Mastery thresholds.** The defaults above are guesses to be tuned against
   the first real classroom data, and should say so in the UI.
3. **Retention scheduling.** A single 7-day check is the simplest honest
   version. A Leitner-style box schedule is the likely next step.
4. **Nynorsk.** `i_can` and `teacher` text is authored in bokmål and English
   today, matching the UI locales. Nynorsk is a content cost, not an
   architecture change.

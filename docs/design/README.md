# Learning design

The design for Pensum's next step: from *quizzes that check a goal* to
*guidance on what a pupil needs at each level, and short tactile activities to
learn it*. The main readers are teachers and the people building Pensum. The
pupils it is designed around are children with mild autism or ADHD, and
through them every other child. Nothing here is implemented yet.

## Read in this order

| document | answers |
|---|---|
| [landscape.md](landscape.md) | what already exists, what to take from it, and the gap Pensum fills |
| [principles.md](principles.md) | the 14 rules every activity follows, with evidence strength and citations; what gamification may and may not do |
| [architecture.md](architecture.md) | strands, skills, activities, evidence, mastery, the session engine, missions, the comfort profile, the teacher views |
| [activities.md](activities.md) | the catalogue of interaction primitives every subject is built from |
| [subjects/](subjects/) | per subject: strands, a progression per checkpoint citing LK20, misconceptions to watch for, activities, missions |

Subjects: [matematikk](subjects/matematikk.md) ·
[norsk](subjects/norsk.md) · [engelsk](subjects/engelsk.md) ·
[naturfag](subjects/naturfag.md) · [samfunnsfag](subjects/samfunnsfag.md) ·
[KRLE](subjects/krle.md). These are the six subjects Pensum already has quiz
items for. Every one of their 398 competence goals is cited by at least one
progression row or mission.

## The design in ten decisions

1. **LK20 stays the authority and stays verbatim.** Pensum adds a layer on top
   (strands and skills) and never edits Udir's text.
2. **The skill is the unit of guidance and of mastery.** One observable thing a
   pupil can do, stated for the teacher and as *I can* for the pupil, citing
   the goals it serves.
3. **Every new idea goes concrete → pictorial → abstract**, and a wrong answer
   steps back down a stage rather than on to something else.
4. **About forty interaction primitives cover every subject.** A primitive is code;
   an activity is data. An activity is declared, not drawn, extending the rule
   the figures already follow.
5. **Grading is a pure function of the final state.** Deterministic, offline,
   testable without a browser, and every primitive has a no-JavaScript
   fallback.
6. **Mastery is a small rule set, not a statistical model**, for the reason
   `quiz/placement.py` already gives: there is no data to fit one to.
7. **No clock, no ranking, no random reward, no loss.** Runs are counted in
   stones, not minutes; the pupil's map only grows.
8. **Calm is the default.** Motion, sound and celebration are things a pupil
   turns on.
9. **Goals a screen cannot check become missions**: short off-screen tasks
   with a checklist and a teacher confirmation, instead of invented quiz
   questions.
10. **Sensitive topics are taught and never gamified.** No rewards, not on the
    class grid, and help information on every screen that touches abuse.

## For a teacher, in one page

- **The progression guide** is the tables in each subject file: strands down,
  checkpoints across. Each cell says what a pupil can *do* when they have it,
  and which competence goals it comes from.
- **Watch for** lists under each strand name the common misconceptions, which is
  usually where a stuck pupil is.
- **Missions** are the parts of the curriculum that happen in the classroom.
  Pensum supplies the card; the teacher confirms.
- **A pupil's comfort profile** (calm, read aloud, fewer choices, step at a
  time, theme, break reminder) is set by the pupil or the teacher and is never
  labelled with a diagnosis.
- **The class grid** shows each pupil's state per skill, and marks the ones who
  can do something with objects but not yet with numbers or words.

## Suggested build order

Each step is usable on its own.

1. **Progression guide, read-only.** `data/skills/*.yaml` with the validator
   (every ref exists, `needs` is acyclic, every goal covered or explained), and
   one page per subject rendering the tables. Useful to teachers with no
   accounts and no activities. The subject files here are its first draft.
2. **Five primitives for matematikk strands 1–4**: `counters`, `ten_frame`,
   `base_ten`, `array`, `balance`. They reuse the figure geometry and the
   number-line interaction that already exist.
3. **The run engine**: stones, warm-up/core/finish, stage stepping, the hint
   ladder, the comfort profile with calm on by default.
4. **Mastery and the map**: evidence rows, the five states, the pupil's map.
5. **Cross-subject primitives**: `sort`, `sequence`, `match`, `label`,
   `highlight`. These open naturfag, samfunnsfag and KRLE.
6. **Language primitives**: `sound_boxes`, `blend`, `word_build`,
   `sentence_build`, `dialogue`.
7. **Teacher views** and printable missions and worksheets.
8. **Simulations**: `explore_sim`, `trials`, `step_code`.

## What this design does not cover

- **Subjects without items today** (kunst og håndverk, musikk, kroppsøving, mat
  og helse, fremmedspråk). Their goals are mostly practical; the mission model
  is the likely route, and that is a later design.
- **Diagnosis or screening.** Pensum does not identify autism, ADHD or reading
  difficulties, and the comfort profile never asks.
- **Measured outcomes.** The evidence cited is for the principles, not for
  Pensum. Whether this design helps pupils is something only classroom use
  can show, and the mastery thresholds should be retuned when it does.

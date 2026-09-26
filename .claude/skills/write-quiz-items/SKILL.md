---
name: write-quiz-items
description: Author Pensum quiz items for one LK20 competence goal set (kompetansemålsett), producing a validated YAML file under data/items/. Use when asked to write, draft or extend quiz questions for a subject and checkpoint — e.g. "write items for NAT01-05 KV81", "add questions for norsk 4. trinn", "fill in the missing goal sets".
---

# Writing quiz items

You are writing practice questions for Norwegian schoolchildren, keyed to
official LK20 competence goals. The questions are **ours**; the goals are
Udir's, quoted verbatim elsewhere and never rewritten.

Your output is one YAML file: `data/items/<SUBJECT>/<GOALSET>.yaml`.

## Before writing anything

Read the goals you are writing for. Never work from the goal codes alone:

```bash
uv run python -c "
from pensum.catalogue.loader import Catalogue
gs = Catalogue.load().subject('MAT01-06').goal_set('KV1021')
print(gs.code, 'after year', gs.after_year, '| klasse', gs.applies_to_years)
for g in gs.goals:
    print(f'  {g.code}: {g.text.get(\"nob\")}')
"
```

Read `data/items/MAT01-06/KV1021.yaml` too. It is the hand-written reference
set and it defines the register — match it rather than inventing a new voice.

## The bar

**Every goal must be either tested or explicitly excused.** Validation enforces
it, so a goal you silently skip fails the build. That is deliberate: an omitted
goal reads as an oversight, whereas a recorded one reads as a decision.

**Refusing is often the right answer.** Many kompetansemål describe things a
pupil *does* — *utforske*, *samtale om*, *delta i*, *lage*, *reflektere over*.
No written question can check those; it can only check something adjacent and
pretend. When that is the case, add the goal to `not_assessable` with a reason
of at least a sentence, and write no items for it.

Do not pad. Two good questions beat five where three are strained. One or two
items per assessable goal is normal; three only where the goal genuinely has
that much range.

**A question must test the goal, not the reading.** If a pupil who knows the
material could still get it wrong because the sentence was long, rewrite it.

## Register, by year

| Years | How to write |
|---|---|
| 1–4 | One short sentence. Concrete nouns. No subordinate clauses. Numbers a child can hold in their head. `multiple_choice` almost always — reading and typing are still hard work. |
| 5–7 | Two sentences at most. Everyday contexts. |
| 8–10 | Normal prose, still plain. |

Contexts should be ordinary and Norwegian: school, home, outdoors, sport, shops,
weather, animals. Avoid anything assuming money to spend, foreign travel, a
particular family shape, a religion, or a body type. A pupil should never meet a
question that quietly excludes them.

Bokmål is the original; write it first and translate to English. Never translate
a competence goal — Udir's own wording is used for that, and paraphrasing a
legal text would be a correctness bug.

## Subject-specific care

**KRLE and samfunnsfag.** Test knowledge *about* religions, worldviews and
society — never adherence to one, and never whether the pupil holds an opinion.
"Hva feirer muslimer under id?" is a fact. "Hvorfor er det viktig å…" is not a
quiz question. Never present a contested political, moral or theological claim
as having one correct answer; if a goal's substance is the pupil's own reasoning
or discussion, that part is `not_assessable`. Norway's minorities — Sami people,
national minorities, immigrant communities, religious groups — are subjects of
these curricula and will be reading. Write as though they are.

**Engelsk.** The pupil is a Norwegian child learning English, so the `nb` prompt
is the instruction and the English is the material being tested. It is the one
subject where the two locales are not a translation of each other: a vocabulary
item asking for the English word cannot show the answer in its own Norwegian
prompt. Test comprehension, vocabulary and structure — not accent, and not
cultural trivia about English-speaking countries beyond what the goals name.

**Norsk.** Grammar, reading comprehension and vocabulary are testable. Writing,
presenting and discussing are not — those goals belong in `not_assessable`.
Where a goal covers both bokmål and nynorsk, remember the pupil may have either
as their hovedmål; do not assume which.

**Naturfag.** Facts and reasoning are testable; *utforske*, practical
investigation and lab work are not. Keep to settled science: a quiz for children
is not the place for a contested finding, and anything you are unsure of should
not be a question at all.

## Item types

- **`multiple_choice`** — at least 3 options, exactly one `correct: true`.
  Distractors must be plausible but clearly wrong to someone who knows the
  material. No trick questions, no near-identical options.
- **`numeric`** — a single number in `answer`. Set `tolerance` above 0 only for
  estimation or decimals.
- **`short_text`** — one or two words. List **every** reasonable spelling,
  synonym and inflection under `accept`. There is no model grading answers at
  runtime; anything not on the list is marked wrong. Prefer multiple choice
  unless the answer is genuinely a single unambiguous word.
- **`number_line`** — the pupil puts a marker on a tick of a number line rather
  than reading a sentence about one. Needs a `figure` of `kind: number_line`,
  and `answer` must land on one of its ticks: pick a `step` that reaches the
  answer, then `label_every` so the answer's own tick is unlabelled. `tolerance`
  is refused, because a marker that snaps has no near miss to forgive. Use it
  where the goal is *placing* a number rather than computing one; a question
  that merely mentions a number line is still a `numeric`.
- **Hands-on kinds**: `counters`, `ten_frame`, `base_ten`, `array`,
  `balance`. The pupil builds the answer on a board. The item has no `answer`,
  `choices` or `accept`; it has an `activity:` block instead, with an `alt`
  in both locales describing the board as it opens, and the kind's own
  parameters. The board's rules and every parameter are documented in the
  module docstrings under `src/pensum/items/primitives/`. For example:

  ```yaml
  - id: KM13232-02
    goal: KM13232
    type: base_ten
    stage: concrete          # optional: concrete | pictorial | abstract
    difficulty: 2
    prompt:
      nb: Vis 47 med så få klosser som mulig.
      en: Show 47 with as few blocks as you can.
    activity:
      alt:
        nb: En tom plassverdi-matte med en kolonne for tiere og en for enere.
        en: An empty place-value mat with a column for tens and one for ones.
      target: 47
      accept: canonical      # any_equivalent (default) also takes 3 tens 17 ones
  ```

  Without JavaScript the pupil is asked a number instead (how many in all, in
  each group, to add, in the box). When that default would be answered by the
  prompt itself -- "make 3 groups of 4" asking "how many in each group?" --
  add a `fallback:` with its own `prompt` and `answer`. Use these where the
  goal is *representing* or *building*: place value, grouping, make-ten,
  equals as a relation. A question that could be answered as well by typing is
  still a `numeric`.
- **Card kinds**, for every subject: `sort` (cards into `bins`, each card's
  `bin` declared; `venn: true` with two bins and `bin: both` for the overlap),
  `sequence` (`cards` in the right order; `cycle: true` grades up to
  rotation), `match` (`pairs` of `left` and `right`), `label` (a built-in
  `diagram` -- `water_cycle`, `skeleton`, `compass` -- and `labels`, each with
  the `slot` it goes on) and `highlight` (`unit: word` with a `text` whose
  answers are in `[brackets]`, or `unit: sentence` with `sentences`, each
  `mark: true` or not). Like the hands-on kinds they take an `activity:` block
  with an `alt`. There is no `fallback:`: without JavaScript the pupil picks
  the right arrangement from a few near misses the board makes itself. No two
  cards may read the same in either language; a norsk `highlight` text is the
  material and is shown as written in both. In KRLE and samfunnsfag, sort
  and match facts about traditions and society, never beliefs or opinions.

`difficulty` is 1–3 **relative to this checkpoint**. A hard year-2 question is
not a hard year-10 question.

## Templates: one question, many numbers

A file may also carry a `templates:` list beside `items:`. A template is a
question whose numbers are generated, so a pupil who meets it three times gets
three different flocks rather than three attempts at remembering one answer.

```yaml
templates:
  - id: KM13324-T1
    goal: KM13324
    difficulty: 3
    params:                       # the free numbers, and their ranges
      sheep: {min: 5, max: 14}
      hens: {min: 6, max: 18}
    derive:                       # everything else, as expressions
      animals: sheep + hens
      legs: 2 * hens + 4 * sheep
    require: ["animals >= 15"]    # combinations that survive
    answer: sheep
    prompt:
      nb: "På en gård er det {animals} dyr og {legs} bein..."
```

Four things to get right:

- **Every number the prose shows needs a name.** A sentence interpolates a
  value, so `2 × {animals}` is not available — derive `twice_animals` and read
  that. This is deliberate: the arithmetic belongs where the validator sees it.
- **Keep the domain reviewable.** The build enumerates every combination, so
  `MAX_DOMAIN` caps the cross product. A few hundred questions is plenty and a
  few thousand is a domain nobody could sign.
- **Use `require` to exclude the degenerate flock.** An answer of nought reads
  as a trick and the validator rejects it, as it does a fractional answer and
  two combinations producing the same sentence.
- **Norwegian inflection is yours to handle.** `{sheep} sauer` reads wrong when
  `sheep` is 1, and nothing detects it. Exclude 1 in `require`.

Numeric only, for now. A template is approved on an instance's review page as
one piece of content: the reviewer sees one variant live and a sample of the
others with their answers.

Every `explanation` should teach. A pupil who got it wrong should understand
why, not just be told they were.

## File shape

```yaml
# <Subject>, kompetansemål etter <N>. trinn (<SUBJECT> / <GOALSET>).
#
# Questions here are ours, not Udir's. The competence goals they test are quoted
# verbatim elsewhere; nothing in this file is official curriculum text.
---
subject: MAT01-06
goal_set: KV1021

items:
  - id: KM13228-01          # <goal code>-<two digits>, unique in the file
    goal: KM13228
    type: multiple_choice
    difficulty: 1
    prompt:
      nb: Hvilket tall er et partall?
      en: Which number is an even number?
    choices:
      - id: a
        text:
          nb: "7"
          en: "7"
      - id: b
        text:
          nb: "10"
          en: "10"
        correct: true
      - id: c
        text:
          nb: "13"
          en: "13"
    explanation:
      nb: 10 kan deles i to like grupper på 5. Da er det et partall.
      en: 10 splits into two equal groups of 5, which makes it even.

not_assessable:
  - goal: KM13229
    reason: >-
      Asks the pupil to explore numbers and counting through play, nature, art,
      music and children's literature. It describes an activity a teacher sets
      up, not knowledge a question can check.
```

### No review flag, ever

You are generating, not publishing. **There is no `reviewed:` key** — the
validator rejects one. Whether a question is shown to pupils is live data on
each running instance: an administrator approves it on that instance's review
page (`/<locale>/admin/gjennomgang`), and the decision is stored in the
instance's database with a fingerprint of the question. Nothing you write in a
file can publish anything, and editing an approved question sends it back for
review on every instance.

### YAML traps

All three of these have already broken this repo:

- **No flow mappings for prose.** `{nb: En sirkel, en ball}` parses "en ball" as
  a *key*, because Norwegian text is full of commas. Always use block style.
- **Quote bare numbers** in choice text: `nb: "7"`, not `nb: 7`.
- **Quote anything containing a colon followed by a space.** This bites hardest
  in maths, because Norwegian writes division as `12 : 3 = 4` — and to YAML a
  colon-space inside a plain scalar means "this is a mapping", so the file stops
  parsing. Write `nb: "12 : 3 = 4, fordi 3 × 4 = 12."` with the quotes, or use a
  block scalar:

  ```yaml
  explanation:
    nb: >-
      Vi deler 12 i 3 like grupper. 12 : 3 = 4, fordi 3 × 4 = 12.
  ```

**Run the validator before you report back.** It parses every file, so it
catches all three of these. A file that does not parse is not a finished file,
and "I wrote it but validation failed" is not done.

## Finishing

```bash
uv run python -m pensum.items.validate    # must print nothing and exit 0
uv run pytest -q
```

The validator checks the schema, that every `goal` code exists in that goal set,
that ids are unique, and that no goal is unaccounted for. Fix what it reports;
do not work around it.

To see your items in the running app, sign in as the local administrator (the
header offers it) and open the review page, or the quiz itself, where anything
not yet approved is labelled:

```bash
PENSUM_LOCAL_ADMIN=1 bin/run_local --native
```

Loopback only, never with an OIDC provider configured; see the README's
"Administering without an identity provider".

## Report back

State: how many items per goal, which goals you marked not assessable and why,
and anything you were unsure about. Flag any goal where you suspect the question
tests reading rather than the skill — that judgement is worth more than a clean
report.

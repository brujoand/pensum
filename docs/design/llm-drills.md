# Fact drills written by a language model (beta)

A new class of drill. An author writes the facts and a human reviews them. A
language model the instance operator runs turns those facts into multiple-choice
questions when a pupil starts the drill. The questions a pupil meets have not
been read by anyone first.

This is a design. Nothing here is implemented yet, and every name below is a
proposal.

## What changes, and what does not

Two statements elsewhere in Pensum are narrowed by this design.

| statement today | after this design |
|---|---|
| "There is no LLM at request time" (`items/schema.py`) | True unless the operator configures a model endpoint. With one, a fact drill calls it when the drill starts. |
| "Nothing is served to a pupil until an administrator has approved it" (README, *Honest limits*) | True for every existing kind of content. For a fact drill, what an administrator approves is the fact pack and the instruction set. The wording of each question is the model's. |

Three statements are untouched.

- **Grading is deterministic and offline.** The model writes questions. It never
  grades one. A fact drill question is an ordinary `multiple_choice` item and
  `QuizItem.is_correct` decides it.
- **The container starts with no environment set.** With no endpoint
  configured the drill is not offered and no outbound request is made.
- **Review state is live data.** Decisions about packs and instruction sets are
  stored in the instance database with a fingerprint, as for every other kind.

**Beta.** The feature is off by default, is turned on per instance, and is
labelled as beta on every page it appears on. The README entry under *Honest
limits* is reworded in the pull request that ships the first pupil-facing page,
and not before.

## The three layers of a prompt

```
 Contract          owned by code       output schema, "use only these facts",
                                       "cite the fact id", output language
 Instruction set   authored, reviewed  how to quiz: styles, distractors, age pitch
 Fact pack         authored, reviewed  what to quiz on
```

An author can change the second and third layers. The first is not authorable,
so no file in `data/` can change what the model is required to return.

### Fact pack

```yaml
# data/drills/SAF01-05/KV1150.yaml
subject: SAF01-05
goal_set: KV1150

packs:
  - id: saf-kv1150-stortinget
    goal: KM14697
    title:
      nb: Stortinget
      en: The Storting
    instructions: recall
    questions: 5
    facts:
      - id: f1
        nb: Stortinget har 169 representanter.
        en: The Storting has 169 members.
      - id: f2
        nb: Det er stortingsvalg hvert fjerde år.
        en: There is a parliamentary election every fourth year.
```

A fact is one sentence that is true on its own, with an id. Prose paragraphs
are not accepted. Atomic facts with ids buy three things:

- a question has to cite the fact it was written from, and the citation is
  checkable;
- the feedback after an answer shows the cited fact, which is reviewed text, so
  the model never writes an explanation;
- evidence can be kept per fact, so a later drill can ask about the facts a
  pupil missed.

A pack names one competence goal, as an item does, and the items validator's
rule applies: the goal must exist at that checkpoint. A pack needs at least as
many facts as `questions`, so that a drill does not ask about one fact twice.

A pack is Pensum's own text. It must never be mistakable for curriculum text,
for the reason `items/schema.py` gives.

### Instruction set

```yaml
# data/drills/instructions/recall.yaml
id: recall
distractors: 3
rules: |
  Ask one question per fact. Ask what the fact states, never why.
  Write for the age given. At most two short sentences per question.
  A wrong choice is the same kind of thing as the right one: a number
  where the answer is a number, a place where it is a place.
  A wrong choice is never true according to any fact in the list.
  Never ask which opinion, belief or party is right.
```

Shared between packs and reviewed once. It is read by the model and never shown
to a pupil, so it is written in English only. The pupil's age is derived from
the checkpoint, as `tools/generate_items.py` does, and passed as a parameter.

### Output

The endpoint is asked for JSON constrained by a schema, in one locale per call.

```json
{"questions": [
  {"fact": "f1",
   "prompt": "Hvor mange representanter har Stortinget?",
   "answer": "169",
   "distractors": ["150", "179", "200"]}
]}
```

The model returns one `answer` and a list of `distractors`. It does not return
a list of choices with an index for the right one. Exactly one correct choice
then holds by construction, and a wrong index is the commonest error a small
model makes with the other shape.

Each question becomes a `QuizItem`:

| `QuizItem` field | comes from |
|---|---|
| `id` | the pack id and a hash of the prompt and answer, so the same question has the same id on every instance |
| `goal`, `difficulty` | the pack |
| `type` | `multiple_choice` |
| `prompt`, `choices` | the model |
| `explanation` | the cited fact, verbatim |

The session engine, `display_choices`, scoring and rendering are reused
unchanged.

**Known compromise.** `AuthoredText` requires both locales and a generated
question has one. The adapter fills both fields with the same string and the
drill is pinned to the locale it was generated in.

## Checks between the model and the pupil

Run in this order. The first three are code. A question that fails any check is
dropped.

1. The response parses against the schema, and the `QuizItem` validators pass.
2. `fact` names a fact in the pack, and no two questions cite the same fact.
3. No two choices are equal after `_normalise`. Prompt and choices are within
   length bounds.
4. **Second pass.** The model is given the facts and the question without the
   key, and asked which choice the facts support. The question is dropped when
   its pick differs from the key, or when it reports that more than one choice
   is supported.

A batch that comes up short is retried once. After that the drill falls back,
in order, to cached questions for the pack, then to authored items for the
goal, then to a page that says the drill is not available right now.

What bounds the cost of a wrong key that passes all four checks: the feedback
shows the reviewed fact next to the model's question, so the pupil sees the
source the question claimed to be written from.

## Runtime

**Configuration.** Three settings, all unset by default.

| setting | meaning |
|---|---|
| `PENSUM_LLM_BASE_URL` | An OpenAI-compatible chat completions endpoint. Unset means fact drills are not offered. |
| `PENSUM_LLM_MODEL` | The model name sent in the request. |
| `PENSUM_LLM_API_KEY` | Optional bearer token. |

The request goes through `httpx`, which is already a dependency. No model SDK
is added.

**When the model is called.** Once per drill, for the whole batch, when the
pupil starts. The pupil sees a page that says the questions are being written.
There is no wait between questions, and no clock on the wait (principle 3).

**Cache.** Accepted questions are stored in the instance database, keyed by the
fingerprints of the pack and the instruction set, the contract version, the
model name and the locale. An edit to the pack or the instruction set changes
the key, so questions written from the old text are never served again. A
drill draws from the cache first and calls the model only for what is missing.

**After-the-fact review.** Every cached question is listed on the review page
under its pack. An administrator can reject one, which removes it from the
cache and records its id so it is not accepted again.

**What is sent.** The contract, the instruction set, the facts, the age and the
locale. Nothing about the pupil, and nothing a pupil typed. Every string in the
prompt is reviewed text, so a pupil has no way to put words in front of the
model.

**What the pupil is told.** The drill page says, in literal words (principle
7), that the questions were written by a machine from the facts shown, and that
the feature is being tried out.

## Where the code goes

| module | holds |
|---|---|
| `pensum.drills.schema` | `Fact`, `FactPack`, `InstructionSet` |
| `pensum.drills.loader` | loads and validates `data/drills/` |
| `pensum.drills.prompt` | builds the messages and the response schema; owns the contract |
| `pensum.drills.client` | the one outbound call |
| `pensum.drills.verify` | the four checks, and the adapter to `QuizItem` |
| `pensum.drills.store` | the cache table and rejected ids |
| `pensum.review` | two new kinds: `pack`, `instructions` |
| `pensum.web.drill_routes` | start, wait, hand over to the session engine |
| `tools/eval_drills.py` | maintainer tooling: runs every pack N times against an endpoint and reports the reject rate per check and the time per batch |

## Build order

Each step is its own pull request and is usable on its own.

1. **Content.** Schema, loader, validator, the two review kinds, one pack. No
   model involved.
2. **Generation, offline.** Prompt, client, checks, and `tools/eval_drills.py`.
   No web surface. The reject rates from this step decide whether a given model
   is good enough to continue with.
3. **The drill.** Cache, routes, the wait page, the beta label, and the README
   rewording.

## Open decisions

1. **Whether the endpoint honours schema-constrained output.** Servers differ.
   If it does not, check 1 does the work and the reject rate rises. Step 2
   measures it.
2. **How long a batch takes.** Unmeasured. If the wait is longer than a pupil
   will sit through, the cache is filled ahead of time by an administrator and
   the pupil-facing call becomes the exception.
3. **Whether the second pass uses the same model.** A model that wrote an
   ambiguous question may also fail to see the ambiguity. A second, different
   model is a configuration cost that step 2's numbers either justify or do
   not.
4. **Free-text answers graded by the model.** Not in this design. It would put
   the model on the grading path, which is the property this design keeps.

# XP

The first mechanic of the game layer (see
[principles.md](principles.md#what-gamification-does)). A signed-in pupil earns
XP for correct answers and for finishing things. XP is never lost, never spent,
and never shown to another pupil.

## Who earns it

Only a signed-in pupil. When a deployment has sign-in configured
(`Settings.auth_enabled`), every exercise requires it: quizzes, the placement
test, reading aloud, writing and listening. A deployment without sign-in keeps
every exercise open and has no XP.

## What earns it

| activity | earns | when |
|---|---|---|
| quiz, topic drill, placement test | 10 per correct answer, 20 for finishing | once, when the result page is first shown for a finished run |
| reading aloud | 20 for reaching the last word | when the reading is marked |
| writing | 20 for finishing a prompt | when the tracing is scored |
| listening and spelling | 10 per correct answer | when the answer is marked |

- **Hints cost nothing.** They never lower the score, so they never lower XP.
- **A wrong answer earns 0 and takes nothing away.**
- **Speed earns nothing.** No rule reads how long anything took.
- **Reading XP does not come from stars.** Stars come from a recogniser that
  mishears children, dialects and second-language speakers. Finishing the
  passage is the one reading result that cannot mislead.
- **Sensitive skills earn nothing.** An item whose skill is `sensitive: true`
  gives 0, in line with design decision 10: sensitive topics are never
  gamified.
- **An abandoned run earns nothing.** A run that never reaches its result page
  never awards its per-answer XP either, because quiz XP is awarded at the
  result.
- **Repeating earns again.** A pupil who retakes a quiz earns its XP again.
  There is no cap. The class grid shows a teacher where XP comes from (below),
  and a cap waits until there is usage to set one from.

## Where it is stored

One ledger table in the same SQLite file as `attempts` and `evidence`, created
with `CREATE TABLE IF NOT EXISTS` like they are:

| column | what it is |
|---|---|
| `user_sub` | the pupil |
| `source` | `quiz`, `placement`, `reading`, `writing` or `listening` |
| `subject` | the subject code, so the class grid can show XP per subject |
| `ref` | what earned it: the attempt hash, or the passage id, prompt id or listening goal set plus a random token |
| `amount` | XP for this row |
| `recorded_at` | when it was earned |

`(user_sub, source, ref)` is the primary key, so reloading a result page cannot
award twice. A total is the sum of the rows, never a stored counter.

## Where it is shown

- **The pupil:** the quiz result page and the reading, writing and listening
  results show "+N XP" and the new total. The pupil map shows the total.
- **The teacher:** the class grid (`/{locale}/admin/klasse/{subject}`) adds two
  columns per pupil: XP in this subject this week, and in total.
- **Other pupils:** never.

There are no levels yet. XP is a number that grows.

## Build order

1. Require sign-in for every exercise when sign-in is configured.
2. The ledger, the awarding rules above, and the pupil-facing totals.
3. The XP columns on the class grid.

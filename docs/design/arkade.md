# Arkade

Short games for practising what has to be remembered: spelling, number facts,
times tables, countries. A pupil chooses to go to Arkade. It is a separate place
from the exercises, and the exercises keep every rule they have today.

Built so far: the pupil's year and timer setting (`pensum.scores.profile`), the
items (`pensum.arkade`), and the balloon game at `/{locale}/arkade`
(`pensum.web.arkade_routes`, `static/arkade-balloons.js`) and memory pairs for
sums (`static/arkade-pairs.js`). Invaders is a proposal.

## What changes, and what does not

| statement today | after this design |
|---|---|
| Rule 3: "No countdown, no speed bonus" on any task | No countdown on any exercise. Arkade games have a drawn timer that the pupil can switch off. There is still no speed bonus anywhere. |
| Game layer: "timers, lives" wait on "a run mode that leaves the untimed default intact" | Arkade is that mode. Timers are in it, and balloons have three lives. |

## The rules

1. **Arkade is opt-in.** A pupil reaches it from its own page. No exercise, run,
   mission or assignment sends a pupil there.
2. **The timer is on by default in Arkade, and the pupil can switch it off.** The
   choice is stored per pupil, beside their year, and applies to every game.
   Switching it off changes nothing else: the same items, the same XP.
3. **The timer is drawn, never written as digits.** A balloon growing or a disc
   shrinking, as rule 5 already requires of the break timer. Where calm mode or
   the device's reduced-motion setting stops animation, the timer cannot be
   drawn, so it does not run: the balloons wait, as with the timer off.
4. **Running out of time earns 0 and is not evidence.** A popped balloon or a
   target that got past is not a wrong answer. It is not written to `evidence`,
   so it never lowers mastery.
5. **No speed bonus.** 10 XP per point (a true balloon let fly, a pair found) and
   20 for finishing a round. A round finished slowly earns the same as one
   finished fast.
6. **A round has a fixed length, shown before it starts.** Rule 5 applies: the
   pupil sees how many items there are. Balloons have three lives: a wrong
   answer spends one, and the third ends the round early. Memory has none.
7. **Every answer ends on the correct form.** Spelling games show misspelt
   words, so the right spelling is always the last thing on screen, whatever
   the pupil picked.
8. **Content comes from the pupil's year,** through `checkpoint_for(subject,
   grade)`, so a 3rd-grader gets 3rd-grade items.
9. **An item on a sensitive skill earns 0,** as it does in a quiz
   ([xp.md](xp.md)). Design decision 10: sensitive topics are never gamified.
10. **No pupil sees another pupil's results.** Rule 4. The teacher's class grid
    shows Arkade XP with the rest.

## Items

Every game draws from one item shape: a **rule**, a set of **candidates**, and
**which candidates match**. A generator produces items for a subject and a year.
A game decides only how they look.

| generator | example | where the content comes from |
|---|---|---|
| arithmetic (`pensum.arkade.arithmetic`) | `5 : 1 = 5` is true, `5 : 1 = 1` is false | generated: adding and subtracting within 20 for years 1-2, within 100 and the 2, 5 and 10 tables for year 3, all tables and division from year 4. Fractions and divisibility are not generated yet |
| spelling (`pensum.arkade.spelling`) | the word `kjøleskap` is spoken; `kjøleskap` and `kjøleskapp` are shown | the words of the passages approved for the pupil's checkpoint, Norwegian or English, and a wrong spelling from `pensum.listening.confusable`, as in the listening exercise |
| letter class | consonant or vowel | generated |
| pairs | `7 × 8` and `56`, a country and its capital, `hund` and `dog` | generated for numbers; word and fact lists for the rest |
| facts | a true and a false statement | the fact packs under `data/drills/`, plus a false version of each fact, reviewed like any other content |

A spelling item is spoken first, so a wrong spelling that is also a real word
(`bok` beside `bak`) is a fair question: the pupil is asked which one is the
word they heard, not which one is not a word.

An item names the skill it practises where one fits closely, and an answer then
becomes one `evidence` row under that skill, as a quiz answer does. Where none
fits, the item names none and its answers record no evidence. Adding within 100
has none, because the year-3 adding skills are about choosing and explaining a
method. Spelling after 2. trinn has none, because those skills each name one
pattern, such as kj and skj.

## Games

| game | the pupil | item shape | round |
|---|---|---|---|
| balloons | sees one balloon with a statement, or hears a word and sees one spelling of it. Swipes left (or ←) to let it fly away if it is true, right (or →) to send it up to the needle if it is not | 1 balloon at a time, true or false about half the time each. A true one flown earns a point; popping a false one is right and earns nothing; getting either wrong costs one of three lives | 8 balloons, or fewer if the lives run out; with the timer on, each rises for 60 seconds and drifts off the top, which earns nothing and costs no life |
| memory pairs | turns cards two at a time to find a sum and its answer | 6 pairs, 12 cards, no two answers alike | one board; with the timer on, a bar empties over 2 minutes. A pair found earns 10 XP; a pair not found when time runs out earns 0 and is turned up, so the board ends on every right form. A wrong turn is forgetting where a card lay, so a board records no evidence |
| invaders | shoots only the targets matching the rule ("divisible by 3", "consonants") | a stream of candidates | 12 targets; with the timer on, targets advance, and a match that gets past earns 0 |

Later, not ruled out: a word search for themed lists, and falling words the
pupil types. Typing is the only game here where a pupil produces a spelling
rather than recognises one.

## Build order

1. The pupil's year. Done: `pensum.scores.profile`.
2. The item model, the arithmetic generator and the spelling generator.
   Done: `pensum.arkade`.
3. Balloons, the Arkade page and the timer setting. Done.
4. Memory pairs, for sums. Done. Word pairs (`hund` and `dog`) and capitals wait on word and fact lists.
5. Invaders.
6. Fact items, once the false versions are written and reviewed.

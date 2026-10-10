# Arkade

Short games for practising what has to be remembered: spelling, number facts,
times tables, countries. A pupil chooses to go to Arkade. It is a separate place
from the exercises, and the exercises keep every rule they have today.

Built so far: the pupil's year and timer setting (`pensum.scores.profile`), the
items (`pensum.arkade`), and the balloon game at `/{locale}/arkade`
(`pensum.web.arkade_routes`, `static/arkade-balloons.js`), memory pairs for
sums (`static/arkade-pairs.js`), and sorting for odd and even numbers and for
vowels and consonants (`pensum.arkade.sorting`, `static/arkade-sort.js`).

## What changes, and what does not

| statement today | after this design |
|---|---|
| Rule 3: "No countdown, no speed bonus" on any task | No countdown on any exercise. Arkade games have a drawn timer that the pupil can switch off. There is still no speed bonus anywhere. |
| Game layer: "timers, lives" wait on "a run mode that leaves the untimed default intact" | Arkade is that mode. Timers are in it, and balloons and sorting have three lives. |

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
5. **No speed bonus.** 10 XP per point (a true balloon let fly, a pair found, a
   card put in its pile) and
   20 for finishing a round. A round finished slowly earns the same as one
   finished fast.
6. **A round has a fixed length, shown before it starts.** Rule 5 applies: the
   pupil sees how many items there are. Balloons and sorting have three lives:
   a wrong answer spends one, and the third ends the round early. Memory has
   none.
7. **The correct form is one press away, and not pushed.** A right answer
   says "Riktig!" and a wrong one "Feil!", and nothing more: a sentence about
   which way the balloon should have gone was read as confusing, and the life
   lost is already shown by the hearts. The next balloon then comes by itself,
   and a question mark gives the correct form of the balloon before. Spelling
   games show misspelt words, so that question mark is where the right
   spelling is. A balloon that drifted away is not a mistake, and it still
   shows its correct form as it goes. Sorting does the same: the question
   mark gives the card before and the pile it belongs in.
8. **Content comes from the pupil's year,** through `checkpoint_for(subject,
   grade)`, so a 3rd-grader gets 3rd-grade items. A game is offered to the
   years its goal belongs to: sorting odd from even is a goal of year 2, so
   year 3 is not offered it.
9. **An item on a sensitive skill earns 0,** as it does in a quiz
   ([xp.md](xp.md)). Design decision 10: sensitive topics are never gamified.
10. **No pupil sees another pupil's results.** Rule 4. The teacher's class grid
    shows Arkade XP with the rest.
11. **A game being played fills the screen.** The whole game fits the window
    and the page does not scroll during a round. The site footer is hidden
    while it is played; the header stays.

## Items

Every game draws from one item shape: a **rule**, a set of **candidates**, and
**which candidates match**. A generator produces items for a subject and a year.
A game decides only how they look.

| generator | example | where the content comes from |
|---|---|---|
| arithmetic (`pensum.arkade.arithmetic`) | `5 : 1 = 5` is true, `5 : 1 = 1` is false | generated, a different set of sums for each year: see [Arithmetic by year](#arithmetic-by-year) |
| spelling (`pensum.arkade.spelling`) | the word `kjøleskap` is spoken; `kjøleskap` and `kjøleskapp` are shown | the words of the passages approved for the pupil's checkpoint, Norwegian or English, and a wrong spelling from `pensum.listening.confusable`, as in the listening exercise |
| sorting (`pensum.arkade.sorting`) | `17` is spoken and shown, and belongs in *odd*; `Ø` belongs in *vowel* | generated, and offered to years 1 and 2 only: numbers to 20 for year 1 and to 100 for year 2; the 29 letters of the Norwegian alphabet. Spoken words sorted by a sound (`ch` beside `sh`) need a word list, reviewed like any other content, and are not generated |
| pairs | `7 × 8` and `56`, a country and its capital, `hund` and `dog` | generated for numbers; word and fact lists for the rest |
| facts | a true and a false statement | the fact packs under `data/drills/`, plus a false version of each fact, reviewed like any other content |

A spelling item is spoken first, so a wrong spelling that is also a real word
(`bok` beside `bak`) is a fair question: the pupil is asked which one is the
word they heard, not which one is not a word.

An item names the skill it practises where one fits closely, and an answer then
becomes one `evidence` row under that skill, as a quiz answer does. Where none
fits, the item names none and its answers record no evidence. Adding within 100
has none, because the year-3 adding skills are about choosing and explaining a
method. Whole tens, table facts with a ten in them and fractions of one
denominator have none for the same reason: their goals are about strategies. Vowels and consonants have none, because the letter skills are about the
sound a letter has. Spelling after 2. trinn has none, because those skills each name one
pattern, such as kj and skj.

## Arithmetic by year

A year drills the sums its own competence goals name, and no other year's.
The numbers are small first, then larger, then fractions and decimals, then
negative numbers and powers. The goals are those of LK20 for mathematics
(MAT01-06), read from `data/curriculum`.

| year | sums | example | goal |
|---|---|---|---|
| 1 | adding and subtracting to 10 | `3 + 4 = 7` | KM13234 |
| 2 | adding and subtracting to 20 | `13 − 5 = 8` | KM13234 |
| 3 | adding and subtracting to 100 | `47 + 26 = 73` | KM13243 |
| 3 | the 2, 5 and 10 tables | `5 · 7 = 35` | KM13245 |
| 3 | doubling and halving, to 100 | `34 + 34 = 68`, `68 : 2 = 34` | KM13254 |
| 4 | the whole table | `7 · 8 = 56` | KM13258 |
| 4 | division inside the table | `56 : 8 = 7` | KM13257 |
| 4 | whole tens added and subtracted, to 1000 | `340 + 250 = 590` | KM13258 |
| 5 | table facts with a ten in them | `6 · 40 = 240`, `240 : 6 = 40` | KM13268 |
| 5 | fractions of one denominator, added and subtracted | `1/5 + 2/5 = 3/5` | KM13268 |
| 5 | a fraction, a decimal and a percent that are the same amount | `1/4 = 0,25`, `0,25 = 25 %` | KM13265 |
| 6 | tenths added and subtracted | `0,7 + 0,5 = 1,2` | KM13276 |
| 6 | tenths times a whole number | `0,4 · 6 = 2,4` | KM13276 |
| 6 | a decimal times or divided by 10 or 100 | `3,5 · 10 = 35` | KM13276 |
| 7 | adding and subtracting across zero | `3 − 8 = −5` | KM13292 |
| 7 | converting between fraction, decimal and percent | `3/8 = 37,5 %` | KM13286 |
| 7 | the order of operations | `2 + 3 · 4 = 14` | KM13287 |
| 8 | squares, cubes and powers of ten | `7² = 49`, `10⁴ = 10000` | KM13297 |
| 8 | square roots of perfect squares | `√81 = 9` | KM13297 |
| 9 | what years 7 and 8 drilled | | none |
| 10 | the square theorems as a way to calculate | `21² = 441`, `19 · 21 = 399` | KM13318 |
| 10 | powers and square roots | | KM13297 |

No goal of year 9 is arithmetic with numbers alone: its goals are geometry,
statistics, probability and compound units. Year 9 therefore keeps powers,
roots, negative numbers and the order of operations.

A false statement shows the mistake the goal's pupils make, not a number
picked near the answer: denominators added (`1/5 + 2/5 = 3/10`), tenths read as
hundredths (`0,7 + 0,5 = 0,12`), a zero put on the end of a decimal
(`3,5 · 10 = 3,50`), a sign dropped (`3 − 8 = 5`), a sum worked left to right
(`2 + 3 · 4 = 20`), an exponent multiplied (`7² = 14`), the middle term of a
square forgotten (`21² = 401`).

A page in Norwegian writes a decimal comma and a page in English a decimal
point. The item is the same either way.

## Games

| game | the pupil | item shape | round |
|---|---|---|---|
| balloons | sees one balloon with a statement, or hears a word and sees one spelling of it. Swipes left (or ←) to let it fly away if it is true, right (or →) to burst it if it is not | 1 balloon at a time, true or false about half the time each. A true one flown earns a point; popping a false one is right and earns nothing; getting either wrong costs one of three lives | 8 balloons, or fewer if the lives run out; with the timer on, each rises for 60 seconds and drifts off the top, which earns nothing and costs no life |
| memory pairs | turns cards two at a time to find a sum and its answer | 6 pairs, 12 cards, no two answers alike | one board; with the timer on, a bar empties over 2 minutes. A pair found earns 10 XP; a pair not found when time runs out earns 0 and is turned up, so the board ends on every right form. A wrong turn is forgetting where a card lay, so a board records no evidence |
| sorting | hears a number or a letter, sees it on a card, and puts it in a pile: taps the pile, presses its number, or with two piles the arrow key on its side | 1 card at a time over 2 to 4 piles, each pile asked for about as often as the others, no card twice. A card put right earns a point and stays in its pile; a wrong pile costs one of three lives | 8 cards, or fewer if the lives run out; with the timer on, a bar empties over 2 minutes. A card not reached when time runs out earns 0 and is not evidence |

A sorting card is shown as well as spoken, so a round can be played where the
browser has no voice for the language. Sorting by a sound is different: there
the word on the card would give the answer away, so it will be heard only.

Later, not ruled out: a word search for themed lists, and falling words the
pupil types. Typing is the only game here where a pupil produces a spelling
rather than recognises one.

## Build order

1. The pupil's year. Done: `pensum.scores.profile`.
2. The item model, the arithmetic generator and the spelling generator.
   Done: `pensum.arkade`.
3. Balloons, the Arkade page and the timer setting. Done.
4. Memory pairs, for sums. Done. Word pairs (`hund` and `dog`) and capitals wait on word and fact lists.
5. Sorting, for odd and even numbers and for vowels and consonants, in years
   1 and 2. Done.
   Spoken words by sound (`ch` and `sh`, `kj` and `skj`) wait on word lists.
6. Fact items, once the false versions are written and reviewed.

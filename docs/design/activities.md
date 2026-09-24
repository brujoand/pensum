# Activity primitives

The engine's vocabulary. Every activity in every subject is one of these,
filled with content. The set is kept small on purpose: each primitive is a
piece of interaction code with its own tests, keyboard model and no-JavaScript
fallback, and a pupil who has learned one primitive in matematikk already knows
how to use it in naturfag.

Four exist today as quiz item kinds (`multiple_choice`, `numeric`,
`short_text`, `number_line`), and three as standalone exercises (read aloud,
trace a letter, listen and spell). Everything else is proposed.

## Rules every primitive follows

1. **Direct manipulation first, typing last.** The pupil moves, groups, cuts,
   places, sorts or builds. A typed number is the abstract stage of a skill,
   reached after the concrete and pictorial stages, never the only way in.
2. **Grading is a pure function of the final state.** See
   [architecture.md](architecture.md#grading-is-a-function-of-final-state).
   Nothing is timed, and a slow pupil and a fast one are scored the same.
3. **Undo is always available and never counted against the pupil.** Trying
   things is the point of a manipulative.
4. **Check is a button.** The pupil decides when they are done. Nothing grades
   itself mid-drag, because a manipulative that flashes red while a child is
   still thinking punishes exploration.
5. **Every pointer action has a keyboard equivalent,** and every drag has a
   tap-tap equivalent (tap the thing, tap where it goes). Tap-tap is also the
   motor-friendlier default on touch screens.
6. **Objects snap.** Counters snap to a ten-frame cell, a marker to a tick, a
   label to its slot. Near misses caused by fine-motor control are not wrong
   answers.
7. **Feedback shows, then says.** On a wrong answer the primitive first shows
   what the pupil built next to what was asked (*you made 43, the task was 34*)
   and then offers the next hint. No red cross, no buzzer, no shake animation.
8. **No colour carries meaning alone.** The existing figure rule (no colour in
   the SVG, everything from stylesheet variables) extends to every primitive.
   State is also carried by shape, pattern or a label.
9. **Themes are cosmetic.** A counter can be a dot, a sheep, a train carriage or
   a planet. The count, the layout and the grading are identical, so a theme
   never changes what a task tests.

## Catalogue

CRA column: which representation stage the primitive serves, concrete (C),
pictorial (P) or abstract (A). One primitive often covers two stages by showing
or hiding its objects.

### Number and quantity

| primitive | the pupil | graded on | CRA | used for |
|---|---|---|---|---|
| `counters` | taps to add or remove counters on a mat or ten-frame, drags them into groups | count, and group sizes if asked | C, P | counting, subitising, odd/even, grouping, sharing division |
| `ten_frame` | fills one or two ten-frames | count and fill pattern | C, P | numbers to 20, make-ten, doubles |
| `base_ten` | drags units, rods and flats onto a place-value mat; ten units can be swapped for a rod and back | represented value, optionally canonical form | C, P | place value, regrouping, addition and subtraction with carrying |
| `number_line` (exists) | drags a marker to a tick | the tick | P, A | ordering, rounding, fractions and decimals on a line |
| `jumps` | draws jumps along a number line: start, size, direction | landing point, and jump sizes if asked | P | counting on and back, skip counting, adding tens, negative numbers |
| `array` | drags a corner to size a rows × columns grid, or splits one array into two | rows, columns, split | C, P | multiplication, commutativity, distributivity, area |
| `bar_model` | draws bars, cuts a bar into equal parts, shades parts, stacks bars to compare | part counts, shaded count, bar lengths | P | fractions, ratio, word problems, comparing quantities |
| `fraction_strips` | stacks strips of halves, thirds, quarters ... under a whole | which strips, and whether they match the whole | C, P | equivalence, adding fractions, comparing |
| `balance` | puts weights and boxes (unknowns) on two pans until it balances; can remove the same from both sides | balanced, and the value of the box | C, P, A | equals as a relation, equations, inequalities |
| `money` | drags coins and notes into a purse or onto a till | total, and change given | C | addition, subtraction, decimals, personal finance |

### Space, shape and measure

| primitive | the pupil | graded on | CRA | used for |
|---|---|---|---|---|
| `geoboard` | stretches bands between pegs on a dot grid | the polygon: vertices, side lengths, area, perimeter | C, P | shapes, area, perimeter, right angles, symmetry |
| `transform` | slides, flips or turns a shape on a grid with handles | final position and orientation | P | congruence transformations, symmetry |
| `coordinates` | places points on a grid, or moves a character to a point | the points | P, A | coordinates, plotting, graphs |
| `measure` | lines up a ruler, reads a scale, fills a jug, drags clock hands | reading or set value, with a declared tolerance in the instrument's own unit | C, P | length, mass, volume, time |
| `shape_sort` | drags 2D or 3D shapes into property bins; can rotate a 3D shape | bin contents | C, P | properties of shapes, faces, edges, corners |

### Data, chance and algorithms

| primitive | the pupil | graded on | CRA | used for |
|---|---|---|---|---|
| `tally_chart` | taps to tally, then drags bars to build a bar chart from the tally | bar heights, axis labels | P | data collection, presentation |
| `read_chart` | taps the bar, point or cell that answers the question | the element | P, A | reading tables and diagrams, all subjects |
| `trials` | spins a spinner or rolls dice 1, 10 or 100 times; the tally fills in | a prediction made before the trials, compared after | P | chance, probability, fractions as frequency |
| `step_code` | arranges command tiles (step, turn, repeat, if) to move a character through a grid | the character reaches the goal; optionally max tiles | P, A | step-by-step instructions, algorithms, loops, conditions |

### Language

| primitive | the pupil | graded on | CRA | used for |
|---|---|---|---|---|
| `sound_boxes` | drags a counter into a box for each sound heard (Elkonin boxes), then letters into the boxes | box count, then letters | C, P | phonemic awareness, sound–letter mapping |
| `blend` | slides letter tiles together; each tile says its sound when touched, and the word is said once joined | the word formed | P | blending, decoding, both norsk and engelsk |
| `word_build` | drags letters, syllables or morphemes into a word frame | the word | P | spelling, compounds, inflection |
| `sentence_build` | drags word tiles into order and drops punctuation where it goes | the sentence, within declared alternatives | P | syntax, punctuation, capitals |
| `highlight` | taps words or sentences in a text that meet a criterion | the set of tapped spans | P | word classes, facts vs opinions, finding evidence, reading comprehension |
| `read_aloud` (exists) | reads a passage aloud | words recognised, pace band | A | fluency |
| `trace` (exists) | traces a letter with a finger | strokes, order, placement | C | letter formation |
| `listen_spell` (exists) | hears a word, picks or types its spelling | the spelling | A | spelling patterns |
| `dialogue` | picks the next line in a short chat between two characters; the partner answers | each pick, from declared acceptable lines | P | conversation, polite phrases, turn-taking, conflict resolution |

### Knowledge and reasoning (all subjects)

| primitive | the pupil | graded on | CRA | used for |
|---|---|---|---|---|
| `sort` | drags cards into two to four labelled bins, or a Venn diagram | bin contents | P | classifying: materials, organisms, word classes, facts/opinions, religions' festivals |
| `sequence` | drags cards into order along a line or a cycle | order (cycles graded up to rotation) | P | life cycles, water cycle, story events, historical timelines, procedures |
| `label` | drags labels onto slots on a picture or map | label per slot | P | body systems, plant parts, maps, the solar system |
| `match` | draws a line between two columns | the pairs | P, A | representations of the same number, word ↔ picture, term ↔ definition |
| `cause_effect` | links cause cards to effect cards with arrows | the arrows | P | naturfag, samfunnsfag, consequences |
| `explore_sim` | predicts, then changes one slider and watches a simulation, then answers | the prediction is recorded, the answer is graded | P | one-variable phenomena: shadows, moon phases, states of matter, energy chains |
| `perspective` | reads a short situation and picks which reason a named character would give | the pick, where the character's view is a fact about the text | P | RLE, samfunnsfag, norsk: whose view, not which view is right |
| `multiple_choice`, `numeric`, `short_text` (exist) | picks or types | exact match | A | the abstract stage of anything, and every no-JS fallback |
| `mission` | does an off-screen task from a checklist and ticks steps | teacher or self confirmation | C | every goal a screen cannot check: see [architecture.md](architecture.md#missions-goals-a-screen-cannot-check) |

## Notes on the primitives that carry the most

### `base_ten`

The swap is the lesson. Ten units dropped on the ones column can be tapped to
become one rod, which animates (or, in calm mode, cross-fades) into the tens
column; tapping a rod breaks it back into ten units. A pupil who does 52 − 17 by
breaking a rod has done regrouping without the word being said. The
`accept: any_equivalent` flag decides whether 2 tens and 14 ones counts as 34:
yes while learning exchange, no when the skill is canonical form.

Without JavaScript: the same mat as a static figure, with a numeric answer.

### `balance`

The equals sign is a relation, and LK20 names this at 2. trinn (KM13242). A
pan balance shows it: `3 + 4 = ☐ + 5` is a balance with 3 and 4 on the left, 5
and a box on the right. Tapping "take the same from both sides" is solving an
equation, and at 8.–10. trinn the same primitive shows `2x + 3 = 11` with two
boxes. One primitive, eight years of the curriculum.

### `step_code`

Unplugged-style programming: tiles, a grid, a character. LK20 introduces
algorithms at 2. trinn (*create and follow rules and step-by-step instructions*)
and has pupils read Python by 10. The primitive shows the tile program and,
from 7. trinn, the equivalent text beside it, so the move from blocks to text is
one more representation of the same program rather than a new subject.

### `explore_sim`

Deliberately small. One slider, one observable, one question. PhET does broad
open simulations far better than Pensum could, and teachers already use them.
The primitive's job is the predict–observe–explain loop, with the prediction
recorded first so it cannot be revised after seeing the answer.

### `perspective`

RLE and samfunnsfag ask pupils to understand other views without Pensum ruling
which view is correct. The primitive is graded only on what the text supports:
*which reason would Amir give*, when the text says what Amir believes. Opinion
questions (*which is right?*) are not items. They belong in a classroom
conversation, and the mission card is how Pensum hands them there.

## Hint ladder

Every activity declares an ordered hint ladder. The engine walks it one step per
request or per wrong check, and the steps are chosen from a fixed set so
feedback wording is consistent across subjects:

1. **Restate** the task in fewer words, read aloud.
2. **Show** what the pupil built next to what was asked.
3. **Step down a stage**: abstract → pictorial → concrete.
4. **Partial**: do the first step (place the first ten, the first word).
5. **Worked example** on a parallel task with different numbers, then back.

A pupil who reaches step 5 is not failed. The attempt counts as *exploring*
evidence, and the next task in the run is the same skill at the lower stage.

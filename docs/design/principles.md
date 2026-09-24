# Design principles

The rules every subject design and every activity is held to. Each one states
what it requires, how strong the evidence behind it is, and where it shows up
in the architecture.

The core audience is teachers, and pupils with mild autism or ADHD. Nothing here
is a separate "special needs mode". A design that is calm, predictable, visual
and untimed costs a typical pupil nothing, and Udir frames *tilpasset
opplæring* as a duty to every pupil, not a track for some
([Udir](https://www.udir.no/laring-og-trivsel/tilpasset-opplaring/)). The
comfort profile in [architecture.md](architecture.md#comfort-profile-accommodations)
adjusts degree, never kind.

Evidence strength uses four labels. **Strong**: meta-analytic or designated
evidence-based practice. **Moderate**: consistent smaller studies, or a
meta-analysis in an adjacent population. **Weak**: thin, mixed or contested.
**Consensus**: accessibility or clinical practice guidance without outcome
trials. Citations are listed at the end. They were gathered by a literature
search for this document and should be re-checked before being quoted
elsewhere.

## The rules

### 1. Concrete, then pictorial, then abstract

A new idea is met first as something to move (blocks, counters, strips, a
balance), then as a drawing of it, then as symbols. Abstract-only practice comes
last, and a wrong answer steps back down a stage.

- **Evidence: moderate.** Several single-case studies with autistic pupils and
  pupils with learning disabilities show acquisition and maintenance gains from
  CRA sequencing [1][2][3]. Virtual manipulatives show a moderate positive effect
  against other instruction in a 66-report meta-analysis, with no settled
  winner against physical ones [4].
- **In the design:** `stages` on every skill; *secure* requires two stages; hint
  step 3 is "step down a stage"; every primitive is tagged C/P/A.
- **Limit:** a screen is not a hand. Physical manipulatives and missions carry
  the concrete stage wherever the classroom has them.

### 2. Progress by mastery, not by the calendar

A pupil moves on when the evidence says they can, not when the week ends.

- **Evidence: moderate to strong.** A 108-study meta-analysis of mastery
  learning found d ≈ 0.61 for lower-attaining pupils and d ≈ 0.40 for others,
  largest in mathematics [5]. Bloom's "two sigma" figure is not supported at
  scale and is not claimed here [6].
- **In the design:** the mastery states; skill selection by `needs`; the
  assignment model has no due dates.

### 3. No clock on any task

No countdown, no speed bonus, no "beat your time". A slow correct answer earns
exactly what a fast one does.

- **Evidence: moderate, by inference.** Time pressure is the mechanism most
  associated with the anxiety these pupils report, and the research on timers
  that *did* help was about visual timers around transitions, not about tasks
  [7]. Pensum's reading screen already refuses to make a target of its speed
  band.
- **In the design:** runs are measured in stones, not minutes. The only timer in
  the product is an optional analogue-style break timer, which rule 5 covers.

### 4. No ranking against other pupils

No leaderboards, no class league tables, no "you beat 80% of pupils".

- **Evidence: moderate.** Leaderboard studies report that a low rank demotivates
  more than no feedback at all, reduces effort, and in at least one longitudinal
  study lowered results [8][9]. The pupils most likely to sit low on a
  leaderboard are the core audience.
- **In the design:** rewards are personal: the map, personal bests, collections.
  The teacher sees a class grid; pupils never see each other.

### 5. Always know what is happening, what is next, and when it ends

Every run shows its length before it starts. The next task can be previewed.
A transition is announced before it happens. Breaks are offered, never forced,
and progress is kept.

- **Evidence: consensus, with moderate support for structure.** Structured
  teaching (TEACCH) shows gains across several domains in a 20-study
  meta-analysis [10]. Transition warnings specifically have no outcome trial;
  they are near-universal practice guidance. Visual timers around transitions
  reduced anxiety and off-task behaviour, more so for pupils at ADHD risk,
  without changing accuracy [7].
- **In the design:** stones; "show what's next"; the break card; the optional
  break timer drawn as a shrinking disc, never as digits.

### 6. Short, chunked, one thing at a time

A run is five to eight tasks. A task asks one thing. A multi-step problem can be
shown one step per screen.

- **Evidence: strong in general, weak for these groups specifically.**
  Worked-example and cognitive-load findings are robust for novices; their
  application to ADHD and autism is extrapolated, not trialled [11].
- **In the design:** the run shape; "step at a time"; hint step 5 is a worked
  example on a parallel task.

### 7. Literal language, and feedback that states what happened

Prompts say exactly what to do. Feedback says what the pupil built and what was
asked, then what to try. No sarcasm, no idiom, no "oops", no praise that
evaluates the child ("you're so smart"). Praise, where there is any, names the
strategy ("you swapped ten ones for a ten").

- **Evidence: consensus for literal language; weak and contested for process
  praise.** Growth-mindset interventions help lower-attaining pupils in one
  large trial [12]; meta-analyses find effects near zero overall, around 0.1 SD
  [13]. Process wording is kept because it is cheap and also literal, not
  because it is proven.
- **In the design:** the fixed hint ladder vocabulary; the "literal feedback"
  setting removes praise lines entirely.

### 8. Errors are information, and early errors are rare

First exposure to a new skill is scaffolded so it mostly succeeds (warm-up on a
secure skill, worked example before a new one). Once the basics are there,
errors are allowed and corrected.

- **Evidence: moderate and mixed.** Errorless teaching helped motor learning in
  small autism studies [14][15]; a group trial teaching language found
  errorless and error-correction procedures equally effective and equally
  unlikely to trigger distress [16].
- **In the design:** warm-up; stage stepping; hints never fail an attempt; the
  pupil's map never goes backwards.

### 9. Calm by default

No decorative motion, no sound effects, no confetti, no flashing, no autoplay.
State changes fade within 150 ms. `prefers-reduced-motion` is honoured.

- **Evidence: consensus.** Accessibility guidance and autism motion-perception
  research support it; there is no learning-outcome trial of calm interfaces
  [17].
- **In the design:** "calm" is the only comfort setting that defaults to on.
  A pupil can turn on sound and celebration; nobody has to turn them off.

### 10. Interest sets the content, not only the reward

A pupil who loves trains counts carriages. Themes change what the objects look
like and what the story in a word problem is about, never what is being tested.

- **Evidence: moderate.** Interest-based intervention shows positive effects in
  young autistic children, and embedding the interest in the task is suggested
  to work better than using it as a prize afterwards [18].
- **In the design:** the theme setting; primitives take a theme as a cosmetic
  parameter; templated word problems may draw nouns from the theme.

### 11. Real choice, small and bounded

Choice of theme, strand, which of two finish tasks, and whether to stop. Not a
menu of twenty.

- **Evidence: moderate.** Self-determination research links autonomy to
  motivation and conceptual learning, with the caveat that only meaningful
  choices help and too many do not [19].
- **In the design:** the finish slot; the strand picker; the break card.

### 12. More than one way in, and more than one way to answer

Every prompt can be read aloud. Every drag has a tap-tap and a keyboard path.
The no-JavaScript fallback is a real task, not an error page.

- **Evidence: consensus (UDL 3.0).** CAST's 2024 guidelines organise this as
  engagement, representation, and action and expression, and add an explicit
  emphasis on joy and play [20].
- **In the design:** activity rules 5 and 6; "read everything aloud"; the
  existing server-rendered SVG with no colour.

### 13. Plain type, generous spacing; no special fonts

Sans-serif, large, short lines, generous line and letter spacing.

- **Evidence: moderate, and negative for dyslexia fonts.** A 15-study
  meta-analysis found no effect of dyslexia-specific typefaces on reading speed
  or accuracy [21]. Spacing and size are the cheaper lever.
- **In the design:** the existing stylesheet; no font setting is offered, a
  spacing setting may be.

### 14. Interleave late

Practice is blocked on one skill until it is *practising*; mixing skills comes
in warm-up and retention checks only.

- **Evidence: weak.** Interleaving helps typical learners, but category learning
  in autism is highly variable and set-shifting is effortful for both groups;
  there is no direct trial [22].
- **In the design:** the run shape keeps core tasks on one skill; spaced checks
  live in warm-up.

## What gamification is allowed to do

The meta-analysis of gamification in education found small to moderate effects,
and that points and badges alone were the weakest designs; challenge, goals and
narrative did better [23]. So the game layer is built from the parts that carry
the effect and leaves out the parts that carry the risk.

**Allowed**

| mechanic | why it is safe |
|---|---|
| a growing map per subject (seed, sprout, plant, flower) | tied to mastery, never shrinks, fully explained |
| collections: earning a sticker, a creature or a museum object per secure skill | deterministic: the pupil can see exactly what earns the next one |
| personal bests, kept in the browser | compares the pupil with themself only; reading already works this way |
| a gentle narrative wrapper per strand ("fix the bridge", "stock the shop") | gives a goal the task serves; switchable off |
| completion marks per run | cannot mislead: finishing is finishing |
| a weekly rhythm (three sessions this week) | a missed day does not reset anything |

**Not allowed**

| mechanic | why |
|---|---|
| leaderboards, rankings, class competition | rule 4 |
| timers, speed bonuses, lives, hearts | rule 3; lives turn errors into loss |
| random rewards, loot boxes, spin-to-win | variable reward schedules are the mechanism of compulsion; no evidence they help learning, and the harm case is plausible though untested here |
| daily streaks that reset | a reset is a loss event, and a pupil's bad day is not a failure. The reading screen's daily streak should become a weekly rhythm |
| currency, shops, upgrades bought with points | turns learning into grinding for the purchase, and adds a second economy to understand |
| anything that works on a pupil outside the session: notifications, "your plant is thirsty" | Pensum has no business in a child's attention when they are not using it |
| avatars as the main reward | cosmetic and cheap to earn quickly, and the cosmetic chase displaces the task |

## Citations

As returned by the literature search for this document (2026-09). PMIDs and
DOIs are given so they can be checked.

1. Yakubova, Hughes & Shinaberry (2016). *J Autism Dev Disord* 46(7):2349–62. doi:10.1007/s10803-016-2768-7
2. Bouck, Park & Nickell (2017). *Res Dev Disabil* 60:24–36. doi:10.1016/j.ridd.2016.11.006
3. Bundock et al. (2024). *J Learn Disabil* 58(3):210–224. doi:10.1177/00222194241254094
4. Moyer-Packenham & Westenskow (2013). *Int J Virtual Personal Learning Environments*. ERIC EJ1154970
5. Kulik, Kulik & Bangert-Drowns (1990). *Rev Educ Res* 60(2):265–306. doi:10.3102/00346543060002265
6. Summary of the two-sigma replication record: https://nintil.com/bloom-sigma/
7. "Time on Their Side" (2025), visual timers and ADHD-risk pupils. PMC12731990
8. Li et al. (2024), systematic review of leaderboards. *J Comput Assist Learn*. doi:10.1111/jcal.13077
9. "The winner takes it all" (2025), leaderboard feedback. *Comput Hum Behav*. Unverified: full reference not checked
10. Li et al. (2025), TEACCH meta-analysis. *Transl Pediatr* 14(12):3263–80. doi:10.21037/tp-2025-466
11. "Cognitive load and neurodiversity in online education" (2024). *Front Educ*. doi:10.3389/feduc.2024.1437673
12. Yeager et al. (2019). *Nature* 573:364–9. doi:10.1038/s41586-019-1466-y
13. Macnamara & Burgoyne (2022); Tipton et al. (2022) re-analysis
14. Homayounnia Firouzjah et al. (2025). *Acta Psychol* 253:104731. doi:10.1016/j.actpsy.2025.104731
15. Arsham, Razeghi & Movahedi (2024). *Percept Mot Skills* 131(3):770–84. doi:10.1177/00315125241238308
16. Leaf et al. (2020). *Anal Verbal Behav* 36(1):1–20. doi:10.1007/s40616-019-00124-y
17. Reduced-motion guidance, e.g. WCAG 2.2 SC 2.3.3; autism motion perception PMC2779370
18. Interest-based intervention in young autistic children. PMC3420674
19. Guay (2022), applying self-determination theory to education. doi:10.1177/08295735211055355
20. CAST (2024), UDL Guidelines 3.0. https://udlguidelines.cast.org/
21. Azzarello et al. (2026), dyslexia fonts meta-analysis. *Ann Dyslexia*. doi:10.1007/s11881-026-00389-8
22. Category learning in autism, PMC4477144; review PMID 32910926
23. Sailer & Homner (2020). *Educ Psychol Rev* 32:77–112. doi:10.1007/s10648-019-09498-w

# Naturfag (NAT01-05)

Checkpoints after 2., 5., 7. and 10. trinn (naturfag skips 4.). Naturfag's core
is inquiry: ask, predict, test, observe, explain. A screen can structure that
loop, and it can check that a pupil can *reason* about a test they did not do.
It cannot do the experiment. So naturfag is designed as screen activities that
set up and debrief a real one, and pure screen activities for the knowledge
strands.

## Strands and progression

| strand | etter 2. trinn | etter 5. trinn | etter 7. trinn | etter 10. trinn |
|---|---|---|---|---|
| 1. Inquiry and models | asks questions about what they see; tells how they found out (KM13806, KM13807) | makes a hypothesis; records data in a table; compares a model with what was seen (KM13816, KM13817, KM13818) | names variables; tells an observation from a conclusion; says why models are used (KM13833, KM13834, KM13835) | separates dependent and independent variables; judges the quality of an investigation; states a model's limits (KM13854, KM13855, KM13856) |
| 2. Materials and chemistry | sorts objects by properties they can observe (KM13809) | describes what happens when substances are mixed (KM13822) | explains melting, freezing and boiling with the particle model; reads hazard symbols (KM13841, KM13852, KM13836) | explains mass conservation; uses atomic models and the periodic table (KM13861, KM13862, KM13857) |
| 3. Energy and forces | | connects speed and temperature to energy; follows an energy chain (KM13823, KM13824) | explores electric and magnetic forces (KM13842) | explains energy conservation and energy quality, and energy's environmental cost (KM13864, KM13865) |
| 4. Living things and ecosystems | describes how local organisms are adapted (KM13810) | compares adaptations; explains why species die out; knows good animal welfare (KM13825, KM13826) | groups organisms; builds food chains and webs; explains biodiversity (KM13843, KM13845, KM13853) | explains evolution, cells, photosynthesis and respiration, and ecosystem cycles (KM13866, KM13867, KM13870, KM13868) |
| 5. Earth and space | notices seasons and the Norwegian and Sami ways of dividing the year; observes weather (KM13811, KM13812) | explains the water cycle (KM13828) | explains day and night, moon phases and seasons; conditions for life; the rock cycle (KM13846, KM13847, KM13848) | explains the greenhouse effect and plate tectonics (KM13863, KM13871) |
| 6. Body and health | names the senses and what they sense; knows how to avoid infection (KM13813, KM13814) | describes muscles and skeleton and the body's outer defences; links lifestyle to health; knows how bodies and genders differ and how humans reproduce (KM13831, KM13830, KM13832, KM13829) | describes organ systems working together; explains puberty (KM13850, KM13849) | compares nervous and hormone systems; explains the immune system and vaccines (KM13873, KM13874, KM13872) |
| 7. Technology and design | suggests an invention (KM13808) | describes how parts of a system work together; builds to a specification (KM13820, KM13821) | programs a system of parts; designs for a user; weighs a technology's dilemmas (KM13838, KM13839, KM13840) | builds a transmitter and receiver; programs to explore a phenomenon (KM13859, KM13860) |
| 8. Sustainability and knowledge | makes environmentally aware choices locally (KM13815) | uses a natural area and resources sustainably (KM13819, KM13827) | gives examples of traditional knowledge in science; protects biodiversity (KM13851, KM13844, KM13837) | discusses resource dilemmas; Sami knowledge in nature management; how research works (KM13875, KM13869, KM13858) |

**Watch for:** heavy things fall faster; plants get their food from the soil;
the seasons come from distance to the sun; *melting* and *dissolving* used as
the same word; a model treated as a copy of reality.

## Activities

### The fair test builder (strand 1, all checkpoints)

The one activity to build first, because it serves every other strand.

1. **Question.** *Does a ball bounce higher on a warm day?* (given at 2.–5.,
   chosen from three at 7., written by the pupil at 10.)
2. **Sort the variables** (`sort`, P). Cards (*temperature*, *ball*, *height
   dropped*, *floor*, *bounce height*) into *what I change*, *what I measure*,
   *what I keep the same*. Graded.
3. **Predict** (recorded, never graded).
4. **Run it**: `explore_sim` for a simulated version, or a mission for a real
   one with a table to fill in.
5. **Read the result** (`read_chart`, P). Graded: what the data says.
6. **Explain**: pick the conclusion the data supports from three. One of the
   distractors is always *true, but not shown by this test*, which is the
   observation/conclusion distinction (KM13834) as a multiple choice.

The steps are always the same six, shown as six stones. That predictability is
part of the design: the content changes, the procedure never does.

### Knowledge strands

- **Floats or sinks** (`sort` + `explore_sim`, C, 2. trinn). Predict, then drop
  each object in the simulated tank.
- **Particle box** (`explore_sim`, P, 7. trinn). A temperature slider; particles
  vibrate, slide, fly apart. Predict the state at a given temperature. In calm
  mode the particles are drawn in still frames, one per state, rather than
  animated.
- **Water cycle wheel** (`sequence`, P). Cards in a cycle, graded up to rotation.
- **Food web** (`cause_effect`, P). Draw arrows from food to eater. *What happens
  to the fox if the voles disappear?*
- **Moon from here** (`explore_sim`, P). Move the moon around the Earth; the
  view from Norway updates beside it.
- **Label the body** (`label`, P). Skeleton, organ systems.
- **Hazard symbols** (`match`, P). Symbol to meaning to *what you do*.
- **Energy chain** (`sequence`, P). Sun → grass → cow → milk → you.
- **Greenhouse** (`cause_effect`, P, 10. trinn).
- **Periodic table puzzle** (`label`, P, 10. trinn). Place elements by
  properties rather than memorising positions.

### Sensitive content

Puberty, gender, sexuality and reproductive health (KM13829, KM13849, KM13872)
are taught, and are therefore in the progression guide. On screen they get
factual `label` and `match` items only, with no rewards, no map growth, and no
evidence rows visible on the class grid: a teacher does not need to see which
pupil got the puberty question wrong, and a pupil should not earn a sticker for
it. Discussion is a classroom matter.

## Missions

| goal | mission |
|---|---|
| KM13812 weather | Look at the sky at the same time for five days; fill the weather table. |
| KM13810, KM13819 local nature | Find three living things in one square metre outside; draw them. |
| KM13813 senses | Blindfolded taste or touch test with a partner, using the checklist. |
| KM13821, KM13839 design | Build something from the kit card that meets two rules. |
| KM13815, KM13827 sustainability | Sort the class rubbish for a day; count each bin. |
| KM13857 safety | Fill in the risk card before any real experiment. |
| KM13838, KM13859 programmed systems | Classroom kit (micro:bit or similar); Pensum hands over the task card only. |

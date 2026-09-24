"""Missions: short off-screen tasks for the goals a screen cannot check.

Some competence goals are conversations, visits, builds and presentations, and
Pensum does not invent a quiz for them. A mission guides one instead: a few
literal steps a pupil can tick, an optional printed script (a turn card, a risk
card) that makes the unwritten rules of the task written, and a line saying who
confirms it is done. It serves exactly one skill, and only a skill marked
`assessable: false`. The design is in `docs/design/architecture.md`.

Nothing a pupil does with a mission is uploaded or recorded here. Confirmation
and evidence belong to the mastery layer, not to this package.
"""

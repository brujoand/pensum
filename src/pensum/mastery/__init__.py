"""Mastery: which skill an answer is evidence for, and what the evidence adds up to.

Two pure halves. `attribution` decides which skills a graded answer counts
towards; `rules` turns a skill's evidence into one of five coarse states. Neither
touches the database or a request -- `pensum.scores.evidence` stores the rows and
the web layer reads them -- so both are tested with constructed sequences rather
than with a browser. The design is "Evidence and mastery" in
`docs/design/architecture.md`.
"""

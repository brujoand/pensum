"""Fact drills: reviewed facts a language model writes questions from.

An author writes a fact pack and an instruction set, and an administrator
reviews both. A model the instance operator runs then turns the facts into
multiple-choice questions. The design is in `docs/design/llm-drills.md`.

This package holds the content only: what a pack and an instruction set may
contain, how they load, and how they are checked. Nothing here calls a model.
"""

"""A short text, and the pupil taps the words or sentences that fit.

Every verb in a passage; the sentence that answers a question; the sentences
that are opinions; the observations rather than the conclusions. Finding it in
the text is the skill, so the tap is what is graded, and a pupil who knows the
topic but did not read cannot get it by knowing.

Two kinds of text, declared by `unit`:

  * `word`: one `text` in one language, with the words to find in square
    brackets -- ``Katten [hopper] opp og [spiser].`` The brackets are how a
    reviewer sees the answer in place. The text is the material, so it is shown
    as written in both interface languages: a norsk text is not translated for
    an English interface any more than a poem would be.
  * `sentence`: a list of `sentences`, each in both languages, with
    `mark: true` on the ones to find. Declared one by one so the two languages
    always have the same sentences in the same places.

Each word or sentence is a button, which is the keyboard path, and pressing it
again unmarks it. A marked one gets a ring and an underline, never only a
colour. Punctuation is not a thing to tap.

Graded on the exact set: everything that should be marked, and nothing else.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pensum.i18n import translate
from pensum.items.primitives.cards import Card, CardBoard, ChoiceActivity, Place, join_words
from pensum.items.text import AuthoredText

MAX_TOKENS = 60
_CHUNK = re.compile(r"\S+")
# Punctuation around a word stays on the page but is not part of what is tapped.
_EDGES = re.compile(r"^([«\"'(\[]*)(.*?)([.,!?;:»\"')\]]*)$")


class Sentence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    text: AuthoredText
    mark: bool = False


class Token(BaseModel):
    model_config = ConfigDict(frozen=True)

    before: str
    text: str
    after: str
    mark: bool


class HighlightState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # The tapped words or sentences, by position, in increasing order.
    marked: tuple[int, ...] = ()


def split_words(text: str) -> list[Token]:
    """``Katten [hopper] opp.`` into tokens, the bracketed ones marked."""
    tokens = []
    for chunk in _CHUNK.findall(text):
        mark = "[" in chunk
        if mark and not re.fullmatch(r"[«\"'(]*\[[^\[\]]+\][.,!?;:»\"')]*", chunk):
            raise ValueError(f"brackets must wrap exactly one word: {chunk!r}")
        before, word, after = _EDGES.match(chunk.replace("[", "").replace("]", "")).groups()
        if not word:
            raise ValueError(f"{chunk!r} has no word to tap")
        tokens.append(Token(before=before, text=word, after=after, mark=mark))
    return tokens


class HighlightActivity(ChoiceActivity):
    """Tap the words or sentences in `text` or `sentences` that are marked."""

    FALLBACK_KEY = "activity.highlight.ask"
    State = HighlightState

    kind: Literal["highlight"] = "highlight"
    unit: Literal["word", "sentence"]
    text: str | None = Field(default=None, min_length=1)
    sentences: tuple[Sentence, ...] = ()

    @model_validator(mode="after")
    def _check(self) -> HighlightActivity:
        if self.unit == "word":
            if self.text is None or self.sentences:
                raise ValueError("unit: word takes a text, not sentences")
        elif self.text is not None or not self.sentences:
            raise ValueError("unit: sentence takes sentences, not a text")
        tokens = self.tokens("nb")
        if not 3 <= len(tokens) <= MAX_TOKENS:
            raise ValueError(f"a text to search has 3 to {MAX_TOKENS} parts")
        marks = sum(t.mark for t in tokens)
        if marks == 0 or marks == len(tokens):
            raise ValueError("something, but not everything, has to be found")
        return self

    def tokens(self, locale: str) -> list[Token]:
        if self.text is not None:
            return split_words(self.text)
        return [
            Token(before="", text=s.text.get(locale), after="", mark=s.mark) for s in self.sentences
        ]

    def answer(self) -> tuple[int, ...]:
        return tuple(i for i, t in enumerate(self.tokens("nb")) if t.mark)

    def made_key(self) -> str:
        return "activity.cards.you_marked"

    # --- rules -------------------------------------------------------------

    def initial(self) -> HighlightState:
        return HighlightState()

    def solution(self) -> HighlightState:
        return HighlightState(marked=self.answer())

    def admits(self, state: HighlightState) -> bool:
        n = len(self.tokens("nb"))
        marked = state.marked
        return all(0 <= i < n for i in marked) and all(
            a < b for a, b in zip(marked, marked[1:], strict=False)
        )

    def grade_state(self, state: HighlightState) -> bool:
        return state.marked == self.answer()

    def near_misses(self) -> list[HighlightState]:
        """One too few, one too many, or -- when one thing is to be found --
        its neighbours instead, nearest first."""
        right = set(self.answer())
        n = len(self.tokens("nb"))
        others = sorted(
            (i for i in range(n) if i not in right),
            key=lambda i: min(abs(i - r) for r in right),
        )
        if len(right) == 1:
            return [HighlightState(marked=(i,)) for i in others]
        fewer = [tuple(sorted(right - {r})) for r in sorted(right, reverse=True)]
        more = [tuple(sorted(right | {i})) for i in others]
        out = []
        for pair in zip(fewer, more, strict=False):
            out.extend(HighlightState(marked=m) for m in pair)
        return out

    def describe(self, state: HighlightState, locale: str) -> str:
        tokens = self.tokens(locale)
        words = [f"«{tokens[i].text}»" for i in state.marked]
        return join_words(words, locale) or translate(locale, "activity.highlight.nothing")

    def limits(self) -> dict[str, int]:
        return {"tokens": len(self.tokens("nb"))}

    def say(self, locale: str) -> dict[str, object]:
        return {
            "and": translate(locale, "activity.and"),
            "nothing": translate(locale, "activity.highlight.nothing"),
            "tokens": [t.text for t in self.tokens(locale)],
        }

    # --- drawing -----------------------------------------------------------

    def board(self, state: HighlightState, locale: str) -> CardBoard:
        tokens = self.tokens(locale)
        marks = tuple(Card("mark", i, t.text, i in state.marked) for i, t in enumerate(tokens))
        return CardBoard(
            "partials/primitives/_highlight_board.html",
            self.alt.get(locale),
            (Place("mark", "", marks, "text"),),
            kind="highlight",
            extra=(("tokens", tuple(tokens)), ("unit", self.unit)),
        )

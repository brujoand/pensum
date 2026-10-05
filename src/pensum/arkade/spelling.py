"""Spelling items: a word is spoken, and the pupil picks the spelling of it.

The listening exercise's "pick" question, served to a game. The words come from
the passages approved for the pupil's checkpoint, and the wrong spelling from
`pensum.listening.confusable`. Because the word is heard, a wrong spelling that
happens to be a real word (`bok` beside `bak`) is a fair question rather than a
false one: the pupil is told which word to find, not that the other is not a
word.
"""

from __future__ import annotations

from random import Random

from pensum.arkade.items import Item
from pensum.listening.exercise import question_for
from pensum.listening.lexicon import Lexicon
from pensum.reading.schema import ReadingText

# Where one skill names what a spoken-word pick shows. Only 2. trinn has one:
# later spelling skills are about a single pattern (kj and skj, double
# consonants), and an item drawn from any word in a passage is not evidence for
# one pattern in particular.
SKILL_BY_CHECKPOINT = {
    ("nb", 2): "nor.decoding.spell-by-sound",
    ("nn", 2): "nor.decoding.spell-by-sound",
}


def spoken_word_items(
    texts: list[ReadingText], lexicon: Lexicon, after_year: int, rng: Random, count: int
) -> list[Item]:
    """Up to `count` items from the words in `texts`, fewer when the passages run out."""
    if not texts:
        return []
    language = texts[0].language
    pool: set[str] = set()
    for text in texts:
        pool |= set(text.word_list)
    words = lexicon.askable(pool)
    rng.shuffle(words)

    items: list[Item] = []
    for word in words:
        question = question_for(word, language, "pick", lexicon)
        if question is None:
            continue
        options = question.options
        items.append(
            Item(
                id=f"{language}:{word}",
                rule="spoken_word",
                candidates=options,
                matches=frozenset({options.index(word)}),
                answer=word,
                skill=SKILL_BY_CHECKPOINT.get((language, after_year)),
                spoken=word,
                language=language,
            )
        )
        if len(items) == count:
            break
    return items

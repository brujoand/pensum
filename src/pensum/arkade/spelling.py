"""Spelling balloons: a word is spoken, and the balloon shows one spelling of it.

Half the time the spelling is right; otherwise it is the listening exercise's
distractor for the word, from `pensum.listening.confusable`. The words come
from the passages approved for the pupil's checkpoint. Because the word is
heard, a wrong spelling that happens to be a real word (`bak` for a spoken
`bok`) is a fair question rather than a false one: the pupil is asked whether
this is the word they heard, not whether it is a word.
"""

from __future__ import annotations

from random import Random

from pensum.arkade.items import Item, balloon
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
        true = rng.random() < 0.5
        other = next(option for option in question.options if option != word)
        items.append(
            balloon(
                f"{language}:{word}",
                "spoken_word",
                word if true else other,
                true=true,
                answer=word,
                skill=SKILL_BY_CHECKPOINT.get((language, after_year)),
                spoken=word,
                language=language,
            )
        )
        if len(items) == count:
            break
    return items

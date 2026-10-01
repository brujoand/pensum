"""The committed fact packs and instruction sets.

These run against `data/drills/` and the real catalogue, so they fail when an
edit to a pack or a curriculum revision breaks one, not only when code changes.
"""

from __future__ import annotations

import pytest

from pensum.drills.loader import DrillLibrary
from pensum.drills.validate import validate


@pytest.fixture(scope="module")
def library() -> DrillLibrary:
    return DrillLibrary.load()


def test_the_committed_drills_validate() -> None:
    assert validate() == []


def test_there_is_something_to_review(library: DrillLibrary) -> None:
    assert library.files
    assert library.instruction_sets


def test_every_pack_names_an_instruction_set_that_loads(library: DrillLibrary) -> None:
    for pack_file in library.files:
        for pack in pack_file.packs:
            assert library.instruction_set(pack.instructions) is not None, pack.id


def test_every_fact_is_one_sentence_in_each_language(library: DrillLibrary) -> None:
    """A question cites one fact, and the fact is its feedback.

    Two sentences in one fact are two facts, and a question written from the
    second would be explained by the first.
    """
    for pack_file in library.files:
        for pack in pack_file.packs:
            for fact in pack.facts:
                for text in (fact.nb, fact.en):
                    where = f"{pack.id}/{fact.id}"
                    assert text.endswith("."), where
                    # A full stop followed by a capital starts a second sentence.
                    # "17. mai" does not: an ordinal's stop is followed by lower case.
                    words = text.split()
                    second = [
                        b
                        for a, b in zip(words, words[1:], strict=False)
                        if a.endswith(".") and b[:1].isupper()
                    ]
                    assert not second, where

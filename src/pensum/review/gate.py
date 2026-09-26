"""The one question every content library asks: may this be shown to a pupil here?

Each library -- items, reading, writing, skills, missions -- holds a gate for its
own kind and asks it about each piece as it serves it. The gate knows the
fingerprint of every piece (computed once, see `pensum.review.content`) and the
ledger of decisions, and nothing else.

**With no ledger, nothing is approved.** A library built without one -- a script,
a test, a tool reading the files -- answers "pending" for everything, and a
serving path that asks for approved content gets none. That is the only safe
direction for a missing collaborator: the alternative is a library that serves
everything because nobody told it not to.
"""

from __future__ import annotations

from pydantic import BaseModel

from pensum.review.content import Fingerprints
from pensum.review.store import Kind, ReviewLedger, State


class ReviewGate:
    """One library's view of the instance's review decisions."""

    def __init__(self, kind: Kind) -> None:
        self.kind: Kind = kind
        self.ledger: ReviewLedger | None = None
        self._fingerprints = Fingerprints()

    def fingerprint(self, content_id: str, content: BaseModel) -> str:
        return self._fingerprints.of(content_id, content)

    def state(self, content_id: str, content: BaseModel) -> State:
        if self.ledger is None:
            return "pending"
        return self.ledger.state(self.kind, content_id, self.fingerprint(content_id, content))

    def publishes(self, content_id: str, content: BaseModel) -> bool:
        return self.state(content_id, content) == "approved"

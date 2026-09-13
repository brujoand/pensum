"""What one deployment chooses to serve, recorded outside the files it concerns.

Two questions live here, and they are deliberately answered in different places.

`reviewed:` in a YAML file asks whether a human has read the content at all.
That is a fact about the question, it is the same in every deployment, and it
belongs in the repository. It is the floor: nothing unread reaches a child
anywhere.

A decision recorded here asks whether *this* school wants it. That has no
repository-wide answer. A Pensum serving a Sámi school and one serving a
congregation school in southern Norway will each want questions the other would
keep away from its pupils, and both are right about their own classroom. A flag
in a shared file cannot hold two answers, so the answer lives in the instance
that has to give it.

The consequence, so nobody has to infer it: the files say what Pensum contains
and what has been read; this table says what one school picked out of it. There
is no exporter back into YAML on purpose -- that would publish a local decision
as though it were everyone's.
"""

from pensum.review.store import (
    KINDS,
    Decision,
    ReviewLedger,
    ReviewStore,
)

__all__ = ["KINDS", "Decision", "ReviewLedger", "ReviewStore"]

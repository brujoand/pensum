"""Human sign-off on authored content, recorded outside the files it concerns.

Every quiz item, reading passage and writing prompt carries `reviewed:` in its
YAML. That flag is the floor, and until this module existed it was also the
ceiling: publishing meant editing a file, committing, and waiting for a release.

A decision recorded here overrides the flag in either direction, which is what
makes a review page possible on a running instance. The cost is stated once,
here, so nobody has to infer it: what the deployed site serves is now the file
plus the database, and the file alone no longer tells you.
"""

from pensum.review.store import (
    KINDS,
    Decision,
    ReviewLedger,
    ReviewStore,
)

__all__ = ["KINDS", "Decision", "ReviewLedger", "ReviewStore"]

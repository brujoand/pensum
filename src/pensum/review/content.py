"""What a decision is about: a fingerprint of the content, and never a flag in it.

Whether a piece of content may be shown to a pupil is live data. It belongs to
the instance that shows it, is set on that instance's review page, and is stored
in that instance's database. It is not a property of the file, and a file that
tries to say it is refused -- `reject_review_keys` is called from every schema
that a human could once mark `reviewed: true`, so the old habit fails loudly at
load instead of being silently ignored.

**A decision is about the content as it was when someone read it.** An
approval records a fingerprint of what the reviewer saw, and it applies only
while the content still has that fingerprint. Edit a question after it was
approved and it is pending again on the next start, with no step anybody has to
remember: the approval was for a sentence that no longer exists.

The fingerprint is taken over the validated model, not the YAML text. That is
the form a loader builds and a page renders from, in both locales, so a comment,
a re-indent or a key order change in the file leaves it alone, and a changed
word in either language does not. Fields left at their default are left out, so
adding an optional field to a schema does not quietly return every piece of
content on every instance to pending.
"""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel

# The keys a file used to carry. Named once, so the schemas and the test that
# sweeps `data/` agree on what is no longer allowed.
REVIEW_KEYS = ("reviewed", "reviewed_by")

REVIEW_KEY_MESSAGE = (
    "`{key}` is not a content field: review state lives in each instance's "
    "database and is set on its review page (/<locale>/admin/gjennomgang), "
    "never in the file"
)


def reject_review_keys(data: object) -> object:
    """Refuse a mapping that tries to say whether it has been reviewed.

    Called as a `mode="before"` validator, so it sees the raw mapping and runs
    whatever the model's `extra` setting is: several content models ignore
    unknown keys, and a silently ignored `reviewed: true` is the one mistake
    that would look like it worked.
    """
    if isinstance(data, dict):
        for key in REVIEW_KEYS:
            if key in data:
                raise ValueError(REVIEW_KEY_MESSAGE.format(key=key))
    return data


def fingerprint(content: BaseModel) -> str:
    """A stable hash of one piece of content, as it is served.

    SHA-256 over canonical JSON: sorted keys, no insignificant whitespace, and
    non-ASCII kept as written so that "blåbær" hashes as the word it is.
    """
    canonical = json.dumps(
        content.model_dump(mode="json", exclude_defaults=True),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class Fingerprints:
    """Fingerprints of one library's content, each computed once.

    Libraries are immutable after load, so a fingerprint never changes for the
    life of the process; caching it is what keeps the per-request question
    "may this be served" to a dict lookup rather than a JSON dump and a hash for
    every item on every page.
    """

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}

    def of(self, content_id: str, content: BaseModel) -> str:
        found = self._cache.get(content_id)
        if found is None:
            found = fingerprint(content)
            self._cache[content_id] = found
        return found

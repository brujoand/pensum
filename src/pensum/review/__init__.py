"""Whether a piece of content is live on this instance: data, never a file flag.

Review state is live data in the running application. It is set on the
instance's own review page by an administrator, stored in the instance's own
database, and read back on every page that serves anything. There is no
`reviewed:` key in any content file, and the schemas refuse one
(`pensum.review.content.reject_review_keys`).

Two reasons it cannot live in the repository, and either would be enough.

* **Whether to show something is a school's decision.** A Pensum serving a Sámi
  school and one serving a congregation school in southern Norway will each
  want questions the other would keep away from its pupils, and both are right
  about their own classroom. A flag in a shared file cannot hold two answers.
* **A merge is not a review.** A flag in a file is set by whoever writes the
  pull request. A decision on the instance is made by an administrator of that
  instance, looking at the question as a pupil would meet it.

The consequence, so nobody has to infer it: the files say what Pensum contains;
this table says what one instance serves. Every instance starts with nothing
approved. There is no exporter back into YAML and no importer from it, on
purpose.

A decision carries a fingerprint of the content it was made about
(`pensum.review.content`), so editing approved content returns it to pending on
its own.
"""

from pensum.review.store import (
    KINDS,
    STATES,
    Decision,
    ReviewLedger,
    ReviewStore,
    State,
)

__all__ = ["KINDS", "STATES", "Decision", "ReviewLedger", "ReviewStore", "State"]

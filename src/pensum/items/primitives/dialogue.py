"""A dialogue: a short scripted chat where the pupil picks each of their lines.

*At the café* from `docs/design/subjects/engelsk.md`. A partner says a line,
the pupil picks what to say back from two or three, and the conversation goes
on. An acceptable line leads to the partner's next line; an unacceptable one
gets a literal reply ("The waiter did not understand. Try *Could I have…*") and
the pupil picks again from the same lines. Speaking is never asked for and
nothing is recorded: the lines are picked, and the browser voice can read the
partner's line aloud where it has one for the item's language.

**The script is a small graph, declared and checked.** `nodes` maps a name to
what the partner says there and the pupil's options; an option either leads to
another node (`next`) or is answered in place (`reply`). A node with no options
is an end. When the item loads, every node must be reachable from `start`,
every option must lead somewhere that exists, every node that is not an end
must have at least one acceptable option, and no chain of acceptable options
may loop -- so every path a pupil can take ends. A script that fails any of
these is a typo, and it fails at load rather than in a child's conversation.

Graded on reaching an end. The state is the list of picks, in order, wrong
ones included, because that is what the pupil did and it is what the feedback
replays; it is re-walked through the graph, and a pick the graph could not have
offered is a state no page produced, so it is refused.

**The page does not say which line is right before it is picked.** The page
has to advance the conversation on its own, with no request to the server, so
it needs every option's outcome. If that were plain -- a `next` for a right
line, null for a wrong one, a reply only where a line is wrong -- the answer
would be readable from the page source at every step. So each option's outcome
(where it leads, and what the partner answers) is shipped as one opaque token:
the JSON of that outcome, padded to the length of the longest in the item and
XORed with a keystream seeded from the node's name and the option's place
(`outcome_token`; `dialogue.js` has the same function). Every token of an item
has the same length and the same alphabet, right or wrong, and no reply text
is on the page until it is said. This is encoding, not secrecy: anyone who runs
the page's own code can decode a token without picking. What it prevents is the
answer being read off the source, which is the bar here; nothing is graded on
the page, and the server grades the final state by walking its own graph.

Without a script there is no conversation to walk. The pupil reads the opening
line and picks their first reply as a radio button; an acceptable one is right.
That is less than the whole dialogue, and said so in the README.
"""

from __future__ import annotations

import json
from collections import deque
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pensum.i18n import translate
from pensum.items.figures import Label
from pensum.items.primitives import tiles
from pensum.items.primitives.base import ActivityConfig, Board, Comparison, Layer, plural
from pensum.items.text import AuthoredText

MAX_NODES = 8
# More picks than any pupil makes. Unacceptable picks do not advance, so a
# state could otherwise be any length; a longer one is refused as malformed.
MAX_PICKS = 40
LINE_H = 18.0
LINE_CHAR_W = 6.6
MARGIN = 12.0


class DialogueOption(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    text: AuthoredText
    # Where an acceptable line leads.
    next: str | None = None
    # What the partner says back to an unacceptable one. The pupil stays.
    reply: AuthoredText | None = None

    @model_validator(mode="after")
    def _one(self) -> DialogueOption:
        if (self.next is None) == (self.reply is None):
            raise ValueError("an option either leads on (next) or is answered in place (reply)")
        return self


class DialogueNode(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    says: AuthoredText
    options: tuple[DialogueOption, ...] = Field(default=(), max_length=3)


class DialogueState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    picks: tuple[int, ...] = Field(default=(), max_length=MAX_PICKS)


class DialogueActivity(ActivityConfig):
    FALLBACK_KEY = "activity.dialogue.ask"
    State = DialogueState

    kind: Literal["dialogue"] = "dialogue"
    language: Literal["nb", "en"]
    # Who the pupil is talking to: "Kelneren" / "The waiter".
    partner: AuthoredText
    start: str
    nodes: dict[str, DialogueNode] = Field(min_length=2, max_length=MAX_NODES)

    @model_validator(mode="after")
    def _check(self) -> DialogueActivity:
        if self.fallback is not None:
            raise ValueError("dialogue asks for the first reply without a script")
        problems = validate_graph(self.start, self.nodes)
        if problems:
            raise ValueError("; ".join(problems))
        return self

    # --- walking the script ------------------------------------------------------

    def walk(self, picks: tuple[int, ...]) -> list[tuple[str, int]] | None:
        """Each pick with the node it was made at, or None if one was impossible."""
        node = self.start
        steps = []
        for pick in picks:
            options = self.nodes[node].options
            if not 0 <= pick < len(options):
                return None
            steps.append((node, pick))
            if options[pick].next is not None:
                node = options[pick].next
        return steps

    def at(self, picks: tuple[int, ...]) -> str | None:
        steps = self.walk(picks)
        if steps is None:
            return None
        if not steps:
            return self.start
        node, pick = steps[-1]
        return self.nodes[node].options[pick].next or node

    def shown_options(self, name: str) -> list[tuple[int, DialogueOption]]:
        """A node's options with their indices, in the order the page lists them."""
        return sorted(
            enumerate(self.nodes[name].options), key=lambda pair: tiles.mix(name, pair[1].text.nb)
        )

    # --- rules -----------------------------------------------------------------

    def initial(self) -> DialogueState:
        return DialogueState()

    def solution(self) -> DialogueState:
        return DialogueState(picks=shortest_path(self.start, self.nodes))

    def admits(self, state: DialogueState) -> bool:
        return self.at(state.picks) is not None

    def grade_state(self, state: DialogueState) -> bool:
        node = self.at(state.picks)
        return node is not None and not self.nodes[node].options

    def default_fallback(self) -> float:
        return 0.0

    def describe(self, state: DialogueState, locale: str) -> str:
        count = len(state.picks)
        key = "activity.dialogue.made" if self.grade_state(state) else "activity.dialogue.open"
        return plural(locale, key, count)

    def made_key(self) -> str:
        return "activity.dialogue.you_made"

    def limits(self) -> dict[str, object]:
        return {
            "start": self.start,
            "language": self.language,
            "max": MAX_PICKS,
            # The graph as the page needs it, one opaque token per option. See
            # the module docstring: right and wrong options look the same.
            "nodes": {
                name: [
                    outcome_token(name, i, _outcome(o), self._outcome_width())
                    for i, o in enumerate(node.options)
                ]
                for name, node in self.nodes.items()
            },
        }

    def _outcome_width(self) -> int:
        return max(
            (len(_outcome(o)) for node in self.nodes.values() for o in node.options), default=0
        )

    def say(self, locale: str) -> dict[str, str]:
        return {
            "made": translate(locale, "activity.dialogue.made"),
            "made_one": translate(locale, "activity.dialogue.made_one"),
            "open": translate(locale, "activity.dialogue.open"),
            "open_one": translate(locale, "activity.dialogue.open_one"),
        }

    def script(self, locale: str) -> dict[str, object]:
        """Every line in the pupil's language, for the page to build the log from."""
        return {
            "partner": self.partner.get(locale),
            "you": translate(locale, "activity.dialogue.you"),
            # Which of a reply's two texts to show; the replies themselves are
            # in the option tokens, so they are not on the page until said.
            "locale": "en" if locale == "en" else "nb",
            "nodes": {
                name: {
                    "says": node.says.get(locale),
                    "options": [o.text.get(locale) for o in node.options],
                }
                for name, node in self.nodes.items()
            },
        }

    def transcript(self, state: DialogueState, locale: str) -> list[tuple[str, str]]:
        """The conversation so far, as (who, line) pairs."""
        partner = self.partner.get(locale)
        you = translate(locale, "activity.dialogue.you")
        lines = [(partner, self.nodes[self.start].says.get(locale))]
        for node, pick in self.walk(state.picks) or []:
            option = self.nodes[node].options[pick]
            lines.append((you, option.text.get(locale)))
            if option.next is not None:
                lines.append((partner, self.nodes[option.next].says.get(locale)))
            elif option.reply is not None:
                lines.append((partner, option.reply.get(locale)))
        return lines

    # --- the no-script road ----------------------------------------------------

    def _first(self, text: str) -> int | None:
        value = text.strip()
        # ASCII digits only: "²".isdigit() is true, and int() refuses it.
        if not value or len(value) > 2 or any(c not in "0123456789" for c in value):
            return None
        index = int(value) - 1
        return index if 0 <= index < len(self.nodes[self.start].options) else None

    def typed_right(self, text: str) -> bool:
        index = self._first(text)
        return index is not None and self.nodes[self.start].options[index].next is not None

    def typed_example(self) -> str:
        options = self.nodes[self.start].options
        return str(next(i for i, o in enumerate(options) if o.next is not None) + 1)

    def typed_compare(self, text: str, locale: str) -> Comparison:
        index = self._first(text)
        options = self.nodes[self.start].options
        first = int(self.typed_example()) - 1
        made = options[index].text.get(locale) if index is not None else (text.strip() or "—")
        asked = options[first].text.get(locale)
        drawn = self.board(DialogueState(picks=(index,)), locale) if index is not None else None
        return Comparison(
            translate(locale, "activity.dialogue.you_answered", made=made, asked=asked),
            made,
            asked,
            drawn,
            self.board(DialogueState(picks=(first,)), locale),
        )

    # --- drawing -----------------------------------------------------------------

    def board(self, state: DialogueState, locale: str) -> Board:
        """The conversation as lines of text, the partner's left and the pupil's
        indented, so who said what is carried by place and name, not colour."""
        lines = self.transcript(state, locale)
        you = translate(locale, "activity.dialogue.you")
        labels = []
        widest = 0.0
        for i, (who, line) in enumerate(lines):
            indent = 28.0 if who == you else 0.0
            text = f"{who}: {line}"
            labels.append(
                Label(
                    MARGIN + indent,
                    MARGIN + LINE_H / 2 + i * LINE_H,
                    text,
                    size=12,
                    anchor="start",
                )
            )
            widest = max(widest, indent + len(text) * LINE_CHAR_W)
        return Board(
            widest + 2 * MARGIN,
            len(lines) * LINE_H + 2 * MARGIN,
            self.alt.get(locale),
            (Layer("base", labels=tuple(labels)),),
        )


# Salt for the keystream, so a token does not decode with a textbook key.
_SALT = "pensum-dialogue"


def _outcome(option: DialogueOption) -> str:
    """What picking an option does, as the page reads it: the node it leads to
    ("" to stay) and the partner's reply in both locales (empty to go on)."""
    reply = {"nb": option.reply.nb, "en": option.reply.en} if option.reply else {}
    return json.dumps(
        {"n": option.next or "", "r": reply}, ensure_ascii=True, separators=(",", ":")
    )


def _keystream(node: str, index: int, length: int) -> list[int]:
    """FNV-1a of the seed, then xorshift32, one byte per step."""
    x = 0x811C9DC5
    for byte in f"{_SALT}\x1f{node}\x1f{index}".encode():
        x = ((x ^ byte) * 0x01000193) & 0xFFFFFFFF
    x = x or 0x9E3779B9
    out = []
    for _ in range(length):
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        out.append(x & 0xFF)
    return out


def outcome_token(node: str, index: int, outcome: str, width: int) -> str:
    """An option's outcome, padded to `width` and encoded, as hex."""
    data = outcome.ljust(width).encode("ascii")
    key = _keystream(node, index, len(data))
    return bytes(b ^ k for b, k in zip(data, key, strict=True)).hex()


def validate_graph(start: str, nodes: dict[str, DialogueNode]) -> list[str]:
    """Every way a declared script can be broken, in words. Empty when sound."""
    problems = []
    if start not in nodes:
        return [f"start {start!r} is not a node"]
    for name, node in nodes.items():
        if len(node.options) == 1:
            problems.append(f"{name}: one option is not a choice; give two or three")
        for option in node.options:
            if option.next is not None and option.next not in nodes:
                problems.append(f"{name}: an option leads to {option.next!r}, which is not a node")
        if node.options and all(o.next is None for o in node.options):
            problems.append(f"{name}: no option leads on, so the conversation cannot end")
    if problems:
        return problems

    # Reachable from the start by acceptable lines, which are the only ones
    # that move.
    seen = {start}
    queue = deque([start])
    while queue:
        for option in nodes[queue.popleft()].options:
            if option.next is not None and option.next not in seen:
                seen.add(option.next)
                queue.append(option.next)
    for name in nodes:
        if name not in seen:
            problems.append(f"{name}: no path from {start!r} reaches it")

    # No loop, so every path ends: a depth-first search that meets a node
    # already on its own path has found one.
    state: dict[str, int] = {}

    def visit(name: str) -> bool:
        state[name] = 1
        for option in nodes[name].options:
            nxt = option.next
            if nxt is None:
                continue
            if state.get(nxt) == 1 or (nxt not in state and not visit(nxt)):
                problems.append(f"{name}: leads back round to {nxt!r}, so it might never end")
                return False
        state[name] = 2
        return True

    visit(start)
    return problems


def shortest_path(start: str, nodes: dict[str, DialogueNode]) -> tuple[int, ...]:
    """The fewest acceptable picks from the start to an end."""
    queue: deque[tuple[str, tuple[int, ...]]] = deque([(start, ())])
    seen = {start}
    while queue:
        name, picks = queue.popleft()
        if not nodes[name].options:
            return picks
        for i, option in enumerate(nodes[name].options):
            if option.next is not None and option.next not in seen:
                seen.add(option.next)
                queue.append((option.next, (*picks, i)))
    return ()

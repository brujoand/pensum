"""Loading drills files from disk.

A goal set with no pack file is an ordinary state: packs are authored goal set
by goal set. So is a missing `data/drills/` altogether, which loads as an empty
library.

Two kinds are reviewed here, each with its own gate: a pack, and an instruction
set. A pack is served only when both it and the instruction set it names are
approved, because the two together are what a model is prompted with.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from pensum.drills.schema import FactPack, InstructionSet, PackFile
from pensum.review.gate import ReviewGate
from pensum.review.store import ReviewLedger, State

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DRILLS_DIR = REPO_ROOT / "data" / "drills"

# The one directory under `data/drills/` that is not a subject.
INSTRUCTIONS_DIR = "instructions"

# What decisions about a pack and an instruction set are filed under.
PACK_KIND = "pack"
INSTRUCTIONS_KIND = "instructions"


def read_packs(path: Path) -> PackFile:
    """Parse one pack file. Raises on YAML or schema errors; the validator reports them."""
    return PackFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def read_instructions(path: Path) -> InstructionSet:
    """Parse one instruction set. Raises as `read_packs` does."""
    return InstructionSet.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def pack_paths(directory: Path) -> list[Path]:
    """Every pack file under `directory`, in a stable order."""
    return sorted(p for p in directory.glob("*/*.yaml") if p.parent.name != INSTRUCTIONS_DIR)


def instruction_paths(directory: Path) -> list[Path]:
    return sorted((directory / INSTRUCTIONS_DIR).glob("*.yaml"))


class DrillLibrary:
    """Every fact pack and instruction set, indexed by id."""

    def __init__(self, files: list[PackFile], instructions: list[InstructionSet]) -> None:
        self._files = tuple(files)
        self._packs = {pack.id: (f, pack) for f in files for pack in f.packs}
        self._instructions = {i.id: i for i in instructions}
        self._pack_gate = ReviewGate(PACK_KIND)
        self._instructions_gate = ReviewGate(INSTRUCTIONS_KIND)

    def with_ledger(self, ledger: ReviewLedger | None) -> DrillLibrary:
        """Same contract as `ItemBank.with_ledger`: None approves nothing."""
        self._pack_gate.ledger = ledger
        self._instructions_gate.ledger = ledger
        return self

    @property
    def has_ledger(self) -> bool:
        return self._pack_gate.ledger is not None

    @classmethod
    def load(cls, drills_dir: Path | None = None) -> DrillLibrary:
        directory = drills_dir or DEFAULT_DRILLS_DIR
        return cls(
            [read_packs(path) for path in pack_paths(directory)],
            [read_instructions(path) for path in instruction_paths(directory)],
        )

    @property
    def files(self) -> tuple[PackFile, ...]:
        return self._files

    @property
    def instruction_sets(self) -> tuple[InstructionSet, ...]:
        return tuple(self._instructions.values())

    def pack(self, pack_id: str) -> tuple[PackFile, FactPack] | None:
        """The pack and the file it belongs to, or None."""
        return self._packs.get(pack_id)

    def instruction_set(self, instructions_id: str) -> InstructionSet | None:
        return self._instructions.get(instructions_id)

    def publishes(self, pack: FactPack) -> bool:
        """Whether a drill may be built from this pack on this instance."""
        instructions = self._instructions.get(pack.instructions)
        if instructions is None:
            return False
        return self._pack_gate.publishes(pack.id, pack) and self._instructions_gate.publishes(
            instructions.id, instructions
        )

    def review_state(self, content_id: str) -> State:
        """Where a pack stands. Its instruction set has a state of its own."""
        found = self._packs.get(content_id)
        return self._pack_gate.state(content_id, found[1]) if found is not None else "pending"

    def instructions_state(self, content_id: str) -> State:
        found = self._instructions.get(content_id)
        if found is None:
            return "pending"
        return self._instructions_gate.state(content_id, found)

    def fingerprint(self, content_id: str) -> str | None:
        found = self._packs.get(content_id)
        return self._pack_gate.fingerprint(content_id, found[1]) if found is not None else None

    def instructions_fingerprint(self, content_id: str) -> str | None:
        found = self._instructions.get(content_id)
        if found is None:
            return None
        return self._instructions_gate.fingerprint(content_id, found)

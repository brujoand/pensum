"""The browser half of the balloon game, run by node in `tests/js/arkade_balloons.test.js`."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from pensum.web.arkade_routes import MAX_PICKS, ROUND_LENGTH

HARNESS = Path(__file__).parent / "js" / "arkade_balloons.test.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_a_round_played_in_the_page() -> None:
    result = subprocess.run(  # noqa: S603
        [shutil.which("node") or "node", str(HARNESS)],
        capture_output=True,
        text=True,
        check=False,
        cwd=HARNESS.parents[2],
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_the_harness_is_reachable() -> None:
    """The check above skips where node is missing; this one does not."""
    assert HARNESS.is_file()


def test_a_full_round_is_within_what_the_server_will_accept() -> None:
    """The page posts one pick per item. More than the server accepts would be a
    422 at the last balloon, the one moment the page has nothing to say."""
    assert ROUND_LENGTH <= MAX_PICKS


PAIRS_HARNESS = Path(__file__).parent / "js" / "arkade_pairs.test.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_a_memory_board_played_in_the_page() -> None:
    result = subprocess.run(  # noqa: S603
        [shutil.which("node") or "node", str(PAIRS_HARNESS)],
        capture_output=True,
        text=True,
        check=False,
        cwd=PAIRS_HARNESS.parents[2],
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_the_pairs_harness_is_reachable() -> None:
    assert PAIRS_HARNESS.is_file()


CONFETTI_HARNESS = Path(__file__).parent / "js" / "arkade_confetti.test.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_confetti_thrown_in_the_page() -> None:
    result = subprocess.run(  # noqa: S603
        [shutil.which("node") or "node", str(CONFETTI_HARNESS)],
        capture_output=True,
        text=True,
        check=False,
        cwd=CONFETTI_HARNESS.parents[2],
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_the_confetti_harness_is_reachable() -> None:
    assert CONFETTI_HARNESS.is_file()


SORT_HARNESS = Path(__file__).parent / "js" / "arkade_sort.test.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_a_sorting_round_played_in_the_page() -> None:
    result = subprocess.run(  # noqa: S603
        [shutil.which("node") or "node", str(SORT_HARNESS)],
        capture_output=True,
        text=True,
        check=False,
        cwd=SORT_HARNESS.parents[2],
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_the_sorting_harness_is_reachable() -> None:
    assert SORT_HARNESS.is_file()


@pytest.mark.parametrize("page", ["balloons.html", "pairs.html", "sort.html"])
def test_every_game_loads_the_confetti_before_itself(page: str) -> None:
    """All are deferred, so they run in the order the page names them."""
    import pensum.web

    html = (Path(pensum.web.__file__).parent / "templates" / "pages" / page).read_text()
    scripts = [line.strip() for line in html.splitlines() if "<script src=" in line]

    assert "arkade-confetti.js" in scripts[0]
    assert len(scripts) == 2

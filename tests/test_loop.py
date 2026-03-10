"""Integration-style tests for etch.loop — mocks agent, git, and display."""

from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from etch import loop
from etch.agent import AgentError
from etch.git import GitError
from etch.prompt import PromptError


FIXER_PROMPT = "# ETCH\nFix edge cases.\n"
BREAKER_PROMPT = "# BREAK\nFind issues.\n"


def _make_display_mock():
    """Return a mock EtchDisplay that acts as a context manager."""
    m = MagicMock()
    m.__enter__ = MagicMock(return_value=m)
    m.__exit__ = MagicMock(return_value=False)
    return m


@pytest.fixture()
def etch_files(tmp_path: Path):
    """Create minimal ETCH.md and BREAK.md in a temp directory."""
    etch = tmp_path / "ETCH.md"
    etch.write_text(FIXER_PROMPT, encoding="utf-8")
    brk = tmp_path / "BREAK.md"
    brk.write_text(BREAKER_PROMPT, encoding="utf-8")
    return etch, brk, tmp_path


class TestLoopCleanExit:
    def test_exits_when_fixer_makes_no_changes(self, etch_files):
        etch, _, _ = etch_files
        disp = _make_display_mock()

        with (
            patch("etch.loop.display.EtchDisplay", return_value=disp),
            patch("etch.loop.agent.run", return_value="nothing to do"),
            patch("etch.loop.git.has_changes", return_value=False),
            patch("etch.loop.git.commit") as mock_commit,
        ):
            loop.run(etch, max_iterations=5)

        # No commit should be made if fixer changed nothing
        mock_commit.assert_not_called()
        # Summary should have been called with no_changes reason
        disp.print_summary.assert_called_once()
        summary_stats = disp.print_summary.call_args[0][0]
        assert summary_stats["reason"] == "no_changes"

    def test_exits_on_breaker_all_clear(self, etch_files):
        etch, _, _ = etch_files
        disp = _make_display_mock()

        with (
            patch("etch.loop.display.EtchDisplay", return_value=disp),
            patch(
                "etch.loop.agent.run",
                side_effect=["fixed null check", "looks good\nETCH_ALL_CLEAR"],
            ),
            patch("etch.loop.git.has_changes", return_value=True),
            patch("etch.loop.git.commit"),
        ):
            loop.run(etch, max_iterations=5)

        summary_stats = disp.print_summary.call_args[0][0]
        assert summary_stats["reason"] == "clear"
        assert summary_stats["fixes"] == 1
        assert summary_stats["issues"] == 0


class TestLoopContinues:
    def test_continues_when_breaker_finds_issues(self, etch_files):
        etch, _, _ = etch_files
        disp = _make_display_mock()

        # Two iterations: first breaker finds issues, second finds nothing to fix
        with (
            patch("etch.loop.display.EtchDisplay", return_value=disp),
            patch(
                "etch.loop.agent.run",
                side_effect=[
                    "fixed bug",           # fixer iter 1
                    "ETCH_ISSUES_FOUND",   # breaker iter 1
                    "no changes needed",   # fixer iter 2 (but git says no changes)
                ],
            ),
            patch("etch.loop.git.has_changes", side_effect=[True, False]),
            patch("etch.loop.git.commit"),
        ):
            loop.run(etch, max_iterations=5)

        summary_stats = disp.print_summary.call_args[0][0]
        assert summary_stats["fixes"] == 1
        assert summary_stats["issues"] == 1
        assert summary_stats["reason"] == "no_changes"

    def test_stops_at_max_iterations(self, etch_files):
        etch, _, _ = etch_files
        disp = _make_display_mock()

        # Agent always finds issues — loop should stop at max_iterations
        with (
            patch("etch.loop.display.EtchDisplay", return_value=disp),
            patch("etch.loop.agent.run", return_value="ETCH_ISSUES_FOUND"),
            patch("etch.loop.git.has_changes", return_value=True),
            patch("etch.loop.git.commit"),
        ):
            loop.run(etch, max_iterations=3)

        summary_stats = disp.print_summary.call_args[0][0]
        assert summary_stats["reason"] == "max_iterations"
        assert summary_stats["iterations"] == 3


class TestLoopFlags:
    def test_dry_run_prints_prompt_and_exits(self, etch_files):
        etch, _, _ = etch_files

        with (
            patch("etch.loop.display.print_dry_run") as mock_dry,
            patch("etch.loop.agent.run") as mock_agent,
        ):
            loop.run(etch, dry_run=True)

        mock_dry.assert_called_once()
        mock_agent.assert_not_called()

    def test_no_commit_skips_git_commit(self, etch_files):
        etch, _, _ = etch_files
        disp = _make_display_mock()

        with (
            patch("etch.loop.display.EtchDisplay", return_value=disp),
            patch(
                "etch.loop.agent.run",
                side_effect=["fixed something", "ETCH_ALL_CLEAR"],
            ),
            patch("etch.loop.git.has_changes", return_value=True),
            patch("etch.loop.git.commit") as mock_commit,
        ):
            loop.run(etch, no_commit=True)

        mock_commit.assert_not_called()


class TestLoopErrorHandling:
    def test_handles_agent_error_gracefully(self, etch_files):
        etch, _, _ = etch_files
        disp = _make_display_mock()

        with (
            patch("etch.loop.display.EtchDisplay", return_value=disp),
            patch("etch.loop.agent.run", side_effect=AgentError("claude not found")),
        ):
            loop.run(etch, max_iterations=5)

        summary_stats = disp.print_summary.call_args[0][0]
        assert summary_stats["reason"] == "agent_error"

    def test_handles_git_error_gracefully(self, etch_files):
        etch, _, _ = etch_files
        disp = _make_display_mock()

        with (
            patch("etch.loop.display.EtchDisplay", return_value=disp),
            patch("etch.loop.agent.run", return_value="fixed bug"),
            patch("etch.loop.git.has_changes", side_effect=GitError("not a git repo")),
        ):
            loop.run(etch, max_iterations=5)

        summary_stats = disp.print_summary.call_args[0][0]
        assert summary_stats["reason"] == "git_error"

    def test_handles_missing_prompt_file(self, tmp_path: Path):
        missing = tmp_path / "ETCH.md"
        with patch("etch.loop.display.print_error") as mock_err:
            loop.run(missing)
        mock_err.assert_called_once()
        assert "not found" in mock_err.call_args[0][0].lower()

    def test_handles_missing_break_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        etch = tmp_path / "ETCH.md"
        etch.write_text("# ETCH prompt\n", encoding="utf-8")
        # No BREAK.md exists

        with patch("etch.loop.display.print_error") as mock_err:
            loop.run(etch)

        mock_err.assert_called_once()

    def test_stats_include_elapsed_time(self, etch_files):
        etch, _, _ = etch_files
        disp = _make_display_mock()

        with (
            patch("etch.loop.display.EtchDisplay", return_value=disp),
            patch("etch.loop.agent.run", return_value="nothing"),
            patch("etch.loop.git.has_changes", return_value=False),
        ):
            loop.run(etch)

        summary_stats = disp.print_summary.call_args[0][0]
        assert "elapsed" in summary_stats
        assert isinstance(summary_stats["elapsed"], float)
        assert summary_stats["elapsed"] >= 0.0

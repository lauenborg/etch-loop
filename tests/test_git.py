"""Tests for etch.git module — mocks subprocess calls."""

from unittest.mock import MagicMock, patch, call
import subprocess

import pytest

from etch.git import GitError, commit, has_changes


class TestHasChanges:
    def test_returns_false_when_no_changes(self):
        """Exit code 0 from git diff means clean working tree."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = has_changes()
        assert result is False
        mock_run.assert_called_once_with(
            ["git", "diff", "--quiet", "HEAD"],
            capture_output=True,
        )

    def test_returns_true_when_changes_present(self):
        """Exit code 1 from git diff means changes exist."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("subprocess.run", return_value=mock_result):
            result = has_changes()
        assert result is True

    def test_raises_git_error_when_git_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            with pytest.raises(GitError, match="not found"):
                has_changes()

    def test_raises_git_error_on_os_error(self):
        with patch("subprocess.run", side_effect=OSError("permission denied")):
            with pytest.raises(GitError, match="Failed to run git"):
                has_changes()

    def test_fallback_to_status_on_unexpected_exit_code(self):
        """For exit codes other than 0 or 1, fall back to git status --porcelain."""
        diff_result = MagicMock()
        diff_result.returncode = 128
        diff_result.stderr = b"fatal: not a git repo"

        status_result = MagicMock()
        status_result.returncode = 0
        status_result.stdout = ""

        with patch("subprocess.run", side_effect=[diff_result, status_result]):
            result = has_changes()
        assert result is False

    def test_fallback_status_shows_changes(self):
        """Fallback to git status shows changes (non-empty porcelain output)."""
        diff_result = MagicMock()
        diff_result.returncode = 128
        diff_result.stderr = b""

        status_result = MagicMock()
        status_result.returncode = 0
        status_result.stdout = "M  src/foo.py\n"

        with patch("subprocess.run", side_effect=[diff_result, status_result]):
            result = has_changes()
        assert result is True


class TestCommit:
    def test_stages_and_commits_successfully(self):
        add_result = MagicMock()
        add_result.returncode = 0
        add_result.stderr = ""

        commit_result = MagicMock()
        commit_result.returncode = 0
        commit_result.stderr = ""
        commit_result.stdout = "[main abc1234] fix(edge): test"

        with patch("subprocess.run", side_effect=[add_result, commit_result]) as mock_run:
            commit("fix(edge): test message")

        calls = mock_run.call_args_list
        assert calls[0] == call(
            ["git", "add", "-A"],
            capture_output=True,
            text=True,
        )
        assert calls[1] == call(
            ["git", "commit", "-m", "fix(edge): test message"],
            capture_output=True,
            text=True,
        )

    def test_raises_git_error_when_add_fails(self):
        add_result = MagicMock()
        add_result.returncode = 1
        add_result.stderr = "error: index file corrupt"

        with patch("subprocess.run", return_value=add_result):
            with pytest.raises(GitError, match="git add -A failed"):
                commit("fix(edge): test")

    def test_raises_git_error_when_commit_fails(self):
        add_result = MagicMock()
        add_result.returncode = 0
        add_result.stderr = ""

        commit_result = MagicMock()
        commit_result.returncode = 1
        commit_result.stderr = "nothing to commit"
        commit_result.stdout = ""

        with patch("subprocess.run", side_effect=[add_result, commit_result]):
            with pytest.raises(GitError, match="git commit failed"):
                commit("fix(edge): test")

    def test_raises_git_error_for_empty_message(self):
        with pytest.raises(GitError, match="empty"):
            commit("")

    def test_raises_git_error_for_whitespace_message(self):
        with pytest.raises(GitError, match="empty"):
            commit("   ")

    def test_raises_git_error_when_git_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            with pytest.raises(GitError, match="not found"):
                commit("fix(edge): test")

    def test_raises_git_error_on_os_error_during_add(self):
        with patch("subprocess.run", side_effect=OSError("broken")):
            with pytest.raises(GitError, match="Failed to run git add"):
                commit("fix(edge): test")

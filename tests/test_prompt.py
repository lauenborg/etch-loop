"""Tests for etch.prompt module."""

import pytest
from pathlib import Path

from etch.prompt import PromptError, load, load_break


class TestLoad:
    def test_returns_content_for_existing_file(self, tmp_path: Path):
        p = tmp_path / "ETCH.md"
        p.write_text("# Hello\nThis is my prompt.", encoding="utf-8")
        result = load(p)
        assert result == "# Hello\nThis is my prompt."

    def test_raises_for_missing_file(self, tmp_path: Path):
        p = tmp_path / "nonexistent.md"
        with pytest.raises(PromptError, match="not found"):
            load(p)

    def test_raises_for_empty_file(self, tmp_path: Path):
        p = tmp_path / "empty.md"
        p.write_text("", encoding="utf-8")
        with pytest.raises(PromptError, match="empty"):
            load(p)

    def test_raises_for_whitespace_only_file(self, tmp_path: Path):
        p = tmp_path / "whitespace.md"
        p.write_text("   \n\t  \n", encoding="utf-8")
        with pytest.raises(PromptError, match="empty"):
            load(p)

    def test_accepts_string_path(self, tmp_path: Path):
        p = tmp_path / "prompt.md"
        p.write_text("Some content", encoding="utf-8")
        result = load(str(p))
        assert result == "Some content"

    def test_raises_for_directory(self, tmp_path: Path):
        with pytest.raises(PromptError):
            load(tmp_path)

    def test_preserves_full_content(self, tmp_path: Path):
        content = "Line 1\nLine 2\n\nLine 4\n"
        p = tmp_path / "prompt.md"
        p.write_text(content, encoding="utf-8")
        assert load(p) == content


class TestLoadBreak:
    def test_loads_break_from_same_dir_as_etch(self, tmp_path: Path):
        etch = tmp_path / "ETCH.md"
        etch.write_text("fixer prompt", encoding="utf-8")
        brk = tmp_path / "BREAK.md"
        brk.write_text("breaker prompt", encoding="utf-8")
        result = load_break(etch)
        assert result == "breaker prompt"

    def test_loads_break_from_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        brk = tmp_path / "BREAK.md"
        brk.write_text("breaker in cwd", encoding="utf-8")
        result = load_break()
        assert result == "breaker in cwd"

    def test_raises_when_break_not_found(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        etch = tmp_path / "subdir" / "ETCH.md"
        etch.parent.mkdir()
        etch.write_text("fixer prompt", encoding="utf-8")
        with pytest.raises(PromptError, match="not found"):
            load_break(etch)

    def test_raises_for_empty_break_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        brk = tmp_path / "BREAK.md"
        brk.write_text("", encoding="utf-8")
        with pytest.raises(PromptError, match="empty"):
            load_break()

    def test_loads_break_directly_when_path_is_break_md(self, tmp_path: Path):
        brk = tmp_path / "BREAK.md"
        brk.write_text("breaker direct", encoding="utf-8")
        result = load_break(brk)
        assert result == "breaker direct"

    def test_prefers_sibling_over_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """BREAK.md alongside ETCH.md should win over BREAK.md in cwd."""
        subdir = tmp_path / "sub"
        subdir.mkdir()
        monkeypatch.chdir(tmp_path)

        cwd_break = tmp_path / "BREAK.md"
        cwd_break.write_text("cwd breaker", encoding="utf-8")

        etch = subdir / "ETCH.md"
        etch.write_text("fixer", encoding="utf-8")
        sibling_break = subdir / "BREAK.md"
        sibling_break.write_text("sibling breaker", encoding="utf-8")

        result = load_break(etch)
        assert result == "sibling breaker"

"""Tests for etch.signals module."""

import pytest

from etch.signals import extract_finding, parse


class TestParse:
    def test_returns_clear_for_all_clear_token(self):
        assert parse("Some output\nETCH_ALL_CLEAR") == "clear"

    def test_returns_issues_for_issues_found_token(self):
        assert parse("Found a bug\nETCH_ISSUES_FOUND") == "issues"

    def test_returns_issues_when_no_token_found(self):
        """Fail-safe: no token means assume issues."""
        assert parse("This output has no signal token at all.") == "issues"

    def test_returns_issues_for_empty_output(self):
        assert parse("") == "issues"

    def test_clear_token_mid_string(self):
        output = "line 1\nETCH_ALL_CLEAR\nsome trailing text"
        assert parse(output) == "clear"

    def test_issues_token_mid_string(self):
        output = "line 1\nETCH_ISSUES_FOUND\nsome trailing text"
        assert parse(output) == "issues"

    def test_clear_token_at_end(self):
        output = "All looks good.\nETCH_ALL_CLEAR"
        assert parse(output) == "clear"

    def test_issues_token_at_end(self):
        output = "Found a null dereference on line 42.\nETCH_ISSUES_FOUND"
        assert parse(output) == "issues"

    def test_clear_takes_priority_when_appears_first(self):
        """If ETCH_ALL_CLEAR appears before ETCH_ISSUES_FOUND, return clear."""
        output = "ETCH_ALL_CLEAR\nETCH_ISSUES_FOUND"
        assert parse(output) == "clear"

    def test_issues_takes_priority_when_appears_first(self):
        """If ETCH_ISSUES_FOUND appears before ETCH_ALL_CLEAR, return issues."""
        output = "ETCH_ISSUES_FOUND\nETCH_ALL_CLEAR"
        assert parse(output) == "issues"

    def test_token_embedded_in_longer_word(self):
        """Token embedded in a longer string should still match."""
        assert parse("prefix_ETCH_ALL_CLEAR_suffix") == "clear"

    def test_whitespace_only_output(self):
        assert parse("   \n\t  ") == "issues"

    def test_non_string_input_returns_issues(self):
        assert parse(None) == "issues"  # type: ignore[arg-type]


class TestExtractFinding:
    def test_extracts_last_meaningful_line_before_clear_token(self):
        output = "Line one\nThis is the finding\nETCH_ALL_CLEAR"
        result = extract_finding(output)
        assert result == "This is the finding"

    def test_extracts_last_meaningful_line_before_issues_token(self):
        output = "Line one\nNull pointer on line 84\nETCH_ISSUES_FOUND"
        result = extract_finding(output)
        assert result == "Null pointer on line 84"

    def test_skips_empty_lines(self):
        output = "Finding text\n\n\nETCH_ALL_CLEAR"
        result = extract_finding(output)
        assert result == "Finding text"

    def test_skips_markdown_headers(self):
        output = "# Header\nActual finding\nETCH_ALL_CLEAR"
        result = extract_finding(output)
        assert result == "Actual finding"

    def test_returns_empty_for_no_content_before_token(self):
        output = "ETCH_ALL_CLEAR"
        result = extract_finding(output)
        assert result == ""

    def test_returns_empty_for_empty_output(self):
        assert extract_finding("") == ""

    def test_returns_empty_for_none(self):
        assert extract_finding(None) == ""  # type: ignore[arg-type]

    def test_no_token_returns_last_line(self):
        """With no token, treats entire output as content."""
        output = "Line one\nLine two"
        result = extract_finding(output)
        assert result == "Line two"

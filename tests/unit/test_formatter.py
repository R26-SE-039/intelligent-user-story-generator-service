"""Unit tests for src.utils.formatter.normalize_text."""

from __future__ import annotations

import pytest

from src.utils.formatter import normalize_text


class TestNormalizeTextFillerWords:
    """Filler words should be removed."""

    def test_removes_um(self):
        assert normalize_text("um this is um a test") == "this is a test"

    def test_removes_uh(self):
        assert normalize_text("uh okay uh let's go") == "okay let's go"

    def test_removes_you_know(self):
        assert normalize_text("you know it's you know important") == "it's important"

    def test_removes_like(self):
        assert normalize_text("it's like really like awesome") == "it's really awesome"

    def test_removes_multiple_filler_types(self):
        text = "um so like you know uh we should proceed"
        result = normalize_text(text)
        for filler in ("um", "uh", "you know", "like"):
            assert filler not in result.lower()

    def test_case_insensitive_removal(self):
        result = normalize_text("UM this is UH a test")
        assert "um" not in result.lower()
        assert "uh" not in result.lower()


class TestNormalizeTextWhitespace:
    """Whitespace collapsing and trimming."""

    def test_collapses_multiple_spaces(self):
        assert normalize_text("hello   world") == "hello world"

    def test_strips_leading_whitespace(self):
        assert normalize_text("   hello") == "hello"

    def test_strips_trailing_whitespace(self):
        assert normalize_text("hello   ") == "hello"

    def test_handles_tabs_and_newlines(self):
        result = normalize_text("hello\t\nworld")
        assert result == "hello world"


class TestNormalizeTextEdgeCases:
    """Edge cases for normalize_text."""

    def test_empty_string_returns_empty(self):
        assert normalize_text("") == ""

    def test_only_filler_returns_empty(self):
        # After removing fillers and stripping, the result should be empty
        result = normalize_text("um uh")
        assert result.strip() == ""

    def test_no_change_needed(self):
        text = "As a product manager I want to create stories."
        assert normalize_text(text) == text

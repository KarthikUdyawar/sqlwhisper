"""Tests for core/constants.py."""

from __future__ import annotations

from core.constants import (
    _BLOCKED_LIST,
    APPROVAL_MODE_DEFAULT,
    BLOCKED_KEYWORDS,
    CORRECTION_PROMPT_TEMPLATE,
    DEFAULT_MODEL,
    FALLBACK_MODEL,
    MAX_RETRIES,
    MAX_ROWS,
    MAX_TABLES_IN_PROMPT,
    MAX_TOOL_CALLS_PER_TURN,
    OLLAMA_BASE_URL,
    OLLAMA_TIMEOUT_SECONDS,
    PROMPT_TEMPLATE,
    SUPPORTED_DIALECTS,
    Dialect,
)


class TestDialect:
    def test_values(self) -> None:
        assert Dialect.POSTGRESQL == "postgresql"
        assert Dialect.SQLITE == "sqlite"
        assert Dialect.MYSQL == "mysql"

    def test_supported_dialects_matches_enum(self) -> None:
        assert SUPPORTED_DIALECTS == {d.value for d in Dialect}

    def test_frozenset_immutable(self) -> None:
        import pytest

        with pytest.raises((AttributeError, TypeError)):
            SUPPORTED_DIALECTS.add("oracle")  # type: ignore[attr-defined]


class TestBlockedKeywords:
    # Immutable, must exactly match BLOCKED_KEYWORDS — catches removals and additions.
    REQUIRED: frozenset[str] = frozenset(
        {
            "DROP",
            "DELETE",
            "UPDATE",
            "INSERT",
            "TRUNCATE",
            "ALTER",
            "GRANT",
            "REVOKE",
            "EXEC",
            "EXECUTE",
            "CREATE",
            "REPLACE",
            "MERGE",
            "CALL",
        }
    )

    def test_required_keywords_present(self) -> None:
        missing = self.REQUIRED - BLOCKED_KEYWORDS
        assert not missing, f"Missing blocked keywords: {missing}"

    def test_no_unexpected_keywords_added(self) -> None:
        extra = BLOCKED_KEYWORDS - self.REQUIRED
        assert not extra, f"Unexpected keywords in BLOCKED_KEYWORDS: {extra}"

    def test_keywords_uppercase(self) -> None:
        for kw in BLOCKED_KEYWORDS:
            assert kw == kw.upper(), f"Keyword '{kw}' must be uppercase"

    def test_frozenset_immutable(self) -> None:
        import pytest

        with pytest.raises((AttributeError, TypeError)):
            BLOCKED_KEYWORDS.add("NEWKW")  # type: ignore[attr-defined]


class TestDefaults:
    def test_ollama_defaults(self) -> None:
        assert DEFAULT_MODEL == "qwen3:8b"
        assert FALLBACK_MODEL == "qwen3:14b"
        assert OLLAMA_BASE_URL == "http://localhost:11434"
        assert OLLAMA_TIMEOUT_SECONDS == 30

    def test_app_defaults(self) -> None:
        assert MAX_ROWS == 500
        assert MAX_RETRIES == 3
        assert MAX_TABLES_IN_PROMPT == 5
        assert MAX_TOOL_CALLS_PER_TURN == 8
        assert APPROVAL_MODE_DEFAULT is False


class TestPromptTemplates:
    def test_prompt_template_has_required_placeholders(self) -> None:
        for placeholder in ("{dialect}", "{schema_subset}", "{question}", "{max_rows}"):
            assert placeholder in PROMPT_TEMPLATE, f"Missing {placeholder}"

    def test_prompt_template_includes_full_blocked_list(self) -> None:
        """Ensure the prompt uses the complete dynamic blocked list."""
        assert "{_BLOCKED_LIST}" in PROMPT_TEMPLATE, (
            "Missing {_BLOCKED_LIST} placeholder"
        )

        # Render it properly for the check
        rendered = PROMPT_TEMPLATE.format(
            dialect="sqlite",
            schema_subset="",
            question="",
            max_rows=500,
            _BLOCKED_LIST=_BLOCKED_LIST,
        )
        assert all(kw in rendered for kw in BLOCKED_KEYWORDS), (
            f"Not all blocked keywords appear in rendered prompt. Missing: "
            f"{BLOCKED_KEYWORDS - set(rendered.split())}"
        )

    def test_correction_template_has_required_placeholders(self) -> None:
        for placeholder in ("{sql}", "{error}"):
            assert placeholder in CORRECTION_PROMPT_TEMPLATE, f"Missing {placeholder}"

    def test_prompt_template_format(self) -> None:
        rendered = PROMPT_TEMPLATE.format(
            dialect="sqlite",
            schema_subset="users(id, name)",
            question="show all users",
            max_rows=500,
            _BLOCKED_LIST=_BLOCKED_LIST,
        )
        assert "sqlite" in rendered
        assert "users(id, name)" in rendered
        assert "show all users" in rendered
        assert "Never use" in rendered
        # Verify actual blocked keywords are present in rendered prompt
        for kw in BLOCKED_KEYWORDS:
            assert kw in rendered, f"Blocked keyword {kw} missing from rendered prompt"

    def test_correction_template_format(self) -> None:
        rendered = CORRECTION_PROMPT_TEMPLATE.format(
            dialect="sqlite",
            schema_subset="users(id, name)",
            question="show all users",
            sql="SELECT * FORM users",
            error="syntax error near FORM",
        )
        assert "SELECT * FORM users" in rendered
        assert "syntax error near FORM" in rendered


class TestHistoryDbPath:
    def test_is_absolute(self) -> None:
        from core.constants import HISTORY_DB_PATH

        assert HISTORY_DB_PATH.is_absolute()

    def test_is_path_object(self) -> None:
        from pathlib import Path

        from core.constants import HISTORY_DB_PATH

        assert isinstance(HISTORY_DB_PATH, Path)

    def test_ends_with_db_filename(self) -> None:
        from core.constants import HISTORY_DB_PATH

        assert HISTORY_DB_PATH.name == "sqlwhisper_history.db"


class TestCorrectionPromptTemplate:
    def test_has_all_required_placeholders(self) -> None:
        for ph in ("{dialect}", "{schema_subset}", "{question}", "{sql}", "{error}"):
            assert ph in CORRECTION_PROMPT_TEMPLATE, f"Missing {ph}"

    def test_formats_correctly(self) -> None:
        rendered = CORRECTION_PROMPT_TEMPLATE.format(
            dialect="sqlite",
            schema_subset="users(id, name)",
            question="show all users",
            sql="SELECT * FORM users",
            error="syntax error near FORM",
        )
        assert "sqlite" in rendered
        assert "users(id, name)" in rendered
        assert "show all users" in rendered
        assert "SELECT * FORM users" in rendered
        assert "syntax error near FORM" in rendered

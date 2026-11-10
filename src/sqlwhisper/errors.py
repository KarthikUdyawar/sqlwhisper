class SourceError(Exception):
    """Bad upload, bad URL, unknown source or unreachable DB. Maps to HTTP 400."""


class SQLIssue(Exception):
    """Model SQL is unusable but fixable. The message goes back to the model for a retry."""


class SyntaxIssue(SQLIssue):
    """SQL does not parse."""


class SchemaIssue(SQLIssue):
    """SQL references a table or column that does not exist."""


class UnsafeSQL(Exception):
    """Not a single read-only SELECT. Never retried. Maps to HTTP 422."""

    def __init__(self, message: str, sql: str = "") -> None:
        super().__init__(message)
        self.sql = sql


class QueryTimeout(Exception):
    """Statement ran past the time limit. Maps to HTTP 504."""


class QueryFailed(Exception):
    """The database rejected the query at run time. Retried like SQLIssue, then 422."""


class ValidationFailed(Exception):
    """No working query after all attempts. Maps to HTTP 422, carries the last SQL tried."""

    def __init__(self, message: str, last_sql: str) -> None:
        super().__init__(message)
        self.last_sql = last_sql


class LLMUnavailable(Exception):
    """Ollama unreachable, timed out, model missing or bad reply. Maps to HTTP 502."""

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


class QueryTimeout(Exception):
    """Statement ran past the time limit. Maps to HTTP 504."""


class QueryFailed(Exception):
    """The database rejected the query at run time. Maps to HTTP 422."""

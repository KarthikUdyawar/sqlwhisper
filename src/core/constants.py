"""SQLWhisper constants — magic strings, numbers, and enumerations.

All literals that appear in more than one place, or that have domain
significance, live here.  Import from this module; never hard-code.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

# ---------------------------------------------------------------------------
# Supported SQL dialects
# ---------------------------------------------------------------------------


class Dialect(StrEnum):
    """Supported SQL dialects in SQLWhisper.

    These values are used both for database connection configuration
    and for instructing the LLM on the correct SQL dialect to generate.
    """

    POSTGRESQL = "postgresql"
    SQLITE = "sqlite"
    MYSQL = "mysql"


SUPPORTED_DIALECTS: frozenset[str] = frozenset(d.value for d in Dialect)


# ---------------------------------------------------------------------------
# Ollama / LLM
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "qwen3:8b"
FALLBACK_MODEL = "qwen3:14b"

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_GENERATE_PATH = "/api/generate"

OLLAMA_TIMEOUT_SECONDS = 30
OLLAMA_TIMEOUT_MIN = 1
OLLAMA_TIMEOUT_MAX = 300
OLLAMA_MAX_TOKENS = 1024

APP_MAX_ROWS_MIN = 1
APP_MAX_ROWS_MAX = 10_000
APP_MAX_RETRIES_MIN = 1
APP_MAX_RETRIES_MAX = 10
APP_MAX_TABLES_MIN = 1
APP_MAX_TABLES_MAX = 20  # upper bound for tables included in the prompt schema context
APP_MAX_TOOL_CALLS_MIN = 1
APP_MAX_TOOL_CALLS_MAX = 20  # circuit breaker ceiling for the agent loop


# ---------------------------------------------------------------------------
# Query execution
# ---------------------------------------------------------------------------

MAX_ROWS = 500  # hard LIMIT appended by executor if missing
MAX_RETRIES = 3  # validation + LLM correction retry loop
MAX_TABLES_IN_PROMPT = 5  # schema-context budget
MAX_TOOL_CALLS_PER_TURN = 8  # agent loop circuit breaker (PRD §5.3)
APPROVAL_MODE_DEFAULT = (
    False  # per-connection flag default; off for local/dev (PRD §5.5)
)

QUERY_HISTORY_LIMIT = 20  # history sidebar entries shown in UI


# ---------------------------------------------------------------------------
# SQL safety — blocked statement types
# ---------------------------------------------------------------------------

BLOCKED_KEYWORDS: frozenset[str] = frozenset(
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

# Derived string for the LLM prompt (keeps prompt and guard always in sync)
_BLOCKED_LIST = ", ".join(sorted(BLOCKED_KEYWORDS))

# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

PROMPT_TEMPLATE = """\
You are an expert {dialect} SQL engineer.

Schema:
{schema_subset}

Rules:
- Return ONLY valid SQL, no explanation, no markdown fences
- Never use {_BLOCKED_LIST}
- Always alias tables
- LIMIT {max_rows} rows unless the user specifies otherwise
- Use exact column names from the schema above

Question: {question}

SQL:"""

# Correction prompt includes dialect + schema so the LLM has full context
# when resolving hallucinated column names or dialect-specific syntax errors.
CORRECTION_PROMPT_TEMPLATE = """\
The following SQL is invalid.

Dialect: {dialect}

Schema:
{schema_subset}

Original question: {question}

SQL:
{sql}

Error:
{error}

Fix the SQL. Return ONLY valid SQL, no explanation, no markdown fences.

SQL:"""


# ---------------------------------------------------------------------------
# Schema introspection
# ---------------------------------------------------------------------------

SCHEMA_CACHE_KEY = "schema_cache"
SCHEMA_MAX_TABLES_WARN = 50  # warn user when DB has more tables than this


# ---------------------------------------------------------------------------
# App / UI
# ---------------------------------------------------------------------------

APP_TITLE = "SQLWhisper"
APP_ICON = "🔍"
STREAMLIT_PORT = 8501

# Anchored to the project root so the path is CWD-independent at runtime
# and consistent inside Docker (where CWD may differ from the project root).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
HISTORY_DB_PATH: Path = _PROJECT_ROOT / "sqlwhisper_history.db"

# Result formatting
CSV_EXPORT_FILENAME = "sqlwhisper_results.csv"
MAX_DISPLAY_ROWS = 500  # rows shown in st.dataframe before pagination
ELAPSED_TIME_DECIMALS = 2  # decimal places for query elapsed time display


# ---------------------------------------------------------------------------
# Config / env
# ---------------------------------------------------------------------------

ENV_PREFIX = "SQLWHISPER_"
ENV_NESTED_DELIMITER = "__"
CONFIG_YAML_FILENAME = "config.yaml"
CONFIG_DIR = "config"  # relative to project root

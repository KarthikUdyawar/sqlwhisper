from dataclasses import dataclass

from sqlwhisper.errors import QueryFailed, SQLIssue, UnsafeSQL, ValidationFailed
from sqlwhisper.executor import run
from sqlwhisper.llm import LLMClient
from sqlwhisper.models import QA, Answer
from sqlwhisper.prompt import conversation, correction, extract_sql, system_prompt
from sqlwhisper.schema import select_tables
from sqlwhisper.sources.base import DataSource
from sqlwhisper.validator import validate


@dataclass(frozen=True)
class PipelineConfig:
    max_rows: int
    max_retries: int
    timeout_s: float
    max_tables: int = 5


def answer(
    question: str, context: list[QA], source: DataSource, llm: LLMClient, cfg: PipelineConfig
) -> Answer:
    """Generate -> validate -> execute. Fixable failures go back to the model, up to max_retries.

    Raises UnsafeSQL (never retried), ValidationFailed (retries exhausted), QueryTimeout (never
    retried) and LLMUnavailable.
    """
    schema = select_tables(question, source.schema(), cfg.max_tables)
    system = system_prompt(source.dialect, schema)
    messages = conversation(question, context)
    attempt = 0
    while True:
        attempt += 1
        sql = extract_sql(llm.complete(system, messages))
        try:
            query = validate(sql, schema, source.dialect)
            result = run(source, query, max_rows=cfg.max_rows, timeout_s=cfg.timeout_s)
        except UnsafeSQL as e:
            raise UnsafeSQL(str(e), sql) from None
        except (SQLIssue, QueryFailed) as e:
            if attempt > cfg.max_retries:
                raise ValidationFailed(str(e), sql) from None
            messages = [*messages, {"role": "assistant", "content": sql}, correction(str(e))]
        else:
            return Answer(result=result, attempts=attempt)

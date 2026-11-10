from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from sqlwhisper.charts import pick_chart
from sqlwhisper.errors import (
    LLMUnavailable,
    QueryTimeout,
    SourceError,
    UnsafeSQL,
    ValidationFailed,
)
from sqlwhisper.history import HistoryStore
from sqlwhisper.llm import LLMClient, OllamaClient
from sqlwhisper.models import (
    Health,
    HistoryEntry,
    QueryRequest,
    QueryResult,
    Schema,
    SourceInfo,
    UrlRequest,
)
from sqlwhisper.pipeline import PipelineConfig, answer
from sqlwhisper.settings import Settings
from sqlwhisper.sources.base import DataSource
from sqlwhisper.sources.csv import CsvSource, purge_uploads
from sqlwhisper.sources.postgres import PostgresSource
from sqlwhisper.sources.registry import SourceRegistry

# exception -> (HTTP status, error code). Bodies never carry stack traces.
_ERRORS: dict[type[Exception], tuple[int, str]] = {
    SourceError: (400, "bad_source"),
    SQLAlchemyError: (400, "bad_source"),
    UnsafeSQL: (422, "unsafe_sql"),
    ValidationFailed: (422, "validation_failed"),
    LLMUnavailable: (502, "llm_unavailable"),
    QueryTimeout: (504, "query_timeout"),
}


def create_app(
    settings: Settings | None = None,
    *,
    llm: LLMClient | None = None,
    health: Callable[[], Health] | None = None,
) -> FastAPI:
    """The only place concrete classes are wired. Pass llm (and health) to swap Ollama out."""
    cfg = settings or Settings()
    if llm is None:
        ollama = OllamaClient(cfg.ollama_url, cfg.ollama_model, cfg.ollama_timeout_s)
        llm, health = ollama, health or ollama.health
    check_health = health or (
        lambda: Health(ollama=False, model=False, model_name=cfg.ollama_model)
    )

    registry = SourceRegistry()
    history = HistoryStore(cfg.data_dir / "history.db")
    pipeline_cfg = PipelineConfig(
        max_rows=cfg.max_rows, max_retries=cfg.max_retries, timeout_s=cfg.query_timeout_s
    )
    max_bytes = cfg.max_upload_mb * 1024 * 1024

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        purge_uploads(cfg.data_dir)  # uploads do not outlive the process
        yield

    app = FastAPI(title="SQLWhisper", lifespan=lifespan)
    app.state.registry = registry

    def info(source: DataSource) -> SourceInfo:
        tables = [t.name for t in source.schema().tables]
        return SourceInfo(source_id=source.id, label=source.label, tables=tables)

    @app.get("/health")
    def get_health() -> Health:
        return check_health()

    @app.post("/sources/csv")
    def upload_csv(file: UploadFile) -> SourceInfo:
        data = file.file.read(max_bytes + 1)  # one byte over the limit is enough to reject
        source = CsvSource.from_upload(
            data, file.filename or "", data_dir=cfg.data_dir, max_bytes=max_bytes
        )
        return info(registry.add(source))

    @app.post("/sources/url")
    def connect_url(body: UrlRequest) -> SourceInfo:
        return info(registry.add(PostgresSource.from_url(body.url)))

    @app.get("/sources/{source_id}/schema")
    def get_schema(source_id: str) -> Schema:
        return registry.get(source_id).schema()

    @app.post("/query")
    def query(body: QueryRequest) -> QueryResult:
        source = registry.get(body.source_id)
        try:
            out = answer(body.question, body.context, source, llm, pipeline_cfg)
        except Exception as e:
            sql = getattr(e, "last_sql", None) or getattr(e, "sql", None) or ""
            history.log(body.question, sql, 0, source.label, ok=False)
            raise
        result = out.result
        history.log(body.question, result.sql, len(result.rows), source.label, ok=True)
        return QueryResult(
            sql=result.sql,
            columns=result.columns,
            rows=result.rows,
            row_count=len(result.rows),
            truncated=result.truncated,
            elapsed_ms=result.elapsed_ms,
            attempts=out.attempts,
            chart=pick_chart(result),
        )

    @app.get("/history")
    def get_history() -> list[HistoryEntry]:
        return history.recent(20)

    _register_error_handlers(app)
    return app


def _body(status: int, code: str, message: str, last_sql: str | None = None) -> JSONResponse:
    content = {"code": code, "message": message}
    if last_sql is not None:
        content["last_sql"] = last_sql
    return JSONResponse(status_code=status, content=content)


def _register_error_handlers(app: FastAPI) -> None:
    def handler_for(status: int, code: str) -> Callable[[Request, Exception], JSONResponse]:
        def handle(request: Request, exc: Exception) -> JSONResponse:
            if isinstance(exc, SQLAlchemyError):
                message = "could not reach the database"  # driver text can carry host details
            else:
                message = str(exc)
            last_sql = getattr(exc, "last_sql", getattr(exc, "sql", None))
            return _body(status, code, message, last_sql)

        return handle

    for exc_type, (status, code) in _ERRORS.items():
        app.add_exception_handler(exc_type, handler_for(status, code))

    def bad_request(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, RequestValidationError)
        # Not FastAPI's default body: that echoes the offending input back.
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        return _body(422, "bad_request", problems)

    def internal(request: Request, exc: Exception) -> JSONResponse:
        return _body(500, "internal_error", "unexpected error")

    app.add_exception_handler(RequestValidationError, bad_request)
    app.add_exception_handler(Exception, internal)

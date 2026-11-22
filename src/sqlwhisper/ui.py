from typing import Any

import httpx
import pandas as pd
import plotly.express as px
import streamlit as st
from plotly.graph_objects import Figure

from sqlwhisper.models import QueryResult
from sqlwhisper.settings import Settings

_CONTEXT_TURNS = 3  # same cap as the server (D-16)
_TIMEOUT_S = 180.0  # up to 3 attempts at OLLAMA_TIMEOUT_S 60 each
_DRAW = {"bar": px.bar, "line": px.line, "scatter": px.scatter}
_ERROR_TEXT = {
    "llm_unavailable": "Ollama is not reachable. Check that it is running and the model is pulled.",
    "unsafe_sql": "Blocked: only read-only SELECT queries are allowed.",
    "query_timeout": "The query ran too long and was stopped. Try a narrower question.",
    "validation_failed": "Could not produce valid SQL: {message}",
    "bad_source": "Problem with the data source: {message}",
    "bad_request": "Invalid request: {message}",
    "api_unreachable": "Cannot reach the SQLWhisper API. Is `make api` running?",
}
_GENERIC_ERROR = "Unexpected error. Check the API log."
_SHOWS_SQL = {"validation_failed", "unsafe_sql"}  # the user can learn from the rejected SQL


def build_figure(result: QueryResult) -> Figure | None:
    """Chart spec to Plotly figure. The API sends the spec, the UI owns Plotly (D-10)."""
    spec = result.chart
    if spec is None:
        return None
    frame = pd.DataFrame(result.rows, columns=result.columns)
    return _DRAW[spec.type](frame, x=spec.x, y=spec.y)


def build_context(turns: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Last 3 answered turns as Q/SQL pairs. A turn without SQL (it failed) is no context."""
    answered = [t for t in turns if t.get("sql")]
    return [{"question": t["question"], "sql": t["sql"]} for t in answered[-_CONTEXT_TURNS:]]


def error_message(body: dict[str, Any]) -> tuple[str, str | None]:
    """API error body to (user text, SQL worth showing). Unknown codes stay generic."""
    code = body.get("code", "")
    template = _ERROR_TEXT.get(code, _GENERIC_ERROR)
    sql = body.get("last_sql") if code in _SHOWS_SQL else None
    return template.format(message=body.get("message", "")), sql


def _call(method: str, path: str, **kwargs: Any) -> tuple[bool, Any]:
    """One API call. A dead API or a non-JSON reply becomes an error body, not an exception."""
    try:
        response = httpx.request(method, Settings().api_url + path, timeout=_TIMEOUT_S, **kwargs)
    except httpx.HTTPError:
        return False, {"code": "api_unreachable"}
    try:
        return response.is_success, response.json()
    except ValueError:
        return False, {}


def _show_error(body: dict[str, Any]) -> None:
    message, sql = error_message(body)
    st.error(message)
    if sql:
        st.code(sql, language="sql")


def _use_source(ok: bool, body: dict[str, Any]) -> None:
    st.session_state["source"] = body if ok else None
    st.session_state["source_error"] = None if ok else body
    st.session_state["turns"] = []


def _health_panel() -> None:
    st.sidebar.title("SQLWhisper")
    ok, health = _call("GET", "/health")
    if not ok:
        st.sidebar.error(error_message(health)[0])
    elif health["ollama"] and health["model"]:
        st.sidebar.success(f"Ollama ready: {health['model_name']}")
    elif health["ollama"]:
        st.sidebar.warning(f"Ollama is up but model {health['model_name']} is missing.")
    else:
        st.sidebar.error(error_message({"code": "llm_unavailable"})[0])


def _source_panel() -> dict[str, Any] | None:
    upload = st.sidebar.file_uploader("CSV file", type="csv")
    if upload is not None and st.session_state.get("upload_id") != upload.file_id:
        st.session_state["upload_id"] = upload.file_id
        file = {"file": (upload.name, upload.getvalue(), "text/csv")}
        _use_source(*_call("POST", "/sources/csv", files=file))

    url = st.sidebar.text_input("Postgres URL", type="password")
    if st.sidebar.button("Connect") and url:
        _use_source(*_call("POST", "/sources/url", json={"url": url}))

    if st.session_state.get("source_error"):
        st.sidebar.error(error_message(st.session_state["source_error"])[0])
    source: dict[str, Any] | None = st.session_state.get("source")
    if source is None:
        return None
    st.sidebar.caption(f"Source: {source['label']} ({', '.join(source['tables'])})")
    with st.sidebar.expander("Schema"):
        ok, schema = _call("GET", f"/sources/{source['source_id']}/schema")
        if ok:
            st.json(schema)
        else:
            st.error(error_message(schema)[0])
    return source


def _history_panel() -> None:
    ok, entries = _call("GET", "/history")
    if not ok or not entries:
        return
    st.sidebar.subheader("History")
    for entry in entries:
        mark = "✓" if entry["ok"] else "✗"
        label = f"{mark} {entry['question'][:40]}"
        if st.sidebar.button(label, key=f"history-{entry['id']}"):
            st.session_state["rerun"] = entry["question"]
            st.rerun()


def _ask(question: str, source_id: str) -> None:
    turns: list[dict[str, Any]] = st.session_state["turns"]
    payload = {"source_id": source_id, "question": question, "context": build_context(turns)}
    with st.spinner("Thinking..."):
        ok, body = _call("POST", "/query", json=payload)
    if ok:
        result = QueryResult.model_validate(body)
        turns.append({"question": question, "sql": result.sql, "result": result, "error": None})
    else:
        turns.append({"question": question, "sql": None, "result": None, "error": body})


def _render_turn(index: int, turn: dict[str, Any]) -> None:
    with st.chat_message("user"):
        st.write(turn["question"])
    with st.chat_message("assistant"):
        if turn["error"] is not None:
            _show_error(turn["error"])
            return
        result: QueryResult = turn["result"]
        with st.expander("SQL"):
            st.code(result.sql, language="sql")
        frame = pd.DataFrame(result.rows, columns=result.columns)
        st.dataframe(frame)
        figure = build_figure(result)
        if figure is not None:
            st.plotly_chart(figure, key=f"chart-{index}")
        note = f"{result.row_count} rows, {result.elapsed_ms} ms, {result.attempts} attempt(s)"
        st.caption(note + (", truncated at the row cap" if result.truncated else ""))
        st.download_button(
            "Download CSV",
            frame.to_csv(index=False),
            file_name="result.csv",
            mime="text/csv",
            key=f"csv-{index}",
        )


def main() -> None:
    st.set_page_config(page_title="SQLWhisper", layout="wide")
    st.session_state.setdefault("turns", [])
    _health_panel()
    source = _source_panel()
    typed = st.chat_input("Ask about your data", disabled=source is None)
    question = st.session_state.pop("rerun", None) or typed
    if source is None:
        st.info("Upload a CSV or connect a Postgres URL in the sidebar.")
    elif question:
        _ask(question, source["source_id"])
    for index, turn in enumerate(st.session_state["turns"]):
        _render_turn(index, turn)
    _history_panel()  # last, so the question just asked is already in the list


if __name__ == "__main__":
    main()

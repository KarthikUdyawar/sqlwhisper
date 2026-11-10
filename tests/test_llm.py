import json

import httpx
import pytest

from sqlwhisper.errors import LLMUnavailable
from sqlwhisper.llm import OllamaClient
from sqlwhisper.models import Message


def client(
    handler: httpx.MockTransport | None, base_url: str = "http://ollama:11434"
) -> OllamaClient:
    return OllamaClient(base_url, "qwen-test", 5, transport=handler)


def reply(content: str) -> httpx.MockTransport:
    return httpx.MockTransport(
        lambda request: httpx.Response(
            200, json={"message": {"role": "assistant", "content": content}}
        )
    )


def test_returns_message_content() -> None:
    assert (
        client(reply("SELECT 1")).complete("sys", [{"role": "user", "content": "hi"}]) == "SELECT 1"
    )


def test_request_shape() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"message": {"content": "SELECT 1"}})

    messages: list[Message] = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "SELECT 1"},
        {"role": "user", "content": "q2"},
    ]
    client(httpx.MockTransport(handler)).complete("be precise", messages)

    request = seen[0]
    body = json.loads(request.content)
    assert request.method == "POST"
    assert request.url.path == "/api/chat"
    assert body["model"] == "qwen-test"
    assert body["stream"] is False
    assert body["options"]["temperature"] == 0
    assert body["messages"][0] == {"role": "system", "content": "be precise"}
    assert body["messages"][1:] == messages


def test_trailing_slash_in_base_url_is_fine() -> None:
    assert client(reply("ok"), "http://ollama:11434/").complete("s", []) == "ok"


def test_connection_refused_is_llm_unavailable() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(LLMUnavailable, match="cannot reach Ollama"):
        client(httpx.MockTransport(refuse)).complete("s", [])


def test_timeout_is_llm_unavailable() -> None:
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow")

    with pytest.raises(LLMUnavailable, match="ReadTimeout"):
        client(httpx.MockTransport(slow)).complete("s", [])


def test_missing_model_surfaces_ollama_message() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(404, json={"error": "model 'x' not found"})
    )
    with pytest.raises(LLMUnavailable, match="404.*not found"):
        client(transport).complete("s", [])


def test_non_json_error_body_is_handled() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(500, text="boom"))
    with pytest.raises(LLMUnavailable, match="500.*boom"):
        client(transport).complete("s", [])


@pytest.mark.parametrize("body", [{}, {"message": {}}, {"message": {"content": 5}}, ["x"]])
def test_malformed_success_body(body: object) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=body))
    with pytest.raises(LLMUnavailable, match="unexpected"):
        client(transport).complete("s", [])


def test_non_json_success_body() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text="<html>"))
    with pytest.raises(LLMUnavailable, match="unexpected"):
        client(transport).complete("s", [])


def tags(*names: str) -> httpx.MockTransport:
    return httpx.MockTransport(
        lambda request: httpx.Response(200, json={"models": [{"name": n} for n in names]})
    )


def test_health_ok_when_model_installed() -> None:
    health = client(tags("qwen-test", "other")).health()
    assert (health.ollama, health.model, health.model_name) == (True, True, "qwen-test")


def test_health_matches_latest_tag() -> None:
    assert client(tags("qwen-test:latest")).health().model is True


def test_health_model_missing() -> None:
    health = client(tags("other:1b")).health()
    assert (health.ollama, health.model) == (True, False)


def test_health_ollama_down() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    health = client(httpx.MockTransport(refuse)).health()
    assert (health.ollama, health.model) == (False, False)


@pytest.mark.parametrize(
    "response", [httpx.Response(500, text="x"), httpx.Response(200, text="<html>")]
)
def test_health_bad_response_counts_as_down(response: httpx.Response) -> None:
    assert client(httpx.MockTransport(lambda request: response)).health().ollama is False

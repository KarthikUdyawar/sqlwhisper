from typing import Protocol

import httpx

from sqlwhisper.errors import LLMUnavailable
from sqlwhisper.models import Message


class LLMClient(Protocol):
    def complete(self, system: str, messages: list[Message]) -> str: ...


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_s: float,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._model = model
        self._http = httpx.Client(base_url=base_url, timeout=timeout_s, transport=transport)

    def complete(self, system: str, messages: list[Message]) -> str:
        payload = {
            "model": self._model,
            "messages": [{"role": "system", "content": system}, *messages],
            "stream": False,
            "options": {"temperature": 0},
        }
        try:
            response = self._http.post("/api/chat", json=payload)
        except httpx.HTTPError as e:  # connect errors, timeouts, protocol errors
            raise LLMUnavailable(f"cannot reach Ollama ({type(e).__name__})") from None
        if response.status_code != 200:
            raise LLMUnavailable(_error_detail(response))
        try:
            content = response.json()["message"]["content"]
        except (ValueError, KeyError, TypeError):
            raise LLMUnavailable("unexpected response from Ollama") from None
        if not isinstance(content, str):
            raise LLMUnavailable("unexpected response from Ollama")
        return content


def _error_detail(response: httpx.Response) -> str:
    try:
        detail = response.json()["error"]
    except (ValueError, KeyError, TypeError):
        detail = response.text[:200]
    return f"Ollama error {response.status_code}: {detail}"

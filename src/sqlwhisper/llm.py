from typing import Protocol

import httpx

from sqlwhisper.errors import LLMUnavailable
from sqlwhisper.models import Health, Message


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

    def health(self) -> Health:
        """Is Ollama reachable, and is the configured model installed?"""
        down = Health(ollama=False, model=False, model_name=self._model)
        try:
            response = self._http.get("/api/tags", timeout=5)
            response.raise_for_status()
            names = {m["name"] for m in response.json()["models"]}
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return down
        present = self._model in names or f"{self._model}:latest" in names
        return Health(ollama=True, model=present, model_name=self._model)


def _error_detail(response: httpx.Response) -> str:
    try:
        detail = response.json()["error"]
    except (ValueError, KeyError, TypeError):
        detail = response.text[:200]
    return f"Ollama error {response.status_code}: {detail}"

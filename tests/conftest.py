import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--bench-model",
        default=None,
        help="Ollama model for `-m bench` (default: OLLAMA_MODEL).",
    )

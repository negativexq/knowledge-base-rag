from app.llm.ollama_client import OllamaClient
from app.llm.ollama_provider import OllamaProvider


def test_ollama_provider_is_ollama_client():
    # No adapter subclass — OllamaClient already implements stream_chat and
    # embed with the exact shapes the provider Protocols require, unchanged
    # since Sprint 0. OllamaProvider is a re-export, not a new type.
    assert OllamaProvider is OllamaClient

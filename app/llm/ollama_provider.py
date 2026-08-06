from app.llm.ollama_client import OllamaClient

# OllamaClient already implements stream_chat(messages, model) and
# embed(text, model, prefix) with exactly the shapes ChatProvider and
# EmbeddingProvider (app/llm/provider.py) require — it has satisfied both
# structurally since Sprint 0, unchanged. A wrapper subclass that just
# repeats those method signatures would add a layer with no behavior, so
# OllamaProvider is a re-export: a distinct, factory-friendly name for the
# same client.
OllamaProvider = OllamaClient

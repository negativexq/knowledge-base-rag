.PHONY: dev test test-ollama lint up down ui langfuse-up langfuse-down

VENV := .venv/bin
VENV_UI := .venv-ui/bin

dev:
	$(VENV)/uvicorn app.server:app --reload --host 0.0.0.0 --port 8000

test:
	$(VENV)/pytest -q -m "not ollama_e2e"

test-ollama:
	$(VENV)/pytest -q -m "ollama_e2e"

lint:
	$(VENV)/ruff check app tests

up:
	docker compose up -d

down:
	docker compose down

# Optional, heavy (6 containers): self-hosted Langfuse on http://localhost:3001.
# The backend exports to it only with LANGFUSE_ENABLED=true in .env.
langfuse-up:
	docker compose -f docker-compose.langfuse.yml up -d

langfuse-down:
	docker compose -f docker-compose.langfuse.yml down

ui:
	PYTHONPATH=. $(VENV_UI)/streamlit run app/ui/streamlit_app.py

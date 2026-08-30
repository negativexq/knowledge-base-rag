.PHONY: dev test test-ollama lint up down ui

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

ui:
	PYTHONPATH=. $(VENV_UI)/streamlit run app/ui/streamlit_app.py

.PHONY: dev test test-adaptive test-ollama lint up down bench-up langfuse-up langfuse-down

VENV := .venv/bin

dev:
	$(VENV)/uvicorn app.server:app --reload --host 0.0.0.0 --port 8000

test:
	$(VENV)/pytest -q -m "not ollama_e2e"

# Fully offline: no models, credentials, Qdrant or parser downloads.
test-adaptive:
	$(VENV)/pytest -q tests/test_research_state.py tests/test_adaptive.py tests/test_adaptive_observability.py tests/test_adaptive_fast_path.py tests/test_research_needs.py tests/test_quantities.py tests/test_quantity_review.py tests/test_quantity_sources.py

test-ollama:
	$(VENV)/pytest -q -m "ollama_e2e"

lint:
	$(VENV)/ruff check app tests scripts
	$(VENV)/mypy app/

up:
	docker compose up -d

down:
	docker compose down

# The backend with benchmark runners, inputs and results bind-mounted from the
# host (docker-compose.bench.yml), e.g.
#   docker exec -w /app kb-rag-backend python scripts/benchmarks/run_mmlongbench_pilot.py \
#     --manifest artifacts/mmlongbench-v2/manifest.json
bench-up:
	docker compose -f docker-compose.yml -f docker-compose.bench.yml up -d backend

# Optional, heavy (6 containers): self-hosted Langfuse on http://localhost:3001.
# The backend exports to it only with LANGFUSE_ENABLED=true in .env.
langfuse-up:
	docker compose -f docker-compose.langfuse.yml up -d

langfuse-down:
	docker compose -f docker-compose.langfuse.yml down

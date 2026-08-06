.PHONY: dev test lint up down

VENV := .venv/bin

test:
	$(VENV)/pytest -q

lint:
	$(VENV)/ruff check app tests

up:
	docker compose up -d

down:
	docker compose down

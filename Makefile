.DEFAULT_GOAL := help
SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
export SNAPSHOT

.PHONY: help setup dev up down logs migrate migrate-down ingest test integration lint format typecheck check smoke clean

help: ## Muestra los comandos disponibles
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: ## Instala dependencias bloqueadas
	uv sync --all-groups --locked

up: ## Inicia PostgreSQL y Redis locales
	docker compose up -d --wait postgres redis

down: ## Detiene los servicios locales
	docker compose down

logs: ## Muestra logs de los servicios locales
	docker compose logs -f postgres redis

migrate: ## Aplica las migraciones pendientes
	@if [[ ! -f .env ]]; then echo "Crea .env desde .env.example antes de migrar."; exit 1; fi
	uv run alembic upgrade head

migrate-down: ## Revierte una migración
	@if [[ ! -f .env ]]; then echo "Crea .env desde .env.example antes de migrar."; exit 1; fi
	uv run alembic downgrade -1

ingest: ## Publica un snapshot de items
	@if [[ -z "$${SNAPSHOT:-}" ]]; then echo "Uso: make ingest SNAPSHOT=/path/to/items.json"; exit 1; fi
	uv run python -m scripts.ingest --input "$${SNAPSHOT}"

dev: up migrate ## Inicia el servidor de desarrollo
	uv run uvicorn app.main:app --reload

test: ## Ejecuta la suite de tests
	uv run pytest

integration: ## Ejecuta tests de integracion contra TEST_DATABASE_URL
	@if [[ -z "$${TEST_DATABASE_URL:-}" ]]; then echo "Define TEST_DATABASE_URL antes de ejecutar la integracion."; exit 1; fi
	TEST_DATABASE_URL="$${TEST_DATABASE_URL}" uv run python scripts/validate_test_database.py
	docker compose up -d --wait postgres redis
	DATABASE_URL="$${TEST_DATABASE_URL}" REDIS_URL=redis://localhost:6379/0 uv run alembic upgrade head
	TEST_DATABASE_URL="$${TEST_DATABASE_URL}" uv run pytest -o addopts="" -m integration

lint: ## Ejecuta lint
	uv run ruff check .

format: ## Formatea el código
	uv run ruff format .

typecheck: ## Comprueba tipos con Pyright
	uv run pyright

check: lint typecheck test ## Ejecuta todos los quality gates
	uv run ruff format --check .

smoke: ## Comprueba salud y preparación del servidor local
	curl -fsS http://127.0.0.1:8000/health
	curl -fsS http://127.0.0.1:8000/health/ready

clean: ## Elimina caches locales de herramientas
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov

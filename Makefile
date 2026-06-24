# ── football-intelligence-lakehouse ──────────────────────────────────────────
# Comandos frecuentes del proyecto.
# Requisitos: uv, docker-compose, .env cargado (ver CLAUDE.md § Gotchas #2)

.PHONY: help up down api dbt-run dbt-test dbt-seed ingest ingest-all lint test train

help:
	@echo "Comandos disponibles:"
	@echo "  make up          Levanta PostgreSQL + MinIO + Airflow"
	@echo "  make down        Para todos los servicios"
	@echo "  make api         Levanta también la FastAPI (profile api)"
	@echo "  make dbt-run     Corre todos los modelos dbt → Neon"
	@echo "  make dbt-test    Corre los tests de calidad dbt"
	@echo "  make dbt-seed    Carga los seeds (team_codes.csv)"
	@echo "  make ingest      Ingesta diaria worldcup26.ir (fecha de ayer)"
	@echo "  make ingest-all  Ingesta desde inicio del torneo (2026-06-11)"
	@echo "  make lint        Ruff check + format"
	@echo "  make test        Pytest (sin conexión a Neon)"
	@echo "  make train       Entrena el modelo ML"

up:
	docker-compose up -d

down:
	docker-compose down

api:
	docker-compose --profile api up -d

dbt-run:
	uv run dbt run --project-dir ./dbt --profiles-dir ./dbt

dbt-test:
	uv run dbt test --project-dir ./dbt --profiles-dir ./dbt

dbt-seed:
	uv run dbt seed --project-dir ./dbt --profiles-dir ./dbt

ingest:
	python -m ingestion.worldcup26_client

ingest-all:
	python -m ingestion.worldcup26_client --all

lint:
	uv run ruff check . && uv run ruff format .

test:
	uv run pytest tests/ -v

train:
	uv run python -m ml.train

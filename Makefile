.DEFAULT_GOAL := help

COMPOSE := docker compose

.PHONY: help up migrate seed pipeline canonicalize quality semantics product pipeline-all test demo down

help:
	@echo "make up | migrate | seed | pipeline | canonicalize | quality | semantics | product | pipeline-all | test | demo | down"

up:
	$(COMPOSE) up -d

migrate:
	$(COMPOSE) up -d db
	$(COMPOSE) run --rm migrate

seed: up
	$(COMPOSE) exec -T api python -m app.cli seed

pipeline: up
	$(COMPOSE) exec -T api python -m app.cli pipeline

canonicalize: up
	$(COMPOSE) exec -T api python -m app.cli canonicalize

quality: up
	$(COMPOSE) exec -T api python -m app.cli quality

semantics: up
	$(COMPOSE) exec -T api python -m app.cli semantics

product: up
	$(COMPOSE) exec -T api python -m app.cli product

pipeline-all: seed pipeline canonicalize quality

test:
	$(COMPOSE) up -d db
	$(COMPOSE) run --rm -e DATABASE_URL=postgresql+psycopg://healthcare:change_me@db:5432/healthcare_factory_test api pytest

demo: up
	$(COMPOSE) exec -T api python -m app.cli seed
	$(COMPOSE) exec -T api python -m app.cli pipeline

down:
	$(COMPOSE) down

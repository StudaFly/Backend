run:
	uvicorn src.main:app --reload --host 0.0.0.0 --port 8080

test:
	pytest --cov=src -v

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

migrate:
	alembic upgrade head

MSG ?= auto
migration:
	alembic revision --autogenerate -m "$(MSG)"

db-setup:
	$(MAKE) migrate && $(MAKE) seed

seed:
	python -m seeds.seed

seed-force:
	python -m seeds.seed --force

seed-dry:
	python -m seeds.seed --dry-run

seed-dest:
	python -m seeds.seed --dest

seed-org:
	python -m seeds.seed --org

seed-roles-demo:
	python -m seeds.roles_demo --reset

demo-check:
	python -m seeds.demo_check

platform-admin:
	python -m src.app.cli create-platform-admin --email $(EMAIL)

revoke-platform-admin:
	python -m src.app.cli revoke-platform-admin --email $(EMAIL)

maintenance:
	python -m src.app.cli maintenance

reminders:
	python -m src.app.cli send-reminders

shell:
	python -c "import asyncio; from src.app.db.session import AsyncSessionLocal; print('Shell ready')"

COMPOSE = docker compose -f docker/docker-compose.yml

services:
	$(COMPOSE) up -d --wait db redis

services-stop:
	$(COMPOSE) stop db redis

dev: services db-setup run

docker-up:
	$(COMPOSE) up --build -d

docker-down:
	$(COMPOSE) down

docker-reset:
	$(COMPOSE) down -v

docker-logs:
	$(COMPOSE) logs -f app

docker-ps:
	$(COMPOSE) ps

.PHONY: run dev services services-stop docker-reset test lint format migrate migration db-setup seed seed-force seed-dry seed-dest seed-org seed-roles-demo demo-check platform-admin revoke-platform-admin maintenance reminders shell docker-up docker-down docker-logs docker-ps

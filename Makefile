run:
	uvicorn src.main:app --reload

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

seed-inst:
	python -m seeds.seed --inst

shell:
	python -c "import asyncio; from src.app.db.session import AsyncSessionLocal; print('Shell ready')"

COMPOSE = docker compose -f docker/docker-compose.yml

docker-up:
	$(COMPOSE) up --build -d

docker-down:
	$(COMPOSE) down -v

docker-logs:
	$(COMPOSE) logs -f app

docker-ps:
	$(COMPOSE) ps

.PHONY: run test lint format migrate migration db-setup seed seed-force seed-dry seed-dest seed-inst shell docker-up docker-down docker-logs docker-ps

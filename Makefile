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

migration:
	@read -p "Migration message: " msg; alembic revision --autogenerate -m "$$msg"

shell:
	python -c "import asyncio; from src.app.db.session import AsyncSessionLocal; print('Shell ready')"

.PHONY: run test lint format migrate migration shell

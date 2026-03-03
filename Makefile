lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

test:
	pytest --cov=src -v

run:
	uvicorn src.main:app --reload

.PHONY: lint format test run

# StudaFly Backend

> Backend API for StudaFly - Prepare your international mobility, serenely.

![CI](https://github.com/StudaFly/Backend/actions/workflows/ci.yml/badge.svg)

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start the server
uvicorn src.main:app --reload
```

## Tests

```bash
# Run tests
pytest

# With coverage
pytest --cov=src --cov-report=html
```

## Linting

```bash
# Check code
ruff check .

# Format code
ruff format .
```

## API Docs

Once the server is running:
- Swagger UI: http://localhost:8080/docs

## Team

- **Code Owner**: @Nathcaa

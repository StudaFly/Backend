# StudaFly Backend

> Backend API for StudaFly - Prepare your international mobility, serenely.

![CI](https://github.com/StudaFly/Backend/actions/workflows/ci.yml/badge.svg)

## Quick Start

### With Docker (recommended)

PostgreSQL and Redis are required (Redis stores refresh tokens and the AI cache).

```bash
cp .env.example .env
make docker-up      # db + redis + API on http://localhost:8080 (migrations and seed run at startup)
make docker-logs
```

### Local API (`make run`)

The API needs PostgreSQL and Redis. Run them in Docker and the API on your machine:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env

make dev          # = make services (PostgreSQL + Redis) + migrations + seed + make run
```

Day to day: `make services` once, then `make run`. If PostgreSQL or Redis is down, the API logs it at
startup, answers **503** (`DATABASE_UNAVAILABLE` / `CACHE_UNAVAILABLE`) instead of a 500, and
`GET /api/v1/health` lists the unreachable service.

`make docker-down` keeps the database; `make docker-reset` deletes it (volumes).

`--host 0.0.0.0` lets the mobile app reach the API from a phone on the same network.

## Reference data (seed)

The backend is the single source of truth: clients hard-code no data.

```bash
make seed        # idempotent: creates what is missing, fills empty fields
make seed-force  # re-applies the seed files over existing rows
```

- `seeds/data/destinations.json` — cities with cost of living and guide (fixed ids).
- `seeds/data/destination_profiles.json` — country profiles (image, summary, facts, key steps),
  migrated from the former web mock; applied to every city of the country and creates the listed
  cities that do not exist yet.
- `seeds/data/institutions.json` — partner schools.

The Docker dev stack runs `alembic upgrade head` and `python -m seeds.seed` at startup.

Shared endpoints for the clients: `GET /api/v1/reference` (mobility types, task categories and
priorities, avatars), `GET /api/v1/stats` (landing page figures), `GET /api/v1/health`,
`GET /api/v1/mobilities/{id}/progress` (dashboard figures).

## Parcours generation

A mobility's tasks are generated when it is created (`POST /api/v1/mobilities`), from
`src/app/data/task_templates.json` with deadlines computed from the departure date.
This works without the Claude API. Set `AI_TASK_GENERATION_ENABLED=true` to try the AI
checklist first (`ANTHROPIC_MODEL`, default `claude-sonnet-5-5`); the templates remain the
fallback whenever the AI call fails.

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

# StudaFly Backend

> API Backend pour StudaFly - Prépare ton départ à l'étranger, sereinement.

![CI](https://github.com/StudaFly/Backend/actions/workflows/ci.yml/badge.svg)

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Installer les dépendances
pip install -r requirements.txt

# Lancer le serveur
uvicorn src.main:app --reload
```

## Tests

```bash
# Lancer les tests
pytest

# Avec couverture
pytest --cov=src --cov-report=html
```

## Linting

```bash
# Vérifier le code
ruff check .

# Formater le code
ruff format .
```

## API Docs

Une fois le serveur lancé :
- Swagger UI : http://localhost:8000/docs
- ReDoc : http://localhost:8000/redoc

## Équipe

- **Code Owner** : @Nathcaa

# Build stage
FROM python:3.11-slim AS builder

WORKDIR /app

RUN pip install --upgrade pip
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Runtime stage
FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /install /usr/local
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini .

ENV APP_ENV=production

EXPOSE 8080

CMD ["uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "4"]

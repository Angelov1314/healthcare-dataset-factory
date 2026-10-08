FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir ".[dev]"
COPY alembic.ini ./
COPY alembic ./alembic
COPY tests ./tests
COPY README.md Makefile ./

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

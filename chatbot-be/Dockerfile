FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

RUN apt-get update && apt-get install -y \
    gcc libpq-dev netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip uv

# Copy dependency files first (cache layer)
COPY pyproject.toml .
COPY alembic.ini .

RUN uv pip install . --system --no-cache-dir

# Copy source code
COPY src src
COPY scripts scripts

RUN chmod +x scripts/db_init.sh

EXPOSE 8000

ENTRYPOINT ["./scripts/db_init.sh"]
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]

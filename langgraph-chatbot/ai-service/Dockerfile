FROM python:3.11-slim

WORKDIR /app

ENV ANONYMIZED_TELEMETRY=False

RUN apt-get update && apt-get install -y --no-install-recommends     gcc libsqlite3-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy training files first — isolated layer so changes to src/ don't bust cache
COPY data/ ./data/
COPY scripts/ ./scripts/
RUN chmod +x ./scripts/*.sh

# Seed DB + train Vanna + pre-download ChromaDB ONNX model (~79MB) at build time.
# This layer is cached: only re-runs when data/ or scripts/ change.
RUN ./scripts/build_vanna_train.sh

# Copy remaining source after training — safe to change without retraining
COPY . .

EXPOSE 8001

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"]
 
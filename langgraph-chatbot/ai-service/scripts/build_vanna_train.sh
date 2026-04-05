#!/bin/sh
# Build-time Vanna training — runs during `docker build`, NOT at container start.
# vn.train() only writes embeddings to ChromaDB via local ONNX model.
# No live connections to OpenAI are made here.
# Placeholder values satisfy config validation without real secrets.

export OPENAI_API_KEY=sk-build-placeholder
export DB_PATH=data/sample.db
export CHROMA_PATH=data/chroma
export VANNA_MODEL=gpt-4o-mini
export PORT=8001
export LOG_LEVEL=INFO

python data/train.py

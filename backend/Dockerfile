# FarmIntel backend — FastAPI + scikit-learn/xgboost + ChromaDB + SQLite store.
# Works on any container host (Hugging Face Spaces uses 7860 by default; set
# BACKEND_PORT and CORS_ORIGINS in the host's environment/secrets).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    BACKEND_PORT=7860

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 7860

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${BACKEND_PORT}"]

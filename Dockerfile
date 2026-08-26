FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# sentence-transformers (app/reranker/cross_encoder.py) pulls torch as a
# transitive dependency; on manylinux pip defaults to the CUDA-enabled
# build (~2GB of nvidia_* wheels) even though this container has no GPU
# (Ollama runs native on the host, see docs/sprint-11-plan.md — Metal GPU
# passthrough isn't available to Docker Desktop on macOS). Installing the
# CPU-only wheel first makes the requirements.txt install below see torch
# already satisfied and skip the CUDA variant entirely — same fix
# production-rag-platform needed for the same library.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY prompts/ ./prompts/
# Evaluation artifacts are read-only server-side data for the operations
# console. Keep them in the image so /ui/evaluations reflects the measured
# Sprint 25 result instead of silently reporting an unavailable artifact.
COPY artifacts/ ./artifacts/

EXPOSE 8000

CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8000"]

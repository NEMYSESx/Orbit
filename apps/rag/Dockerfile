FROM python:3.10-slim as builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

RUN python -c "from huggingface_hub import snapshot_download; snapshot_download('intfloat/multilingual-e5-large-instruct', local_dir='/app/model')"

RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('/app/model')"

FROM python:3.10-slim

WORKDIR /app

COPY --from=builder /usr/local /usr/local
COPY --from=builder /app/model /app/model

COPY . .

ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["python", "api/main.py"]

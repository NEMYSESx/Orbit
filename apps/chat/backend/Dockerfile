FROM python:3.12-slim AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=100

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

RUN find /opt/venv -name "*.pyc" -delete && \
    find /opt/venv -name "__pycache__" -type d -exec rm -rf {} + && \
    find /opt/venv -name "*.pyo" -delete

FROM python:3.12-slim AS production

WORKDIR /rag

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/rag \
    PATH="/opt/venv/bin:$PATH"

COPY --from=builder /opt/venv /opt/venv

RUN groupadd -r appgroup && useradd -r -g appgroup -d /rag appuser

RUN mkdir -p /rag/data && chown -R appuser:appgroup /rag/data

COPY --chown=appuser:appgroup . .

RUN rm -rf tests/ *.md .git* .pytest_cache/ __pycache__/ \
    && find . -name "*.pyc" -delete \
    && find . -name "__pycache__" -type d -exec rm -rf {} +

RUN chown -R appuser:appgroup /rag/data

USER appuser

EXPOSE 8080

ENTRYPOINT ["python"]
CMD ["main.py"]
# Two-stage build: dependencies resolved with uv, runtime image without build tools.
# The embedding model is baked in so the container starts offline (air-gapped mode).

FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --extra postgres
COPY . .
RUN uv sync --frozen --no-dev --extra postgres
# Pre-download the local embedding model into the image.
ENV FASTEMBED_CACHE_PATH=/opt/fastembed
RUN /opt/venv/bin/python -c "from reviewer.retrieval import _embedder; _embedder()"

FROM python:3.12-slim
RUN useradd --create-home --uid 10001 ccr
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /opt/fastembed /opt/fastembed
COPY --from=builder /app/src /app/src
COPY --from=builder /app/customers /app/customers
COPY --from=builder /app/pyproject.toml /app/pyproject.toml
ENV PATH="/opt/venv/bin:$PATH" \
    FASTEMBED_CACHE_PATH=/opt/fastembed \
    PYTHONUNBUFFERED=1 \
    CCR_CUSTOMER=harlow-pryce \
    DATABASE_URL=sqlite:////data/reviewer.db \
    PORT=8000
RUN mkdir -p /data && chown ccr:ccr /data
USER ccr
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)"
CMD ["sh", "-c", "uvicorn reviewer.app.main:app --host 0.0.0.0 --port ${PORT}"]

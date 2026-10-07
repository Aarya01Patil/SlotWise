FROM ghcr.io/astral-sh/uv:0.11.6 AS uv
FROM python:3.13-slim
COPY --from=uv /uv /uvx /bin/
ENV PYTHONUNBUFFERED=1 UV_LINK_MODE=copy UV_CACHE_DIR=/tmp/uv-cache
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY slotwise ./slotwise
COPY examples ./examples
RUN uv sync --frozen --no-dev && useradd --uid 10001 --create-home slotwise && chown -R slotwise:slotwise /app
USER slotwise
EXPOSE 10000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','10000')+'/healthz', timeout=4)"
CMD ["sh", "-c", "exec uv run --no-sync slotwise serve --host 0.0.0.0 --port \"${PORT:-10000}\""]

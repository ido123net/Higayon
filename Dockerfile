FROM ghcr.io/astral-sh/uv:0.13.7 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /uvx /bin/
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY manage.py ./
COPY higayon/ higayon/
COPY puzzles/ puzzles/
COPY static/ static/
COPY templates/ templates/
RUN DEBUG=true uv run --no-sync python manage.py collectstatic --noinput     && useradd --create-home app && chown -R app:app /app
USER app
EXPOSE 8000
CMD ["uvicorn", "higayon.asgi:application", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "3", "--no-access-log"]

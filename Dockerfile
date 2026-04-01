FROM python:3.12-slim AS base

WORKDIR /bridge

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

RUN useradd --uid 1000 --no-create-home appuser \
    && chown -R appuser:appuser /bridge

USER appuser

ENTRYPOINT ["python", "server.py"]


FROM base AS dev

USER root
RUN pip install --no-cache-dir pytest pytest-asyncio ruff mypy
RUN chown -R appuser:appuser /bridge
USER appuser

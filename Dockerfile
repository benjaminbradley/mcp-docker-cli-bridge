FROM python:3.12-slim AS base

# Supply-chain cooldown window (see doc/SECURITY.md §6).
ARG PIP_UPLOADED_PRIOR_TO=P3D
ENV PIP_UPLOADED_PRIOR_TO=${PIP_UPLOADED_PRIOR_TO}

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
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt
RUN chown -R appuser:appuser /bridge
USER appuser

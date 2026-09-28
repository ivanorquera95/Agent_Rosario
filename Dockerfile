# Dos etapas: la primera compila el frontend, la segunda corre la API y sirve
# los archivos ya compilados. Asi la imagen final no lleva Node ni node_modules.
FROM node:20-slim AS frontend

WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build


FROM python:3.11-slim

# uv instala las dependencias mas rapido que pip y respeta el uv.lock.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Las dependencias primero: si no cambian, Docker reusa esta capa.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY agent_rosario.py rosario.md ./
COPY api/ ./api/
COPY scripts/ ./scripts/
COPY --from=frontend /web/dist ./web/dist

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Railway asigna el puerto en la variable PORT.
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
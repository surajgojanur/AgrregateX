# AgrregateX API + built UI on one port. Build context: hackathon/
FROM node:22-alpine AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.14-slim
WORKDIR /srv
COPY app/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app/axapi ./axapi
# B-4 metric registry. Compose bind-mounts this directory read-only so the file can be edited live.
COPY app/config ./config
COPY --from=ui /ui/dist ./ui
ENV AX_STATIC_DIR=/srv/ui PYTHONUNBUFFERED=1
RUN useradd --system --uid 10001 ax
USER ax
EXPOSE 8000
CMD ["uvicorn", "axapi.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM node:22-alpine AS web
WORKDIR /src/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY backend ./backend
COPY --from=web /src/web/dist ./web/dist
EXPOSE 8000
CMD ["sh", "-c", "python -m backend.server --db /data/agal.sqlite --host 0.0.0.0 --port ${PORT:-8000}"]

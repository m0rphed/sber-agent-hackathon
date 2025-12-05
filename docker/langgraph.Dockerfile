# ══════════════════════════════════════════════════════════════
# LangGraph Server Dockerfile
# Основной API сервер с графами агента
# ══════════════════════════════════════════════════════════════
FROM python:3.12-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Установка uv
RUN pip install uv

# Копирование файлов зависимостей
COPY pyproject.toml uv.lock ./

# Синхронизация зависимостей (без dev)
RUN uv sync --frozen --no-dev

# Копирование исходного кода
COPY app/ ./app/
COPY langgraph.json ./

# Порт LangGraph Server
EXPOSE 2024

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:2024/health || exit 1

# Запуск LangGraph Server
CMD ["uv", "run", "langgraph", "up", "--host", "0.0.0.0", "--port", "2024"]

# ══════════════════════════════════════════════════════════════
# MAX/VK Teams Bot Dockerfile
# Бот для MAX/VK Teams (maxapi)
# ══════════════════════════════════════════════════════════════
FROM python:3.12-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Установка uv
RUN pip install uv

# Копирование файлов зависимостей
COPY pyproject.toml uv.lock ./

# Синхронизация зависимостей
RUN uv sync --frozen --no-dev

# Копирование кода бота
COPY bots/ ./bots/
COPY app/__init__.py ./app/
COPY app/config.py ./app/

# Запуск MAX бота
CMD ["uv", "run", "python", "-m", "bots.max.bot_main"]

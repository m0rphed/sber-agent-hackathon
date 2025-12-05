# ══════════════════════════════════════════════════════════════
# Streamlit UI Dockerfile
# Веб-интерфейс чата
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

# Копирование UI кода
COPY app/ui/ ./app/ui/
COPY app/__init__.py ./app/
COPY app/config.py ./app/
COPY .streamlit/ ./.streamlit/

# Порт Streamlit
EXPOSE 8501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Запуск Streamlit
CMD ["uv", "run", "streamlit", "run", "app/ui/streamlit_app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]

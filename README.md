# 🏙️ Цифровой Ассистент Санкт-Петербурга

**ПРЕЗЕНТАЦИЯ** в корневом каталоге 👉 [Городской-помощник-Сбер.pptx](Городской-помощник-Сбер.pptx)

> **Sber Agent Hackathon 2025** — AI-ассистент для жителей и гостей Санкт-Петербурга

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-green.svg)](https://langchain-ai.github.io/langgraph/)
[![GigaChat](https://img.shields.io/badge/LLM-GigaChat--2--Max-orange.svg)](https://developers.sber.ru/portal/products/gigachat)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 📋 Оглавление

- [Архитектура](#-архитектура)
- [Быстрый старт](#-быстрый-старт)
- [UV Workspaces (Монорепо)](#-uv-workspaces-монорепо)
- [Переменные окружения](#-переменные-окружения)
- [Docker](#-docker)
- [Запуск компонентов](#-запуск-компонентов)
- [Разработка](#-разработка)
- [Структура проекта](#-структура-проекта)

---

## 🏗️ Архитектура

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Telegram Bot  │     │   MAX/VK Bot    │     │   Streamlit UI  │
│   (aiogram 3)   │     │   (maxapi)      │     │   (Web Chat)    │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 ▼
                    ┌────────────────────────┐
                    │   LangGraph Server     │
                    │   (API Gateway)        │
                    │   Port: 2024           │
                    └───────────┬────────────┘
                                │
         ┌──────────────────────┼──────────────────────┐
         ▼                      ▼                      ▼
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│   Supervisor    │   │     Hybrid      │   │      RAG        │
│     Graph       │   │     Graph       │   │     Graph       │
└────────┬────────┘   └────────┬────────┘   └────────┬────────┘
         │                     │                     │
         └─────────────────────┼─────────────────────┘
                               ▼
              ┌────────────────────────────┐
              │        Tool Layer          │
              │  • MFC Search              │
              │  • District Info           │
              │  • Events/Afisha           │
              │  • Sport Events            │
              └────────────────────────────┘
                               │
         ┌─────────────────────┼─────────────────────┐
         ▼                     ▼                     ▼
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│   GigaChat-2    │   │    ChromaDB     │   │  External APIs  │
│   (LLM)         │   │    (RAG Store)  │   │  (City Data)    │
└─────────────────┘   └─────────────────┘   └─────────────────┘
```

### Компоненты

| Компонент | Описание | Порт | Технологии |
|-----------|----------|------|------------|
| **LangGraph Server** | Основной API, оркестрация графов | 2024 | LangGraph, FastAPI |
| **Streamlit UI** | Веб-интерфейс чата | 8501 | Streamlit |
| **Telegram Bot** | Бот для Telegram | — | aiogram 3.22+ |
| **MAX Bot** | Бот для MAX/VK Teams | — | maxapi 0.9.9 |

---

## 🚀 Быстрый старт

### Требования

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) — современный менеджер пакетов

### Установка uv

```powershell
# Windows (PowerShell)
irm https://astral.sh/uv/install.ps1 | iex

# Linux/macOS
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Клонирование и запуск

```powershell
# Клонировать репозиторий
git clone https://github.com/m0rphed/sber-agent-hackathon.git
cd sber-agent-hackathon

# Создать .env файл (см. раздел "Переменные окружения")
cp .env.example .env

# Установить зависимости и запустить LangGraph Server
uv sync
uv run langgraph dev
```

---

## 📦 UV Workspaces (Монорепо)

> **Планируемая структура** — переход на uv workspaces для изоляции компонентов

```
sber-agent-hackathon/
├── pyproject.toml              # Корневой workspace
├── packages/
│   ├── langgraph-app/          # LangGraph Server + Agent
│   │   ├── pyproject.toml
│   │   └── src/
│   │       └── langgraph_app/
│   │           ├── agent/
│   │           ├── graphs/
│   │           └── tools/
│   │
│   ├── streamlit-ui/           # Web UI
│   │   ├── pyproject.toml
│   │   └── src/
│   │       └── streamlit_ui/
│   │
│   ├── bot-telegram/           # Telegram Bot
│   │   ├── pyproject.toml
│   │   └── src/
│   │       └── bot_telegram/
│   │
│   └── bot-max/                # MAX/VK Teams Bot
│       ├── pyproject.toml
│       └── src/
│           └── bot_max/
│
├── libs/
│   └── shared/                 # Общие утилиты
│       ├── pyproject.toml
│       └── src/
│           └── shared/
│               ├── config.py
│               └── schemas.py
│
└── docker/
    ├── langgraph-app.Dockerfile
    ├── streamlit-ui.Dockerfile
    ├── bot-telegram.Dockerfile
    └── bot-max.Dockerfile
```

### Корневой pyproject.toml (workspace)

```toml
[project]
name = "sber-agent-hackathon"
version = "0.1.0"
requires-python = ">=3.12"

[tool.uv.workspace]
members = [
    "packages/*",
    "libs/*"
]

[tool.uv.sources]
shared = { workspace = true }
langgraph-app = { workspace = true }
```

---

## 🔐 Переменные окружения

Создайте файл `.env` на основе `.env.example`:

```bash
cp .env.example .env
```

### Основные переменные

```env
# ══════════════════════════════════════════════════════════════
# GigaChat API (обязательно)
# ══════════════════════════════════════════════════════════════
GIGACHAT_CREDENTIALS=<your-credentials>
GIGACHAT_SCOPE=GIGACHAT_API_PERS
GIGACHAT_MODEL=GigaChat-2
GIGACHAT_VERIFY_SSL_CERTS=false
EMBEDDINGS_MODEL=EmbeddingsGigaR

# ══════════════════════════════════════════════════════════════
# RAG Configuration
# ══════════════════════════════════════════════════════════════
CHUNK_SIZE=800
CHUNK_OVERLAP=200
TOP_K=5
RAG_USE_QUERY_REWRITING=true
RAG_USE_DOCUMENT_GRADING=true

# ══════════════════════════════════════════════════════════════
# City API ("Я Здесь Живу")
# ══════════════════════════════════════════════════════════════
API_GEO=https://yazzh-geo.gate.petersburg.ru
API_SITE=https://yazzh.gate.petersburg.ru
REGION_ID=78

# ══════════════════════════════════════════════════════════════
# Yandex Geocoder API
# ══════════════════════════════════════════════════════════════
YANDEX_API_KEY=<your-yandex-api-key>

# ══════════════════════════════════════════════════════════════
# LangSmith Observability (опционально)
# ══════════════════════════════════════════════════════════════
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=<your-langsmith-key>
LANGSMITH_PROJECT=city-assistant

# ══════════════════════════════════════════════════════════════
# LangGraph Server
# ══════════════════════════════════════════════════════════════
LANGGRAPH_URL=http://localhost:2024

# ══════════════════════════════════════════════════════════════
# Боты (токены)
# ══════════════════════════════════════════════════════════════
TOKEN_TG=<telegram-bot-token>
TOKEN_MAX=<max-bot-token>

# ══════════════════════════════════════════════════════════════
# Режим разработки
# ══════════════════════════════════════════════════════════════
LOG_LEVEL=DEBUG
LOG_FORMAT=console
IS_DEBUG=true
```

### Описание переменных

| Переменная | Обязательная | Описание |
|------------|--------------|----------|
| `GIGACHAT_CREDENTIALS` | ✅ | Credentials для GigaChat API |
| `GIGACHAT_SCOPE` | ❌ | Scope API (PERS/CORP/B2B) |
| `GIGACHAT_MODEL` | ❌ | Модель: GigaChat-2, GigaChat-2-Max |
| `YANDEX_API_KEY` | ⚠️ | API ключ Яндекс.Геокодера |
| `TOKEN_TG` | ⚠️ | Токен Telegram бота |
| `TOKEN_MAX` | ⚠️ | Токен MAX бота |
| `LANGSMITH_API_KEY` | ❌ | API ключ LangSmith для трейсинга |

---

## 🐳 Docker

### Dockerfile для каждого компонента

#### 1. LangGraph Server (`docker/langgraph-app.Dockerfile`)

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Установка uv
RUN pip install uv

# Копирование зависимостей
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Копирование кода
COPY app/ ./app/
COPY langgraph.json ./

# Порт LangGraph Server
EXPOSE 2024

# Запуск
CMD ["uv", "run", "langgraph", "up", "--host", "0.0.0.0", "--port", "2024"]
```

#### 2. Streamlit UI (`docker/streamlit-ui.Dockerfile`)

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app/ui/ ./app/ui/

EXPOSE 8501

CMD ["uv", "run", "streamlit", "run", "app/ui/streamlit_app.py", \
     "--server.port=8501", "--server.address=0.0.0.0"]
```

#### 3. Telegram Bot (`docker/bot-telegram.Dockerfile`)

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app/bots/telegram_bot.py ./app/bots/

CMD ["uv", "run", "python", "-m", "app.bots.telegram_bot"]
```

#### 4. MAX Bot (`docker/bot-max.Dockerfile`)

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app/bots/max_bot.py ./app/bots/

CMD ["uv", "run", "python", "-m", "app.bots.max_bot"]
```

### Docker Compose (`docker-compose.yml`)

```yaml
version: "3.9"

services:
  # ═══════════════════════════════════════════════════════════
  # LangGraph Server (основной API)
  # ═══════════════════════════════════════════════════════════
  langgraph-app:
    build:
      context: .
      dockerfile: docker/langgraph-app.Dockerfile
    container_name: spb-langgraph
    ports:
      - "2024:2024"
    environment:
      - GIGACHAT_CREDENTIALS=${GIGACHAT_CREDENTIALS}
      - GIGACHAT_SCOPE=${GIGACHAT_SCOPE:-GIGACHAT_API_PERS}
      - GIGACHAT_MODEL=${GIGACHAT_MODEL:-GigaChat-2-Max}
      - CHROMA_PERSIST_DIR=/data/chroma
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
    volumes:
      - chroma-data:/data/chroma
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:2024/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped

  # ═══════════════════════════════════════════════════════════
  # Streamlit Web UI
  # ═══════════════════════════════════════════════════════════
  streamlit-ui:
    build:
      context: .
      dockerfile: docker/streamlit-ui.Dockerfile
    container_name: spb-streamlit
    ports:
      - "8501:8501"
    environment:
      - LANGGRAPH_API_URL=http://langgraph-app:2024
    depends_on:
      langgraph-app:
        condition: service_healthy
    restart: unless-stopped

  # ═══════════════════════════════════════════════════════════
  # Telegram Bot
  # ═══════════════════════════════════════════════════════════
  bot-telegram:
    build:
      context: .
      dockerfile: docker/bot-telegram.Dockerfile
    container_name: spb-telegram-bot
    environment:
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - LANGGRAPH_API_URL=http://langgraph-app:2024
    depends_on:
      langgraph-app:
        condition: service_healthy
    restart: unless-stopped

  # ═══════════════════════════════════════════════════════════
  # MAX / VK Teams Bot
  # ═══════════════════════════════════════════════════════════
  bot-max:
    build:
      context: .
      dockerfile: docker/bot-max.Dockerfile
    container_name: spb-max-bot
    environment:
      - MAX_BOT_TOKEN=${MAX_BOT_TOKEN}
      - LANGGRAPH_API_URL=http://langgraph-app:2024
    depends_on:
      langgraph-app:
        condition: service_healthy
    restart: unless-stopped

volumes:
  chroma-data:
    driver: local
```

### Команды Docker

```powershell
# Сборка всех образов
docker compose build

# Запуск всех сервисов
docker compose up -d

# Запуск только LangGraph + Streamlit
docker compose up -d langgraph-app streamlit-ui

# Просмотр логов
docker compose logs -f langgraph-app

# Остановка
docker compose down
```

---

## 🎮 Запуск компонентов

### С помощью UV (разработка)

```powershell
# ═══════════════════════════════════════════════════════════
# LangGraph Server (dev mode с hot-reload)
# ═══════════════════════════════════════════════════════════
uv run langgraph dev

# LangGraph Server (production mode)
uv run langgraph up --host 0.0.0.0 --port 2024

# ═══════════════════════════════════════════════════════════
# Streamlit UI
# ═══════════════════════════════════════════════════════════
uv run streamlit run app/ui/streamlit_app.py --server.port 8501

# ═══════════════════════════════════════════════════════════
# Telegram Bot
# ═══════════════════════════════════════════════════════════
uv run python -m bots.tg.bot_main

# ═══════════════════════════════════════════════════════════
# MAX Bot
# ═══════════════════════════════════════════════════════════
uv run python -m bots.max.bot_main

# ═══════════════════════════════════════════════════════════
# Все тесты
# ═══════════════════════════════════════════════════════════
uv run pytest

# Тесты с покрытием
uv run pytest --cov=app --cov-report=html
```

### Параллельный запуск (dev)

```powershell
# Терминал 1: LangGraph Server
uv run langgraph dev

# Терминал 2: Streamlit UI
uv run streamlit run app/ui/streamlit_app.py

# Терминал 3: Telegram Bot (опционально)
uv run python -m bots.tg.bot_main

# Терминал 4: MAX Bot (опционально)
uv run python -m bots.max.bot_main
```

---

## 🛠️ Разработка

### Линтинг и форматирование

```powershell
# Форматирование (ruff)
uv run ruff format .

# Линтинг
uv run ruff check .

# Линтинг с автофиксом
uv run ruff check . --fix

# Type checking (mypy)
uv run mypy app/
```

### LangGraph Studio

LangGraph Studio — визуальный отладчик графов:

```powershell
# Запуск в dev режиме (открывает Studio автоматически)
uv run langgraph dev

# Studio доступна по адресу:
# http://localhost:2024/studio
```

### Добавление зависимостей

```powershell
# Добавить runtime зависимость
uv add <package-name>

# Добавить dev зависимость
uv add --dev <package-name>

# Синхронизация после изменений
uv sync
```

---

## 📄 Лицензия

MIT License — см. [LICENSE](LICENSE)

---

## 👥 Команда

**Sber Agent Hackathon 2025**

---

<div align="center">
  <sub>Built with ❤️ for Saint Petersburg</sub>
</div>

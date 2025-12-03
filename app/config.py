"""
Конфигурация приложения.

Централизованное место для параметров:
- Agent (timeouts, retries, temperatures, ...)
- LLM (model names, parameters)
- API (endpoints, credentials)

Для RAG конфигурации используйте:
    from app.rag.config import get_rag_config

Использование:
    from app.config import get_agent_config

    agent_cfg = get_agent_config()
    print(agent_cfg.llm.model)  # GigaChat-2-Max
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

# =============================================================================
# Lazy .env loading
# =============================================================================
# НЕ вызываем load_dotenv() на уровне модуля!
# - langgraph dev/up автоматически загружает .env через langgraph.json
# - Вызов os.getcwd() в load_dotenv() блокирует ASGI event loop
#
# Для standalone запуска (без langgraph) вызовите ensure_dotenv() явно.

_dotenv_loaded = False


def ensure_dotenv() -> None:
    """
    Загружает .env файл, если он ещё не загружен.

    Безопасно вызывать многократно.
    Для langgraph dev/up этот вызов не нужен (env уже загружен).
    """
    global _dotenv_loaded
    if _dotenv_loaded:
        return

    # Проверяем, не загружены ли уже переменные (langgraph context)
    if os.getenv('GIGACHAT_CREDENTIALS'):
        _dotenv_loaded = True
        return

    # Fallback: загружаем вручную для standalone запуска
    from dotenv import load_dotenv

    load_dotenv()
    _dotenv_loaded = True


# =============================================================================
# Базовые переменные окружения (legacy compatibility)
# =============================================================================


def _get_data_dir() -> Path:
    """Lazy getter для DATA_DIR."""
    return Path(os.getenv('DATA_DIR', 'data'))


# базовая директория для данных (lazy property)
DATA_DIR = _get_data_dir()

# GigaChat
GIGACHAT_CREDENTIALS = os.getenv('GIGACHAT_CREDENTIALS', '')
GIGACHAT_SCOPE = os.getenv('GIGACHAT_SCOPE', '')
GIGACHAT_VERIFY_SSL_CERTS = os.getenv('GIGACHAT_VERIFY_SSL_CERTS', 'false').lower() == 'true'

# Настройки модели (legacy, используйте RAGConfig из app.rag.config)
CHUNK_SIZE = os.getenv('CHUNK_SIZE', '800')
CHUNK_OVERLAP = os.getenv('CHUNK_OVERLAP', '200')
TOP_K = os.getenv('TOP_K', '5')

# API "Я Здесь Живу"
API_GEO = os.getenv('API_GEO', 'https://yazzh-geo.gate.petersburg.ru')
API_SITE = os.getenv('API_SITE', 'https://yazzh.gate.petersburg.ru')

# регион по умолчанию (78 = Санкт-Петербург)
REGION_ID = os.getenv('REGION_ID', '78')

# путь к базе данных для памяти агента
MEMORY_DB_PATH = os.getenv('MEMORY_DB_PATH', 'data/memory.db')

SYSTEM_PROMPT_PATH = os.getenv('SYSTEM_PROMPT_PATH', 'prompts/city_agent_prompt.txt')


# =============================================================================
# Agent Dataclass Configs
# =============================================================================


@dataclass(frozen=True)
class TimeoutConfig:
    """Конфигурация таймаутов."""

    llm_seconds: int = 30
    """Таймаут LLM вызова."""

    api_seconds: int = 10
    """Таймаут внешнего API."""

    embeddings_seconds: int = 60
    """Таймаут эмбеддингов."""


@dataclass(frozen=True)
class RetryConfig:
    """Конфигурация retry политики."""

    max_attempts: int = 3
    """Максимальное количество попыток."""

    initial_interval: float = 1.0
    """Начальный интервал между попытками (секунды)."""

    multiplier: float = 2.0
    """Множитель экспоненциального backoff."""

    max_interval: float = 10.0
    """Максимальный интервал между попытками."""

    jitter: bool = True
    """Добавлять случайный jitter."""


@dataclass(frozen=True)
class LLMConfig:
    """Конфигурация LLM параметров."""

    model: str = 'GigaChat-2-Max'
    """Название модели."""

    temperature_classification: float = 0.0
    """Temperature для классификации (детерминированно)."""

    temperature_tools: float = 0.3
    """Temperature для работы с инструментами."""

    temperature_conversation: float = 0.7
    """Temperature для разговора."""

    max_tokens_classification: int = 256
    """Max tokens для классификации."""

    max_tokens_default: int = 1024
    """Max tokens по умолчанию."""

    max_tokens_conversation: int = 512
    """Max tokens для разговора."""


@dataclass(frozen=True)
class MemoryConfig:
    """Конфигурация памяти агента."""

    max_sessions: int = 100
    """Максимальное количество сессий."""

    max_messages_per_session: int = 50
    """Максимум сообщений на сессию."""

    context_window_size: int = 6
    """Количество последних сообщений в контексте."""

    recursion_limit: int = 5
    """Лимит рекурсии ReAct агента."""


@dataclass(frozen=True)
class AgentConfig:
    """
    Полная конфигурация агента.

    Использование:
        config = AgentConfig()  # дефолтные значения
        config = AgentConfig(timeout=TimeoutConfig(llm_seconds=60))
    """

    timeout: TimeoutConfig = field(default_factory=TimeoutConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)


# =============================================================================
# Global Config (Singleton)
# =============================================================================

_agent_config: AgentConfig | None = None


def get_agent_config() -> AgentConfig:
    """
    Возвращает глобальный AgentConfig.

    Читает значения из переменных окружения при первом вызове.
    """
    global _agent_config

    if _agent_config is None:
        # Читаем из env, если заданы
        llm_timeout = int(os.getenv('AGENT_LLM_TIMEOUT', '30'))
        api_timeout = int(os.getenv('AGENT_API_TIMEOUT', '10'))
        max_attempts = int(os.getenv('AGENT_RETRY_MAX_ATTEMPTS', '3'))
        context_window = int(os.getenv('AGENT_CONTEXT_WINDOW', '6'))
        model = os.getenv('AGENT_LLM_MODEL', 'GigaChat-2-Max')

        _agent_config = AgentConfig(
            timeout=TimeoutConfig(
                llm_seconds=llm_timeout,
                api_seconds=api_timeout,
            ),
            retry=RetryConfig(
                max_attempts=max_attempts,
            ),
            llm=LLMConfig(
                model=model,
            ),
            memory=MemoryConfig(
                context_window_size=context_window,
            ),
        )

    return _agent_config


def set_agent_config(config: AgentConfig) -> None:
    """Установить кастомный AgentConfig (для тестов и DI)."""
    global _agent_config
    _agent_config = config


def reset_agent_config() -> None:
    """Сбросить конфиг (для тестов)."""
    global _agent_config
    _agent_config = None


# =============================================================================
# Вспомогательные функции для LLM параметров
# =============================================================================


@lru_cache(maxsize=1)
def get_llm_kwargs_classification() -> dict:
    """Параметры LLM для классификации."""
    config = get_agent_config().llm
    return {
        'model': config.model,
        'temperature': config.temperature_classification,
        'max_tokens': config.max_tokens_classification,
    }


@lru_cache(maxsize=1)
def get_llm_kwargs_tools() -> dict:
    """Параметры LLM для работы с инструментами."""
    config = get_agent_config().llm
    return {
        'model': config.model,
        'temperature': config.temperature_tools,
        'max_tokens': config.max_tokens_default,
    }


@lru_cache(maxsize=1)
def get_llm_kwargs_conversation() -> dict:
    """Параметры LLM для разговора."""
    config = get_agent_config().llm
    return {
        'model': config.model,
        'temperature': config.temperature_conversation,
        'max_tokens': config.max_tokens_conversation,
    }

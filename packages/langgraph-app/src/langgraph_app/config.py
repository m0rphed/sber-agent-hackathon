"""
Конфигурация приложения.

Централизованное место для параметров:
- Agent (timeouts, retries, temperatures, ...)
- LLM (model names, parameters)
- API (endpoints, credentials)

Для RAG конфигурации используйте:
    from langgraph_app.rag.config import get_rag_config

Использование:
    from langgraph_app.config import get_agent_config

    agent_cfg = get_agent_config()
    print(agent_cfg.llm.model)  # GigaChat-2-Max
"""

from dataclasses import dataclass, field
from functools import lru_cache
import os
from pathlib import Path
import sys

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

# ВАЖНО: загружаем .env ДО чтения переменных окружения!
ensure_dotenv()


def _get_data_dir() -> Path:
    """
    Lazy getter для DATA_DIR
    """
    return Path(os.getenv('DATA_DIR', 'data'))


# базовая директория для данных (lazy property)
DATA_DIR = _get_data_dir()


def get_gigachat_credentials() -> str:
    """Lazy getter для GIGACHAT_CREDENTIALS."""
    ensure_dotenv()
    return os.getenv('GIGACHAT_CREDENTIALS', '')


def get_gigachat_scope() -> str:
    """Lazy getter для GIGACHAT_SCOPE."""
    ensure_dotenv()
    return os.getenv('GIGACHAT_SCOPE', '')


def get_gigachat_verify_ssl() -> bool:
    """Lazy getter для GIGACHAT_VERIFY_SSL_CERTS."""
    ensure_dotenv()
    return os.getenv('GIGACHAT_VERIFY_SSL_CERTS', 'false').lower() == 'true'


# GigaChat (legacy - используйте get_gigachat_* функции)
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

# Yandex Geocoder API (для геокодирования метро и адресов)
YANDEX_API_KEY = os.getenv('YANDEX_API_KEY', '')

# регион по умолчанию (78 = Санкт-Петербург)
REGION_ID = os.getenv('REGION_ID', '78')

# =============================================================================
# Checkpointer Configuration
# =============================================================================
# PostgreSQL URL для checkpointer (production)
# Если указан — используется PostgreSQL, иначе — SQLite fallback
POSTGRES_CHECKPOINTER_URL = os.getenv('POSTGRES_CHECKPOINTER_URL', '')

# путь к базе данных для памяти агента (SQLite fallback)
MEMORY_DB_PATH = os.getenv('MEMORY_DB_PATH', 'data/memory.db')

# Базовый путь пакета (для относительных путей к промптам)
_PACKAGE_DIR = Path(__file__).parent
# Корень проекта (UV workspace root) - packages/langgraph-app/src/langgraph_app -> 4 уровня вверх
_PROJECT_ROOT = _PACKAGE_DIR.parent.parent.parent.parent

# Добавляем корень проекта в sys.path для импорта prompts
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

SYSTEM_PROMPT_PATH = os.getenv(
    'SYSTEM_PROMPT_PATH',
    str(_PROJECT_ROOT / 'prompts' / 'city_agent_prompt.txt')
)


# =============================================================================
# Agent Dataclass Configs
# =============================================================================


@dataclass(frozen=True)
class TimeoutConfig:
    """
    Конфигурация таймаутов
    """

    llm_seconds: int = 30
    """
    Таймаут LLM вызова
    """

    api_seconds: int = 10
    """
    Таймаут внешнего API
    """

    embeddings_seconds: int = 60
    """
    Таймаут эмбеддингов
    """


@dataclass(frozen=True)
class RetryConfig:
    """
    Конфигурация retry политики
    """

    max_attempts: int = 3
    """
    Максимальное количество попыток
    """

    initial_interval: float = 1.0
    """
    Начальный интервал между попытками (секунды)
    """

    multiplier: float = 2.0
    """
    Множитель экспоненциального backoff
    """

    max_interval: float = 10.0
    """
    Максимальный интервал между попытками
    """

    jitter: bool = True
    """
    Добавлять случайный jitter
    """


@dataclass(frozen=True)
class LLMConfig:
    """
    Конфигурация LLM параметров
    """

    model: str = 'GigaChat-2-Max'
    """
    Название модели
    """

    temperature_classification: float = 0.0
    """
    Temperature для классификации (детерминированность)
    """

    temperature_tools: float = 0.3
    """
    Temperature для работы с инструментами
    """

    temperature_conversation: float = 0.7
    """
    Temperature для разговора
    """

    max_tokens_classification: int = 256
    """
    Max tokens для классификации
    """

    max_tokens_default: int = 1024
    """
    Max tokens по умолчанию
    """

    max_tokens_conversation: int = 512
    """
    Max tokens для разговора
    """


@dataclass(frozen=True)
class MemoryConfig:
    """
    Конфигурация памяти агента
    """

    max_sessions: int = 100
    """
    Максимальное количество сессий
    """

    max_messages_per_session: int = 50
    """
    Максимум сообщений на сессию
    """

    context_window_size: int = 6
    """
    Количество последних сообщений в контексте
    """

    recursion_limit: int = 5
    """
    Лимит рекурсии ReAct агента
    """


@dataclass(frozen=True)
class GeoConfig:
    """
    Конфигурация geo-модуля (маршруты, геокодирование).

    Все пути относительно DATA_DIR (в Docker это /app/data).
    """

    city_name: str = 'Санкт-Петербург, Россия'
    """
    Название города для геокодирования и загрузки графов OSM
    """

    graphs_subdir: str = 'graphs'
    """
    Подпапка для хранения графов OSM (внутри DATA_DIR)
    """

    geocode_db_name: str = 'geocode_cache.sqlite3'
    """
    Имя файла SQLite-кеша геокодирования
    """

    osmnx_cache_subdir: str = 'osmnx_cache'
    """
    Подпапка для кеша osmnx
    """

    walk_graph_name: str = 'spb_walk'
    """
    Базовое имя пешеходного графа (без расширения)
    """

    drive_graph_name: str = 'spb_drive'
    """
    Базовое имя автомобильного графа (без расширения)
    """

    spb_metro_data_path: str = 'spb_metro_data_address.json'
    """
    Путь к файлу со статическими данными метро Санкт-Петербурга
    """


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
    """
    Установить кастомный AgentConfig (для тестов и DI)
    """
    global _agent_config
    _agent_config = config


def reset_agent_config() -> None:
    """
    Сбросить конфиг (для тестов)
    """
    global _agent_config
    _agent_config = None


# =============================================================================
# Geo Config (Singleton)
# =============================================================================

_geo_config: GeoConfig | None = None


def get_geo_config() -> GeoConfig:
    """
    Возвращает глобальный GeoConfig.

    Читает значения из переменных окружения при первом вызове.
    """
    global _geo_config

    if _geo_config is None:
        city_name = os.getenv('GEO_CITY_NAME', 'Санкт-Петербург, Россия')
        graphs_subdir = os.getenv('GEO_GRAPHS_SUBDIR', 'graphs')
        geocode_db = os.getenv('GEO_GEOCODE_DB', 'geocode_cache.sqlite3')
        osmnx_cache = os.getenv('GEO_OSMNX_CACHE', 'osmnx_cache')
        spb_metro_data_path = os.getenv('GEO_SPB_METRO_DATA_PATH', 'spb_metro_data_address.json')
        _geo_config = GeoConfig(
            city_name=city_name,
            graphs_subdir=graphs_subdir,
            geocode_db_name=geocode_db,
            osmnx_cache_subdir=osmnx_cache,
            spb_metro_data_path=spb_metro_data_path,
        )

    return _geo_config


def get_geo_paths() -> dict[str, Path]:
    """
    Возвращает все пути для geo-модуля.

    Returns:
        dict с ключами:
        - data_dir: корневая директория данных
        - graph_dir: директория графов OSM
        - geocode_db: путь к SQLite кешу геокодирования
        - osmnx_cache: директория кеша osmnx
        - walk_graphml: путь к пешеходному графу (.graphml)
        - drive_graphml: путь к автомобильному графу (.graphml)
        - walk_pickle: путь к пешеходному графу (.pickle)
        - drive_pickle: путь к автомобильному графу (.pickle)
    """
    geo_cfg = get_geo_config()
    data_dir = Path(os.getenv('DATA_DIR', 'data'))

    graph_dir = data_dir / geo_cfg.graphs_subdir

    return {
        'data_dir': data_dir,
        'graph_dir': graph_dir,
        'geocode_db': data_dir / geo_cfg.geocode_db_name,
        'osmnx_cache': data_dir / geo_cfg.osmnx_cache_subdir,
        'walk_graphml': graph_dir / f'{geo_cfg.walk_graph_name}.graphml',
        'drive_graphml': graph_dir / f'{geo_cfg.drive_graph_name}.graphml',
        'walk_pickle': graph_dir / f'{geo_cfg.walk_graph_name}.pickle',
        'drive_pickle': graph_dir / f'{geo_cfg.drive_graph_name}.pickle',
    }


def reset_geo_config() -> None:
    """
    Сбросить geo конфиг (для тестов)
    """
    global _geo_config
    _geo_config = None


# =============================================================================
# Вспомогательные функции для LLM параметров
# =============================================================================


@lru_cache(maxsize=1)
def get_llm_kwargs_classification() -> dict:
    """
    Параметры LLM для классификации
    """
    config = get_agent_config().llm
    return {
        'model': config.model,
        'temperature': config.temperature_classification,
        'max_tokens': config.max_tokens_classification,
    }


@lru_cache(maxsize=1)
def get_llm_kwargs_tools() -> dict:
    """
    Параметры LLM для работы с инструментами
    """
    config = get_agent_config().llm
    return {
        'model': config.model,
        'temperature': config.temperature_tools,
        'max_tokens': config.max_tokens_default,
    }


@lru_cache(maxsize=1)
def get_llm_kwargs_conversation() -> dict:
    """
    Параметры LLM для разговора
    """
    config = get_agent_config().llm
    return {
        'model': config.model,
        'temperature': config.temperature_conversation,
        'max_tokens': config.max_tokens_conversation,
    }

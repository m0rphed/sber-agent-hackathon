"""
Модуль структурированного логирования с поддержкой structlog и rich.

Режимы работы:
- DEBUG/development: красивый вывод в консоль с rich
- PRODUCTION: структурированный JSON-формат для машинной обработки

Использование:
    from app.logging_config import get_logger

    logger = get_logger(__name__)
    logger.info("event_name", param1="value1", param2=123)
"""

import logging
import os
import sys
from typing import Any

import structlog
from structlog.typing import Processor

# определяем режим работы из переменных окружения
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
LOG_FORMAT = os.getenv('LOG_FORMAT', 'console')  # "console" | "json"
IS_DEBUG = LOG_LEVEL == 'DEBUG' or os.getenv('DEBUG', 'false').lower() == 'true'


def _add_app_context(
    logger: logging.Logger, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """
    Добавляет контекст приложения в каждое сообщение
    """
    event_dict['app'] = 'city-assistant'
    return event_dict


def _order_keys(
    logger: logging.Logger, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """
    Упорядочивает ключи для читаемости: timestamp, level, event, остальное
    """
    ordered = {}

    # Приоритетные ключи в начале
    priority_keys = ['timestamp', 'level', 'event', 'logger']
    for key in priority_keys:
        if key in event_dict:
            ordered[key] = event_dict.pop(key)

    # Остальные ключи в алфавитном порядке
    for key in sorted(event_dict.keys()):
        ordered[key] = event_dict[key]

    return ordered


def _get_console_processors() -> list[Processor]:
    """
    Процессоры для красивого вывода в консоль (dev режим)
    """
    return [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt='%H:%M:%S', utc=False),
        _add_app_context,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer(
            colors=True,
            exception_formatter=structlog.dev.plain_traceback,
            # Умеренные символы, не перебарщиваем с emoji
            level_styles={
                'debug': structlog.dev.BLUE,
                'info': structlog.dev.GREEN,
                'warning': structlog.dev.YELLOW,
                'error': structlog.dev.RED,
                'critical': structlog.dev.MAGENTA,
            },
        ),
    ]


def _get_json_processors() -> list[Processor]:
    """
    Процессоры для JSON-вывода (production режим)
    """
    return [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt='iso', utc=True),
        _add_app_context,
        _order_keys,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(ensure_ascii=False),
    ]


def _configure_stdlib_logging() -> None:
    """
    Настройка стандартного logging для интеграции с structlog
    """
    # определяем уровень
    level = getattr(logging, LOG_LEVEL, logging.INFO)

    # отключаем стандартные handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    # создаём handler для вывода
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    # устанавливаем базовую конфигурацию
    logging.basicConfig(
        format='%(message)s',
        level=level,
        handlers=[handler],
        force=True,
    )

    # понижаем уровень для шумных библиотек
    noisy_loggers = [
        'httpx',
        'httpcore',
        'chromadb',
        'urllib3',
        'asyncio',
    ]
    for logger_name in noisy_loggers:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def configure_logging() -> None:
    """
    Инициализирует структурированное логирование.
    Вызывается один раз при старте приложения

    Режимы:
    - LOG_FORMAT=console (по умолчанию): красивый вывод для разработки
    - LOG_FORMAT=json: структурированный JSON для production
    """
    _configure_stdlib_logging()

    # выбираем процессоры в зависимости от режима
    # JSON-формат имеет приоритет если явно указан
    if LOG_FORMAT == 'json':
        processors = _get_json_processors()
    else:
        processors = _get_console_processors()

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, LOG_LEVEL, logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    """
    Получает настроенный logger

    Args:
        name: Имя модуля (обычно __name__)

    Returns:
        Настроенный structlog BoundLogger

    Пример:
        logger = get_logger(__name__)
        logger.info("search_started", query="загранпаспорт", k=5)
        logger.debug("documents_retrieved", count=10, elapsed_ms=150)
    """
    return structlog.get_logger(name or 'app')


def bind_context(**kwargs: Any) -> None:
    """
    Привязывает контекст ко всем последующим сообщениям в текущем потоке

    Args:
        **kwargs: Контекстные переменные

    Пример:
        bind_context(request_id="abc-123", user_id="user-1")
        logger.info("processing")  # будет включать request_id и user_id
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_context() -> None:
    """
    Очищает привязанный контекст
    """
    structlog.contextvars.clear_contextvars()


# автоматически настраиваем при импорте
configure_logging()

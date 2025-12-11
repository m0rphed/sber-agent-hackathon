"""
Модуль устойчивости агента к ошибкам.

Обеспечивает:
- Централизованную обработку ошибок
- Retry политики для LangGraph узлов
- Graceful degradation при недоступности сервисов
- Timeout для всех внешних вызовов

Типы ошибок и стратегии:
┌─────────────────────┬─────────────────┬────────────────────────────────┐
│ Тип ошибки          │ Стратегия       │ Действие                       │
├─────────────────────┼─────────────────┼────────────────────────────────┤
│ Transient (network) │ RetryPolicy     │ Автоматический retry           │
│ Timeout             │ RetryPolicy     │ Retry с увеличением интервала  │
│ Rate Limit          │ RetryPolicy     │ Retry с backoff                │
│ Hard Error (500)    │ Graceful exit   │ Сообщение пользователю         │
│ Validation Error    │ Fail fast       │ Логирование + сообщение        │
└─────────────────────┴─────────────────┴────────────────────────────────┘
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from langgraph.types import RetryPolicy

from langgraph_app.config import AgentConfig, get_agent_config
from langgraph_app.logging_config import get_logger

logger = get_logger(__name__)


# =============================================================================
# Константы (legacy - используйте get_agent_config())
# =============================================================================

# Таймауты (в секундах) - для обратной совместимости
DEFAULT_LLM_TIMEOUT: float = 30.0
DEFAULT_API_TIMEOUT: float = 15.0
DEFAULT_EMBEDDING_TIMEOUT: float = 20.0

# Retry параметры - для обратной совместимости
DEFAULT_MAX_ATTEMPTS: int = 3
DEFAULT_INITIAL_INTERVAL: float = 1.0
DEFAULT_BACKOFF_FACTOR: float = 2.0
DEFAULT_MAX_INTERVAL: float = 10.0
DEFAULT_JITTER: bool = True


# =============================================================================
# Custom Exceptions
# =============================================================================


class AgentErrorType(StrEnum):
    """
    Типы ошибок агента
    """
    TRANSIENT = 'transient'     # временная ошибка (retry поможет)
    TIMEOUT = 'timeout'         # таймаут запроса
    RATE_LIMIT = 'rate_limit'   # превышен лимит запросов
    SERVICE_UNAVAILABLE = 'service_unavailable' # сервис недоступен
    VALIDATION = 'validation'   # ошибка валидации данных
    UNKNOWN = 'unknown'         # неизвестная ошибка


@dataclass
class AgentError(Exception):
    """
    Базовое исключение агента с метаданными.

    Позволяет классифицировать ошибки и выбирать стратегию обработки.
    """

    error_type: AgentErrorType
    message: str
    user_message: str   # сообщение для пользователя
    details: dict[str, Any] | None = None
    original_exception: Exception | None = None

    def __str__(self) -> str:
        return f'[{self.error_type}] {self.message}'

    @property
    def is_retryable(self) -> bool:
        """
        Можно ли повторить запрос
        """
        return self.error_type in (
            AgentErrorType.TRANSIENT,
            AgentErrorType.TIMEOUT,
            AgentErrorType.RATE_LIMIT,
        )


class LLMTimeoutError(AgentError):
    """
    Таймаут при вызове LLM
    """

    def __init__(self, timeout: float, details: dict | None = None):
        super().__init__(
            error_type=AgentErrorType.TIMEOUT,
            message=f'LLM request timed out after {timeout}s',
            user_message='Сервис временно перегружен. Пожалуйста, повторите запрос через несколько секунд.',
            details=details,
        )


class LLMServiceError(AgentError):
    """
    Ошибка сервиса LLM (5xx)
    """

    def __init__(self, status_code: int | None = None, details: dict | None = None):
        super().__init__(
            error_type=AgentErrorType.SERVICE_UNAVAILABLE,
            message=f'LLM service error (status={status_code})',
            user_message='Сервис временно недоступен. Мы уже работаем над решением проблемы.',
            details=details,
        )


class APITimeoutError(AgentError):
    """
    Таймаут при вызове внешнего API
    """

    def __init__(self, api_name: str, timeout: float, details: dict | None = None):
        super().__init__(
            error_type=AgentErrorType.TIMEOUT,
            message=f'API {api_name} timed out after {timeout}s',
            user_message=f'Сервис {api_name} временно недоступен. Попробуйте позже.',
            details=details,
        )


class RateLimitError(AgentError):
    """
    Превышен лимит запросов
    """

    def __init__(self, retry_after: float | None = None, details: dict | None = None):
        super().__init__(
            error_type=AgentErrorType.RATE_LIMIT,
            message=f'Rate limit exceeded (retry_after={retry_after})',
            user_message='Слишком много запросов. Пожалуйста, подождите немного.',
            details=details,
        )


# =============================================================================
# User-friendly Error Messages
# =============================================================================

ERROR_MESSAGES = {
    AgentErrorType.TRANSIENT: (
        'Произошла временная ошибка. Пожалуйста, повторите запрос.'
    ),
    AgentErrorType.TIMEOUT: (
        'Сервис не ответил вовремя. Попробуйте ещё раз через несколько секунд.'
    ),
    AgentErrorType.RATE_LIMIT: (
        'Слишком много запросов. Пожалуйста, подождите минуту и попробуйте снова.'
    ),
    AgentErrorType.SERVICE_UNAVAILABLE: (
        'Сервис временно недоступен. Мы уже работаем над решением проблемы. '
        'Попробуйте позже.'
    ),
    AgentErrorType.VALIDATION: (
        'Не удалось обработать запрос. Пожалуйста, переформулируйте вопрос.'
    ),
    AgentErrorType.UNKNOWN: (
        'Произошла непредвиденная ошибка. Мы уже знаем о проблеме и работаем над её решением.'
    ),
}


def get_user_error_message(error: Exception) -> str:
    """
    Получить user-friendly сообщение для исключения.

    Args:
        error: Исключение

    Returns:
        Сообщение для отображения пользователю
    """
    if isinstance(error, AgentError):
        return error.user_message

    # Классифицируем по типу исключения
    error_str = str(error).lower()

    if 'timeout' in error_str or 'timed out' in error_str:
        return ERROR_MESSAGES[AgentErrorType.TIMEOUT]

    if 'rate limit' in error_str or '429' in error_str:
        return ERROR_MESSAGES[AgentErrorType.RATE_LIMIT]

    if any(code in error_str for code in ['500', '502', '503', '504']):
        return ERROR_MESSAGES[AgentErrorType.SERVICE_UNAVAILABLE]

    if 'connection' in error_str or 'network' in error_str:
        return ERROR_MESSAGES[AgentErrorType.TRANSIENT]

    return ERROR_MESSAGES[AgentErrorType.UNKNOWN]


# =============================================================================
# Retry Policies
# =============================================================================


def should_retry_exception(exc: Exception) -> bool:
    """
    Определяет, нужно ли повторять запрос при данном исключении.

    Используется как retry_on параметр в RetryPolicy.

    Args:
        exc: Исключение

    Returns:
        True если стоит повторить запрос
    """
    # Наши кастомные исключения
    if isinstance(exc, AgentError):
        return exc.is_retryable

    # Стандартные исключения которые НЕ ретраим
    non_retryable = (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        SyntaxError,
        ImportError,
        NameError,
    )
    if isinstance(exc, non_retryable):
        return False

    # Проверяем по тексту ошибки
    error_str = str(exc).lower()

    # Ретраим timeout и network ошибки
    if any(word in error_str for word in ['timeout', 'timed out', 'connection', 'network']):
        return True

    # Ретраим 5xx и 429
    if any(code in error_str for code in ['429', '500', '502', '503', '504']):
        return True

    # По умолчанию НЕ ретраим неизвестные ошибки
    return False


def get_default_retry_policy(config: AgentConfig | None = None) -> RetryPolicy:
    """
    Стандартная retry policy для узлов графа.

    Args:
        config: Конфигурация агента (None = глобальный)

    Returns:
        RetryPolicy с настройками по умолчанию
    """
    cfg = config or get_agent_config()
    return RetryPolicy(
        max_attempts=cfg.retry.max_attempts,
        initial_interval=cfg.retry.initial_interval,
        backoff_factor=cfg.retry.multiplier,
        max_interval=cfg.retry.max_interval,
        jitter=cfg.retry.jitter,
        retry_on=should_retry_exception,
    )


def get_llm_retry_policy(config: AgentConfig | None = None) -> RetryPolicy:
    """
    Retry policy для LLM вызовов (более агрессивная).

    Args:
        config: Конфигурация агента (None = глобальный)

    Returns:
        RetryPolicy для LLM
    """
    cfg = config or get_agent_config()
    return RetryPolicy(
        max_attempts=cfg.retry.max_attempts,
        initial_interval=cfg.retry.initial_interval,
        backoff_factor=cfg.retry.multiplier,
        max_interval=cfg.retry.max_interval,
        jitter=cfg.retry.jitter,
        retry_on=should_retry_exception,
    )


def get_api_retry_policy(config: AgentConfig | None = None) -> RetryPolicy:
    """
    Retry policy для внешних API.

    Args:
        config: Конфигурация агента (None = глобальный)

    Returns:
        RetryPolicy для API
    """
    cfg = config or get_agent_config()
    # для API меньше попыток и меньше интервал
    return RetryPolicy(
        max_attempts=max(1, cfg.retry.max_attempts - 1),
        initial_interval=cfg.retry.initial_interval * 0.5,
        backoff_factor=cfg.retry.multiplier,
        max_interval=cfg.retry.max_interval * 0.5,
        jitter=cfg.retry.jitter,
        retry_on=should_retry_exception,
    )


# =============================================================================
# State helpers for graceful errors
# =============================================================================


def create_error_state_update(
    error: Exception,
    handler: str = 'error',
) -> dict[str, Any]:
    """
    Создаёт обновление состояния для graceful exit при ошибке.

    Используется в узлах графа для возврата user-friendly сообщения.

    Args:
        error: Исключение
        handler: Имя обработчика для метаданных

    Returns:
        Dict для обновления состояния графа
    """
    user_message = get_user_error_message(error)

    error_type = AgentErrorType.UNKNOWN
    if isinstance(error, AgentError):
        error_type = error.error_type

    logger.error(
        'graceful_error_exit',
        error_type=error_type,
        error_message=str(error),
        user_message=user_message,
        handler=handler,
    )

    return {
        'final_response': user_message,
        'tool_result': None,
        'metadata': {
            'handler': handler,
            'error': True,
            'error_type': error_type,
            'error_message': str(error),
        },
    }


# =============================================================================
# LLM wrapper with timeout
# =============================================================================


def get_llm_with_timeout(
    temperature: float | None = None,
    max_tokens: int | None = None,
    timeout: float | None = None,
    config: AgentConfig | None = None,
):
    """
    Создаёт GigaChat LLM с настроенным timeout.

    Args:
        temperature: Температура генерации (None = из конфига)
        max_tokens: Максимум токенов (None = из конфига)
        timeout: Таймаут в секундах (None = из конфига)
        config: Конфигурация агента (None = глобальный)

    Returns:
        GigaChat instance с timeout
    """
    from langchain_gigachat import GigaChat

    from langgraph_app.config import (
        GIGACHAT_CREDENTIALS,
        GIGACHAT_SCOPE,
        GIGACHAT_VERIFY_SSL_CERTS,
    )

    cfg = config or get_agent_config()

    effective_temp = temperature if temperature is not None else cfg.llm.temperature_conversation
    effective_max_tokens = max_tokens if max_tokens is not None else cfg.llm.max_tokens_default
    effective_timeout = timeout if timeout is not None else float(cfg.timeout.llm_seconds)

    return GigaChat(
        credentials=GIGACHAT_CREDENTIALS,
        scope=GIGACHAT_SCOPE,
        verify_ssl_certs=GIGACHAT_VERIFY_SSL_CERTS,
        temperature=effective_temp,
        max_tokens=effective_max_tokens,
        timeout=effective_timeout,
    )


# =============================================================================
# Декоратор для safe node execution
# =============================================================================


def safe_node(handler_name: str):
    """
    Декоратор для безопасного выполнения узла графа.

    Ловит исключения и возвращает graceful error state.

    Args:
        handler_name: Имя обработчика для логов

    Usage:
        @safe_node('api_handler')
        def api_handler_node(state):
            ...
    """

    def decorator(func):
        def wrapper(state):
            try:
                return func(state)
            except AgentError as e:
                logger.warning(
                    'node_agent_error',
                    handler=handler_name,
                    error_type=e.error_type,
                    error=str(e),
                )
                return create_error_state_update(e, handler=handler_name)
            except Exception as e:
                logger.exception(
                    'node_unexpected_error',
                    handler=handler_name,
                    error=str(e),
                )
                return create_error_state_update(e, handler=handler_name)

        return wrapper

    return decorator


# =============================================================================
# CLI test
# =============================================================================

if __name__ == '__main__':
    print('=== Testing Resilience Module ===\n')

    # Test error messages
    print('1. Error messages:')
    for error_type, message in ERROR_MESSAGES.items():
        print(f'   {error_type}: {message[:50]}...')

    # Test retry policy
    print('\n2. Default retry policy:')
    policy = get_default_retry_policy()
    print(f'   max_attempts: {policy.max_attempts}')
    print(f'   initial_interval: {policy.initial_interval}')
    print(f'   backoff_factor: {policy.backoff_factor}')

    # Test should_retry
    print('\n3. Should retry tests:')
    test_exceptions = [
        (ValueError('bad value'), False),
        (TimeoutError('connection timed out'), True),
        (ConnectionError('network error'), True),
        (LLMTimeoutError(30.0), True),
        (LLMServiceError(503), False),  # Service unavailable не ретраим
    ]
    for exc, expected in test_exceptions:
        result = should_retry_exception(exc)
        status = '✓' if result == expected else '✗'
        print(f'   {status} {type(exc).__name__}: retry={result} (expected={expected})')

    # Test LLM with timeout
    print('\n4. LLM with timeout:')
    try:
        llm = get_llm_with_timeout(timeout=5.0)
        print('   ✓ Created GigaChat with timeout=5.0s')
    except Exception as e:
        print(f'   ✗ Error: {e}')

    print('\n=== Done ===')

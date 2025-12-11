"""
LangChain Tools для работы с API "Я Здесь Живу" (YAZZH) - новая версия.

Эти инструменты используют новый асинхронный клиент app.api.yazzh_new
с улучшенной типизацией и форматированием.
"""

import asyncio
from collections.abc import Callable
from functools import wraps
import json
from typing import Annotated

import httpx
from langchain_core.tools import tool
from pydantic import Field

from langgraph_app.api.yazzh_final import (
    ApiClientUnified,
    format_building_search_for_chat,
)
from langgraph_app.api.yazzh_models import (
    API_UNAVAILABLE_MESSAGE,
    AddressNotFoundError,
    ServiceUnavailableError,
)
from langgraph_app.logging_config import get_logger

logger = get_logger(__name__)

# Применяем патч для работы asyncio.run() внутри уже запущенного event loop


# ============================================================================
# Хелпер для запуска async функций в синхронном контексте
# ============================================================================


def run_async_with_error_handling(func: Callable):
    """
    Декоратор для запуска асинхронных функций в синхронном контексте.
    Автоматически обрабатывает ServiceUnavailableError (502/504).
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return asyncio.run(func(*args, **kwargs))
        except (ServiceUnavailableError, httpx.TimeoutException, httpx.ConnectError):
            logger.error('api_unavailable', func=func.__name__)
            return API_UNAVAILABLE_MESSAGE

    return wrapper


def run_async(func: Callable):
    """
    Декоратор для запуска асинхронных функций в синхронном контексте.
    Используется для LangChain tools, которые пока не поддерживают async.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        return asyncio.run(func(*args, **kwargs))

    return wrapper


# ============================================================================
# Аннотированные типы для параметров tools (улучшает JSON schema для LLM)
# ============================================================================

# Список районов СПб для валидации
SPB_DISTRICTS = [
    'Адмиралтейский',
    'Василеостровский',
    'Выборгский',
    'Калининский',
    'Кировский',
    'Колпинский',
    'Красногвардейский',
    'Красносельский',
    'Кронштадтский',
    'Курортный',
    'Московский',
    'Невский',
    'Петроградский',
    'Петродворцовый',
    'Приморский',
    'Пушкинский',
    'Фрунзенский',
    'Центральный',
]

# Аннотации для адреса - явно указывают что это улица + дом
AddressParam = Annotated[
    str,
    Field(
        description=(
            "АДРЕС в формате 'улица номер_дома'. "
            "Примеры: 'Невский проспект 1', 'ул. Садовая 50', 'Большевиков 68'. "
            'НЕ путать с названием района!'
        )
    ),
]

AddressOptionalParam = Annotated[
    str | None,
    Field(
        default=None,
        description=(
            "АДРЕС (опционально). Формат: 'улица номер_дома'. "
            "Примеры: 'Невский проспект 1', 'пр. Просвещения 50'."
        ),
    ),
]


# ============================================================================
# Инструменты для поиска адресов
# ============================================================================


@tool
def search_address_tool(query: str) -> str:
    """
    Найти адрес в Санкт-Петербурге по текстовому запросу.

    Используй этот инструмент, когда:
    - Нужно уточнить адрес пользователя
    - Пользователь указал неточный или неполный адрес
    - Нужно проверить существование адреса

    Args:
        query: Текстовый запрос для поиска адреса
               (например: "Невский 10", "Большевиков 68 к1", "Лиговский проспект")

    Returns:
        Список найденных адресов или сообщение об ошибке
    """
    logger.info('tool_call', tool='search_address', query=query)

    async def _search():
        async with ApiClientUnified() as client:
            try:
                buildings = await client.search_building_legacy(query, count=5)
                return format_building_search_for_chat(buildings)
            except AddressNotFoundError:
                return 'Адрес не найден. Пожалуйста, уточните запрос.'

    try:
        result = asyncio.run(_search())
    except (ServiceUnavailableError, httpx.TimeoutException, httpx.ConnectError):
        logger.error('api_unavailable', tool='search_address')
        return API_UNAVAILABLE_MESSAGE

    logger.info('tool_result', tool='search_address', result_preview=result[:100])
    return result


# Список всех новых инструментов v2
city_tools_v2 = [
    search_address_tool,
]

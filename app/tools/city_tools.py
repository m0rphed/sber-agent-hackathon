"""
LangChain Tools для работы с API "Я Здесь Живу"
"""

import json

from langchain_core.tools import tool

from app.logging_config import get_logger

logger = get_logger(__name__)

# ленивый импорт клиента, чтобы избежать циклических зависимостей
_client = None


def _get_client():
    """
    Получает singleton клиента API
    """
    global _client
    if _client is None:
        from app.api.yazz import CityAppClient

        _client = CityAppClient()
    return _client


@tool
def find_nearest_mfc_tool(address: str) -> str:
    """
    Найти ближайший МФЦ (Многофункциональный центр) по адресу пользователя.

    Используй этот инструмент, когда пользователь спрашивает:
    - Где находится ближайший МФЦ?
    - Как найти МФЦ рядом с моим домом?
    - Адрес МФЦ около [адрес]
    - Часы работы МФЦ

    Args:
        address: Адрес пользователя в Санкт-Петербурге (например: "Невский проспект 1" или "Большевиков 68")

    Returns:
        Информация о ближайшем МФЦ в формате JSON (название, адрес, телефоны, часы работы)
    """
    logger.info("tool_call", tool="find_nearest_mfc", address=address)

    client = _get_client()
    result = client.find_nearest_mfc(address)

    if result is None:
        logger.warning("tool_no_result", tool="find_nearest_mfc", address=address)
        return 'К сожалению, не удалось найти МФЦ по указанному адресу. Пожалуйста, уточните адрес.'

    logger.info("tool_result", tool="find_nearest_mfc", mfc_name=result.get("name", "N/A"))
    return json.dumps(result, ensure_ascii=False, indent=2)


@tool
def get_pensioner_categories_tool() -> str:
    """
    Получить список категорий услуг для пенсионеров

    Используй этот инструмент, когда пользователь спрашивает:
    - Какие услуги есть для пенсионеров?
    - Какие кружки/секции доступны для пожилых?
    - Категории занятий для пенсионеров

    Returns:
        Список доступных категорий услуг для пенсионеров
    """
    logger.info("tool_call", tool="get_pensioner_categories")

    client = _get_client()
    result = client.pensioner_service_category()

    if result is None:
        logger.warning("tool_no_result", tool="get_pensioner_categories")
        return 'Не удалось получить список категорий услуг.'

    count = len(result) if isinstance(result, list) else 1
    logger.info("tool_result", tool="get_pensioner_categories", categories_count=count)
    return json.dumps(result, ensure_ascii=False, indent=2)


@tool
def get_pensioner_services_tool(district: str, categories: str) -> str:
    """
    Найти услуги для пенсионеров по району и категориям.

    Используй этот инструмент, когда пользователь спрашивает:
    - Какие занятия для пенсионеров есть в [район]?
    - Где записаться на компьютерные курсы для пожилых?
    - Кружки для пенсионеров в Невском районе

    Args:
        district: Название района Санкт-Петербурга (например: "Невский", "Центральный")
        categories: Категории услуг через запятую (например: "Вокал,Компьютерные курсы")

    Returns:
        Список услуг для пенсионеров в указанном районе
    """
    logger.info(
        "tool_call",
        tool="get_pensioner_services",
        district=district,
        categories=categories,
    )

    client = _get_client()
    category_list = [c.strip() for c in categories.split(',')]
    result = client.pensioner_services(district, category_list)

    if result is None:
        logger.warning(
            "tool_no_result",
            tool="get_pensioner_services",
            district=district,
        )
        return 'Не удалось найти услуги по указанным параметрам.'

    count = len(result) if isinstance(result, list) else 1
    logger.info("tool_result", tool="get_pensioner_services", services_count=count)
    return json.dumps(result, ensure_ascii=False, indent=2)


# список всех доступных инструментов
ALL_TOOLS = [
    find_nearest_mfc_tool,
    get_pensioner_categories_tool,
    get_pensioner_services_tool,
]

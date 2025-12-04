"""
LangChain Tools для работы с API "Я Здесь Живу" (YAZZH) - новая версия.

Эти инструменты используют новый асинхронный клиент app.api.yazzh_new
с улучшенной типизацией и форматированием.
"""

import asyncio
from collections.abc import Callable
from functools import wraps
import json

import httpx
from langchain_core.tools import tool
import nest_asyncio

from app.api.yazzh_new import (
    API_UNAVAILABLE_MESSAGE,
    AddressNotFoundError,
    ServiceUnavailableError,
    YazzhAsyncClient,
    format_building_search_for_chat,
    format_mfc_for_chat,
    format_polyclinics_for_chat,
    format_schools_for_chat,
)
from app.logging_config import get_logger

logger = get_logger(__name__)

# Применяем патч для работы asyncio.run() внутри уже запущенного event loop
nest_asyncio.apply()


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
        async with YazzhAsyncClient() as client:
            try:
                buildings = await client.search_building(query, count=5)
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


# ============================================================================
# Инструменты для МФЦ
# ============================================================================


@tool
def find_nearest_mfc_v2(address: str) -> str:
    """
    Найти ближайший МФЦ (Многофункциональный центр) по адресу пользователя.

    Используй этот инструмент, когда пользователь спрашивает:
    - Где находится ближайший МФЦ?
    - Как найти МФЦ рядом с моим домом?
    - Адрес МФЦ около [адрес]
    - Часы работы МФЦ
    - Контакты МФЦ

    Args:
        address: Адрес пользователя в Санкт-Петербурге
                 (например: "Невский проспект 1" или "Большевиков 68")

    Returns:
        Информация о ближайшем МФЦ (название, адрес, телефоны, часы работы)
        или сообщение об ошибке
    """
    logger.info('tool_call', tool='find_nearest_mfc_v2', address=address)

    async def _find_mfc():
        async with YazzhAsyncClient() as client:
            mfc = await client.get_nearest_mfc_by_address(address)
            return format_mfc_for_chat(mfc)

    try:
        result = asyncio.run(_find_mfc())
    except (ServiceUnavailableError, httpx.TimeoutException, httpx.ConnectError):
        logger.error('api_unavailable', tool='find_nearest_mfc_v2')
        return API_UNAVAILABLE_MESSAGE

    logger.info(
        'tool_result', tool='find_nearest_mfc_v2', result_preview=result[:100] if result else 'None'
    )
    return result


@tool
def get_mfc_list_by_district_v2(district: str) -> str:
    """
    Получить список всех МФЦ в указанном районе Санкт-Петербурга.

    Используй этот инструмент, когда пользователь спрашивает:
    - Какие МФЦ есть в [район]?
    - Список МФЦ в Невском районе
    - Все МФЦ Центрального района

    Args:
        district: Название района Санкт-Петербурга
                  (например: "Невский", "Центральный", "Адмиралтейский")

    Returns:
        Список МФЦ с адресами и контактами
    """
    logger.info('tool_call', tool='get_mfc_list_by_district_v2', district=district)

    async def _get_mfc_list():
        async with YazzhAsyncClient() as client:
            mfc_list = await client.get_mfc_by_district(district)

            if not mfc_list:
                return f"МФЦ в районе '{district}' не найдены. Проверьте название района."

            lines = [f'МФЦ в {district} районе ({len(mfc_list)} шт.):\n']
            for mfc in mfc_list:
                lines.append(mfc.format_for_human())
                lines.append('')
            return '\n'.join(lines)

    try:
        result = asyncio.run(_get_mfc_list())
    except (ServiceUnavailableError, httpx.TimeoutException, httpx.ConnectError):
        logger.error('api_unavailable', tool='get_mfc_list_by_district_v2')
        return API_UNAVAILABLE_MESSAGE

    logger.info('tool_result', tool='get_mfc_list_by_district_v2', result_preview=result[:100])
    return result


# ============================================================================
# Инструменты для поликлиник
# ============================================================================


@tool
def get_polyclinics_by_address_v2(address: str) -> str:
    """
    Найти поликлиники, обслуживающие дом по указанному адресу.

    Используй этот инструмент, когда пользователь спрашивает:
    - К какой поликлинике я прикреплён?
    - Где моя поликлиника по адресу [адрес]?
    - Какие поликлиники обслуживают мой дом?
    - Контакты поликлиники для моего адреса

    Args:
        address: Адрес пользователя в Санкт-Петербурге

    Returns:
        Список поликлиник с контактами и адресами
    """
    logger.info('tool_call', tool='get_polyclinics_by_address_v2', address=address)

    async def _get_polyclinics():
        async with YazzhAsyncClient() as client:
            clinics = await client.get_polyclinics_by_address(address)
            return format_polyclinics_for_chat(clinics)

    try:
        result = asyncio.run(_get_polyclinics())
    except (ServiceUnavailableError, httpx.TimeoutException, httpx.ConnectError):
        logger.error('api_unavailable', tool='get_polyclinics_by_address_v2')
        return API_UNAVAILABLE_MESSAGE

    logger.info('tool_result', tool='get_polyclinics_by_address_v2', result_preview=result[:100])
    return result


# ============================================================================
# Инструменты для школ
# ============================================================================


@tool
def get_linked_schools_by_address_v2(address: str) -> str:
    """
    Найти школы, прикреплённые к дому по указанному адресу.

    Используй этот инструмент, когда пользователь спрашивает:
    - К какой школе прикреплён мой дом?
    - В какую школу записать ребёнка по адресу [адрес]?
    - Какие школы обслуживают наш дом?
    - Запись в первый класс по прописке

    Args:
        address: Адрес пользователя в Санкт-Петербурге

    Returns:
        Список прикреплённых школ с информацией о свободных местах
    """
    logger.info('tool_call', tool='get_linked_schools_by_address_v2', address=address)

    async def _get_schools():
        async with YazzhAsyncClient() as client:
            schools = await client.get_linked_schools_by_address(address)
            return format_schools_for_chat(schools)

    try:
        result = asyncio.run(_get_schools())
    except (ServiceUnavailableError, httpx.TimeoutException, httpx.ConnectError):
        logger.error('api_unavailable', tool='get_linked_schools_by_address_v2')
        return API_UNAVAILABLE_MESSAGE

    logger.info('tool_result', tool='get_linked_schools_by_address_v2', result_preview=result[:100])
    return result


# ============================================================================
# Инструменты для управляющих компаний
# ============================================================================


@tool
def get_management_company_by_address_v2(address: str) -> str:
    """
    Найти управляющую компанию (УК) для дома по указанному адресу.

    Используй этот инструмент, когда пользователь спрашивает:
    - Какая УК обслуживает мой дом?
    - Контакты управляющей компании
    - Кто управляет домом по адресу [адрес]?
    - Как связаться с УК?
    - ЖЭК/ЖКХ моего дома

    Args:
        address: Адрес дома в Санкт-Петербурге

    Returns:
        Информация об управляющей компании (название, адрес, контакты)
    """
    logger.info('tool_call', tool='get_management_company_by_address_v2', address=address)

    async def _get_uk():
        async with YazzhAsyncClient() as client:
            uk = await client.get_management_company_by_address(address)

            if uk is None:
                return 'Информация об управляющей компании не найдена для указанного адреса.'

            lines = ['🏢 Управляющая компания:\n']
            if uk.name:
                lines.append(f'   Название: {uk.name}')
            if uk.address:
                lines.append(f'   Адрес: {uk.address}')
            if uk.phone:
                lines.append(f'   📞 Телефон: {uk.phone}')
            if uk.email:
                lines.append(f'   ✉️ Email: {uk.email}')
            if uk.inn:
                lines.append(f'   ИНН: {uk.inn}')
            return '\n'.join(lines)

    try:
        result = asyncio.run(_get_uk())
    except (ServiceUnavailableError, httpx.TimeoutException, httpx.ConnectError):
        logger.error('api_unavailable', tool='get_management_company_by_address_v2')
        return API_UNAVAILABLE_MESSAGE

    logger.info(
        'tool_result', tool='get_management_company_by_address_v2', result_preview=result[:100]
    )
    return result


# ============================================================================
# Инструменты для получения информации о районах
# ============================================================================


@tool
def get_districts_list() -> str:
    """
    Получить список всех районов Санкт-Петербурга.

    Используй этот инструмент, когда пользователь спрашивает:
    - Какие районы есть в Санкт-Петербурге?
    - Список районов СПб
    - В каких районах можно искать?

    Returns:
        Список районов города
    """
    logger.info('tool_call', tool='get_districts_list')

    async def _get_districts():
        async with YazzhAsyncClient() as client:
            districts = await client.get_districts()

            if not districts:
                return 'Не удалось получить список районов.'

            lines = [f'Районы Санкт-Петербурга ({len(districts)} шт.):\n']
            for d in sorted(districts, key=lambda x: x.name):
                lines.append(f'• {d.name}')
            return '\n'.join(lines)

    try:
        result = asyncio.run(_get_districts())
    except (ServiceUnavailableError, httpx.TimeoutException, httpx.ConnectError):
        logger.error('api_unavailable', tool='get_districts_list')
        return API_UNAVAILABLE_MESSAGE

    logger.info('tool_result', tool='get_districts_list', result_preview=result[:100])
    return result


@tool
def get_district_info_by_address_v2(address: str) -> str:
    """
    Получить справочную информацию о районе по адресу.

    Включает полезные контакты и службы района: аварийные службы,
    отделы социальной защиты, здравоохранение и др.

    Используй этот инструмент, когда пользователь спрашивает:
    - Полезные телефоны для моего района
    - Службы по адресу [адрес]
    - Контакты администрации района
    - Социальные службы моего района

    Args:
        address: Адрес в Санкт-Петербурге

    Returns:
        Справочная информация о районе (контакты служб)
    """
    logger.info('tool_call', tool='get_district_info_by_address_v2', address=address)

    async def _get_district_info():
        async with YazzhAsyncClient() as client:
            try:
                building = await client.search_building_first(address)
            except AddressNotFoundError:
                return f"Адрес '{address}' не найден."

            info = await client.get_district_info_by_building(building.building_id)

            if not info:
                return 'Не удалось получить информацию о районе.'

            # info может быть списком категорий
            if isinstance(info, list):
                lines = ['📋 Справочная информация по району:\n']
                for category in info[:5]:  # Ограничим вывод
                    cat_name = category.get('category', '')
                    if cat_name:
                        lines.append(f'\n📌 {cat_name}:')
                        data = category.get('data', [])
                        for item in data[:3]:  # Первые 3 записи
                            name = item.get('name', '')
                            phone = item.get('phone', '')
                            if name:
                                line = f'   • {name}'
                                if phone:
                                    line += f' — {phone}'
                                lines.append(line)
                return '\n'.join(lines)

            return json.dumps(info, ensure_ascii=False, indent=2)

    try:
        result = asyncio.run(_get_district_info())
    except (ServiceUnavailableError, httpx.TimeoutException, httpx.ConnectError):
        logger.error('api_unavailable', tool='get_district_info_by_address_v2')
        return API_UNAVAILABLE_MESSAGE

    logger.info('tool_result', tool='get_district_info_by_address_v2', result_preview=result[:100])
    return result


# ============================================================================
# Инструменты для детских садов (ДОУ)
# ============================================================================


@tool
def get_kindergartens_v2(district: str, age_years: int = 3, age_months: int = 0) -> str:
    """
    Найти детские сады в районе для ребёнка определённого возраста.

    Используй этот инструмент, когда пользователь спрашивает:
    - Какие детские сады есть в [район]?
    - Куда отдать ребёнка 3 лет в детский сад?
    - Детсады со свободными местами в Невском районе
    - Государственные детские сады для ребёнка 2 лет

    Args:
        district: Название района Санкт-Петербурга (например: "Невский", "Центральный")
        age_years: Возраст ребёнка в годах (0-9)
        age_months: Возраст ребёнка в месяцах (0-11)

    Returns:
        Список детских садов со свободными местами
    """
    logger.info('tool_call', tool='get_kindergartens_v2', district=district, age_years=age_years)

    async def _get_kindergartens():
        async with YazzhAsyncClient() as client:
            from app.api.yazzh_new import format_kindergartens_for_chat

            kindergartens = await client.get_kindergartens(
                district=district,
                age_year=age_years,
                age_month=age_months,
                count=10,
            )
            return format_kindergartens_for_chat(kindergartens)

    try:
        result = asyncio.run(_get_kindergartens())
    except (ServiceUnavailableError, httpx.TimeoutException, httpx.ConnectError):
        logger.error('api_unavailable', tool='get_kindergartens_v2')
        return API_UNAVAILABLE_MESSAGE

    logger.info('tool_result', tool='get_kindergartens_v2', result_preview=result[:100])
    return result


# ============================================================================
# Инструменты для афиши (мероприятий)
# ============================================================================


@tool
def get_city_events_v2(
    days_ahead: int = 7,
    category: str = '',
    free_only: bool = False,
    for_kids: bool = False,
) -> str:
    """
    Найти мероприятия и события в Санкт-Петербурге.

    Используй этот инструмент, когда пользователь спрашивает:
    - Что интересного в городе на выходных?
    - Какие концерты будут на этой неделе?
    - Бесплатные мероприятия в СПб
    - Куда сходить с ребёнком?
    - Выставки в ближайшие дни

    Args:
        days_ahead: На сколько дней вперёд искать (1-30)
        category: Категория мероприятия (например: "Концерт", "Выставка", "Спектакль", "")
        free_only: Только бесплатные мероприятия
        for_kids: Подходит для детей

    Returns:
        Список мероприятий с датами и местами
    """
    logger.info(
        'tool_call',
        tool='get_city_events_v2',
        days_ahead=days_ahead,
        category=category,
        free_only=free_only,
    )

    async def _get_events():
        import pendulum

        async with YazzhAsyncClient() as client:
            from app.api.yazzh_new import format_events_for_chat

            now = pendulum.now('Europe/Moscow')
            start_date = now.format('YYYY-MM-DDTHH:mm:ss')
            end_date = now.add(days=days_ahead).format('YYYY-MM-DDTHH:mm:ss')

            events = await client.get_events(
                start_date=start_date,
                end_date=end_date,
                category=category if category else None,
                free=True if free_only else None,
                kids=True if for_kids else None,
                count=10,
            )
            return format_events_for_chat(events)

    try:
        result = asyncio.run(_get_events())
    except (ServiceUnavailableError, httpx.TimeoutException, httpx.ConnectError):
        logger.error('api_unavailable', tool='get_city_events_v2')
        return API_UNAVAILABLE_MESSAGE

    logger.info('tool_result', tool='get_city_events_v2', result_preview=result[:100])
    return result


@tool
def get_event_categories_v2() -> str:
    """
    Получить список категорий мероприятий в афише города.

    Используй этот инструмент, когда пользователь спрашивает:
    - Какие категории мероприятий есть?
    - Что можно посмотреть в городе?
    - Типы событий в афише

    Returns:
        Список доступных категорий мероприятий с количеством
    """
    logger.info('tool_call', tool='get_event_categories_v2')

    async def _get_categories():
        async with YazzhAsyncClient() as client:
            categories = await client.get_event_categories()

            if not categories:
                return 'Не удалось получить список категорий мероприятий.'

            # categories теперь dict {категория: количество}
            lines = ['📋 Категории мероприятий в афише:\n']
            # Сортируем по количеству (убывание)
            sorted_cats = sorted(categories.items(), key=lambda x: x[1], reverse=True)
            for cat, count in sorted_cats:
                lines.append(f'• {cat} ({count} мероприятий)')
            return '\n'.join(lines)

    try:
        result = asyncio.run(_get_categories())
    except (ServiceUnavailableError, httpx.TimeoutException, httpx.ConnectError):
        logger.error('api_unavailable', tool='get_event_categories_v2')
        return API_UNAVAILABLE_MESSAGE

    logger.info('tool_result', tool='get_event_categories_v2', result_preview=result[:100])
    return result


# ============================================================================
# Инструменты для отключений коммунальных услуг
# ============================================================================


@tool
def get_disconnections_by_address_v2(address: str) -> str:
    """
    Проверить наличие отключений воды или электричества по адресу.

    Используй этот инструмент, когда пользователь спрашивает:
    - Когда отключат воду/горячую воду в моём доме?
    - Будут ли отключения электричества по адресу [адрес]?
    - Есть ли плановые отключения по моему адресу?
    - Почему нет воды/света?

    Args:
        address: Адрес дома в Санкт-Петербурге (например: "Невский проспект 100")

    Returns:
        Информация об отключениях или сообщение что отключений нет
    """
    logger.info('tool_call', tool='get_disconnections_by_address_v2', address=address)

    async def _get_disconnections():
        async with YazzhAsyncClient() as client:
            from app.api.yazzh_new import format_disconnections_for_chat

            disconnections = await client.get_disconnections_by_address(address)
            return format_disconnections_for_chat(disconnections)

    try:
        result = asyncio.run(_get_disconnections())
    except (ServiceUnavailableError, httpx.TimeoutException, httpx.ConnectError):
        logger.error('api_unavailable', tool='get_disconnections_by_address_v2')
        return API_UNAVAILABLE_MESSAGE

    logger.info('tool_result', tool='get_disconnections_by_address_v2', result_preview=result[:100])
    return result


# ============================================================================
# Инструменты для спортивных мероприятий
# ============================================================================


@tool
def get_sport_events_v2(
    district: str = '',
    days_ahead: int = 14,
    category: str = '',
    for_disabled: bool = False,
    family_hour: bool = False,
) -> str:
    """
    Найти спортивные мероприятия в Санкт-Петербурге.

    Используй этот инструмент, когда пользователь спрашивает:
    - Какие спортивные мероприятия будут в [район]?
    - Соревнования по футболу/баскетболу/волейболу
    - Спортивные события для людей с ОВЗ
    - Семейные спортивные мероприятия
    - Где позаниматься спортом?

    Args:
        district: Район города (например: "Невский", "Центральный"). Пустая строка = все районы.
        days_ahead: На сколько дней вперёд искать (1-30)
        category: Вид спорта (например: "Футбол", "Баскетбол", "Скандинавская ходьба")
        for_disabled: Только мероприятия, доступные для людей с ОВЗ
        family_hour: Только мероприятия программы "Семейный час"

    Returns:
        Список спортивных мероприятий с датами и адресами
    """
    logger.info(
        'tool_call',
        tool='get_sport_events_v2',
        district=district,
        days_ahead=days_ahead,
        category=category,
    )

    async def _get_sport_events():
        import pendulum

        async with YazzhAsyncClient() as client:
            from app.api.yazzh_new import format_sport_events_for_chat

            now = pendulum.now('Europe/Moscow')
            start_date = now.format('YYYY-MM-DD')
            end_date = now.add(days=days_ahead).format('YYYY-MM-DD')

            events = await client.get_sport_events(
                district=district if district else None,
                categoria=category if category else None,
                start_date=start_date,
                end_date=end_date,
                ovz=True if for_disabled else None,
                family_hour=True if family_hour else None,
                count=10,
            )
            return format_sport_events_for_chat(events)

    try:
        result = asyncio.run(_get_sport_events())
    except (ServiceUnavailableError, httpx.TimeoutException, httpx.ConnectError):
        logger.error('api_unavailable', tool='get_sport_events_v2')
        return API_UNAVAILABLE_MESSAGE

    logger.info('tool_result', tool='get_sport_events_v2', result_preview=result[:100])
    return result


@tool
def get_sport_categories_by_district_v2(district: str) -> str:
    """
    Получить список видов спорта, доступных в районе.

    Используй этот инструмент, когда пользователь спрашивает:
    - Какие виды спорта есть в [район]?
    - Каким спортом можно заняться в Невском районе?
    - Что из спорта проводится в моём районе?

    Args:
        district: Название района (например: "Невский", "Центральный")

    Returns:
        Список видов спорта, по которым проводятся мероприятия в районе
    """
    logger.info('tool_call', tool='get_sport_categories_by_district_v2', district=district)

    async def _get_categories():
        async with YazzhAsyncClient() as client:
            categories = await client.get_sport_event_categories(district)

            if not categories:
                return f"Информация о видах спорта в районе '{district}' не найдена."

            lines = [f'🏅 Виды спорта в {district} районе:\n']
            for cat in sorted(categories):
                lines.append(f'• {cat}')
            return '\n'.join(lines)

    try:
        result = asyncio.run(_get_categories())
    except (ServiceUnavailableError, httpx.TimeoutException, httpx.ConnectError):
        logger.error('api_unavailable', tool='get_sport_categories_by_district_v2')
        return API_UNAVAILABLE_MESSAGE

    logger.info(
        'tool_result', tool='get_sport_categories_by_district_v2', result_preview=result[:100]
    )
    return result


# ============================================================================
# Инструменты для услуг пенсионерам (Долголетие)
# ============================================================================


@tool
def get_pensioner_service_categories_v2() -> str:
    """
    Получить список категорий услуг для пенсионеров (программа "Долголетие").

    Используй этот инструмент, когда пользователь спрашивает:
    - Какие занятия есть для пенсионеров?
    - Что входит в программу Долголетие?
    - Виды активностей для пожилых людей

    Returns:
        Список категорий услуг (Вокал, Здоровье, Спорт и т.д.)
    """
    logger.info('tool_call', tool='get_pensioner_service_categories_v2')

    async def _get_categories():
        async with YazzhAsyncClient() as client:
            categories = await client.get_pensioner_service_categories()

            if not categories:
                return 'Не удалось получить список категорий услуг для пенсионеров.'

            lines = ['🎭 Категории услуг для пенсионеров (программа "Долголетие"):\n']
            for cat in sorted(categories):
                lines.append(f'• {cat}')
            return '\n'.join(lines)

    try:
        result = asyncio.run(_get_categories())
    except (ServiceUnavailableError, httpx.TimeoutException, httpx.ConnectError):
        logger.error('api_unavailable', tool='get_pensioner_service_categories_v2')
        return API_UNAVAILABLE_MESSAGE

    logger.info(
        'tool_result', tool='get_pensioner_service_categories_v2', result_preview=result[:100]
    )
    return result


@tool
def get_pensioner_services_v2(
    district: str,
    category: str = '',
) -> str:
    """
    Найти услуги для пенсионеров в районе по программе "Долголетие".

    Используй этот инструмент, когда пользователь спрашивает:
    - Какие занятия для пенсионеров есть в [район]?
    - Где заниматься йогой/танцами/рукоделием для пожилых?
    - Услуги по программе Долголетие в моём районе
    - Активности для людей старшего возраста

    Args:
        district: Район города (например: "Невский", "Центральный")
        category: Категория услуги (например: "Здоровье", "Спорт", "Танцы").
                  Пустая строка = все категории.

    Returns:
        Список услуг с адресами и описаниями
    """
    logger.info(
        'tool_call',
        tool='get_pensioner_services_v2',
        district=district,
        category=category,
    )

    async def _get_services():
        async with YazzhAsyncClient() as client:
            from app.api.yazzh_new import format_pensioner_services_for_chat

            categories = [category] if category else None
            services = await client.get_pensioner_services(
                district=district,
                categories=categories,
                count=10,
            )
            return format_pensioner_services_for_chat(services)

    try:
        result = asyncio.run(_get_services())
    except (ServiceUnavailableError, httpx.TimeoutException, httpx.ConnectError):
        logger.error('api_unavailable', tool='get_pensioner_services_v2')
        return API_UNAVAILABLE_MESSAGE

    logger.info('tool_result', tool='get_pensioner_services_v2', result_preview=result[:100])
    return result


# ============================================================================
# Инструменты для памятных дат
# ============================================================================


@tool
def get_memorable_dates_today_v2() -> str:
    """
    Получить памятные даты в истории Санкт-Петербурга на сегодня.

    Используй этот инструмент, когда пользователь спрашивает:
    - Какие события произошли сегодня в истории Петербурга?
    - Памятные даты на сегодня
    - Что интересного случилось в этот день в истории города?
    - Исторические события сегодняшнего дня

    Returns:
        Список памятных дат с описаниями
    """
    logger.info('tool_call', tool='get_memorable_dates_today_v2')

    async def _get_dates():
        async with YazzhAsyncClient() as client:
            from app.api.yazzh_new import format_memorable_dates_for_chat

            dates = await client.get_memorable_dates_today()
            return format_memorable_dates_for_chat(dates)

    try:
        result = asyncio.run(_get_dates())
    except (ServiceUnavailableError, httpx.TimeoutException, httpx.ConnectError):
        logger.error('api_unavailable', tool='get_memorable_dates_today_v2')
        return API_UNAVAILABLE_MESSAGE

    logger.info('tool_result', tool='get_memorable_dates_today_v2', result_preview=result[:100])
    return result


# ============================================================================
# Инструменты для спортплощадок (статистика)
# ============================================================================


@tool
def get_sportgrounds_count_v2(district: str = '') -> str:
    """
    Получить количество спортплощадок в городе или конкретном районе.

    Используй этот инструмент, когда пользователь спрашивает:
    - Сколько спортплощадок в Санкт-Петербурге?
    - Сколько спортплощадок в [район]?
    - Статистика спортплощадок по районам
    - В каком районе больше всего спортплощадок?

    Args:
        district: Район города (например: "Невский"). Пустая строка = статистика по всем районам.

    Returns:
        Количество спортплощадок
    """
    logger.info('tool_call', tool='get_sportgrounds_count_v2', district=district)

    async def _get_count():
        async with YazzhAsyncClient() as client:
            from app.api.yazzh_new import format_sportgrounds_count_for_chat

            if district:
                # Конкретный район
                counts = await client.get_sportgrounds_count_by_district(district)
                return format_sportgrounds_count_for_chat(counts)
            else:
                # Статистика по всем районам
                counts = await client.get_sportgrounds_count_by_district()
                return format_sportgrounds_count_for_chat(counts)

    try:
        result = asyncio.run(_get_count())
    except (ServiceUnavailableError, httpx.TimeoutException, httpx.ConnectError):
        logger.error('api_unavailable', tool='get_sportgrounds_count_v2')
        return API_UNAVAILABLE_MESSAGE

    logger.info('tool_result', tool='get_sportgrounds_count_v2', result_preview=result[:100])
    return result


@tool
def get_sportgrounds_v2(
    district: str = '',
    sport_types: str = '',
    count: int = 10,
) -> str:
    """
    Найти спортивные площадки с фильтрами по району и типу спорта.

    Используй этот инструмент, когда пользователь спрашивает:
    - Где находятся спортплощадки в [район]?
    - Покажи футбольные площадки в Невском районе
    - Найди площадку для баскетбола рядом с домом
    - Какие спортплощадки есть в [район]?
    - Хочу поиграть в футбол, где можно?

    Args:
        district: Район города (например: "Невский"). Пустая строка = весь город.
        sport_types: Типы спорта через запятую (например: "Футбол, Баскетбол").
                     Пустая строка = все типы.
        count: Количество площадок (по умолчанию 10, максимум 50).

    Returns:
        Список спортплощадок с адресами и типами спорта
    """
    logger.info(
        'tool_call',
        tool='get_sportgrounds_v2',
        district=district,
        sport_types=sport_types,
        count=count,
    )

    # Ограничим количество
    count = min(max(1, count), 50)

    async def _get_sportgrounds():
        async with YazzhAsyncClient() as client:
            from app.api.yazzh_new import format_sportgrounds_for_chat

            sportgrounds, total = await client.get_sportgrounds(
                district=district or None,
                sport_types=sport_types or None,
                count=count,
            )
            return format_sportgrounds_for_chat(sportgrounds, total)

    try:
        result = asyncio.run(_get_sportgrounds())
    except (ServiceUnavailableError, httpx.TimeoutException, httpx.ConnectError):
        logger.error('api_unavailable', tool='get_sportgrounds_v2')
        return API_UNAVAILABLE_MESSAGE

    logger.info('tool_result', tool='get_sportgrounds_v2', result_preview=result[:100])
    return result


# ============================================================================
# Экспорт инструментов
# ============================================================================

# Список всех новых инструментов v2
city_tools_v2 = [
    search_address_tool,
    find_nearest_mfc_v2,
    get_mfc_list_by_district_v2,
    get_polyclinics_by_address_v2,
    get_linked_schools_by_address_v2,
    get_management_company_by_address_v2,
    get_districts_list,
    get_district_info_by_address_v2,
    # Новые инструменты
    get_kindergartens_v2,
    get_city_events_v2,
    get_event_categories_v2,
    # Отключения и спорт
    get_disconnections_by_address_v2,
    get_sport_events_v2,
    get_sport_categories_by_district_v2,
    # Tier 1: Пенсионеры, памятные даты, спортплощадки
    get_pensioner_service_categories_v2,
    get_pensioner_services_v2,
    get_memorable_dates_today_v2,
    get_sportgrounds_count_v2,
    get_sportgrounds_v2,
]

ALL_TOOLS = city_tools_v2

"""
LangChain Tools V3 — версия для GigaChat с @giga_tool и few-shot examples.

Полностью async версия без nest_asyncio.
API: yazzh_final.ApiClientUnified (НЕ yazzh_new!)

Отличия от city_tools_v3.py:
- Использует @giga_tool вместо @tool
- Добавлены few_shot_examples для улучшения понимания моделью
- Более детальные docstrings адаптированные под GigaChat
"""

from functools import wraps
from typing import Any

import httpx
from langchain_gigachat.tools.giga_tool import giga_tool

from langgraph_app.api.geo.geocoding_service import (
    GeocodingResult,
    geocode_address,
    geocode_address_with_candidates,
)
from langgraph_app.api.yazzh_final import ApiClientUnified
from langgraph_app.logging_config import get_logger

logger = get_logger(__name__)

API_UNAVAILABLE_MESSAGE = (
    '⚠️ Сервис временно недоступен. Пожалуйста, попробуйте позже или обратитесь '
    'на портал «Я здесь живу»: https://yazzh.ru'
)


# =============================================================================
# Async Error Handling Decorator
# =============================================================================


def handle_api_errors(func):
    """Декоратор для обработки ошибок API в async tools."""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            logger.error('api_unavailable', tool=func.__name__, error=str(e))
            return API_UNAVAILABLE_MESSAGE
        except Exception as e:
            logger.error('tool_error', tool=func.__name__, error=str(e))
            return f'Ошибка при выполнении запроса: {e}'

    return wrapper


def _extract_json(result: dict[str, Any]) -> Any | None:
    """Извлечь JSON из результата API."""
    if result.get('status_code') != 200:
        return None
    return result.get('json')


# =============================================================================
# Address / Geo Tools
# =============================================================================


@giga_tool(
    few_shot_examples=[
        {'request': 'Найди адрес Невский 10', 'params': {'query': 'Невский 10'}},
        {'request': 'Проверь адрес Большевиков 68', 'params': {'query': 'Большевиков 68'}},
        {'request': 'Какой это адрес - Садовая улица 50?', 'params': {'query': 'Садовая улица 50'}},
    ]
)
@handle_api_errors
async def search_address(query: str) -> str:
    """
    Найти адрес в Санкт-Петербурге по текстовому запросу.

    Используй когда нужно уточнить или проверить адрес пользователя.

    Args:
        query: Текстовый запрос для поиска адреса (например: "Невский 10", "Большевиков 68 к1")

    Returns:
        Список найденных адресов или сообщение об ошибке
    """
    logger.info('tool_call', tool='search_address', query=query)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.search_building_full_text_search(query=query, count=5)
        data = _extract_json(result)

        if not data:
            return f"Адрес '{query}' не найден. Уточните запрос."

        buildings = (
            data if isinstance(data, list) else data.get('data') or data.get('results') or []
        )

        if not buildings:
            return f"Адрес '{query}' не найден. Уточните запрос."

        if len(buildings) == 1:
            b = buildings[0]
            return f'Найден адрес: {b.get("full_address", b.get("address", str(b)))}'

        lines = ['Найдено несколько адресов. Уточните, какой из них вам нужен:\n']
        for i, b in enumerate(buildings[:5], 1):
            addr = b.get('full_address') or b.get('address') or str(b)
            lines.append(f'{i}. {addr}')

        return '\n'.join(lines)


@giga_tool(
    few_shot_examples=[
        {'request': 'Какие есть районы в Питере?', 'params': {}},
        {'request': 'Список районов СПб', 'params': {}},
    ]
)
@handle_api_errors
async def get_districts_list() -> str:
    """
    Получить список всех районов Санкт-Петербурга.

    Используй для справки о районах города.

    Returns:
        Список районов СПб
    """
    logger.info('tool_call', tool='get_districts_list')

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_districts()
        data = _extract_json(result)

        if not data:
            return 'Не удалось получить список районов.'

        districts = data if isinstance(data, list) else data.get('data') or []

        lines = ['Районы Санкт-Петербурга:\n']
        for d in districts:
            if isinstance(d, dict):
                name = d.get('name') or d.get('district') or str(d)
            else:
                name = str(d)
            lines.append(f'• {name}')

        return '\n'.join(lines)


@giga_tool(
    few_shot_examples=[
        {'request': 'Расскажи про Невский район', 'params': {'district': 'Невский'}},
        {'request': 'Информация о Центральном районе', 'params': {'district': 'Центральный'}},
        {'request': 'Что за район Приморский?', 'params': {'district': 'Приморский'}},
    ]
)
@handle_api_errors
async def get_district_info(district: str) -> str:
    """
    Получить подробную информацию о районе Санкт-Петербурга.

    ВАЖНО: Принимает только НАЗВАНИЕ РАЙОНА, НЕ адрес!

    Args:
        district: Название РАЙОНА (не адрес!). Примеры: "Невский", "Центральный", "Приморский"

    Returns:
        Информация о районе (население, площадь, муниципалитеты)
    """
    logger.info('tool_call', tool='get_district_info', district=district)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_district_info_by_name(district_name=district)
        data = _extract_json(result)

        if not data:
            return f"Информация о районе '{district}' не найдена."

        lines = [f'📍 Район: {district}\n']

        if isinstance(data, dict):
            if 'population' in data:
                lines.append(f'👥 Население: {data["population"]}')
            if 'area' in data:
                lines.append(f'📐 Площадь: {data["area"]} км²')
            if 'municipalities' in data:
                munis = data['municipalities']
                if munis:
                    lines.append(f'🏘 Муниципальные образования: {len(munis)}')

        return '\n'.join(lines) if len(lines) > 1 else str(data)


@giga_tool(
    few_shot_examples=[
        {'request': 'В каком районе Невский 10?', 'params': {'address': 'Невский проспект 10'}},
        {'request': 'Какой район у адреса Садовая 50?', 'params': {'address': 'Садовая 50'}},
    ]
)
@handle_api_errors
async def get_district_info_by_address(address: str) -> str:
    """
    Определить район по адресу и получить информацию о нём.

    Args:
        address: АДРЕС (улица + дом). Примеры: "Невский проспект 1", "Садовая 50"

    Returns:
        Информация о районе, в котором находится адрес
    """
    logger.info('tool_call', tool='get_district_info_by_address', address=address)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_district_info_by_building(address_query=address)
        data = _extract_json(result)

        if not data:
            return f"Район для адреса '{address}' не определён."

        if isinstance(data, dict):
            district_name = data.get('district') or data.get('name')
            if district_name:
                return f'Адрес «{address}» находится в {district_name} районе.'

        return f'Информация о районе: {data}'


# =============================================================================
# Location Resolution Tool (для уточнения адреса)
# =============================================================================


def _format_location_candidates(candidates: list[GeocodingResult], query: str) -> str:
    """Форматировать список кандидатов геокодирования."""
    if not candidates:
        return f"Локация '{query}' не найдена. Уточните адрес или станцию метро."

    if len(candidates) == 1:
        c = candidates[0]
        lines = [f'✅ Найдена локация: **{c.address}**']
        lines.append(f'📍 Координаты: {c.lat:.6f}, {c.lon:.6f}')
        if c.district:
            lines.append(f'🏘️ Район: {c.district}')
        lines.append(f'🔍 Источник: {c.source}')
        if c.building_id:
            lines.append(f'🆔 ID здания: {c.building_id}')
        return '\n'.join(lines)

    lines = [f'Найдено несколько вариантов для «{query}»:\n']
    for i, c in enumerate(candidates, 1):
        lines.append(f'{i}. 📍 **{c.address}**')
        if c.district:
            lines.append(f'   🏘️ Район: {c.district}')
        lines.append(f'   📌 Координаты: {c.lat:.6f}, {c.lon:.6f}')
        if c.building_id:
            lines.append(f'   🆔 ID: {c.building_id}')

    lines.append('\n💡 Уточните, какой вариант вам нужен.')
    return '\n'.join(lines)


@giga_tool(
    few_shot_examples=[
        {'request': 'Уточни адрес Невский 10', 'params': {'query': 'Невский 10'}},
        {'request': 'Какие координаты у метро Чернышевская?', 'params': {'query': 'метро Чернышевская'}},
        {'request': 'Найди координаты Садовая 50', 'params': {'query': 'Садовая 50'}},
        {'request': 'Где находится улица Большевиков 68?', 'params': {'query': 'Большевиков 68'}},
    ]
)
@handle_api_errors
async def resolve_location(query: str, limit: int = 5) -> str:
    """
    Уточнить адрес или станцию метро и получить координаты.

    Используй эту функцию когда:
    - Нужно получить точные координаты адреса или метро
    - Пользователь указал неточный адрес и нужно предложить варианты
    - Перед вызовом инструментов, требующих координаты

    Args:
        query: Адрес или станция метро. Примеры: "Невский 10", "метро Чернышевская", "Садовая 50"
        limit: Максимальное количество кандидатов (по умолчанию 5)

    Returns:
        Информация о найденной локации с координатами или список кандидатов для выбора
    """
    limit = max(1, min(limit, 10))
    logger.info('tool_call', tool='resolve_location', query=query, limit=limit)

    candidates = await geocode_address_with_candidates(query, limit=limit)
    return _format_location_candidates(candidates, query)


# =============================================================================
# MFC Tools
# =============================================================================


def _format_mfc_list(data: Any, limit: int = 10, offset: int = 0) -> str:
    """Форматировать список МФЦ для чата с пагинацией."""
    if not data:
        return 'МФЦ не найдены.'

    mfc_list = data if isinstance(data, list) else data.get('data') or data.get('results') or [data]

    if not mfc_list:
        return 'МФЦ не найдены.'

    total = len(mfc_list)
    paginated = mfc_list[offset : offset + limit]

    if not paginated:
        return f'МФЦ не найдены (offset={offset} выходит за пределы списка из {total} элементов).'

    lines = []
    for i, mfc in enumerate(paginated, start=offset + 1):
        if isinstance(mfc, dict):
            name = mfc.get('name') or mfc.get('title') or 'МФЦ'
            address = mfc.get('address') or mfc.get('full_address') or ''
            phone = mfc.get('phone') or mfc.get('phones') or ''
            schedule = mfc.get('schedule') or mfc.get('work_time') or ''
            district = mfc.get('district') or ''

            lines.append(f'{i}. 🏛️ **{name}**')
            if address:
                lines.append(f'   📍 {address}')
            if district:
                lines.append(f'   🏘️ Район: {district}')
            if phone:
                lines.append(f'   📞 {phone}')
            if schedule:
                lines.append(f'   🕐 {schedule}')
        else:
            lines.append(f'{i}. {mfc}')

    # Информация о пагинации
    shown_end = offset + len(paginated)
    lines.append(f'\n📊 Показано {offset + 1}-{shown_end} из {total}')
    if shown_end < total:
        remaining = total - shown_end
        lines.append(f'💡 Ещё {remaining} МФЦ. Используйте offset={shown_end} для следующих.')

    return '\n'.join(lines)


@giga_tool(
    few_shot_examples=[
        {'request': 'Где ближайший МФЦ к Невскому 10?', 'params': {'address': 'Невский 10'}},
        {'request': 'МФЦ рядом с Садовой 50', 'params': {'address': 'Садовая 50'}},
        {
            'request': 'Найди МФЦ около моего дома на Большевиков 68',
            'params': {'address': 'Большевиков 68'},
        },
        {
            'request': 'Покажи все МФЦ рядом с Невским 10',
            'params': {'address': 'Невский 10', 'limit': 20},
        },
    ]
)
@handle_api_errors
async def find_nearest_mfc(address: str, limit: int = 5, offset: int = 0) -> str:
    """
    Найти ближайший МФЦ по адресу.

    Используй когда пользователь указал конкретный адрес и хочет найти МФЦ рядом.

    Args:
        address: Адрес для поиска (улица + дом). Примеры: "Невский 10", "Садовая 50"
        limit: Максимальное количество МФЦ в ответе (по умолчанию 5, максимум 30)
        offset: Смещение для пагинации (по умолчанию 0)

    Returns:
        Информация о ближайших МФЦ
    """
    limit = max(1, min(limit, 30))
    offset = max(0, offset)

    logger.info('tool_call', tool='find_nearest_mfc', address=address, limit=limit, offset=offset)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_mfc_nearest_by_coords(address_query=address, distance_km=5)
        data = _extract_json(result)

        if not data:
            result = await client.get_mfc_by_building(address_query=address)
            data = _extract_json(result)

        if not data:
            return f"МФЦ рядом с адресом '{address}' не найдены."

        return _format_mfc_list(data, limit=limit, offset=offset)


@giga_tool(
    few_shot_examples=[
        {'request': 'МФЦ в Невском районе', 'params': {'district': 'Невский'}},
        {'request': 'Какие МФЦ есть в Центральном районе?', 'params': {'district': 'Центральный'}},
        {'request': 'Список МФЦ Приморского района', 'params': {'district': 'Приморский'}},
        {'request': 'Все МФЦ Невского района', 'params': {'district': 'Невский', 'limit': 30}},
    ]
)
@handle_api_errors
async def get_mfc_by_district(district: str, limit: int = 10, offset: int = 0) -> str:
    """
    Получить список МФЦ в районе.

    ВАЖНО: Принимает только НАЗВАНИЕ РАЙОНА, НЕ адрес!
    Для поиска по адресу используй find_nearest_mfc.

    Args:
        district: Название РАЙОНА (не адрес!). Примеры: "Невский", "Центральный"
        limit: Максимальное количество МФЦ в ответе (по умолчанию 10, максимум 30)
        offset: Смещение для пагинации (по умолчанию 0)

    Returns:
        Список МФЦ в указанном районе
    """
    limit = max(1, min(limit, 30))
    offset = max(0, offset)
    logger.info('tool_call', tool='get_mfc_by_district', district=district, limit=limit, offset=offset)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_mfc_by_district(district=district)
        data = _extract_json(result)

        if not data:
            return f"МФЦ в районе '{district}' не найдены."

        return _format_mfc_list(data, limit=limit, offset=offset)


@giga_tool(
    few_shot_examples=[
        {'request': 'Список всех МФЦ СПб', 'params': {}},
        {'request': 'Сколько МФЦ в Петербурге?', 'params': {}},
    ]
)
@handle_api_errors
async def get_all_mfc() -> str:
    """
    Получить список всех МФЦ Санкт-Петербурга.

    Returns:
        Список всех МФЦ сгруппированных по районам
    """
    logger.info('tool_call', tool='get_all_mfc')

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_all_mfc()
        data = _extract_json(result)

        if not data:
            return 'Не удалось получить список МФЦ.'

        mfc_list = data if isinstance(data, list) else data.get('data') or []

        lines = [f'📋 Всего МФЦ: {len(mfc_list)}\n']

        by_district: dict[str, list] = {}
        for mfc in mfc_list:
            if isinstance(mfc, dict):
                district = mfc.get('district') or 'Другие'
                by_district.setdefault(district, []).append(mfc)

        for district, mfcs in sorted(by_district.items()):
            lines.append(f'\n**{district} район** ({len(mfcs)} МФЦ)')

        return '\n'.join(lines)


# =============================================================================
# Polyclinic Tools
# =============================================================================


def _format_polyclinics(data: Any, limit: int = 10, offset: int = 0) -> str:
    """Форматировать список поликлиник для чата с пагинацией."""
    if not data:
        return 'Поликлиники не найдены.'

    clinics = data if isinstance(data, list) else data.get('data') or data.get('results') or [data]

    if not clinics:
        return 'Поликлиники не найдены.'

    total = len(clinics)
    paginated = clinics[offset : offset + limit]

    if not paginated:
        return f'Поликлиники не найдены (offset={offset} выходит за пределы списка из {total} элементов).'

    lines = []
    for i, clinic in enumerate(paginated, start=offset + 1):
        if isinstance(clinic, dict):
            name = clinic.get('name') or clinic.get('title') or 'Поликлиника'
            address = clinic.get('address') or clinic.get('full_address') or ''
            phone = clinic.get('phone') or clinic.get('phones') or ''
            clinic_type = clinic.get('type') or clinic.get('clinic_type') or ''
            district = clinic.get('district') or ''

            lines.append(f'{i}. 🏥 **{name}**')
            if clinic_type:
                lines.append(f'   📋 Тип: {clinic_type}')
            if address:
                lines.append(f'   📍 {address}')
            if district:
                lines.append(f'   🏘️ Район: {district}')
            if phone:
                lines.append(f'   📞 {phone}')
        else:
            lines.append(f'{i}. {clinic}')

    # Информация о пагинации
    shown_end = offset + len(paginated)
    lines.append(f'\n📊 Показано {offset + 1}-{shown_end} из {total}')
    if shown_end < total:
        remaining = total - shown_end
        lines.append(f'💡 Ещё {remaining} поликлиник. Используйте offset={shown_end} для следующих.')

    return '\n'.join(lines)


@giga_tool(
    few_shot_examples=[
        {
            'request': 'К какой поликлинике я прикреплён по адресу Невский 10?',
            'params': {'address': 'Невский 10'},
        },
        {'request': 'Поликлиника для адреса Садовая 50', 'params': {'address': 'Садовая 50'}},
        {
            'request': 'Моя поликлиника, живу на Большевиков 68',
            'params': {'address': 'Большевиков 68'},
        },
        {
            'request': 'Покажи все поликлиники для адреса Невский 10',
            'params': {'address': 'Невский 10', 'limit': 20},
        },
    ]
)
@handle_api_errors
async def get_polyclinics_by_address(address: str, limit: int = 5, offset: int = 0) -> str:
    """
    Найти поликлиники, к которым прикреплён адрес.

    Используй когда пользователь хочет узнать свою поликлинику по месту прописки/жительства.

    Args:
        address: Адрес прописки (улица + дом). Примеры: "Невский 10", "Садовая 50"
        limit: Максимальное количество поликлиник в ответе (по умолчанию 5, максимум 30)
        offset: Смещение для пагинации (по умолчанию 0)

    Returns:
        Список поликлиник, к которым прикреплён дом
    """
    limit = max(1, min(limit, 30))
    offset = max(0, offset)

    logger.info('tool_call', tool='get_polyclinics_by_address', address=address, limit=limit, offset=offset)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_polyclinics_by_building(address_query=address)
        data = _extract_json(result)

        if not data:
            return f"Поликлиники для адреса '{address}' не найдены."

        return _format_polyclinics(data, limit=limit, offset=offset)


# =============================================================================
# School Tools
# =============================================================================


def _format_schools(data: Any, limit: int = 10, offset: int = 0) -> str:
    """Форматировать список школ для чата с пагинацией."""
    if not data:
        return 'Школы не найдены.'

    schools = data if isinstance(data, list) else data.get('data') or data.get('results') or [data]

    if not schools:
        return 'Школы не найдены.'

    total = len(schools)
    paginated = schools[offset : offset + limit]

    if not paginated:
        return f'Школы не найдены (offset={offset} выходит за пределы списка из {total} элементов).'

    lines = []
    for i, school in enumerate(paginated, start=offset + 1):
        if isinstance(school, dict):
            name = school.get('name') or school.get('title') or school.get('short_name') or 'Школа'
            address = school.get('address') or school.get('full_address') or ''
            phone = school.get('phone') or school.get('phones') or ''
            school_type = school.get('type') or school.get('org_type') or ''
            district = school.get('district') or ''

            lines.append(f'{i}. 🏫 **{name}**')
            if school_type:
                lines.append(f'   📋 Тип: {school_type}')
            if address:
                lines.append(f'   📍 {address}')
            if district:
                lines.append(f'   🏘️ Район: {district}')
            if phone:
                lines.append(f'   📞 {phone}')
        else:
            lines.append(f'{i}. {school}')

    # Информация о пагинации
    shown_end = offset + len(paginated)
    lines.append(f'\n📊 Показано {offset + 1}-{shown_end} из {total}')
    if shown_end < total:
        remaining = total - shown_end
        lines.append(f'💡 Ещё {remaining} школ. Используйте offset={shown_end} для следующих.')

    return '\n'.join(lines)


@giga_tool(
    few_shot_examples=[
        {
            'request': 'К какой школе прикреплён адрес Невский 10?',
            'params': {'address': 'Невский 10'},
        },
        {'request': 'Школа по прописке Садовая 50', 'params': {'address': 'Садовая 50'}},
        {
            'request': 'В какую школу идти ребёнку, живём на Большевиков 68',
            'params': {'address': 'Большевиков 68'},
        },
        {
            'request': 'Покажи все школы для адреса Невский 10',
            'params': {'address': 'Невский 10', 'limit': 20},
        },
    ]
)
@handle_api_errors
async def get_schools_by_address(address: str, limit: int = 5, offset: int = 0) -> str:
    """
    Найти школы, к которым прикреплён адрес по месту прописки.

    Используй когда пользователь хочет узнать, в какую школу может поступить ребёнок по прописке.

    Args:
        address: Адрес прописки (улица + дом). Примеры: "Невский 10", "Садовая 50"
        limit: Максимальное количество школ в ответе (по умолчанию 5, максимум 50)
        offset: Смещение для пагинации (по умолчанию 0)

    Returns:
        Список школ, к которым прикреплён дом
    """
    limit = max(1, min(limit, 50))
    offset = max(0, offset)

    logger.info('tool_call', tool='get_schools_by_address', address=address, limit=limit, offset=offset)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_linked_schools(address_query=address)
        data = _extract_json(result)

        if not data:
            return f"Школы для адреса '{address}' не найдены."

        return _format_schools(data, limit=limit, offset=offset)


@giga_tool(
    few_shot_examples=[
        {'request': 'Школы в Невском районе', 'params': {'district': 'Невский'}},
        {
            'request': 'Какие школы есть в Центральном районе?',
            'params': {'district': 'Центральный'},
        },
        {'request': 'Список школ Приморского района', 'params': {'district': 'Приморский'}},
        {'request': 'Все школы Невского района', 'params': {'district': 'Невский', 'limit': 50}},
    ]
)
@handle_api_errors
async def get_schools_in_district(district: str, limit: int = 10, offset: int = 0) -> str:
    """
    Найти школы в районе.

    ВАЖНО: Принимает только НАЗВАНИЕ РАЙОНА, НЕ адрес!
    Для поиска по адресу используй get_schools_by_address.

    Args:
        district: Название РАЙОНА (не адрес!). Примеры: "Невский", "Центральный"
        limit: Максимальное количество школ в ответе (по умолчанию 10, максимум 50)
        offset: Смещение для пагинации (по умолчанию 0)

    Returns:
        Список школ в указанном районе
    """
    limit = max(1, min(limit, 50))
    offset = max(0, offset)

    logger.info('tool_call', tool='get_schools_in_district', district=district, limit=limit, offset=offset)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_schools_map(district=district)
        data = _extract_json(result)

        if not data:
            return f"Школы в районе '{district}' не найдены."

        return _format_schools(data, limit=limit, offset=offset)


@giga_tool(
    few_shot_examples=[
        {'request': 'Информация о школе с ID 123', 'params': {'school_id': 123}},
        {'request': 'Подробности о школе номер 456', 'params': {'school_id': 456}},
    ]
)
@handle_api_errors
async def get_school_by_id(school_id: int) -> str:
    """
    Получить информацию о школе по ID.

    Args:
        school_id: ID школы (число)

    Returns:
        Подробная информация о школе
    """
    logger.info('tool_call', tool='get_school_by_id', school_id=school_id)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_school_by_id(school_id=school_id)
        data = _extract_json(result)

        if not data:
            return f'Школа с ID {school_id} не найдена.'

        return _format_schools([data])


# =============================================================================
# Management Company Tools
# =============================================================================


@giga_tool(
    few_shot_examples=[
        {'request': 'Какая УК у дома Невский 10?', 'params': {'address': 'Невский 10'}},
        {
            'request': 'Управляющая компания по адресу Садовая 50',
            'params': {'address': 'Садовая 50'},
        },
        {
            'request': 'Кто управляет домом на Большевиков 68?',
            'params': {'address': 'Большевиков 68'},
        },
    ]
)
@handle_api_errors
async def get_management_company(address: str) -> str:
    """
    Найти управляющую компанию по адресу.

    Используй когда пользователь хочет узнать, какая УК обслуживает его дом.

    Args:
        address: Адрес дома (улица + дом). Примеры: "Невский 10", "Садовая 50"

    Returns:
        Информация об УК для указанного дома
    """
    logger.info('tool_call', tool='get_management_company', address=address)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_management_company(address_query=address)
        data = _extract_json(result)

        if not data:
            return f"Управляющая компания для адреса '{address}' не найдена."

        if isinstance(data, dict):
            name = data.get('name') or data.get('company_name') or 'УК'
            inn = data.get('inn') or ''
            address_uk = data.get('address') or data.get('legal_address') or ''
            phone = data.get('phone') or data.get('phones') or ''

            lines = [f'🏢 **{name}**']
            if inn:
                lines.append(f'   ИНН: {inn}')
            if address_uk:
                lines.append(f'   📍 {address_uk}')
            if phone:
                lines.append(f'   📞 {phone}')

            return '\n'.join(lines)

        return str(data)


# =============================================================================
# Kindergarten Tools
# =============================================================================


@giga_tool(
    few_shot_examples=[
        {'request': 'Детские сады в Невском районе', 'params': {'district': 'Невский'}},
        {
            'request': 'Какие есть детсады в Центральном районе?',
            'params': {'district': 'Центральный'},
        },
        {
            'request': 'Покажи все садики в Приморском районе',
            'params': {'district': 'Приморский', 'limit': 50},
        },
        {
            'request': 'Следующие 10 садов в Невском районе',
            'params': {'district': 'Невский', 'offset': 10},
        },
    ]
)
@handle_api_errors
async def get_kindergartens_by_district(district: str, limit: int = 10, offset: int = 0) -> str:
    """
    Найти детские сады в районе.

    ВАЖНО: Принимает только НАЗВАНИЕ РАЙОНА, НЕ адрес!

    Args:
        district: Название РАЙОНА (не адрес!). Примеры: "Невский", "Центральный"
        limit: Максимальное количество садов в ответе (по умолчанию 10, максимум 50)
        offset: Смещение для пагинации (по умолчанию 0)

    Returns:
        Список детских садов в указанном районе
    """
    # Ограничиваем limit и offset разумными значениями
    limit = max(1, min(limit, 50))
    offset = max(0, offset)

    logger.info('tool_call', tool='get_kindergartens_by_district', district=district, limit=limit, offset=offset)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_dou(district=district)
        data = _extract_json(result)

        if not data:
            return f"Детские сады в районе '{district}' не найдены."

        kinders = data if isinstance(data, list) else data.get('data') or [data]
        total = len(kinders)
        paginated = kinders[offset : offset + limit]

        if not paginated:
            return f'Детские сады не найдены (offset={offset} выходит за пределы списка из {total} элементов).'

        lines = [f'👶 Детские сады в {district} районе:\n']
        for i, k in enumerate(paginated, start=offset + 1):
            if isinstance(k, dict):
                # API возвращает doo_short, sum (свободные места), coordinates
                name = k.get('doo_short') or k.get('name') or k.get('title') or 'Детский сад'
                spots = k.get('sum')  # свободные места
                status = k.get('doo_status')
                building_id = k.get('building_id')

                lines.append(f'{i}. 🏫 **{name}**')
                if spots is not None:
                    lines.append(f'   🪑 Свободных мест: {spots}')
                if status:
                    lines.append(f'   📋 Статус: {status}')
                if building_id:
                    lines.append(f'   🆔 ID: {building_id}')
            else:
                lines.append(f'{i}. {k}')

        # Информация о пагинации
        shown_end = offset + len(paginated)
        lines.append(f'\n📊 Показано {offset + 1}-{shown_end} из {total}')
        if shown_end < total:
            remaining = total - shown_end
            lines.append(f'💡 Ещё {remaining} садов. Используйте offset={shown_end} для следующих.')

        return '\n'.join(lines)


# =============================================================================
# Pet Tools
# =============================================================================


@giga_tool(
    few_shot_examples=[
        {
            'request': 'Где площадки для выгула собак рядом с координатами 59.93, 30.33?',
            'params': {'lat': 59.93, 'lon': 30.33, 'radius_km': 5.0},
        },
        {
            'request': 'Площадки для собак около Невского',
            'params': {'lat': 59.9343, 'lon': 30.3351, 'radius_km': 5.0},
        },
        {
            'request': 'Покажи все площадки для собак',
            'params': {'lat': 59.9343, 'lon': 30.3351, 'limit': 20},
        },
    ]
)
@handle_api_errors
async def get_pet_parks(lat: float, lon: float, radius_km: float = 5.0, limit: int = 10, offset: int = 0) -> str:
    """
    Найти площадки для выгула собак рядом с координатами.

    Args:
        lat: Широта (например: 59.9343)
        lon: Долгота (например: 30.3351)
        radius_km: Радиус поиска в километрах (по умолчанию 5)
        limit: Максимальное количество в ответе (по умолчанию 10, максимум 30)
        offset: Смещение для пагинации (по умолчанию 0)

    Returns:
        Список площадок для выгула собак
    """
    from langgraph_app.tools.formatters_v2 import format_pet_parks_list

    limit = max(1, min(limit, 30))
    offset = max(0, offset)

    logger.info('tool_call', tool='get_pet_parks', lat=lat, lon=lon, radius_km=radius_km, limit=limit, offset=offset)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_pet_parks(lat=lat, lon=lon, radius_km=int(radius_km))
        data = _extract_json(result)

        if not data:
            return 'Площадки для выгула не найдены.'

        parks = data.get('data', [])
        return format_pet_parks_list(parks, limit=limit, offset=offset)


@giga_tool(
    few_shot_examples=[
        {
            'request': 'Ветеринарные клиники рядом с координатами 59.93, 30.33',
            'params': {'lat': 59.93, 'lon': 30.33, 'radius_km': 10.0},
        },
        {
            'request': 'Где ветклиника рядом?',
            'params': {'lat': 59.9343, 'lon': 30.3351, 'radius_km': 10.0},
        },
        {
            'request': 'Все ветклиники поблизости',
            'params': {'lat': 59.9343, 'lon': 30.3351, 'limit': 20},
        },
    ]
)
@handle_api_errors
async def get_vet_clinics(lat: float, lon: float, radius_km: float = 10.0, limit: int = 10, offset: int = 0) -> str:
    """
    Найти ближайшие ветеринарные клиники.

    Args:
        lat: Широта
        lon: Долгота
        radius_km: Радиус поиска в километрах (по умолчанию 10)
        limit: Максимальное количество в ответе (по умолчанию 10, максимум 30)
        offset: Смещение для пагинации (по умолчанию 0)

    Returns:
        Список ветеринарных клиник
    """
    from langgraph_app.tools.formatters_v2 import format_vet_clinics_list

    limit = max(1, min(limit, 30))
    offset = max(0, offset)

    logger.info('tool_call', tool='get_vet_clinics', lat=lat, lon=lon, radius_km=radius_km, limit=limit, offset=offset)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_vet_clinics(lat=lat, lon=lon, radius_km=int(radius_km))
        data = _extract_json(result)

        if not data:
            return 'Ветклиники не найдены.'

        clinics = data.get('data', [])
        return format_vet_clinics_list(clinics, limit=limit, offset=offset)


@giga_tool(
    few_shot_examples=[
        {
            'request': 'Приюты для животных рядом',
            'params': {'lat': 59.93, 'lon': 30.33, 'radius_km': 10.0},
        },
        {
            'request': 'Где приют для собак?',
            'params': {'lat': 59.9343, 'lon': 30.3351, 'radius_km': 10.0},
        },
        {
            'request': 'Все приюты в городе',
            'params': {'lat': 59.9343, 'lon': 30.3351, 'limit': 20},
        },
    ]
)
@handle_api_errors
async def get_pet_shelters(lat: float, lon: float, radius_km: float = 10.0, limit: int = 10, offset: int = 0) -> str:
    """
    Найти приюты для животных.

    Args:
        lat: Широта
        lon: Долгота
        radius_km: Радиус поиска в километрах (по умолчанию 10)
        limit: Максимальное количество в ответе (по умолчанию 10, максимум 30)
        offset: Смещение для пагинации (по умолчанию 0)

    Returns:
        Список приютов с информацией о посещении
    """
    from langgraph_app.tools.formatters_v2 import format_shelters_list

    limit = max(1, min(limit, 30))
    offset = max(0, offset)

    logger.info('tool_call', tool='get_pet_shelters', lat=lat, lon=lon, radius_km=radius_km, limit=limit, offset=offset)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_mypets_shelters(lat=lat, lon=lon, radius_km=int(radius_km))
        data = _extract_json(result)

        if not data:
            return 'Приюты не найдены.'

        shelters = data.get('data', [])
        return format_shelters_list(shelters, limit=limit, offset=offset)


# =============================================================================
# Address-based Pet Tools (принимают location вместо координат)
# =============================================================================


@giga_tool(
    few_shot_examples=[
        {
            'request': 'Площадки для выгула собак около метро Чернышевская',
            'params': {'location': 'метро Чернышевская', 'radius_km': 5.0},
        },
        {
            'request': 'Где погулять с собакой рядом с Невским 10?',
            'params': {'location': 'Невский 10', 'radius_km': 5.0},
        },
        {
            'request': 'Площадки для собак у метро Площадь Восстания',
            'params': {'location': 'метро Площадь Восстания'},
        },
        {
            'request': 'Где выгулять собаку около Садовой?',
            'params': {'location': 'Садовая', 'radius_km': 3.0},
        },
    ]
)
@handle_api_errors
async def get_pet_parks_near(
    location: str, radius_km: float = 5.0, limit: int = 10, offset: int = 0
) -> str:
    """
    Найти площадки для выгула собак рядом с адресом или станцией метро.

    РЕКОМЕНДУЕТСЯ использовать эту функцию вместо get_pet_parks, так как
    пользователи обычно указывают адреса, а не координаты.

    Args:
        location: Адрес или станция метро. Примеры: "Невский 10", "метро Чернышевская"
        radius_km: Радиус поиска в километрах (по умолчанию 5)
        limit: Максимальное количество в ответе (по умолчанию 10, максимум 30)
        offset: Смещение для пагинации (по умолчанию 0)

    Returns:
        Список площадок для выгула собак
    """
    from langgraph_app.tools.formatters_v2 import format_pet_parks_list

    limit = max(1, min(limit, 30))
    offset = max(0, offset)

    logger.info('tool_call', tool='get_pet_parks_near', location=location, radius_km=radius_km, limit=limit, offset=offset)

    # Геокодируем адрес
    geo_result = await geocode_address(location)
    if not geo_result:
        return f"Не удалось определить координаты для '{location}'. Уточните адрес или станцию метро."

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_pet_parks(lat=geo_result.lat, lon=geo_result.lon, radius_km=int(radius_km))
        data = _extract_json(result)

        if not data:
            return f'Площадки для выгула рядом с «{geo_result.address}» не найдены.'

        parks = data.get('data', [])
        formatted = format_pet_parks_list(parks, limit=limit, offset=offset)
        return f'📍 Поиск от: {geo_result.address}\n\n{formatted}'


@giga_tool(
    few_shot_examples=[
        {
            'request': 'Ветклиника около метро Пионерская',
            'params': {'location': 'метро Пионерская', 'radius_km': 10.0},
        },
        {
            'request': 'Где ветеринар рядом с Большевиков 68?',
            'params': {'location': 'Большевиков 68'},
        },
        {
            'request': 'Ветеринарные клиники у Садовой',
            'params': {'location': 'Садовая', 'radius_km': 5.0},
        },
    ]
)
@handle_api_errors
async def get_vet_clinics_near(
    location: str, radius_km: float = 10.0, limit: int = 10, offset: int = 0
) -> str:
    """
    Найти ветеринарные клиники рядом с адресом или станцией метро.

    РЕКОМЕНДУЕТСЯ использовать эту функцию вместо get_vet_clinics, так как
    пользователи обычно указывают адреса, а не координаты.

    Args:
        location: Адрес или станция метро. Примеры: "Невский 10", "метро Пионерская"
        radius_km: Радиус поиска в километрах (по умолчанию 10)
        limit: Максимальное количество в ответе (по умолчанию 10, максимум 30)
        offset: Смещение для пагинации (по умолчанию 0)

    Returns:
        Список ветеринарных клиник
    """
    from langgraph_app.tools.formatters_v2 import format_vet_clinics_list

    limit = max(1, min(limit, 30))
    offset = max(0, offset)

    logger.info('tool_call', tool='get_vet_clinics_near', location=location, radius_km=radius_km, limit=limit, offset=offset)

    geo_result = await geocode_address(location)
    if not geo_result:
        return f"Не удалось определить координаты для '{location}'. Уточните адрес или станцию метро."

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_vet_clinics(lat=geo_result.lat, lon=geo_result.lon, radius_km=int(radius_km))
        data = _extract_json(result)

        if not data:
            return f'Ветклиники рядом с «{geo_result.address}» не найдены.'

        clinics = data.get('data', [])
        formatted = format_vet_clinics_list(clinics, limit=limit, offset=offset)
        return f'📍 Поиск от: {geo_result.address}\n\n{formatted}'


@giga_tool(
    few_shot_examples=[
        {
            'request': 'Приюты для животных около метро Купчино',
            'params': {'location': 'метро Купчино', 'radius_km': 10.0},
        },
        {
            'request': 'Где приют для кошек рядом с Невским?',
            'params': {'location': 'Невский проспект'},
        },
    ]
)
@handle_api_errors
async def get_pet_shelters_near(
    location: str, radius_km: float = 10.0, limit: int = 10, offset: int = 0
) -> str:
    """
    Найти приюты для животных рядом с адресом или станцией метро.

    РЕКОМЕНДУЕТСЯ использовать эту функцию вместо get_pet_shelters, так как
    пользователи обычно указывают адреса, а не координаты.

    Args:
        location: Адрес или станция метро. Примеры: "метро Купчино", "Невский 10"
        radius_km: Радиус поиска в километрах (по умолчанию 10)
        limit: Максимальное количество в ответе (по умолчанию 10, максимум 30)
        offset: Смещение для пагинации (по умолчанию 0)

    Returns:
        Список приютов с информацией о посещении
    """
    from langgraph_app.tools.formatters_v2 import format_shelters_list

    limit = max(1, min(limit, 30))
    offset = max(0, offset)

    logger.info('tool_call', tool='get_pet_shelters_near', location=location, radius_km=radius_km, limit=limit, offset=offset)

    geo_result = await geocode_address(location)
    if not geo_result:
        return f"Не удалось определить координаты для '{location}'. Уточните адрес или станцию метро."

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_mypets_shelters(lat=geo_result.lat, lon=geo_result.lon, radius_km=int(radius_km))
        data = _extract_json(result)

        if not data:
            return f'Приюты рядом с «{geo_result.address}» не найдены.'

        shelters = data.get('data', [])
        formatted = format_shelters_list(shelters, limit=limit, offset=offset)
        return f'📍 Поиск от: {geo_result.address}\n\n{formatted}'


# =============================================================================
# Events Tools
# =============================================================================


@giga_tool(
    few_shot_examples=[
        {
            'request': 'Какие мероприятия проходят рядом?',
            'params': {'lat': 59.93, 'lon': 30.33, 'radius_km': 10.0, 'count': 5},
        },
        {
            'request': 'Что интересного в городе сегодня?',
            'params': {'lat': 59.9343, 'lon': 30.3351, 'radius_km': 10.0, 'count': 5},
        },
    ]
)
@handle_api_errors
async def get_city_events(
    lat: float,
    lon: float,
    radius_km: float = 10.0,
    limit: int = 10,
    offset: int = 0,
) -> str:
    """
    Найти мероприятия в городе рядом с указанными координатами.

    Args:
        lat: Широта
        lon: Долгота
        radius_km: Радиус поиска в километрах
        limit: Максимальное количество в ответе (по умолчанию 10, максимум 30)
        offset: Смещение для пагинации (по умолчанию 0)

    Returns:
        Список мероприятий с датами и местами проведения
    """
    from datetime import datetime, timedelta

    from langgraph_app.tools.formatters_v2 import format_events_list

    limit = max(1, min(limit, 30))
    offset = max(0, offset)

    logger.info('tool_call', tool='get_city_events', lat=lat, lon=lon, limit=limit, offset=offset)

    start_date = datetime.now()
    end_date = start_date + timedelta(days=30)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_events(
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            lat=lat,
            lon=lon,
            radius_km=int(radius_km),
            count=100,  # запрашиваем больше для пагинации
        )
        data = _extract_json(result)

        if not data:
            return 'Мероприятия не найдены.'

        events = data.get('data', [])
        return format_events_list(events, limit=limit, offset=offset)


@giga_tool(
    few_shot_examples=[
        {
            'request': 'Мероприятия около метро Невский проспект',
            'params': {'location': 'метро Невский проспект', 'radius_km': 10.0},
        },
        {
            'request': 'Что интересного рядом с Садовой 50?',
            'params': {'location': 'Садовая 50'},
        },
        {
            'request': 'События у метро Чернышевская',
            'params': {'location': 'метро Чернышевская', 'radius_km': 5.0},
        },
    ]
)
@handle_api_errors
async def get_city_events_near(
    location: str,
    radius_km: float = 10.0,
    limit: int = 10,
    offset: int = 0,
) -> str:
    """
    Найти мероприятия в городе рядом с адресом или станцией метро.

    РЕКОМЕНДУЕТСЯ использовать эту функцию вместо get_city_events, так как
    пользователи обычно указывают адреса, а не координаты.

    Args:
        location: Адрес или станция метро. Примеры: "метро Невский", "Садовая 50"
        radius_km: Радиус поиска в километрах
        limit: Максимальное количество в ответе (по умолчанию 10, максимум 30)
        offset: Смещение для пагинации (по умолчанию 0)

    Returns:
        Список мероприятий с датами и местами проведения
    """
    from datetime import datetime, timedelta

    from langgraph_app.tools.formatters_v2 import format_events_list

    limit = max(1, min(limit, 30))
    offset = max(0, offset)

    logger.info('tool_call', tool='get_city_events_near', location=location, limit=limit, offset=offset)

    geo_result = await geocode_address(location)
    if not geo_result:
        return f"Не удалось определить координаты для '{location}'. Уточните адрес или станцию метро."

    start_date = datetime.now()
    end_date = start_date + timedelta(days=30)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_events(
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            lat=geo_result.lat,
            lon=geo_result.lon,
            radius_km=int(radius_km),
            count=100,
        )
        data = _extract_json(result)

        if not data:
            return f'Мероприятия рядом с «{geo_result.address}» не найдены.'

        events = data.get('data', [])
        formatted = format_events_list(events, limit=limit, offset=offset)
        return f'📍 Поиск от: {geo_result.address}\n\n{formatted}'


@giga_tool(
    few_shot_examples=[
        {
            'request': 'Спортивные соревнования в Невском районе',
            'params': {'district': 'Невский'},
        },
        {
            'request': 'Какие спортивные события в СПб?',
            'params': {'district': 'Центральный'},
        },
        {
            'request': 'Все спортивные мероприятия в Невском',
            'params': {'district': 'Невский', 'limit': 20},
        },
    ]
)
@handle_api_errors
async def get_sport_events(district: str, limit: int = 10, offset: int = 0) -> str:
    """
    Найти спортивные мероприятия в районе.

    Args:
        district: Название района (например: "Кировский", "Невский")
        limit: Максимальное количество в ответе (по умолчанию 10, максимум 30)
        offset: Смещение для пагинации (по умолчанию 0)

    Returns:
        Список спортивных мероприятий
    """
    from langgraph_app.tools.formatters_v2 import format_sport_events_list

    limit = max(1, min(limit, 30))
    offset = max(0, offset)

    logger.info('tool_call', tool='get_sport_events', district=district, limit=limit, offset=offset)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_sport_events(district=district, count=100)  # запрашиваем больше
        data = _extract_json(result)

        if not data:
            return f'Спортивные мероприятия в {district} районе не найдены.'

        inner = data.get('data', {})
        events = inner.get('data', []) if isinstance(inner, dict) else []
        return format_sport_events_list(events, limit=limit, offset=offset)


# =============================================================================
# Pensioner Tools
# =============================================================================


@giga_tool(
    few_shot_examples=[
        {
            'request': 'Услуги для пенсионеров в Невском районе',
            'params': {'district': 'Невский', 'count': 5},
        },
        {'request': 'Что есть для пожилых?', 'params': {'district': 'Центральный', 'count': 5}},
    ]
)
@handle_api_errors
async def get_pensioner_services(district: str, count: int = 5) -> str:
    """
    Найти занятия и услуги для пенсионеров в районе.

    Args:
        district: Название района (например: "Кировский", "Центральный")
        count: Количество результатов

    Returns:
        Список занятий (танцы, вокал, клубы по интересам и т.д.)
    """
    from langgraph_app.tools.formatters_v2 import format_pensioner_services_list

    logger.info('tool_call', tool='get_pensioner_services', district=district)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_pensioner_services(district=district, count=count)
        data = _extract_json(result)

        if not data:
            return f'Услуги для пенсионеров в {district} районе не найдены.'

        services = data.get('data', [])
        return format_pensioner_services_list(services)


@giga_tool(
    few_shot_examples=[
        {
            'request': 'Горячие линии для пенсионеров в Невском районе',
            'params': {'district': 'Невский'},
        },
        {'request': 'Куда позвонить пожилому человеку?', 'params': {'district': 'Центральный'}},
    ]
)
@handle_api_errors
async def get_pensioner_hotlines(district: str) -> str:
    """
    Получить горячие линии для пенсионеров в районе.

    Args:
        district: Название района

    Returns:
        Телефоны горячих линий
    """
    logger.info('tool_call', tool='get_pensioner_hotlines', district=district)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_pensioner_hotlines_by_district(district=district)
        data = _extract_json(result)

        if not data:
            return f'Горячие линии для {district} района не найдены.'

        lines = [f'📞 Горячие линии для пенсионеров ({district} район):\n']
        if isinstance(data, list):
            for item in data:
                if phone := item.get('phone'):
                    title = item.get('title', '')
                    lines.append(f'• {title}: {phone}')
        elif isinstance(data, dict):
            for key, value in data.items():
                lines.append(f'• {key}: {value}')

        return '\n'.join(lines) if len(lines) > 1 else 'Информация не найдена.'


# =============================================================================
# Sport Tools
# =============================================================================


@giga_tool(
    few_shot_examples=[
        {
            'request': 'Спортплощадки в Невском районе',
            'params': {'district': 'Невский', 'count': 5},
        },
        {'request': 'Где поиграть в баскетбол?', 'params': {'district': 'Центральный', 'count': 5}},
    ]
)
@handle_api_errors
async def get_sportgrounds(district: str, count: int = 5) -> str:
    """
    Найти спортивные площадки в районе.

    Args:
        district: Название района
        count: Количество результатов

    Returns:
        Список спортплощадок с видами спорта
    """
    from langgraph_app.tools.formatters_v2 import format_sportgrounds_list

    logger.info('tool_call', tool='get_sportgrounds', district=district)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_sportgrounds(district=district, count=count)
        data = _extract_json(result)

        if not data:
            return f'Спортплощадки в {district} районе не найдены.'

        grounds = data.get('data', [])
        return format_sportgrounds_list(grounds)


# =============================================================================
# Tourism Tools
# =============================================================================


@giga_tool(
    few_shot_examples=[
        {
            'request': 'Достопримечательности в Невском районе',
            'params': {'district': 'Невский', 'count': 5},
        },
        {'request': 'Что посмотреть туристу?', 'params': {'district': 'Центральный', 'count': 5}},
    ]
)
@handle_api_errors
async def get_beautiful_places(district: str, count: int = 5) -> str:
    """
    Найти достопримечательности в районе.

    Args:
        district: Название района
        count: Количество результатов

    Returns:
        Список достопримечательностей с описанием
    """
    from langgraph_app.tools.formatters_v2 import format_beautiful_places_list

    logger.info('tool_call', tool='get_beautiful_places', district=district)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_beautiful_places(district=district, count=count)
        data = _extract_json(result)

        if not data:
            return f'Достопримечательности в {district} районе не найдены.'

        places = data.get('data', [])
        return format_beautiful_places_list(places)


@giga_tool(
    few_shot_examples=[
        {'request': 'Туристические маршруты по городу', 'params': {'count': 5}},
        {'request': 'Пешеходные экскурсии СПб', 'params': {'count': 3}},
    ]
)
@handle_api_errors
async def get_tourist_routes(count: int = 5) -> str:
    """
    Найти туристические маршруты.

    Args:
        count: Количество результатов

    Returns:
        Список туристических маршрутов
    """
    logger.info('tool_call', tool='get_tourist_routes')

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_beautiful_place_routes(count=count)
        data = _extract_json(result)

        if not data:
            return 'Туристические маршруты не найдены.'

        routes = data.get('data', [])
        if not routes:
            return 'Туристические маршруты не найдены.'

        lines = [f'🗺️ Найдено маршрутов: {len(routes)}\n']
        for route in routes[:count]:
            place = route.get('place', route)
            lines.append(f'🚶 **{place.get("title", "Маршрут")}**')
            if desc := place.get('description'):
                short = desc[:150] + '...' if len(desc) > 150 else desc
                lines.append(f'   {short}')
            lines.append('')

        return '\n'.join(lines)


# =============================================================================
# Recycling Tools
# =============================================================================


@giga_tool(
    few_shot_examples=[
        {
            'request': 'Пункты сбора мусора рядом',
            'params': {'lat': 59.93, 'lon': 30.33, 'count': 5},
        },
        {
            'request': 'Где сдать раздельный мусор?',
            'params': {'lat': 59.9343, 'lon': 30.3351, 'count': 5},
        },
    ]
)
@handle_api_errors
async def get_recycling_points(lat: float, lon: float, count: int = 5) -> str:
    """
    Найти ближайшие пункты переработки отходов.

    Args:
        lat: Широта
        lon: Долгота
        count: Количество результатов

    Returns:
        Пункты приёма вторсырья по категориям
    """
    from langgraph_app.tools.formatters_v2 import format_recycling_by_category

    logger.info('tool_call', tool='get_recycling_points', lat=lat, lon=lon)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_recycling_nearest(lat=lat, lon=lon, count=count)
        data = _extract_json(result)

        if not data:
            return 'Пункты переработки не найдены.'

        categories = data.get('data', data) if isinstance(data, dict) else data
        return format_recycling_by_category(categories)


@giga_tool(
    few_shot_examples=[
        {
            'request': 'Пункты сбора мусора около метро Площадь Восстания',
            'params': {'location': 'метро Площадь Восстания', 'count': 5},
        },
        {
            'request': 'Где сдать вторсырье рядом с Невским 10?',
            'params': {'location': 'Невский 10'},
        },
        {
            'request': 'Раздельный сбор мусора у метро Чернышевская',
            'params': {'location': 'метро Чернышевская'},
        },
    ]
)
@handle_api_errors
async def get_recycling_points_near(location: str, count: int = 5) -> str:
    """
    Найти ближайшие пункты переработки отходов рядом с адресом или метро.

    РЕКОМЕНДУЕТСЯ использовать эту функцию вместо get_recycling_points, так как
    пользователи обычно указывают адреса, а не координаты.

    Args:
        location: Адрес или станция метро. Примеры: "метро Площадь Восстания", "Невский 10"
        count: Количество результатов

    Returns:
        Пункты приёма вторсырья по категориям
    """
    from langgraph_app.tools.formatters_v2 import format_recycling_by_category

    logger.info('tool_call', tool='get_recycling_points_near', location=location)

    geo_result = await geocode_address(location)
    if not geo_result:
        return f"Не удалось определить координаты для '{location}'. Уточните адрес или станцию метро."

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_recycling_nearest(lat=geo_result.lat, lon=geo_result.lon, count=count)
        data = _extract_json(result)

        if not data:
            return f'Пункты переработки рядом с «{geo_result.address}» не найдены.'

        categories = data.get('data', data) if isinstance(data, dict) else data
        formatted = format_recycling_by_category(categories)
        return f'📍 Поиск от: {geo_result.address}\n\n{formatted}'


# =============================================================================
# Infrastructure Tools
# =============================================================================


@giga_tool(
    few_shot_examples=[
        {'request': 'Отключения воды по зданию 12345', 'params': {'building_id': 12345}},
        {'request': 'Когда отключат отопление в моём доме?', 'params': {'building_id': 67890}},
        {'request': 'Все отключения для дома', 'params': {'building_id': 12345, 'limit': 20}},
    ]
)
@handle_api_errors
async def get_disconnections(building_id: int, limit: int = 10, offset: int = 0) -> str:
    """
    Проверить отключения воды/электричества по зданию.

    Args:
        building_id: ID здания из системы YAZZH
        limit: Максимальное количество в ответе (по умолчанию 10, максимум 30)
        offset: Смещение для пагинации (по умолчанию 0)

    Returns:
        Информация об отключениях или "отключений нет"
    """
    from langgraph_app.tools.formatters_v2 import format_disconnections_list

    limit = max(1, min(limit, 30))
    offset = max(0, offset)

    logger.info('tool_call', tool='get_disconnections', building_id=building_id, limit=limit, offset=offset)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_disconnections(building_id=str(building_id))
        data = _extract_json(result)

        if result.get('status_code') == 204 or not data:
            return '✅ Отключений не запланировано. Всё работает!'

        discs = data if isinstance(data, list) else data.get('data', [])
        return format_disconnections_list(discs, limit=limit, offset=offset)


@giga_tool(
    few_shot_examples=[
        {
            'request': 'Дорожные работы в Невском районе',
            'params': {'district': 'Невский', 'count': 10},
        },
        {'request': 'Где ремонтируют дороги?', 'params': {'district': 'Центральный', 'count': 5}},
    ]
)
@handle_api_errors
async def get_road_works(district: str, count: int = 10) -> str:
    """
    Получить информацию о дорожных работах в районе.

    Args:
        district: Название района
        count: Количество результатов

    Returns:
        Список дорожных работ по типам
    """
    from langgraph_app.tools.formatters_v2 import format_road_works_list

    logger.info('tool_call', tool='get_road_works', district=district)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_gati_orders_map(district=district, count=count)
        data = _extract_json(result)

        if not data:
            return f'Информация о дорожных работах в {district} районе не найдена.'

        works = data.get('data', [])
        return format_road_works_list(works)


# =============================================================================
# Export all tools
# =============================================================================

ALL_TOOLS_GIGA = [
    # Geo / Address / Location
    search_address,
    resolve_location,  # NEW: уточнение адреса с кандидатами
    get_districts_list,
    get_district_info,
    get_district_info_by_address,
    # MFC
    find_nearest_mfc,
    get_mfc_by_district,
    get_all_mfc,
    # Polyclinics
    get_polyclinics_by_address,
    # Schools
    get_schools_by_address,
    get_schools_in_district,
    get_school_by_id,
    # Management Company
    get_management_company,
    # Kindergartens
    get_kindergartens_by_district,
    # Pets (address-based RECOMMENDED)
    get_pet_parks_near,      # NEW: по адресу/метро
    get_vet_clinics_near,    # NEW: по адресу/метро
    get_pet_shelters_near,   # NEW: по адресу/метро
    get_pet_parks,           # координатная версия (legacy)
    get_vet_clinics,         # координатная версия (legacy)
    get_pet_shelters,        # координатная версия (legacy)
    # Events (address-based RECOMMENDED)
    get_city_events_near,    # NEW: по адресу/метро
    get_city_events,         # координатная версия (legacy)
    get_sport_events,
    # Pensioner
    get_pensioner_services,
    get_pensioner_hotlines,
    # Sport
    get_sportgrounds,
    # Tourism
    get_beautiful_places,
    get_tourist_routes,
    # Recycling (address-based RECOMMENDED)
    get_recycling_points_near,  # NEW: по адресу/метро
    get_recycling_points,       # координатная версия (legacy)
    # Infrastructure
    get_disconnections,
    get_road_works,
]

# Группировка по категориям для registry
TOOLS_BY_CATEGORY_GIGA = {
    'address': [search_address, resolve_location, get_district_info_by_address],
    'district': [get_districts_list, get_district_info],
    'mfc': [find_nearest_mfc, get_mfc_by_district, get_all_mfc],
    'polyclinic': [get_polyclinics_by_address],
    'school': [get_schools_by_address, get_schools_in_district, get_school_by_id],
    'management_company': [get_management_company],
    'kindergarten': [get_kindergartens_by_district],
    'pets': [get_pet_parks_near, get_vet_clinics_near, get_pet_shelters_near, get_pet_parks, get_vet_clinics, get_pet_shelters],
    'events': [get_city_events_near, get_city_events, get_sport_events],
    'pensioner': [get_pensioner_services, get_pensioner_hotlines],
    'sport': [get_sportgrounds],
    'tourism': [get_beautiful_places, get_tourist_routes],
    'recycling': [get_recycling_points_near, get_recycling_points],
    'infrastructure': [get_disconnections, get_road_works],
}

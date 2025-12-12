"""
LangChain Tools V3 — базовая версия для OpenRouter и других моделей.

Полностью async версия без nest_asyncio.
Использует стандартный @tool декоратор из langchain_core.
API: yazzh_final.ApiClientUnified (НЕ yazzh_new!)

Для GigaChat используйте city_tools_v3_giga.py с @giga_tool и few-shot examples.
"""

from __future__ import annotations

from functools import wraps
from typing import Any

import httpx
from langchain_core.tools import tool

from langgraph_app.api.yazzh_final import ApiClientUnified
from langgraph_app.logging_config import get_logger

logger = get_logger(__name__)

API_UNAVAILABLE_MESSAGE = (
    "⚠️ Сервис временно недоступен. Пожалуйста, попробуйте позже или обратитесь "
    "на портал «Я здесь живу»: https://yazzh.ru"
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
            logger.error("api_unavailable", tool=func.__name__, error=str(e))
            return API_UNAVAILABLE_MESSAGE
        except Exception as e:
            logger.error("tool_error", tool=func.__name__, error=str(e))
            return f"Ошибка при выполнении запроса: {e}"

    return wrapper


def _extract_json(result: dict[str, Any]) -> Any | None:
    """Извлечь JSON из результата API."""
    if result.get("status_code") != 200:
        return None
    return result.get("json")


# =============================================================================
# Address / Geo Tools
# =============================================================================


@tool
@handle_api_errors
async def search_address(query: str) -> str:
    """
    Найти адрес в Санкт-Петербурге по текстовому запросу.

    Используй когда нужно уточнить или проверить адрес пользователя.

    Args:
        query: Текстовый запрос (например: "Невский 10", "Большевиков 68 к1")

    Returns:
        Список найденных адресов или сообщение об ошибке
    """
    logger.info("tool_call", tool="search_address", query=query)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.search_building_full_text_search(query=query, count=5)
        data = _extract_json(result)

        if not data:
            return f"Адрес '{query}' не найден. Уточните запрос."

        # Данные могут быть списком или dict с ключом data/results
        buildings = data if isinstance(data, list) else data.get("data") or data.get("results") or []

        if not buildings:
            return f"Адрес '{query}' не найден. Уточните запрос."

        if len(buildings) == 1:
            b = buildings[0]
            return f"Найден адрес: {b.get('full_address', b.get('address', str(b)))}"

        lines = ["Найдено несколько адресов. Уточните, какой из них вам нужен:\n"]
        for i, b in enumerate(buildings[:5], 1):
            addr = b.get("full_address") or b.get("address") or str(b)
            lines.append(f"{i}. {addr}")

        return "\n".join(lines)


@tool
@handle_api_errors
async def get_districts_list() -> str:
    """
    Получить список всех районов Санкт-Петербурга.

    Используй для справки о районах города.

    Returns:
        Список районов СПб
    """
    logger.info("tool_call", tool="get_districts_list")

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_districts()
        data = _extract_json(result)

        if not data:
            return "Не удалось получить список районов."

        districts = data if isinstance(data, list) else data.get("data") or []

        lines = ["Районы Санкт-Петербурга:\n"]
        for d in districts:
            if isinstance(d, dict):
                name = d.get("name") or d.get("district") or str(d)
            else:
                name = str(d)
            lines.append(f"• {name}")

        return "\n".join(lines)


@tool
@handle_api_errors
async def get_district_info(district: str) -> str:
    """
    Получить подробную информацию о районе Санкт-Петербурга.

    Args:
        district: Название РАЙОНА (НЕ адрес!). Примеры: "Невский", "Центральный"

    Returns:
        Информация о районе
    """
    logger.info("tool_call", tool="get_district_info", district=district)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_district_info_by_name(district_name=district)
        data = _extract_json(result)

        if not data:
            return f"Информация о районе '{district}' не найдена."

        # Форматируем данные
        lines = [f"📍 Район: {district}\n"]

        if isinstance(data, dict):
            if "population" in data:
                lines.append(f"👥 Население: {data['population']}")
            if "area" in data:
                lines.append(f"📐 Площадь: {data['area']} км²")
            if "municipalities" in data:
                munis = data["municipalities"]
                if munis:
                    lines.append(f"🏘 Муниципальные образования: {len(munis)}")

        return "\n".join(lines) if len(lines) > 1 else str(data)


@tool
@handle_api_errors
async def get_district_info_by_address(address: str) -> str:
    """
    Определить район по адресу и получить информацию о нём.

    Args:
        address: АДРЕС (улица + дом). Примеры: "Невский проспект 1", "Садовая 50"

    Returns:
        Информация о районе, в котором находится адрес
    """
    logger.info("tool_call", tool="get_district_info_by_address", address=address)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_district_info_by_building(address_query=address)
        data = _extract_json(result)

        if not data:
            return f"Район для адреса '{address}' не определён."

        if isinstance(data, dict):
            district_name = data.get("district") or data.get("name")
            if district_name:
                return f"Адрес «{address}» находится в {district_name} районе."

        return f"Информация о районе: {data}"


# =============================================================================
# MFC Tools
# =============================================================================


def _format_mfc_list(data: Any) -> str:
    """Форматировать список МФЦ для чата."""
    if not data:
        return "МФЦ не найдены."

    mfc_list = data if isinstance(data, list) else data.get("data") or data.get("results") or [data]

    if not mfc_list:
        return "МФЦ не найдены."

    lines = []
    for mfc in mfc_list[:5]:  # Ограничиваем 5 результатами
        if isinstance(mfc, dict):
            name = mfc.get("name") or mfc.get("title") or "МФЦ"
            address = mfc.get("address") or mfc.get("full_address") or ""
            phone = mfc.get("phone") or mfc.get("phones") or ""
            schedule = mfc.get("schedule") or mfc.get("work_time") or ""

            lines.append(f"📋 **{name}**")
            if address:
                lines.append(f"   📍 {address}")
            if phone:
                lines.append(f"   📞 {phone}")
            if schedule:
                lines.append(f"   🕐 {schedule}")
            lines.append("")
        else:
            lines.append(str(mfc))

    return "\n".join(lines) if lines else "МФЦ не найдены."


@tool
@handle_api_errors
async def find_nearest_mfc(address: str) -> str:
    """
    Найти ближайший МФЦ по адресу.

    Args:
        address: Адрес для поиска (улица + дом). Примеры: "Невский 10", "Садовая 50"

    Returns:
        Информация о ближайших МФЦ
    """
    logger.info("tool_call", tool="find_nearest_mfc", address=address)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_mfc_nearest_by_coords(address_query=address, distance_km=5)
        data = _extract_json(result)

        if not data:
            # Попробуем получить МФЦ по зданию
            result = await client.get_mfc_by_building(address_query=address)
            data = _extract_json(result)

        if not data:
            return f"МФЦ рядом с адресом '{address}' не найдены."

        return _format_mfc_list(data)


@tool
@handle_api_errors
async def get_mfc_by_district(district: str) -> str:
    """
    Получить список МФЦ в районе.

    Args:
        district: Название РАЙОНА (НЕ адрес!). Примеры: "Невский", "Центральный"

    Returns:
        Список МФЦ в указанном районе
    """
    logger.info("tool_call", tool="get_mfc_by_district", district=district)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_mfc_by_district(district=district)
        data = _extract_json(result)

        if not data:
            return f"МФЦ в районе '{district}' не найдены."

        return _format_mfc_list(data)


@tool
@handle_api_errors
async def get_all_mfc() -> str:
    """
    Получить список всех МФЦ Санкт-Петербурга.

    Returns:
        Список всех МФЦ
    """
    logger.info("tool_call", tool="get_all_mfc")

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_all_mfc()
        data = _extract_json(result)

        if not data:
            return "Не удалось получить список МФЦ."

        mfc_list = data if isinstance(data, list) else data.get("data") or []

        lines = [f"📋 Всего МФЦ: {len(mfc_list)}\n"]

        # Группируем по районам
        by_district: dict[str, list] = {}
        for mfc in mfc_list:
            if isinstance(mfc, dict):
                district = mfc.get("district") or "Другие"
                by_district.setdefault(district, []).append(mfc)

        for district, mfcs in sorted(by_district.items()):
            lines.append(f"\n**{district} район** ({len(mfcs)} МФЦ)")

        return "\n".join(lines)


# =============================================================================
# Polyclinic Tools
# =============================================================================


def _format_polyclinics(data: Any) -> str:
    """Форматировать список поликлиник для чата."""
    if not data:
        return "Поликлиники не найдены."

    clinics = data if isinstance(data, list) else data.get("data") or data.get("results") or [data]

    if not clinics:
        return "Поликлиники не найдены."

    lines = []
    for clinic in clinics[:5]:
        if isinstance(clinic, dict):
            name = clinic.get("name") or clinic.get("title") or "Поликлиника"
            address = clinic.get("address") or clinic.get("full_address") or ""
            phone = clinic.get("phone") or clinic.get("phones") or ""
            clinic_type = clinic.get("type") or clinic.get("clinic_type") or ""

            lines.append(f"🏥 **{name}**")
            if clinic_type:
                lines.append(f"   Тип: {clinic_type}")
            if address:
                lines.append(f"   📍 {address}")
            if phone:
                lines.append(f"   📞 {phone}")
            lines.append("")
        else:
            lines.append(str(clinic))

    return "\n".join(lines) if lines else "Поликлиники не найдены."


@tool
@handle_api_errors
async def get_polyclinics_by_address(address: str) -> str:
    """
    Найти поликлиники, к которым прикреплён адрес.

    Args:
        address: Адрес прописки (улица + дом). Примеры: "Невский 10", "Садовая 50"

    Returns:
        Список поликлиник, к которым прикреплён дом
    """
    logger.info("tool_call", tool="get_polyclinics_by_address", address=address)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_polyclinics_by_building(address_query=address)
        data = _extract_json(result)

        if not data:
            return f"Поликлиники для адреса '{address}' не найдены."

        return _format_polyclinics(data)


# =============================================================================
# School Tools
# =============================================================================


def _format_schools(data: Any) -> str:
    """Форматировать список школ для чата."""
    if not data:
        return "Школы не найдены."

    schools = data if isinstance(data, list) else data.get("data") or data.get("results") or [data]

    if not schools:
        return "Школы не найдены."

    lines = []
    for school in schools[:5]:
        if isinstance(school, dict):
            name = school.get("name") or school.get("title") or school.get("short_name") or "Школа"
            address = school.get("address") or school.get("full_address") or ""
            phone = school.get("phone") or school.get("phones") or ""
            school_type = school.get("type") or school.get("org_type") or ""

            lines.append(f"🏫 **{name}**")
            if school_type:
                lines.append(f"   Тип: {school_type}")
            if address:
                lines.append(f"   📍 {address}")
            if phone:
                lines.append(f"   📞 {phone}")
            lines.append("")
        else:
            lines.append(str(school))

    return "\n".join(lines) if lines else "Школы не найдены."


@tool
@handle_api_errors
async def get_schools_by_address(address: str) -> str:
    """
    Найти школы, к которым прикреплён адрес по месту прописки.

    Args:
        address: Адрес прописки (улица + дом). Примеры: "Невский 10", "Садовая 50"

    Returns:
        Список школ, к которым прикреплён дом
    """
    logger.info("tool_call", tool="get_schools_by_address", address=address)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_linked_schools(address_query=address)
        data = _extract_json(result)

        if not data:
            return f"Школы для адреса '{address}' не найдены."

        return _format_schools(data)


@tool
@handle_api_errors
async def get_schools_in_district(district: str) -> str:
    """
    Найти школы в районе.

    Args:
        district: Название РАЙОНА (НЕ адрес!). Примеры: "Невский", "Центральный"

    Returns:
        Список школ в указанном районе
    """
    logger.info("tool_call", tool="get_schools_in_district", district=district)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_schools_map(district=district)
        data = _extract_json(result)

        if not data:
            return f"Школы в районе '{district}' не найдены."

        return _format_schools(data)


@tool
@handle_api_errors
async def get_school_by_id(school_id: int) -> str:
    """
    Получить информацию о школе по ID.

    Args:
        school_id: ID школы

    Returns:
        Подробная информация о школе
    """
    logger.info("tool_call", tool="get_school_by_id", school_id=school_id)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_school_by_id(school_id=school_id)
        data = _extract_json(result)

        if not data:
            return f"Школа с ID {school_id} не найдена."

        return _format_schools([data])


# =============================================================================
# Management Company Tools
# =============================================================================


@tool
@handle_api_errors
async def get_management_company(address: str) -> str:
    """
    Найти управляющую компанию по адресу.

    Args:
        address: Адрес дома (улица + дом). Примеры: "Невский 10", "Садовая 50"

    Returns:
        Информация об УК для указанного дома
    """
    logger.info("tool_call", tool="get_management_company", address=address)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_management_company(address_query=address)
        data = _extract_json(result)

        if not data:
            return f"Управляющая компания для адреса '{address}' не найдена."

        if isinstance(data, dict):
            name = data.get("name") or data.get("company_name") or "УК"
            inn = data.get("inn") or ""
            address_uk = data.get("address") or data.get("legal_address") or ""
            phone = data.get("phone") or data.get("phones") or ""

            lines = [f"🏢 **{name}**"]
            if inn:
                lines.append(f"   ИНН: {inn}")
            if address_uk:
                lines.append(f"   📍 {address_uk}")
            if phone:
                lines.append(f"   📞 {phone}")

            return "\n".join(lines)

        return str(data)


# =============================================================================
# Kindergarten Tools
# =============================================================================


@tool
@handle_api_errors
async def get_kindergartens_by_district(district: str) -> str:
    """
    Найти детские сады в районе.

    Args:
        district: Название РАЙОНА (НЕ адрес!). Примеры: "Невский", "Центральный"

    Returns:
        Список детских садов в указанном районе
    """
    logger.info("tool_call", tool="get_kindergartens_by_district", district=district)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_dou(district=district)
        data = _extract_json(result)

        if not data:
            return f"Детские сады в районе '{district}' не найдены."

        kinders = data if isinstance(data, list) else data.get("data") or [data]

        lines = [f"👶 Детские сады в {district} районе:\n"]
        for k in kinders[:10]:
            if isinstance(k, dict):
                name = k.get("name") or k.get("title") or k.get("short_name") or "Детский сад"
                addr = k.get("address") or ""
                spots = k.get("available_spots")

                lines.append(f"• **{name}**")
                if addr:
                    lines.append(f"   📍 {addr}")
                if spots is not None:
                    lines.append(f"   🪑 Свободных мест: {spots}")
            else:
                lines.append(f"• {k}")

        return "\n".join(lines) if len(lines) > 1 else "Детские сады не найдены."


# =============================================================================
# PETS Tools
# =============================================================================


@tool
@handle_api_errors
async def get_pet_parks(lat: float, lon: float, radius_km: float = 5.0) -> str:
    """
    Найти площадки для выгула собак рядом с координатами.

    Args:
        lat: Широта (например: 59.9343)
        lon: Долгота (например: 30.3351)
        radius_km: Радиус поиска в километрах (по умолчанию 5)

    Returns:
        Список площадок для выгула собак
    """
    logger.info("tool_call", tool="get_pet_parks", lat=lat, lon=lon, radius_km=radius_km)

    from langgraph_app.tools.formatters import format_pet_parks_list

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_pet_parks(lat=lat, lon=lon, radius_km=int(radius_km))
        data = _extract_json(result)

        if not data:
            return "Площадки для выгула не найдены."

        parks = data.get("data", [])
        return format_pet_parks_list(parks)


@tool
@handle_api_errors
async def get_vet_clinics(lat: float, lon: float, radius_km: float = 10.0) -> str:
    """
    Найти ближайшие ветеринарные клиники.

    Args:
        lat: Широта
        lon: Долгота
        radius_km: Радиус поиска в километрах (по умолчанию 10)

    Returns:
        Список ветеринарных клиник
    """
    logger.info("tool_call", tool="get_vet_clinics", lat=lat, lon=lon, radius_km=radius_km)

    from langgraph_app.tools.formatters import format_vet_clinics_list

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_vet_clinics(lat=lat, lon=lon, radius_km=int(radius_km))
        data = _extract_json(result)

        if not data:
            return "Ветклиники не найдены."

        clinics = data.get("data", [])
        return format_vet_clinics_list(clinics)


@tool
@handle_api_errors
async def get_pet_shelters(lat: float, lon: float, radius_km: float = 10.0) -> str:
    """
    Найти приюты для животных.

    Args:
        lat: Широта
        lon: Долгота
        radius_km: Радиус поиска в километрах (по умолчанию 10)

    Returns:
        Список приютов с информацией о посещении
    """
    logger.info("tool_call", tool="get_pet_shelters", lat=lat, lon=lon, radius_km=radius_km)

    from langgraph_app.tools.formatters import format_shelters_list

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_mypets_shelters(lat=lat, lon=lon, radius_km=int(radius_km))
        data = _extract_json(result)

        if not data:
            return "Приюты не найдены."

        shelters = data.get("data", [])
        return format_shelters_list(shelters)


# =============================================================================
# EVENTS Tools
# =============================================================================


@tool
@handle_api_errors
async def get_city_events(
    lat: float,
    lon: float,
    radius_km: float = 10.0,
    count: int = 5,
) -> str:
    """
    Найти мероприятия в городе рядом с указанными координатами.

    Args:
        lat: Широта
        lon: Долгота
        radius_km: Радиус поиска в километрах
        count: Количество результатов (по умолчанию 5)

    Returns:
        Список мероприятий с датами и местами проведения
    """
    logger.info("tool_call", tool="get_city_events", lat=lat, lon=lon)

    from datetime import datetime, timedelta

    from langgraph_app.tools.formatters import format_events_list

    start_date = datetime.now()
    end_date = start_date + timedelta(days=30)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_events(
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            lat=lat,
            lon=lon,
            radius_km=int(radius_km),
            count=count,
        )
        data = _extract_json(result)

        if not data:
            return "Мероприятия не найдены."

        events = data.get("data", [])
        return format_events_list(events)


@tool
@handle_api_errors
async def get_sport_events(district: str, count: int = 5) -> str:
    """
    Найти спортивные мероприятия в районе.

    Args:
        district: Название района (например: "Кировский", "Невский")
        count: Количество результатов

    Returns:
        Список спортивных мероприятий
    """
    logger.info("tool_call", tool="get_sport_events", district=district)

    from langgraph_app.tools.formatters import format_sport_events_list

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_sport_events(district=district, count=count)
        data = _extract_json(result)

        if not data:
            return f"Спортивные мероприятия в {district} районе не найдены."

        # Структура: data.data.data (вложенность)
        inner = data.get("data", {})
        events = inner.get("data", []) if isinstance(inner, dict) else []
        return format_sport_events_list(events)


# =============================================================================
# PENSIONER Tools
# =============================================================================


@tool
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
    logger.info("tool_call", tool="get_pensioner_services", district=district)

    from langgraph_app.tools.formatters import format_pensioner_services_list

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_pensioner_services(district=district, count=count)
        data = _extract_json(result)

        if not data:
            return f"Услуги для пенсионеров в {district} районе не найдены."

        services = data.get("data", [])
        return format_pensioner_services_list(services)


@tool
@handle_api_errors
async def get_pensioner_hotlines(district: str) -> str:
    """
    Получить горячие линии для пенсионеров в районе.

    Args:
        district: Название района

    Returns:
        Телефоны горячих линий
    """
    logger.info("tool_call", tool="get_pensioner_hotlines", district=district)

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_pensioner_hotlines_by_district(district=district)
        data = _extract_json(result)

        if not data:
            return f"Горячие линии для {district} района не найдены."

        # Форматируем вручную, т.к. структура простая
        lines = [f"📞 Горячие линии для пенсионеров ({district} район):\n"]
        if isinstance(data, list):
            for item in data:
                if phone := item.get("phone"):
                    title = item.get("title", "")
                    lines.append(f"• {title}: {phone}")
        elif isinstance(data, dict):
            for key, value in data.items():
                lines.append(f"• {key}: {value}")

        return "\n".join(lines) if len(lines) > 1 else "Информация не найдена."


# =============================================================================
# SPORT Tools
# =============================================================================


@tool
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
    logger.info("tool_call", tool="get_sportgrounds", district=district)

    from langgraph_app.tools.formatters import format_sportgrounds_list

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_sportgrounds(district=district, count=count)
        data = _extract_json(result)

        if not data:
            return f"Спортплощадки в {district} районе не найдены."

        grounds = data.get("data", [])
        return format_sportgrounds_list(grounds)


# =============================================================================
# TOURISM Tools
# =============================================================================


@tool
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
    logger.info("tool_call", tool="get_beautiful_places", district=district)

    from langgraph_app.tools.formatters import format_beautiful_places_list

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_beautiful_places(district=district, count=count)
        data = _extract_json(result)

        if not data:
            return f"Достопримечательности в {district} районе не найдены."

        places = data.get("data", [])
        return format_beautiful_places_list(places)


@tool
@handle_api_errors
async def get_tourist_routes(count: int = 5) -> str:
    """
    Найти туристические маршруты.

    Args:
        count: Количество результатов

    Returns:
        Список туристических маршрутов
    """
    logger.info("tool_call", tool="get_tourist_routes")

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_beautiful_place_routes(count=count)
        data = _extract_json(result)

        if not data:
            return "Туристические маршруты не найдены."

        routes = data.get("data", [])
        if not routes:
            return "Туристические маршруты не найдены."

        lines = [f"🗺️ Найдено маршрутов: {len(routes)}\n"]
        for route in routes[:count]:
            place = route.get("place", route)
            lines.append(f"🚶 **{place.get('title', 'Маршрут')}**")
            if desc := place.get("description"):
                short = desc[:150] + "..." if len(desc) > 150 else desc
                lines.append(f"   {short}")
            lines.append("")

        return "\n".join(lines)


# =============================================================================
# RECYCLING Tools
# =============================================================================


@tool
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
    logger.info("tool_call", tool="get_recycling_points", lat=lat, lon=lon)

    from langgraph_app.tools.formatters import format_recycling_by_category

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_recycling_nearest(lat=lat, lon=lon, count=count)
        data = _extract_json(result)

        if not data:
            return "Пункты переработки не найдены."

        # data — это список категорий
        categories = data.get("data", data) if isinstance(data, dict) else data
        return format_recycling_by_category(categories)


# =============================================================================
# INFRASTRUCTURE Tools
# =============================================================================


@tool
@handle_api_errors
async def get_disconnections(building_id: int) -> str:
    """
    Проверить отключения воды/электричества по зданию.

    Args:
        building_id: ID здания из системы YAZZH

    Returns:
        Информация об отключениях или "отключений нет"
    """
    logger.info("tool_call", tool="get_disconnections", building_id=building_id)

    from langgraph_app.tools.formatters import format_disconnections_list

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_disconnections(building_id=str(building_id))
        data = _extract_json(result)

        # 204 No Content означает отсутствие отключений
        if result.get("status_code") == 204 or not data:
            return "✅ Отключений не запланировано. Всё работает!"

        discs = data if isinstance(data, list) else data.get("data", [])
        return format_disconnections_list(discs)


@tool
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
    logger.info("tool_call", tool="get_road_works", district=district)

    from langgraph_app.tools.formatters import format_road_works_list

    async with ApiClientUnified(verbose=False) as client:
        result = await client.get_gati_orders_map(district=district, count=count)
        data = _extract_json(result)

        if not data:
            return f"Информация о дорожных работах в {district} районе не найдена."

        works = data.get("data", [])
        return format_road_works_list(works)


# =============================================================================
# Export all tools
# =============================================================================

ALL_TOOLS = [
    # Geo / Address
    search_address,
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
    # PETS (NEW)
    get_pet_parks,
    get_vet_clinics,
    get_pet_shelters,
    # EVENTS (NEW)
    get_city_events,
    get_sport_events,
    # PENSIONER (NEW)
    get_pensioner_services,
    get_pensioner_hotlines,
    # SPORT (NEW)
    get_sportgrounds,
    # TOURISM (NEW)
    get_beautiful_places,
    get_tourist_routes,
    # RECYCLING (NEW)
    get_recycling_points,
    # INFRASTRUCTURE (NEW)
    get_disconnections,
    get_road_works,
]

# Группировка по категориям для registry
TOOLS_BY_CATEGORY = {
    "address": [search_address, get_district_info_by_address],
    "district": [get_districts_list, get_district_info],
    "mfc": [find_nearest_mfc, get_mfc_by_district, get_all_mfc],
    "polyclinic": [get_polyclinics_by_address],
    "school": [get_schools_by_address, get_schools_in_district, get_school_by_id],
    "housing": [get_management_company],
    "kindergarten": [get_kindergartens_by_district],
    # NEW CATEGORIES
    "pets": [get_pet_parks, get_vet_clinics, get_pet_shelters],
    "events": [get_city_events, get_sport_events],
    "pensioner": [get_pensioner_services, get_pensioner_hotlines],
    "sport": [get_sportgrounds],
    "tourism": [get_beautiful_places, get_tourist_routes],
    "recycling": [get_recycling_points],
    "infrastructure": [get_disconnections, get_road_works],
}


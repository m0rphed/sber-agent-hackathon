"""
Сервис геокодирования с fallback chain.

Порядок попыток:
1. YAZZH API (даёт building_id для дальнейших запросов)
2. Yandex Geocoder (более точный для СПб)
3. Nominatim/OSM (резервный вариант с кешем)

Также поддерживает геокодирование станций метро по статическим данным.
"""

from dataclasses import dataclass

from langgraph_app.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class GeocodingResult:
    """
    Результат геокодирования адреса.

    Attributes:
        lat: Широта
        lon: Долгота
        address: Нормализованный адрес
        source: Источник данных ("yazzh", "yandex", "nominatim", "metro_static")
        building_id: ID здания в YAZZH API (только для source="yazzh")
        district: Район (если известен)
    """

    lat: float
    lon: float
    address: str
    source: str
    building_id: int | None = None
    district: str | None = None


async def geocode_metro_station(station_name: str) -> GeocodingResult | None:
    """
    Геокодирует станцию метро по статическим данным.

    Args:
        station_name: Название станции (например: "Невский проспект", "Площадь Восстания")

    Returns:
        GeocodingResult или None если станция не найдена
    """
    from langgraph_app.api.geo.geocoding import spb_metro_station_to_coords

    try:
        coords = await spb_metro_station_to_coords(station_name)
        if coords:
            lat, lon = coords
            return GeocodingResult(
                lat=lat,
                lon=lon,
                address=f'м. {station_name}',
                source='metro_static',
            )
    except Exception as e:
        logger.warning('metro_geocoding_failed', station=station_name, error=str(e))

    return None


async def geocode_with_yazzh(address: str, limit: int = 5) -> list[GeocodingResult]:
    """
    Геокодирует адрес через YAZZH API.

    Преимущество: возвращает building_id, который можно использовать
    для получения детальной информации о здании.

    Args:
        address: Адрес для поиска
        limit: Максимальное количество результатов

    Returns:
        Список результатов (может быть пустым)
    """
    from langgraph_app.api.yazzh_new import AddressNotFoundError, YazzhAsyncClient

    try:
        async with YazzhAsyncClient() as client:
            buildings = await client.search_building(address, count=limit)

            return [
                GeocodingResult(
                    lat=b.latitude or 0.0,
                    lon=b.longitude or 0.0,
                    address=b.full_address,
                    source='yazzh',
                    building_id=int(b.id) if b.id else None,
                    district=b.district,
                )
                for b in buildings
            ]
    except AddressNotFoundError:
        logger.info('yazzh_address_not_found', address=address)
        return []
    except Exception as e:
        logger.warning('yazzh_geocoding_failed', address=address, error=str(e))
        return []


async def geocode_with_yandex(address: str) -> GeocodingResult | None:
    """
    Геокодирует адрес через Yandex Geocoder API.

    Args:
        address: Адрес для поиска

    Returns:
        GeocodingResult или None
    """
    from langgraph_app.api.geo.geocoding import address_to_coords_yandex

    try:
        coords = await address_to_coords_yandex(address)
        if coords:
            lat, lon = coords
            return GeocodingResult(
                lat=lat,
                lon=lon,
                # геокодер yandex не возвращает нормализованный адрес в этой функции
                # TODO: вообще-то яндекс может возвращать нормализованный адрес, просто мы его не извлекаем - поправить
                address=address,
                source='yandex',
            )
    except Exception as e:
        logger.warning('yandex_geocoding_failed', address=address, error=str(e))

    return None


def geocode_with_nominatim(address: str) -> GeocodingResult | None:
    """
    Геокодирует адрес через Nominatim (OSM) с кешированием.

    Синхронная функция (использует osmnx под капотом).

    Args:
        address: Адрес для поиска

    Returns:
        GeocodingResult или None
    """
    from langgraph_app.api.geo.geocoding import geocode_with_cache

    try:
        coords = geocode_with_cache(address)
        if coords:
            lat, lon = coords
            return GeocodingResult(
                lat=lat,
                lon=lon,
                address=address,
                source='nominatim',
            )
    except Exception as e:
        logger.warning('nominatim_geocoding_failed', address=address, error=str(e))

    return None


async def geocode_address(
    address: str,
    prefer_yazzh: bool = True,
    include_metro: bool = True,
) -> GeocodingResult | None:
    """
    Главная функция геокодирования с fallback chain.

    Порядок попыток:
    1. Если include_metro и похоже на метро — статические данные метро
    2. Если prefer_yazzh — YAZZH API (возвращает первый результат)
    3. Yandex Geocoder
    4. Nominatim (OSM)

    Args:
        address: Адрес или название станции метро
        prefer_yazzh: Начинать с YAZZH API (даёт building_id)
        include_metro: Проверять станции метро

    Returns:
        GeocodingResult или None если не найден
    """
    address_lower = address.lower()

    # 1. проверяем, не станция ли это метро
    if include_metro:
        metro_keywords = ['метро', 'м.', 'станция']
        is_metro = any(kw in address_lower for kw in metro_keywords)

        if is_metro:
            # убираем ключевые слова и пробуем найти станцию
            station_name = address
            for kw in metro_keywords:
                station_name = station_name.lower().replace(kw, '').strip()

            result = await geocode_metro_station(station_name)
            if result:
                logger.info('geocoded_via_metro', station=station_name)
                return result

    # 2. yazzh - "Я Здесь Живу" API
    if prefer_yazzh:
        results = await geocode_with_yazzh(address, limit=1)
        if results:
            logger.info('geocoded_via_yazzh', address=address)
            return results[0]

    # 3. yandex geocoder
    result = await geocode_with_yandex(address)
    if result:
        logger.info('geocoded_via_yandex', address=address)
        return result

    # 4. nominatim (синхронный fallback)
    result = geocode_with_nominatim(address)
    if result:
        logger.info('geocoded_via_nominatim', address=address)
        return result

    logger.warning('geocoding_failed_all_sources', address=address)
    return None


async def geocode_address_with_candidates(
    address: str,
    limit: int = 5,
) -> list[GeocodingResult]:
    """
    Геокодирует адрес и возвращает список кандидатов.

    Используется для валидации адреса с показом вариантов пользователю.

    Args:
        address: Адрес для поиска
        limit: Максимальное количество кандидатов

    Returns:
        Список GeocodingResult (может быть пустым)
    """
    # сначала пробуем "Я Здесь Живу API" (yazzh) — он возвращает несколько результатов
    results = await geocode_with_yazzh(address, limit=limit)

    if results:
        return results

    # fallback на Yandex (только один результат)
    yandex_result = await geocode_with_yandex(address)
    if yandex_result:
        return [yandex_result]

    # fallback на Nominatim (только один результат)
    nominatim_result = geocode_with_nominatim(address)
    if nominatim_result:
        return [nominatim_result]

    return []

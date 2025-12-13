"""
Yandex Geocoder API Client.

Используется для геокодирования адресов, в том числе станций метро,
когда YAZZH API не может найти объект по названию.

Пример использования:
    from langgraph_app.api.yandex_geo import geocode, geocode_metro

    # Геокодирование любого адреса
    lat, lon = geocode("Невский проспект 1, Санкт-Петербург")

    # Геокодирование станции метро
    lat, lon = geocode_metro("Пионерская")
"""

import os
from typing import Any

from ymaps import Geocode  # type: ignore

from langgraph_app.logging_config import get_logger

logger = get_logger(__name__)


def _get_yandex_api_key() -> str:
    """
    Возвращает API ключ Yandex
    """
    key = os.getenv('YANDEX_API_KEY', '')
    if not key:
        raise ValueError(
            'YANDEX_API_KEY не задан. '
            'Получите ключ на https://developer.tech.yandex.ru/ '
            'и добавьте в .env файл.'
        )
    return key


def _get_client() -> Geocode:
    """
    Возвращает клиент Yandex GeoСoder.
    """
    return Geocode(_get_yandex_api_key())


def geocode(address: str) -> tuple[float, float]:
    """
    Геокодировать адрес через Yandex Geocoder API.

    Args:
        address: Полный адрес для поиска

    Returns:
        Кортеж (latitude, longitude)

    Raises:
        ValueError: Если адрес не найден
    """
    logger.info('yandex_geocode', address=address)

    client = _get_client()
    resp: dict[str, Any] = client.geocode(address)

    collection = resp.get('response', {}).get('GeoObjectCollection', {})
    members = collection.get('featureMember', [])

    if not members:
        logger.warning('yandex_geocode_not_found', address=address)
        raise ValueError(f'Адрес не найден Яндексом: {address!r}')

    geo = members[0]['GeoObject']
    pos_str: str = geo['Point']['pos']  # формат: "lon lat"
    lon_str, lat_str = pos_str.split()
    lon = float(lon_str)
    lat = float(lat_str)

    logger.info('yandex_geocode_result', address=address, lat=lat, lon=lon)
    return lat, lon


def geocode_metro(metro_name: str, city: str = 'Санкт-Петербург') -> tuple[float, float]:
    """
    Геокодировать станцию метро.

    Args:
        metro_name: Название станции метро (например: "Пионерская", "Невский проспект")
        city: Город (по умолчанию Санкт-Петербург)

    Returns:
        Кортеж (latitude, longitude)

    Raises:
        ValueError: Если станция не найдена
    """
    # Формируем запрос для метро
    query = f'Россия, {city}, метро {metro_name}'
    return geocode(query)


def geocode_address_spb(address: str) -> tuple[float, float]:
    """
    Геокодировать адрес в Санкт-Петербурге.

    Добавляет "Санкт-Петербург" к запросу для уточнения.

    Args:
        address: Адрес (например: "Невский проспект 1")

    Returns:
        Кортеж (latitude, longitude)
    """
    # Добавляем город если не указан
    if 'петербург' not in address.lower() and 'спб' not in address.lower():
        address = f'Санкт-Петербург, {address}'

    return geocode(address)


def reverse_geocode(lat: float, lon: float) -> str:
    """
    Обратное геокодирование: координаты → адрес.

    Args:
        lat: Широта
        lon: Долгота

    Returns:
        Полный адрес

    Raises:
        ValueError: Если адрес не найден
    """
    logger.info('yandex_reverse_geocode', lat=lat, lon=lon)

    client = _get_client()
    # Yandex принимает координаты в формате "lon,lat" (долгота, широта!)
    query = f'{lon},{lat}'
    resp: dict[str, Any] = client.geocode(query)

    collection = resp.get('response', {}).get('GeoObjectCollection', {})
    members = collection.get('featureMember', [])

    if not members:
        logger.warning('yandex_reverse_geocode_not_found', lat=lat, lon=lon)
        raise ValueError(f'Адрес не найден по координатам: ({lat}, {lon})')

    geo = members[0]['GeoObject']
    address = geo.get('metaDataProperty', {}).get('GeocoderMetaData', {}).get('text', '')

    if not address:
        # Fallback на name
        address = geo.get('name', f'{lat}, {lon}')

    logger.info('yandex_reverse_geocode_result', lat=lat, lon=lon, address=address)
    return address


def reverse_geocode_structured(lat: float, lon: float) -> dict[str, Any]:
    """
    Обратное геокодирование с полной структурой адреса.

    Args:
        lat: Широта
        lon: Долгота

    Returns:
        Словарь с компонентами адреса:
        - full_address: Полный адрес
        - country: Страна
        - city: Город
        - street: Улица
        - house: Дом
        - district: Район
    """
    logger.info('yandex_reverse_geocode_structured', lat=lat, lon=lon)

    client = _get_client()
    query = f'{lon},{lat}'
    resp: dict[str, Any] = client.geocode(query)

    collection = resp.get('response', {}).get('GeoObjectCollection', {})
    members = collection.get('featureMember', [])

    if not members:
        raise ValueError(f'Адрес не найден по координатам: ({lat}, {lon})')

    geo = members[0]['GeoObject']
    meta = geo.get('metaDataProperty', {}).get('GeocoderMetaData', {})

    # Извлекаем компоненты адреса
    address_details = meta.get('Address', {})
    components = address_details.get('Components', [])

    result: dict[str, Any] = {
        'full_address': meta.get('text', ''),
        'country': None,
        'city': None,
        'street': None,
        'house': None,
        'district': None,
    }

    # Маппинг типов компонентов Yandex
    kind_mapping = {
        'country': 'country',
        'locality': 'city',
        'street': 'street',
        'house': 'house',
        'district': 'district',
    }

    for comp in components:
        kind = comp.get('kind', '')
        name = comp.get('name', '')
        if kind in kind_mapping:
            result[kind_mapping[kind]] = name

    logger.info('yandex_reverse_geocode_structured_result', result=result)
    return result

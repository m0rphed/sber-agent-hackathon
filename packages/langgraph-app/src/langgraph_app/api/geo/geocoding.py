"""
Модуль геокодинга - должен в себе объединять все доступные способы геокодинга:

# 1. Геокодинг названий станций МЕТРО по статическим данным
# 2. Геокодинг адресов в координаты через Yandex Geocoding API
# 3. Обратный геокодинг координат в адреса через Yandex Geocoding API
# 4. Геокодинг через Nominatim (OpenStreetMap) - для резервного варианта
"""

import json
import os

from dotenv import load_dotenv
import osmnx as ox
from ymaps import GeocodeAsync

from langgraph_app.config import get_geo_config
from langgraph_app.osmnx_config import get_osm_geocode_db

load_dotenv()

YANDEX_API_KEY = os.getenv('YANDEX_API_KEY')
_yandex_geocode_client = GeocodeAsync(YANDEX_API_KEY)


async def _read_json_metro_all_stations():
    geo_config = get_geo_config()
    with open(geo_config.spb_metro_data_path, encoding='utf-8') as f:
        data = json.load(f)
        return data


async def spb_metro_station_to_coords(metro_name: str) -> tuple[float, float] | None:
    """
    Геокодирование названия станции метро Санкт-Петербурга в координаты (lat, lon).
    Возвращает кортеж (lat, lon) или None, если станция не найдена.
    """
    # TODO: 1) нормально написать поиск станции (с учётом разных вариантов написания)
    # TODO: 2) сделать так чтобы формат статических данных был удобным для поиска

    data = await _read_json_metro_all_stations()
    for station in data:
        station_name: str = station['metro_name']
        # поиск подстроки в названии станции (регистр игнорируем)
        is_substring = metro_name.lower() in station_name.lower()
        if is_substring:
            coords: list = station['coords']
            lat, lon = coords
            return (lat, lon)
    return None


async def address_to_coords_yandex(user_address: str) -> tuple[float, float] | None:
    """
    Геокодирование адреса в координаты.
    Возвращает [lat, lon] или None, если ничего не найдено.
    """
    lower_user_address = user_address.lower()
    if (
        'спб' not in lower_user_address
        and 'санкт-петербург' not in lower_user_address
        and 'санкт петербург' not in lower_user_address
    ):
        user_address = 'Санкт-Петербург, ' + user_address

    data = await _yandex_geocode_client.geocode(user_address, results=1, format='json')

    collection = data['response']['GeoObjectCollection']
    members = collection.get('featureMember', [])
    if not members:
        return None

    geo_obj = members[0]['GeoObject']

    # "lon lat" (строка)
    pos_str = geo_obj['Point']['pos']
    lon_str, lat_str = pos_str.split()

    lon = float(lon_str)
    lat = float(lat_str)

    # возвращаем в привычном порядке (lat, lon)
    return (lat, lon)


async def coords_to_address_yandex(lat: float, lon: float):
    """
    Обратное геокодирование: по координатам (lat, lon) вернуть полный адрес.
    Возвращает строку-адрес или None, если ничего не найдено.
    """

    # Яндекс ждёт [lon, lat], то есть [долгота, широта]
    coords = [lon, lat]

    data = await _yandex_geocode_client.reverse(
        coords,  # positional arg = geocode
        results=1,
        format='json',
        # при желании можно добавить kind='house' или kind='metro'
    )

    collection = data['response']['GeoObjectCollection']
    members = collection.get('featureMember', [])
    if not members:
        return None

    geo_obj = members[0]['GeoObject']
    meta = geo_obj.get('metaDataProperty', {}).get('GeocoderMetaData', {})

    # Основной адрес
    text = meta.get('text')
    if text:
        return text

    # fallback — собрать из name/description, если вдруг text отсутствует
    name = geo_obj.get('name')
    desc = geo_obj.get('description')
    if name or desc:
        return ', '.join(x for x in (name, desc) if x)

    return None


# ----------------------------------------------------------
# Геокодирование с кешем через Nominatim (OpenStreetMap)
# ----------------------------------------------------------
class GeocodingError(RuntimeError):
    """
    Ошибка геокодирования адреса через Nominatim
    """


def geocode_with_cache(address: str) -> tuple[float, float] | None:
    """
    Геокодирует адрес в пределах СПб с кешем в SQLite.
    Возвращает (lat, lon).

    Если Nominatim не смог найти или вернул ошибку — возвращает None.
    """
    geo_cfg = get_geo_config()
    conn = get_osm_geocode_db()
    full = f'{address}, {geo_cfg.city_name}'

    # 1. проверяем кеш
    cur = conn.cursor()
    cur.execute(
        'SELECT lat, lon FROM geocode_cache WHERE full_address = ?',
        (full,),
    )
    row = cur.fetchone()

    if row is not None:
        lat, lon = row
        return float(lat), float(lon)

    # 2. если в кеше нет — идём в Nominatim
    try:
        lat, lon = ox.geocode(full)
    except Exception as _exc:  # osmnx/Nominatim могут кидать разные ошибки
        return None
        # raise GeocodingError(f'Не удалось геокодировать адрес: {full}') from exc

    if lat is None or lon is None:
        return None
        # raise GeocodingError(f'Nominatim не вернул координаты для: {full}')

    # 3. сохраняем в кеш
    conn.execute(
        'INSERT OR REPLACE INTO geocode_cache (full_address, lat, lon) VALUES (?, ?, ?)',
        (full, float(lat), float(lon)),
    )
    conn.commit()

    return float(lat), float(lon)

"""
Сервис геокодирования с fallback chain.

Порядок попыток:
1. Метро (статические данные) — если ввод похож на станцию
2. YAZZH API (даёт building_id для дальнейших запросов)
3. Yandex Geocoder (более точный для СПб)
4. Nominatim/OSM (резервный вариант с кешем)

Также поддерживает геокодирование станций метро по статическим данным.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from langgraph_app.logging_config import get_logger

from langgraph_app.config import DATA_DIR


logger = get_logger(__name__)

# ============================================================================
# Список станций метро (контракт распознавания)
# ============================================================================

ADDRESS_MARKERS = (
    'ул', 'улица',
    'пр', 'проспект',
    'пер', 'переулок',
    'пл', 'площадь',
    'наб', 'набережная',
    'дом', 'д.', 'корп', 'к.',
    'строение', 'стр',
    'литер', 'лит',
)

SPB_METRO_STATIONS_2025_RU = [
    # Линия 1 — Кировско-Выборгская (M1)
    'Девяткино',
    'Гражданский проспект',
    'Академическая',
    'Политехническая',
    'Площадь Мужества',
    'Лесная',
    'Выборгская',
    'Площадь Ленина',
    'Чернышевская',
    'Площадь Восстания',
    'Владимирская',
    'Пушкинская',
    'Технологический институт 1',
    'Балтийская',
    'Нарвская',
    'Кировский завод',
    'Автово',
    'Ленинский проспект',
    'Проспект Ветеранов',
    # Линия 2 — Московско-Петроградская (M2)
    'Парнас',
    'Проспект Просвещения',
    'Озерки',
    'Удельная',
    'Пионерская',
    'Чёрная речка',
    'Петроградская',
    'Горьковская',
    'Невский проспект',
    'Сенная площадь',
    'Технологический институт 2',
    'Фрунзенская',
    'Московские ворота',
    'Электросила',
    'Парк Победы',
    'Московская',
    'Звёздная',
    'Купчино',
    # Линия 3 — Невско-Василеостровская (M3)
    'Беговая',
    'Зенит',
    'Приморская',
    'Василеостровская',
    'Гостиный двор',
    'Маяковская',
    'Площадь Александра Невского 1',
    'Елизаровская',
    'Ломоносовская',
    'Пролетарская',
    'Обухово',
    'Рыбацкое',
    # Линия 4 — Лахтинско-Правобережная (M4)
    'Горный институт',
    'Спасская',
    'Достоевская',
    'Лиговский проспект',
    'Площадь Александра Невского 2',
    'Новочеркасская',
    'Ладожская',
    'Проспект Большевиков',
    'Улица Дыбенко',
    # Линия 5 — Фрунзенско-Приморская (M5)
    'Комендантский проспект',
    'Старая Деревня',
    'Крестовский остров',
    'Чкаловская',
    'Спортивная',
    'Адмиралтейская',
    'Садовая',
    'Звенигородская',
    'Обводный канал',
    'Волковская',
    'Бухарестская',
    'Международная',
    'Проспект Славы',
    'Дунайская',
    'Шушары',
]

# ============================================================================
# Метро: загрузка JSON и индексы
# ============================================================================
_METRO_CACHE: list[dict] | None = None
_METRO_BY_NAME_NORM: dict[str, dict] | None = None
_METRO_INDEX: dict[str, str] | None = None



def _load_metro_data() -> list[dict]:
    """
    Загружает JSON со статикой метро (coords/address/line/closed) и кеширует в памяти.
    """
    global _METRO_CACHE
    if _METRO_CACHE is None:
        path = Path('spb_metro.json') #для блокнота просто spb_metro.json, для прода: './data/spb_metro.json'
        with path.open(encoding='utf-8') as f:
            _METRO_CACHE = json.load(f)
    return _METRO_CACHE

def looks_like_address(text: str) -> bool:
    t = normalize_text(text)

    # есть цифры → почти всегда адрес
    if any(ch.isdigit() for ch in t):
        return True

    # есть адресные маркеры
    for kw in ADDRESS_MARKERS:
        if kw in t:
            return True

    return False


def normalize_text(s: str) -> str:
    """
    Единая нормализация текста для сопоставления:
    - lower
    - ё->е
    - убираем слова-индикаторы метро
    - сжимаем пробелы
    """
    s = s.lower().replace('ё', 'е')
    for kw in ('метро', 'м.', 'станция'):
        s = s.replace(kw, ' ')
    s = ' '.join(s.split())
    return s.strip()


def _build_metro_indexes() -> None:
    """
    Строит индексы:
    - _METRO_INDEX: нормализованное имя -> каноническое имя из списка станций
    - _METRO_BY_NAME_NORM: нормализованное имя -> запись из JSON (coords/address/closed)
    """
    global _METRO_INDEX, _METRO_BY_NAME_NORM

    if _METRO_INDEX is None:
        _METRO_INDEX = {normalize_text(name): name for name in SPB_METRO_STATIONS_2025_RU}

    if _METRO_BY_NAME_NORM is None:
        by_name: dict[str, dict] = {}
        for item in _load_metro_data():
            name = item.get('metro_name', '')
            if not name:
                continue
            by_name[normalize_text(name)] = item
        _METRO_BY_NAME_NORM = by_name

def is_explicit_metro_query(text: str) -> bool:
    t = text.lower()
    return any(
        kw in t
        for kw in ('метро', 'м.', 'станция', 'м ')
    )


def has_address_number(text: str) -> bool:
    return any(ch.isdigit() for ch in text)

def extract_metro_station(address: str) -> str | None:
    _build_metro_indexes()

    q_norm = normalize_text(address)
    if not q_norm:
        return None

    # 1️⃣ метро ТОЛЬКО если явно указано
    if is_explicit_metro_query(address):
        return _METRO_INDEX.get(q_norm)

    # 2️⃣ если есть номер — это адрес, не метро
    if has_address_number(address):
        return None

    # 3️⃣ омонимы → не решаем здесь
    return None


def geocode_metro_candidates(query: str) -> list['GeocodingResult']:
    """
    Возвращает список кандидатов метро на основе:
    - извлечённой станции по списку
    - данных из JSON (coords/address)
    """
    _build_metro_indexes()

    station = extract_metro_station(query)
    if not station:
        return []

    # пытаемся взять точную запись из JSON по нормализованному имени станции
    item = _METRO_BY_NAME_NORM.get(normalize_text(station)) if _METRO_BY_NAME_NORM else None
    if not item:
        return []

    if item.get('is_closed'):
        return []

    coords = item.get('coords')
    if not coords or len(coords) != 2:
        return []

    lat, lon = coords

    return [
        GeocodingResult(
            lat=float(lat),
            lon=float(lon),
            address=f'м. {item.get("metro_name", station)}',
            source='metro_static',
            district=None,
        )
    ]


# ============================================================================
# Модель результата
# ============================================================================
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


# ============================================================================
# Геокодеры (источники)
# ============================================================================
async def geocode_with_yazzh(address: str, limit: int = 5) -> list[GeocodingResult]:
    """
    Геокодирует адрес через YAZZH API.
    """
    from langgraph_app.api.yazzh_final import AddressNotFoundError, ApiClientUnified

    try:
        async with ApiClientUnified() as client:
            buildings = await client.search_building_full_text_search(query = address, count=limit)

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
    """
    from langgraph_app.api.geo.geocoding import address_to_coords_yandex
    
    try:
        coords = await address_to_coords_yandex(address)
        if coords:
            lat, lon = coords
            return GeocodingResult(
                lat=lat,
                lon=lon,
                address=address,  # TODO: при желании извлекать нормализованный адрес из ответа Yandex
                source='yandex',
            )
    except Exception as e:
        logger.warning('yandex_geocoding_failed', address=address, error=str(e))

    return None


def geocode_with_nominatim(address: str) -> GeocodingResult | None:
    """
    Геокодирует адрес через Nominatim (OSM) с кешированием.
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


# ============================================================================
# High-level API
# ============================================================================
async def geocode_address(
    address: str,
    prefer_yazzh: bool = True,
    include_metro: bool = True,
) -> GeocodingResult | None:

    # 1️⃣ если явно метро — сначала метро
    if include_metro and is_explicit_metro_query(address):
        metro_results = geocode_metro_candidates(address)
        if metro_results:
            logger.info('geocoded_via_metro_explicit', address=address)
            return metro_results[0]

    # 2️⃣ пробуем адрес (YAZZH)
    if prefer_yazzh:
        results = await geocode_with_yazzh(address, limit=1)
        if results:
            logger.info('geocoded_via_yazzh', address=address)
            return results[0]

    # 3️⃣ Yandex
    result = await geocode_with_yandex(address)
    if result:
        logger.info('geocode_via_yandex', address=address)
        return result

    # 4️⃣ если адрес не найден — пробуем метро как fallback
    if include_metro:
        metro_results = geocode_metro_candidates(address)
        if metro_results:
            logger.info('geocoded_via_metro_fallback', address=address)
            return metro_results[0]

    # 5️⃣ nominatim
    result = geocode_with_nominatim(address)
    if result:
        return result

    return None


async def geocode_address_with_candidates(
    address: str,
    limit: int = 5,
) -> list[GeocodingResult]:
    """
    Геокодирует адрес и возвращает список кандидатов (для валидации).
    """
    # 1) метро — кандидаты
    metro_results = geocode_metro_candidates(address)
    if metro_results:
        logger.info('geocoded_candidates_via_metro', address=address, count=len(metro_results))
        return metro_results[:limit]

    # 2) yazzh — несколько кандидатов
    results = await geocode_with_yazzh(address, limit=limit)
    if results:
        return results

    # 3) yandex — один кандидат
    yandex_result = await geocode_with_yandex(address)
    if yandex_result:
        return [yandex_result]

    # 4) nominatim — один кандидат
    nominatim_result = geocode_with_nominatim(address)
    if nominatim_result:
        return [nominatim_result]

    return []

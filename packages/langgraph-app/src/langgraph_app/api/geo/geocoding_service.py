"""
Сервис геокодирования с fallback chain.

Порядок попыток:
1. Метро (статические данные из JSON) — если ввод похож на станцию
2. YAZZH API (даёт building_id для дальнейших запросов)
3. Yandex Geocoder (более точный для СПб)
4. Nominatim/OSM (резервный вариант с кешем)

Также поддерживает геокодирование станций метро по статическим данным.
"""

from dataclasses import dataclass
import json

from langgraph_app.config import DATA_DIR
from langgraph_app.logging_config import get_logger

logger = get_logger(__name__)

# ============================================================================
# Константы
# ============================================================================

ADDRESS_MARKERS = (
    'ул',
    'улица',
    'пр',
    'проспект',
    'пер',
    'переулок',
    'пл',
    'площадь',
    'наб',
    'набережная',
    'дом',
    'д.',
    'корп',
    'к.',
    'строение',
    'стр',
    'литер',
    'лит',
)

METRO_KEYWORDS = ('метро', 'м.', 'станция', 'м ')

# ============================================================================
# Кеш данных метро (загружается из JSON один раз)
# ============================================================================
_METRO_BY_NAME: dict[str, dict] | None = None


def _get_metro_index() -> dict[str, dict]:
    """
    Возвращает индекс станций метро: {нормализованное_имя: данные_станции}.
    Загружает JSON один раз и кеширует.
    """
    global _METRO_BY_NAME

    if _METRO_BY_NAME is None:
        path = DATA_DIR / 'spb_metro.json'
        with path.open(encoding='utf-8') as f:
            data = json.load(f)

        _METRO_BY_NAME = {}
        for item in data:
            name = item.get('metro_name', '')
            if name:
                _METRO_BY_NAME[_normalize(name)] = item

    return _METRO_BY_NAME


def _normalize(s: str) -> str:
    """
    Нормализация текста для сопоставления:
    - lower, ё→е
    - убираем слова-индикаторы метро
    - сжимаем пробелы
    """
    s = s.lower().replace('ё', 'е')
    for kw in ('метро', 'м.', 'станция'):
        s = s.replace(kw, ' ')
    return ' '.join(s.split()).strip()


def _is_metro_query(text: str) -> bool:
    """Проверяет, явно ли указано метро в запросе."""
    t = text.lower()
    return any(kw in t for kw in METRO_KEYWORDS)


def _looks_like_address(text: str) -> bool:
    """Проверяет, похоже ли на адрес (есть цифры или адресные маркеры)."""
    t = _normalize(text)
    if any(ch.isdigit() for ch in t):
        return True
    return any(kw in t for kw in ADDRESS_MARKERS)


def geocode_metro_candidates(query: str) -> list['GeocodingResult']:
    """
    Ищет станцию метро по запросу.
    Возвращает список с одним результатом если найдено, иначе пустой список.
    """
    # Только если явно указано "метро" / "м." / "станция"
    if not _is_metro_query(query):
        return []

    index = _get_metro_index()
    norm_query = _normalize(query)

    item = index.get(norm_query)
    if not item:
        return []

    coords = item.get('coords')
    if not coords or len(coords) != 2:
        return []

    lat, lon = coords
    return [
        GeocodingResult(
            lat=float(lat),
            lon=float(lon),
            address=f'м. {item.get("metro_name", norm_query)}',
            source='metro_static',
            district=None,
        )
    ]


# Для обратной совместимости
def normalize_text(s: str) -> str:
    """Алиас для _normalize (обратная совместимость)."""
    return _normalize(s)


def looks_like_address(text: str) -> bool:
    """Алиас для _looks_like_address (обратная совместимость)."""
    return _looks_like_address(text)


def is_explicit_metro_query(text: str) -> bool:
    """Алиас для _is_metro_query (обратная совместимость)."""
    return _is_metro_query(text)


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
        async with ApiClientUnified(verbose=False) as client:
            response = await client.search_building_full_text_search(query=address, count=limit)

            # response = {"status_code": 200, "json": {"success": true, "data": [...]}}
            json_data = response.get('json', {}) if isinstance(response, dict) else {}
            buildings = json_data.get('data', []) if isinstance(json_data, dict) else []

            return [
                GeocodingResult(
                    lat=float(b.get('latitude', 0.0)),
                    lon=float(b.get('longitude', 0.0)),
                    address=b.get('full_address', address),
                    source='yazzh',
                    building_id=int(b['id']) if b.get('id') else None,
                    district=b.get('district'),
                )
                for b in buildings
                if b.get('latitude') and b.get('longitude')
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

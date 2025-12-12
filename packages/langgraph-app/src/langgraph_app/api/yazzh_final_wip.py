__api__ = 'work in progress'

import json
from typing import Any

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from langgraph_app.api.utils import _log_error, _log_json
from langgraph_app.api.yazzh_models import AddressNotFoundError, BuildingSearchResult, YazzhAPIError

console = Console()

API_GEO = 'https://yazzh-geo.gate.petersburg.ru'
API_SITE = 'https://yazzh.gate.petersburg.ru'
REGION_ID = '78'


def format_building_search_for_chat(buildings: list[BuildingSearchResult]) -> str:
    """
    Форматировать результаты поиска адресов для уточнения
    """
    if not buildings:
        return 'Адрес не найден. Пожалуйста, уточните адрес.'

    if len(buildings) == 1:
        return f'Найден адрес: {buildings[0].full_address}'

    lines = ['Найдено несколько адресов. Уточните, какой из них вам нужен:\n']
    for i, b in enumerate(buildings, 1):
        lines.append(f'{i}. {b.full_address}')
    return '\n'.join(lines)


class ApiClientUnified:
    """
    Клиент "Я здесь живу" API с опциональным логированием JSON ответов.
    """

    def __init__(
        self,
        api_geo: str = API_GEO,
        api_site: str = API_SITE,
        region_id: str = REGION_ID,
        timeout: float = 30.0,
        verbose: bool = True,
    ):
        self.api_geo = f'{api_geo.rstrip("/")}/api/v2'
        self.api_geo_v1 = f'{api_geo.rstrip("/")}/api/v1'
        self.api_site = api_site.rstrip('/')
        self.region_id = region_id
        self.timeout = timeout
        self.verbose = verbose
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> 'ApiClientUnified':
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            headers={'region': self.region_id},
        )
        if self.verbose:
            console.print(Panel('[bold green]🚀 ApiAsyncClient initialized[/bold green]'))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        if self.verbose:
            console.print('[dim]👋 Client closed[/dim]')

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError('Use as context manager: async with ApiAsyncClient() as client')
        return self._client

    async def _get_request(
        self,
        method_name: str,
        url: str,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> dict[str, Any]:
        """
        Выполняет HTTP GET запрос с логированием.
        """
        if self.verbose:
            console.rule(f'[bold cyan]📡 {method_name}[/bold cyan]')
            table = Table(title='Request', show_header=False, box=None)
            table.add_row('[dim]URL:[/dim]', url)
            if params:
                table.add_row('[dim]Params:[/dim]', str(params))
            if headers:
                table.add_row('[dim]Headers:[/dim]', str(headers))
            console.print(table)

        try:
            response = await self.client.get(url, params=params, headers=headers)

            if self.verbose:
                console.print(f'[bold]Status:[/bold] {response.status_code}')

            if response.status_code in (502, 504):
                if self.verbose:
                    _log_error('Gateway Error', f'Status {response.status_code}')
                return {
                    'status_code': response.status_code,
                    'json': None,
                    'error': f'Gateway Error {response.status_code}',
                    'url': str(response.url),
                }

            try:
                data = response.json()
                if self.verbose:
                    _log_json(f'Response JSON ({method_name})', data)
                return {
                    'status_code': response.status_code,
                    'json': data,
                    'url': str(response.url),
                }
            except json.JSONDecodeError as e:
                if self.verbose:
                    _log_error('JSON Decode Error', str(e))
                    console.print(f'[dim]Raw text:[/dim] {response.text[:500]}')
                return {
                    'status_code': response.status_code,
                    'json': None,
                    'raw_text': response.text,
                    'url': str(response.url),
                }

        except httpx.TimeoutException:
            if self.verbose:
                _log_error('Timeout', 'Request timed out')
            return {'status_code': 0, 'json': None, 'error': 'Timeout'}
        except httpx.ConnectError as e:
            if self.verbose:
                _log_error('Connection Error', str(e))
            return {'status_code': 0, 'json': None, 'error': str(e)}

    # ---------------------------------------------------------------------
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ДЛЯ КООРДИНАТ
    # ---------------------------------------------------------------------

    def _find_lat_lon_in_obj(self, obj: Any) -> tuple[float, float] | None:
        """
        Рекурсивный поиск первой пары (lat, lon) в произвольном JSON.
        """
        lat_keys = {'lat', 'latitude', 'y'}
        lon_keys = {'lon', 'lng', 'longitude', 'x'}

        if isinstance(obj, dict):
            lat_val: float | None = None
            lon_val: float | None = None
            for k, v in obj.items():
                key = k.lower()
                if key in lat_keys:
                    try:
                        lat_val = float(v)
                    except (TypeError, ValueError):
                        pass
                if key in lon_keys:
                    try:
                        lon_val = float(v)
                    except (TypeError, ValueError):
                        pass
            if lat_val is not None and lon_val is not None:
                return lat_val, lon_val

            for v in obj.values():
                nested = self._find_lat_lon_in_obj(v)
                if nested is not None:
                    return nested

        if isinstance(obj, list):
            for item in obj:
                nested = self._find_lat_lon_in_obj(item)
                if nested is not None:
                    return nested

        return None

    async def _get_building_id_by_address(
        self,
        address_query: str,
    ) -> tuple[str | None, str | None, tuple[float, float] | None]:
        """
        Найти здание по текстовому адресу.

        Возвращает:
        - building_id (str | None)
        - full_address (str | None)
        - (lat, lon) или None, если координаты не удалось определить
        """
        res = await self.search_building_full_text_search(query=address_query, count=1)

        if res.get('status_code') != 200 or not res.get('json'):
            if self.verbose:
                _log_error('_get_building_id_by_address', f'Status {res.get("status_code")}')
            return None, None, None

        data = res['json']
        if isinstance(data, dict):
            buildings = data.get('data') or data.get('results') or []
        else:
            buildings = data

        if not buildings:
            return None, None, None

        first = buildings[0]

        building_id: str | None = None
        full_address: str | None = None
        lat: float | None = None
        lon: float | None = None

        if isinstance(first, dict):
            building_id = first.get('id') or first.get('building_id') or first.get('buildingId')
            full_address = (
                first.get('full_address') or first.get('address') or first.get('house_address')
            )
            coords = self._find_lat_lon_in_obj(first)
            if coords is not None:
                lat, lon = coords
        else:
            # fallback, если вдруг это Pydantic-модель
            for attr in ('id', 'building_id', 'buildingId'):
                if hasattr(first, attr):
                    building_id = getattr(first, attr)
                    break
            for attr in ('full_address', 'address', 'house_address'):
                if hasattr(first, attr):
                    full_address = getattr(first, attr)
                    break

        # Если координат нет, но есть building_id — дотягиваем через get_building_info
        if building_id and (lat is None or lon is None):
            info_res = await self.get_building_info(str(building_id))
            if info_res.get('status_code') == 200 and info_res.get('json') is not None:
                coords = self._find_lat_lon_in_obj(info_res['json'])
                if coords is not None:
                    lat, lon = coords

        if full_address is not None and not isinstance(full_address, str):
            full_address = str(full_address)

        coords_pair: tuple[float, float] | None
        if lat is not None and lon is not None:
            coords_pair = (lat, lon)
        else:
            coords_pair = None

        return (
            str(building_id) if building_id is not None else None,
            full_address,
            coords_pair,
        )

    async def _resolve_coords(
        self,
        lat: float | None = None,
        lon: float | None = None,
        building_id: str | None = None,
        address_query: str | None = None,
    ) -> tuple[float | None, float | None]:
        """
        Универсальное разрешение координат:
        - если lat & lon заданы, вернуть их;
        - иначе попытаться получить координаты по building_id;
        - иначе по address_query (через поиск здания).
        """
        # 1. Уже есть координаты
        if lat is not None and lon is not None:
            return lat, lon

        # 2. Пытаемся по building_id
        if building_id:
            res = await self.get_building_info(building_id)
            if res.get('status_code') == 200 and res.get('json') is not None:
                coords = self._find_lat_lon_in_obj(res['json'])
                if coords is not None:
                    return coords

        # 3. Пытаемся по address_query (в том же стиле, что _get_building_id_by_address)
        if address_query:
            _, _, coords = await self._get_building_id_by_address(address_query)
            if coords is not None:
                return coords

        return lat, lon

    def _drop_district_if_coords(
        self,
        params: dict[str, Any],
        lat: float | None,
        lon: float | None,
        district_keys: tuple[str, ...] = ('district',),
    ) -> None:
        """
        Если координаты заданы, выкидываем из params поля района.

        Используется для API, где либо район, либо координаты.
        """
        if lat is None and lon is None:
            return

        for key in district_keys:
            if key in params:
                params.pop(key, None)

    # ----------------------------------------
    # ГЕОКОДИНГ
    # ----------------------------------------

    async def search_building_full_text_search(
        self,
        query: str,
        count: int = 5,
    ) -> dict[str, Any]:
        """
        🔍 Ищет здания по адресу (полнотекстовый поиск).

        Endpoint: GET /geo/buildings/search/
        """
        url = f'{self.api_geo}/geo/buildings/search/'
        params = {
            'query': query,
            'count': min(count, 12),
            'region_of_search': self.region_id,
        }
        return await self._get_request('search_building', url, params)

    async def get_building_info(
        self,
        building_id: str,
        output_format: str = 'extended',
    ) -> dict[str, Any]:
        """
        🏠 Информация о здании по ID.

        Endpoint: GET /geo/buildings/{building_id}
        """
        url = f'{self.api_geo}/geo/buildings/{building_id}'
        params = {'format': output_format}
        return await self._get_request('get_building_info', url, params)

    async def get_districts(self) -> dict[str, Any]:
        """
        📍 Список районов СПб.

        Endpoint: GET /geo/district/
        """
        url = f'{self.api_geo}/geo/district/'
        return await self._get_request('get_districts', url)

    # =========================================================================
    # УПРАВЛЯЮЩИЕ КОМПАНИИ
    # =========================================================================

    async def get_management_company(
        self,
        building_id: str | None = None,
        address_query: str | None = None,
    ) -> dict[str, Any]:
        """
        🏢 УК по ID здания или по адресу.

        Endpoint: GET /api/v1/mancompany/{building_id}
        """
        if building_id is None and address_query:
            building_id, _, _ = await self._get_building_id_by_address(address_query)

        if not building_id:
            if self.verbose:
                _log_error('get_management_company', 'Не удалось определить building_id')
            return {
                'status_code': 0,
                'json': None,
                'error': 'building_id_or_address_query_required',
            }

        url = f'{self.api_geo_v1}/mancompany/{building_id}'
        params = {'region_of_search': self.region_id}
        return await self._get_request('get_management_company', url, params)

    async def get_management_company_company(
        self,
        company_id: str | None = None,
        company_name: str | None = None,
        company_inn: str | None = None,
    ) -> dict[str, Any]:
        """
        🏢 Информация об УК по ID / названию / ИНН.

        Endpoint: GET /api/v1/mancompany/company/
        """
        url = f'{self.api_geo_v1}/mancompany/company/'
        params: dict[str, Any] = {}
        if company_id:
            params['company_id'] = company_id
        if company_name:
            params['company_name'] = company_name
        if company_inn:
            params['company_inn'] = company_inn
        return await self._get_request('get_management_company_company', url, params or None)

    # =========================================================================
    # МФЦ
    # =========================================================================

    async def get_mfc_by_building(
        self,
        building_id: str | None = None,
        address_query: str | None = None,
    ) -> dict[str, Any]:
        """
        📋 МФЦ по ID здания или адресу.

        Endpoint: GET /mfc/
        """
        if building_id is None and address_query:
            building_id, _, _ = await self._get_building_id_by_address(address_query)

        if not building_id:
            if self.verbose:
                _log_error('get_mfc_by_building', 'Не удалось определить building_id')
            return {
                'status_code': 0,
                'json': None,
                'error': 'building_id_or_address_query_required',
            }

        url = f'{self.api_site}/mfc/'
        params = {'id_building': building_id}
        return await self._get_request('get_mfc_by_building', url, params)

    async def get_all_mfc(self) -> dict[str, Any]:
        """
        📋 Все МФЦ.

        Endpoint: GET /mfc/all/
        """
        url = f'{self.api_site}/mfc/all/'
        return await self._get_request('get_all_mfc', url)

    async def get_mfc_by_district(self, district: str) -> dict[str, Any]:
        """
        📋 МФЦ по району.

        Endpoint: GET /mfc/district/
        """
        url = f'{self.api_site}/mfc/district/'
        params = {'district': district}
        return await self._get_request('get_mfc_by_district', url, params)

    async def get_mfc_nearest_by_coords(
        self,
        lat: float | None = None,
        lon: float | None = None,
        distance_km: int = 5,
        building_id: str | None = None,
        address_query: str | None = None,
    ) -> dict[str, Any]:
        """
        📋 Ближайший МФЦ по координатам / building_id / адресу.

        Endpoint: GET /mfc/nearest
        """
        # Если координаты не заданы или есть address_query/building_id — пытаемся их разрешить
        if building_id is not None or address_query is not None or lat is None or lon is None:
            lat, lon = await self._resolve_coords(
                lat=lat,
                lon=lon,
                building_id=building_id,
                address_query=address_query,
            )

        if lat is None or lon is None:
            if self.verbose:
                _log_error(
                    'get_mfc_nearest_by_coords', 'Не удалось определить координаты пользователя'
                )
            return {
                'status_code': 0,
                'json': None,
                'error': 'coordinates_or_address_required',
            }

        url = f'{self.api_site}/mfc/nearest'

        async def _call(distance: int) -> dict[str, Any]:
            params = {
                'user_pos': f'{lon} {lat}',
                'distance': distance,
            }
            return await self._get_request('get_mfc_nearest_by_coords', url, params)

        res = await _call(distance_km)

        if distance_km != 5:
            return res

        if res.get('status_code') != 200:
            return res

        json_data = res.get('json')
        if json_data is None:
            return res

        is_empty = False
        if isinstance(json_data, dict):
            if 'data' in json_data:
                data_field = json_data['data']
                if isinstance(data_field, list) and len(data_field) == 0:
                    is_empty = True
            elif len(json_data) == 0:
                is_empty = True
        elif isinstance(json_data, list):
            if len(json_data) == 0:
                is_empty = True

        if not is_empty:
            return res

        fallback_res = await _call(10)
        return fallback_res

        # =========================================================================

    # ГОС ПАБЛИКИ (официальные паблики органов власти)
    # =========================================================================

    async def get_gos_publics_types(self) -> dict[str, Any]:
        """
        🏛️ Типы гос-пабликов.

        Endpoint: GET /gos-publics/type/
        """
        url = f'{self.api_site}/gos-publics/type/'
        return await self._get_request('get_gos_publics_types', url)

    async def get_gos_publics_map(
        self,
        gos_type: str | None = None,
        name: str | None = None,
        district: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        radius_km: int | None = None,
        page: int = 1,
        count: int = 50,
        building_id: str | None = None,
        address_query: str | None = None,
    ) -> dict[str, Any]:
        """
        🏛️ Гос-паблики на карте.

        Endpoint: GET /gos-publics/map/
        """
        url = f'{self.api_site}/gos-publics/map/'
        params: dict[str, Any] = {'page': page, 'count': count}
        if gos_type:
            params['type'] = gos_type
        if name:
            params['name'] = name
        if district:
            params['district'] = district

        lat, lon = await self._resolve_coords(
            lat=lat,
            lon=lon,
            building_id=building_id,
            address_query=address_query,
        )
        if lat is not None:
            params['location_latitude'] = lat
        if lon is not None:
            params['location_longitude'] = lon
        if radius_km is not None:
            params['location_radius'] = radius_km

        return await self._get_request('get_gos_publics_map', url, params)

    async def get_gos_public_by_id(self, gos_public_id: int) -> dict[str, Any]:
        """
        🏛️ Гос-паблик по ID.

        Endpoint: GET /gos-publics/{id}
        """
        url = f'{self.api_site}/gos-publics/{gos_public_id}'
        return await self._get_request('get_gos_public_by_id', url)

    # =========================================================================
    # ПОЛИКЛИНИКИ
    # =========================================================================

    async def get_polyclinics_by_building(
        self,
        building_id: str | None = None,
        address_query: str | None = None,
    ) -> dict[str, Any]:
        """
        🏥 Прикреплённые поликлиники по ID здания или адресу.

        Endpoint: GET /polyclinics/
        """
        if building_id is None and address_query:
            building_id, _, _ = await self._get_building_id_by_address(address_query)

        if not building_id:
            if self.verbose:
                _log_error('get_polyclinics_by_building', 'Не удалось определить building_id')
            return {
                'status_code': 0,
                'json': None,
                'error': 'building_id_or_address_query_required',
            }

        url = f'{self.api_site}/polyclinics/'
        params = {'id': building_id}
        return await self._get_request('get_polyclinics_by_building', url, params)

    # =========================================================================
    # ШКОЛЫ
    # =========================================================================

    async def get_linked_schools(
        self,
        building_id: str | None = None,
        scheme: int = 1,
        address_query: str | None = None,
    ) -> dict[str, Any]:
        """
        🏫 Прикреплённые школы по месту прописки (building_id или адрес).

        Endpoint: GET /school/linked/{building_id}
        """
        if building_id is None and address_query:
            building_id, _, _ = await self._get_building_id_by_address(address_query)

        if not building_id:
            if self.verbose:
                _log_error('get_linked_schools', 'Не удалось определить building_id')
            return {
                'status_code': 0,
                'json': None,
                'error': 'building_id_or_address_query_required',
            }

        url = f'{self.api_site}/school/linked/{building_id}'
        params = {'scheme': scheme}
        return await self._get_request('get_linked_schools', url, params)

    async def get_school_by_id(
        self,
        school_id: int,
        scheme: int | None = None,
    ) -> dict[str, Any]:
        """
        🏫 Школа по ID.

        Endpoint: GET /school/{school_id}
        """
        url = f'{self.api_site}/school/{school_id}'
        params: dict[str, Any] = {}
        if scheme is not None:
            params['scheme'] = scheme
        return await self._get_request('get_school_by_id', url, params or None)

    async def get_schools_map(
        self,
        district: str | None = None,
        org_type: str | None = None,
        profile: str | None = None,
        subject: str | None = None,
        available_spots: bool | None = None,
        scheme: int | None = None,
    ) -> dict[str, Any]:
        """
        🏫 Карта школ.

        Endpoint: GET /school/map/
        """
        url = f'{self.api_site}/school/map/'
        params: dict[str, Any] = {}
        if district:
            params['district'] = district
        if org_type:
            params['org_type'] = org_type
        if profile:
            params['profile'] = profile
        if subject:
            params['subject'] = subject
        if available_spots is not None:
            params['available_spots'] = str(available_spots).lower()
        if scheme is not None:
            params['scheme'] = scheme
        return await self._get_request('get_schools_map', url, params or None)

    async def get_school_kinds(self) -> dict[str, Any]:
        """
        🏫 Виды образовательных организаций.

        Endpoint: GET /school/kind/
        """
        url = f'{self.api_site}/school/kind/'
        return await self._get_request('get_school_kinds', url)

    async def get_school_profiles(self) -> dict[str, Any]:
        """
        🏫 Профили обучения.

        Endpoint: GET /school/profile/
        """
        url = f'{self.api_site}/school/profile/'
        return await self._get_request('get_school_profiles', url)

    async def get_school_stat(
        self,
        district: str | None = None,
        scheme: int | None = None,
    ) -> dict[str, Any]:
        """
        🏫 Статистика по школам.

        Endpoint: GET /school/stat/
        """
        url = f'{self.api_site}/school/stat/'
        params: dict[str, Any] = {}
        if district:
            params['district'] = district
        if scheme is not None:
            params['scheme'] = scheme
        return await self._get_request('get_school_stat', url, params or None)

    async def get_school_commissions(self, district: str) -> dict[str, Any]:
        """
        🏫 Школьные комиссии по району.

        Endpoint: GET /school/commissions/
        """
        url = f'{self.api_site}/school/commissions/'
        params = {'district': district}
        return await self._get_request('get_school_commissions', url, params)

    async def get_school_subjects(self) -> dict[str, Any]:
        """
        🏫 Предметы.

        Endpoint: GET /school/subject/
        """
        url = f'{self.api_site}/school/subject/'
        return await self._get_request('get_school_subjects', url)

    async def get_school_helpful(self) -> dict[str, Any]:
        """
        🏫 Полезная информация по школам.

        Endpoint: GET /school/helpful/
        """
        url = f'{self.api_site}/school/helpful/'
        return await self._get_request('get_school_helpful', url)

    async def get_school_available_spots_by_district(
        self,
        district: str | None = None,
    ) -> dict[str, Any]:
        """
        🏫 Наличие свободных мест по району.

        Endpoint: GET /school/available-spots/district/
        """
        url = f'{self.api_site}/school/available-spots/district/'
        params: dict[str, Any] = {}
        if district:
            params['district'] = district
        return await self._get_request(
            'get_school_available_spots_by_district', url, params or None
        )

    async def get_school_by_ogrn(self, ogrn: str) -> dict[str, Any]:
        """
        🏫 Школа по ОГРН.

        Endpoint: GET /school/ogrn/{ogrn}
        """
        url = f'{self.api_site}/school/ogrn/{ogrn}'
        return await self._get_request('get_school_by_ogrn', url)

        # =========================================================================
    # ДЕТСКИЕ САДЫ
    # =========================================================================

    async def get_dou(
        self,
        *,
        legal_form: str | None = None,
        district: str | None = None,
        age_year: int | None = None,
        age_month: int | None = None,
        group_type: str | None = None,
        group_shift: str | None = None,
        edu_program: list[str] | None = None,
        available_spots: int | None = None,
        disabled_type: str | None = None,
        recovery_type: str | None = None,
        doo_status: str | None = None,
    ) -> Any:
        """
        GET /dou/
        Получение детских садов в соответствии с выбранными фильтрами.
        """
        url = f'{self.api_site}/dou/'
        params: dict[str, Any] = {}

        if legal_form is not None:
            params['legal_form'] = legal_form
        if district is not None:
            params['district'] = district
        if age_year is not None:
            params['age_year'] = age_year
        if age_month is not None:
            params['age_month'] = age_month
        if group_type is not None:
            params['group_type'] = group_type
        if group_shift is not None:
            params['group_shift'] = group_shift
        if edu_program:
            # API объявлено как type=array; httpx закодирует повторяющиеся ключи
            params['edu_program'] = edu_program
        if available_spots is not None:
            params['available_spots'] = available_spots
        if disabled_type is not None:
            params['disabled_type'] = disabled_type
        if recovery_type is not None:
            params['recovery_type'] = recovery_type
        if doo_status is not None:
            params['doo_status'] = doo_status

        return await self._get_request('get_dou', url, params or None)

    async def get_dou_districts(self) -> Any:
        """
        GET /dou/district/
        Список всех районов.
        """
        url = f'{self.api_site}/dou/district/'
        return await self._get_request('get_dou_districts', url)

    async def get_dou_group_names(self) -> Any:
        """
        GET /dou/group-name/
        Список всех групп.
        """
        url = f'{self.api_site}/dou/group-name/'
        return await self._get_request('get_dou_group_names', url)

    async def get_dou_group_types(self) -> Any:
        """
        GET /dou/group-type/
        Список всех специфик групп.
        """
        url = f'{self.api_site}/dou/group-type/'
        return await self._get_request('get_dou_group_types', url)

    async def get_dou_group_shifts(self) -> Any:
        """
        GET /dou/group-shift/
        Список всех режимов работы групп.
        """
        url = f'{self.api_site}/dou/group-shift/'
        return await self._get_request('get_dou_group_shifts', url)

    async def get_dou_edu_programs(self) -> Any:
        """
        GET /dou/edu-program/
        Список всех видов образовательных программ.
        """
        url = f'{self.api_site}/dou/edu-program/'
        return await self._get_request('get_dou_edu_programs', url)

    async def get_dou_disabled_types(self) -> Any:
        """
        GET /dou/disabled-type/
        Список всех типов групп с ОВЗ.
        """
        url = f'{self.api_site}/dou/disabled-type/'
        return await self._get_request('get_dou_disabled_types', url)

    async def get_dou_recovery_types(self) -> Any:
        """
        GET /dou/recovery-type/
        Список всех типов оздоровительных групп.
        """
        url = f'{self.api_site}/dou/recovery-type/'
        return await self._get_request('get_dou_recovery_types', url)

    async def get_dou_legal_forms(self) -> Any:
        """
        GET /dou/legal-form/
        Список типов принадлежности детских садов.
        """
        url = f'{self.api_site}/dou/legal-form/'
        return await self._get_request('get_dou_legal_forms', url)

    async def get_dou_disabled_types_by_group_type(
        self,
        *,
        group_type: str | None = None,
    ) -> Any:
        """
        GET /dou/group-type/disabled-type/
        Типы групп с ОВЗ, относящиеся к конкретной специфике группы.
        """
        url = f'{self.api_site}/dou/group-type/disabled-type/'
        params: dict[str, Any] = {}
        if group_type is not None:
            params['group_type'] = group_type

        return await self._get_request('get_dou_disabled_types_by_group_type', url, params or None)

    async def get_dou_recovery_types_by_group_type(
        self,
        *,
        group_type: str | None = None,
    ) -> Any:
        """
        GET /dou/group-type/recovery-type/
        Типы оздоровительных групп, относящиеся к конкретной специфике группы.
        """
        url = f'{self.api_site}/dou/group-type/recovery-type/'
        params: dict[str, Any] = {}
        if group_type is not None:
            params['group_type'] = group_type

        return await self._get_request('get_dou_recovery_types_by_group_type', url, params or None)

    async def get_dou_available_spots(self) -> Any:
        """
        GET /dou/available-spots/
        Общая сумма свободных мест в детских садах СПб.
        """
        url = f'{self.api_site}/dou/available-spots/'
        return await self._get_request('get_dou_available_spots', url)

    async def get_dou_available_spots_by_district(
        self,
        *,
        district: str | None = None,
    ) -> Any:
        """
        GET /dou/available-spots/district/
        Общая сумма свободных мест в детских садах по району.
        """
        url = f'{self.api_site}/dou/available-spots/district/'
        params: dict[str, Any] = {}
        if district is not None:
            params['district'] = district

        return await self._get_request('get_dou_available_spots_by_district', url, params or None)

    async def get_dou_short_titles(self) -> Any:
        """
        GET /dou/dou-title/
        Список сокращённых наименований детских садов (без фильтрации).
        """
        url = f'{self.api_site}/dou/dou-title/'
        return await self._get_request('get_dou_short_titles', url)

    async def search_dou_by_short_title(
        self,
        *,
        doutitle: str,
    ) -> Any:
        """
        GET /dou/
        Поиск детских садов по короткому наименованию (doutitle).
        """
        url = f'{self.api_site}/dou/'
        params: dict[str, Any] = {'doutitle': doutitle}
        return await self._get_request('search_dou_by_short_title', url, params)

    async def get_dou_by_id(
        self,
        *,
        id: int | None = None,
        doo_id: int | None = None,
        building_id: str | None = None,
        group_name: str | None = None,
        doo_full: str | None = None,
        district: str | None = None,
        age_year: int | None = None,
        age_month: int | None = None,
        group_type: str | None = None,
        group_shift: str | None = None,
        edu_program: str | None = None,
        available_spots: int | None = None,
        disabled_type: str | None = None,
        recovery_type: str | None = None,
        doo_status: str | None = None,
    ) -> Any:
        """
        GET /dou/by_id/
        Объекты раздела «Детские сады» с фильтрами (в т.ч. по id и doo_id).
        """
        url = f'{self.api_site}/dou/by_id/'
        params: dict[str, Any] = {}

        if id is not None:
            params['id'] = id
        if doo_id is not None:
            params['doo_id'] = doo_id
        if building_id is not None:
            params['building_id'] = building_id
        if group_name is not None:
            params['group_name'] = group_name
        if doo_full is not None:
            params['doo_full'] = doo_full
        if district is not None:
            params['district'] = district
        if age_year is not None:
            params['age_year'] = age_year
        if age_month is not None:
            params['age_month'] = age_month
        if group_type is not None:
            params['group_type'] = group_type
        if group_shift is not None:
            params['group_shift'] = group_shift
        if edu_program is not None:
            params['edu_program'] = edu_program
        if available_spots is not None:
            params['available_spots'] = available_spots
        if disabled_type is not None:
            params['disabled_type'] = disabled_type
        if recovery_type is not None:
            params['recovery_type'] = recovery_type
        if doo_status is not None:
            params['doo_status'] = doo_status

        return await self._get_request('get_dou_by_id', url, params or None)

    async def get_dou_commissions(
        self,
        *,
        district: str,
    ) -> Any:
        """
        GET /dou/commissions/
        Список ответственных организаций по району.
        Параметр district обязателен по спецификации.
        """
        url = f'{self.api_site}/dou/commissions/'
        params = {'district': district}
        return await self._get_request('get_dou_commissions', url, params)


    # =========================================================================
    # РАЙОН - СПРАВКА
    # =========================================================================

    async def get_district_info_by_building(
        self,
        building_id: str | None = None,
        address_query: str | None = None,
    ) -> dict[str, Any]:
        """
        📊 Справка по району (по building_id или адресу).

        Endpoint: GET /districts-info/building-id/{id}
        """
        if building_id is None and address_query:
            building_id, _, _ = await self._get_building_id_by_address(address_query)

        if not building_id:
            if self.verbose:
                _log_error('get_district_info_by_building', 'Не удалось определить building_id')
            return {
                'status_code': 0,
                'json': None,
                'error': 'building_id_or_address_query_required',
            }

        url = f'{self.api_site}/districts-info/building-id/{building_id}'
        return await self._get_request('get_district_info_by_building', url)

    async def get_district_info_by_name(self, district_name: str) -> dict[str, Any]:
        """
        📊 Справка по району (по названию).

        Endpoint: GET /districts-info/district/
        """
        url = f'{self.api_site}/districts-info/district/'
        params = {'district_name': district_name}
        return await self._get_request('get_district_info_by_name', url, params)

    # =========================================================================
    # ОТКЛЮЧЕНИЯ
    # =========================================================================

    async def get_disconnections(
        self,
        building_id: str | None = None,
        address_query: str | None = None,
    ) -> dict[str, Any]:
        """
        ⚡ Отключения по ID здания или адресу.

        Endpoint: GET /disconnections/
        """
        if building_id is None and address_query:
            building_id, _, _ = await self._get_building_id_by_address(address_query)

        if not building_id:
            if self.verbose:
                _log_error('get_disconnections', 'Не удалось определить building_id')
            return {
                'status_code': 0,
                'json': None,
                'error': 'building_id_or_address_query_required',
            }

        url = f'{self.api_site}/disconnections/'
        params = {'id': building_id}
        return await self._get_request('get_disconnections', url, params)

    # =========================================================================
    # СПОРТ (список)
    # =========================================================================

    async def get_sport_events(
        self,
        district: str | None = None,
        categoria: str | list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        count: int = 10,
    ) -> dict[str, Any]:
        """
        🏅 Спортивные мероприятия.

        Endpoint: GET /sport-events/
        """
        url = f'{self.api_site}/sport-events/'
        params: dict[str, Any] = {'count': count, 'page': 1}
        if district:
            params['district'] = district
        if categoria:
            if isinstance(categoria, list):
                # TODO: множественный выбор категорий (через запятую)
                params['categoria'] = ','.join(categoria)
            else:
                params['categoria'] = categoria
        if start_date:
            params['start_date'] = start_date
        if end_date:
            params['end_date'] = end_date
        return await self._get_request('get_sport_events', url, params)

    async def get_sportgrounds(
        self,
        district: str | None = None,
        types: str | list[str] | None = None,
        count: int = 10,
        lat: float | None = None,
        lon: float | None = None,
        radius_km: int | None = None,
        building_id: str | None = None,
        address_query: str | None = None,
    ) -> dict[str, Any]:
        """
        🏟️ Спортплощадки (список).

        Endpoint: GET /sportgrounds/
        """
        url = f'{self.api_site}/sportgrounds/'
        params: dict[str, Any] = {'count': count, 'page': 1}
        if district:
            params['district'] = district
        if types:
            if isinstance(types, list):
                # TODO: множественный выбор типов (через запятую)
                params['types'] = ','.join(types)
            else:
                params['types'] = types

        lat, lon = await self._resolve_coords(
            lat=lat,
            lon=lon,
            building_id=building_id,
            address_query=address_query,
        )
        if lat is not None:
            params['location_latitude'] = lat
        if lon is not None:
            params['location_longitude'] = lon
        if radius_km is not None:
            params['location_radius'] = radius_km

        self._drop_district_if_coords(params, lat, lon, district_keys=('district',))

        return await self._get_request('get_sportgrounds', url, params)

    async def get_sportgrounds_count(self) -> dict[str, Any]:
        """
        🏟️ Общая статистика спортплощадок.

        Endpoint: GET /sportgrounds/count/
        """
        url = f'{self.api_site}/sportgrounds/count/'
        return await self._get_request('get_sportgrounds_count', url)

    # =========================================================================
    # АФИША / МЕРОПРИЯТИЯ
    # =========================================================================

    async def get_events(
        self,
        start_date: str,
        end_date: str,
        categoria: str | list[str] | None = None,
        separation: bool | None = None,
        free: bool | None = None,
        kids: bool | None = None,
        lat: float | None = None,
        lon: float | None = None,
        radius_km: int | None = None,
        count: int = 10,
        page: int = 1,
        service: str | None = None,
        building_id: str | None = None,
        address_query: str | None = None,
    ) -> dict[str, Any]:
        """
        🎭 Мероприятия (афиша).

        Endpoint: GET /afisha/all/
        """
        url = f'{self.api_site}/afisha/all/'
        params: dict[str, Any] = {
            'start_date': start_date,
            'end_date': end_date,
            'count': count,
            'page': page,
        }
        if separation is not None:
            params['separation'] = str(separation).lower()
        if categoria:
            if isinstance(categoria, list):
                # TODO: множественный выбор категорий (через запятую)
                params['categoria'] = ','.join(categoria)
            else:
                params['categoria'] = categoria
        if free is not None:
            params['free'] = str(free).lower()
        if kids is not None:
            params['kids'] = str(kids).lower()
        if service:
            params['service'] = service

        lat, lon = await self._resolve_coords(
            lat=lat,
            lon=lon,
            building_id=building_id,
            address_query=address_query,
        )
        if lat is not None:
            params['location_latitude'] = lat
        if lon is not None:
            params['location_longitude'] = lon
        if radius_km is not None:
            params['location_radius'] = radius_km

        self._drop_district_if_coords(params, lat, lon, district_keys=('district',))

        return await self._get_request('get_events', url, params)

    async def get_event_categories(
        self,
        start_date: str,
        end_date: str,
        service: str | None = None,
    ) -> dict[str, Any]:
        """
        🎭 Категории мероприятий.

        Endpoint: GET /afisha/category/all/
        """
        url = f'{self.api_site}/afisha/category/all/'
        params: dict[str, Any] = {
            'start_date': start_date,
            'end_date': end_date,
        }
        if service:
            params['service'] = service
        return await self._get_request('get_event_categories', url, params)

    # =========================================================================
    # ПЕНСИОНЕРЫ
    # =========================================================================

    async def get_pensioner_categories(self) -> dict[str, Any]:
        """
        👴 Категории услуг для пенсионеров.

        Endpoint: GET /pensioner/services/category/
        """
        url = f'{self.api_site}/pensioner/services/category/'
        return await self._get_request('get_pensioner_categories', url)

    async def get_pensioner_services(
        self,
        district: str | None = None,
        category: str | list[str] | None = None,
        location_title: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        radius_km: int | None = None,
        count: int = 10,
        page: int = 1,
        egs: bool | None = None,
        building_id: str | None = None,
        address_query: str | None = None,
    ) -> dict[str, Any]:
        """
        👴 Услуги для пенсионеров.

        Endpoint: GET /pensioner/services/
        """
        url = f'{self.api_site}/pensioner/services/'
        params: dict[str, Any] = {'count': count, 'page': page}
        if location_title:
            params['location_title'] = location_title
        if category:
            if isinstance(category, list):
                # TODO: множественный выбор категорий (через запятую)
                params['category'] = ','.join(category)
            else:
                params['category'] = category
        if district:
            params['district'] = district
        if egs is not None:
            params['egs'] = str(egs).lower()

        lat, lon = await self._resolve_coords(
            lat=lat,
            lon=lon,
            building_id=building_id,
            address_query=address_query,
        )
        if lat is not None:
            params['location_latitude'] = lat
        if lon is not None:
            params['location_longitude'] = lon
        if radius_km is not None:
            params['location_radius'] = radius_km

        self._drop_district_if_coords(params, lat, lon, district_keys=('district',))

        return await self._get_request('get_pensioner_services', url, params)

    async def get_pensioner_hotlines(self) -> dict[str, Any]:
        """
        👴 Горячие линии для пенсионеров (все).

        Endpoint: GET /pensioner/hotlines/
        """
        url = f'{self.api_site}/pensioner/hotlines/'
        return await self._get_request('get_pensioner_hotlines', url)

    async def get_pensioner_hotlines_by_district(self, district: str) -> dict[str, Any]:
        """
        👴 Горячие линии для пенсионеров по району.

        Endpoint: GET /pensioner/hotlines/district/
        """
        url = f'{self.api_site}/pensioner/hotlines/district/'
        params = {'district': district}
        return await self._get_request('get_pensioner_hotlines_by_district', url, params)

    async def get_pensioner_service_by_id(
        self, service_id: int, egs: bool | None
    ) -> dict[str, Any]:
        """
        👴 Услуга для пенсионеров по ID.

        Endpoint: GET /pensioner/services/{id}
        """
        url = f'{self.api_site}/pensioner/services/{service_id}'
        params = {'egs': egs}
        return await self._get_request('get_pensioner_service_by_id', url, params=params)

    async def get_pensioner_services_by_district(self) -> dict[str, Any]:
        """
        👴 Сводка услуг по районам.

        Endpoint: GET /pensioner/services/district/
        """
        url = f'{self.api_site}/pensioner/services/district/'
        return await self._get_request('get_pensioner_services_by_district', url)

    async def get_pensioner_services_location(
        self,
        category: str | None = None,
        district: str | None = None,
    ) -> dict[str, Any]:
        """
        👴 Локации услуг для пенсионеров (агрегированно по району/категории).

        Endpoint: GET /pensioner/services/location/
        """
        url = f'{self.api_site}/pensioner/services/location/'
        params: dict[str, Any] = {}
        if category:
            params['category'] = category
        if district:
            params['district'] = district
        return await self._get_request('get_pensioner_services_location', url, params or None)

    async def get_pensioner_sports_location(
        self,
        category: str | None = None,
        district: str | None = None,
    ) -> dict[str, Any]:
        """
        👴 Спортивные локации для пенсионеров по району/категории.

        Endpoint: GET /pensioner/sports/location/
        """
        url = f'{self.api_site}/pensioner/sports/location/'
        params: dict[str, Any] = {}
        if category:
            params['category'] = category
        if district:
            params['district'] = district
        return await self._get_request('get_pensioner_sports_location', url, params or None)

    async def get_pensioner_map_categories(self) -> dict[str, Any]:
        """
        👴 Категории объектов на карте.

        Endpoint: GET /pensioner/map/category/
        """
        url = f'{self.api_site}/pensioner/map/category/'
        return await self._get_request('get_pensioner_map_categories', url)

    async def get_pensioner_map(
        self,
        category: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        radius_km: int | None = None,
        building_id: str | None = None,
        address_query: str | None = None,
    ) -> dict[str, Any]:
        """
        👴 Объекты на карте для пенсионеров.

        Endpoint: GET /pensioner/map/
        """
        url = f'{self.api_site}/pensioner/map/'
        params: dict[str, Any] = {}
        if category:
            params['category'] = category

        lat, lon = await self._resolve_coords(
            lat=lat,
            lon=lon,
            building_id=building_id,
            address_query=address_query,
        )
        if lat is not None:
            params['location_latitude'] = lat
        if lon is not None:
            params['location_longitude'] = lon
        if radius_km is not None:
            params['location_radius'] = radius_km

        return await self._get_request('get_pensioner_map', url, params or None)

    async def get_pensioner_map_by_id(self, obj_id: int) -> dict[str, Any]:
        """
        👴 Объект карты по ID.

        Endpoint: GET /pensioner/map/{id}
        """
        url = f'{self.api_site}/pensioner/map/{obj_id}'
        return await self._get_request('get_pensioner_map_by_id', url)

    async def get_pensioner_posts_categories(self) -> dict[str, Any]:
        """
        👴 Категории постов (материалы для пенсионеров).

        Endpoint: GET /pensioner/posts/category/
        """
        url = f'{self.api_site}/pensioner/posts/category/'
        return await self._get_request('get_pensioner_posts_categories', url)

    async def get_pensioner_posts(
        self,
        category: str | None = None,
        page: int = 1,
        count: int = 10,
    ) -> dict[str, Any]:
        """
        👴 Посты/статьи для пенсионеров.

        Endpoint: GET /pensioner/posts/
        """
        url = f'{self.api_site}/pensioner/posts/'
        params: dict[str, Any] = {'page': page, 'count': count}
        if category:
            params['category'] = category
        return await self._get_request('get_pensioner_posts', url, params)

    async def get_pensioner_post_by_id(self, post_id: int) -> dict[str, Any]:
        """
        👴 Пост для пенсионеров по ID.

        Endpoint: GET /pensioner/posts/{id}
        """
        url = f'{self.api_site}/pensioner/posts/{post_id}'
        return await self._get_request('get_pensioner_post_by_id', url)

    async def get_pensioner_charity_categories(self) -> dict[str, Any]:
        """
        👴 Категории благотворительности.

        Endpoint: GET /pensioner/charity/category/
        """
        url = f'{self.api_site}/pensioner/charity/category/'
        return await self._get_request('get_pensioner_charity_categories', url)

    async def get_pensioner_charity(
        self,
        category: str | None = None,
        district: str | None = None,
        page: int = 1,
        count: int = 10,
    ) -> dict[str, Any]:
        """
        👴 Благотворительные организации/проекты для пенсионеров.

        Endpoint: GET /pensioner/charity/
        """
        url = f'{self.api_site}/pensioner/charity/'
        params: dict[str, Any] = {'page': page, 'count': count}
        if category:
            params['category'] = category
        if district:
            params['district'] = district
        return await self._get_request('get_pensioner_charity', url, params)

    async def get_pensioner_charity_by_id(self, charity_id: int) -> dict[str, Any]:
        """
        👴 Благотворительный проект по ID.

        Endpoint: GET /pensioner/charity/{id}
        """
        url = f'{self.api_site}/pensioner/charity/{charity_id}'
        return await self._get_request('get_pensioner_charity_by_id', url)

    # =========================================================================
    # ПИТОМЦЫ (простые)
    # =========================================================================

    async def get_vet_clinics(
        self,
        lat: float | None = None,
        lon: float | None = None,
        radius_km: int = 10,
        building_id: str | None = None,
        address_query: str | None = None,
    ) -> dict[str, Any]:
        """
        🐕 Ветеринарные клиники.

        Endpoint: GET /mypets/all-category/
        """
        url = f'{self.api_site}/mypets/all-category/'
        params: dict[str, Any] = {'type': 'Ветклиника'}

        lat, lon = await self._resolve_coords(
            lat=lat,
            lon=lon,
            building_id=building_id,
            address_query=address_query,
        )
        if lat is not None and lon is not None:
            params['location_latitude'] = lat
            params['location_longitude'] = lon
            params['location_radius'] = radius_km

        return await self._get_request('get_vet_clinics', url, params)

    async def get_pet_parks(
        self,
        lat: float | None = None,
        lon: float | None = None,
        radius_km: int = 7,
        building_id: str | None = None,
        address_query: str | None = None,
    ) -> dict[str, Any]:
        """
        🐕 Парки для питомцев.

        Endpoint: GET /mypets/all-category/
        """
        url = f'{self.api_site}/mypets/all-category/'
        params: dict[str, Any] = {'type': 'Парк'}

        lat, lon = await self._resolve_coords(
            lat=lat,
            lon=lon,
            building_id=building_id,
            address_query=address_query,
        )
        if lat is not None and lon is not None:
            params['location_latitude'] = lat
            params['location_longitude'] = lon
            params['location_radius'] = radius_km

        return await self._get_request('get_pet_parks', url, params)

    async def get_mypets_all_category_by_id(self, item_id: int) -> dict[str, Any]:
        """
        🐾 Мой питомец: категория/объект по id.

        Endpoint: GET /mypets/all-category/id/

        Параметры соответствуют спецификации API :contentReference[oaicite:3]{index=3}:
        - id (query): целочисленный идентификатор категории или объекта.
        """
        url = f'{self.api_site}/mypets/all-category/id/'
        params = {'id': item_id}
        return await self._get_request('get_mypets_all_category_by_id', url, params)

    # =========================================================================
    # КРАСИВЫЕ МЕСТА
    # =========================================================================

    async def get_beautiful_places(
        self,
        district: str | None = None,
        categoria: str | list[str] | None = None,
        area: str | None = None,
        keywords: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        radius_km: int | None = None,
        count: int = 10,
        page: int = 1,
        building_id: str | None = None,
        address_query: str | None = None,
    ) -> dict[str, Any]:
        """
        🏛️ Красивые места.

        Endpoint: GET /beautiful_places/
        """
        url = f'{self.api_site}/beautiful_places/'
        params: dict[str, Any] = {'count': count, 'page': page}
        if district:
            params['district'] = district
        if categoria:
            if isinstance(categoria, list):
                # TODO: множественный выбор категорий (через запятую)
                params['categoria'] = ','.join(categoria)
            else:
                params['categoria'] = categoria
        if area:
            params['area'] = area
        if keywords:
            params['keywords'] = keywords

        lat, lon = await self._resolve_coords(
            lat=lat,
            lon=lon,
            building_id=building_id,
            address_query=address_query,
        )
        if lat is not None:
            params['location_latitude'] = lat
        if lon is not None:
            params['location_longitude'] = lon
        if radius_km is not None:
            params['location_radius'] = radius_km

        # Документация: либо район, либо координаты
        self._drop_district_if_coords(params, lat, lon, district_keys=('district',))

        return await self._get_request('get_beautiful_places', url, params)

    async def get_beautiful_place_by_id(self, ids: int) -> dict[str, Any]:
        """
        🏛️ Красивые места по ID.

        Endpoint: GET /beautiful_places/id/
        """
        url = f'{self.api_site}/beautiful_places/id/'
        params = {'ids': ids}
        return await self._get_request('get_beautiful_place_by_id', url, params)

    async def get_beautiful_places_area(self) -> dict[str, Any]:
        """
        🏛️ Области интересных мест.

        Endpoint: GET /beautiful_places/area/
        """
        url = f'{self.api_site}/beautiful_places/area/'
        return await self._get_request('get_beautiful_places_area', url)

    async def get_beautiful_places_area_districts(
        self,
        area: str | None = None,
    ) -> dict[str, Any]:
        """
        🏛️ Районы по области.

        Endpoint: GET /beautiful_places/area/district/
        """
        url = f'{self.api_site}/beautiful_places/area/district/'
        params: dict[str, Any] = {}
        if area:
            params['area'] = area
        return await self._get_request('get_beautiful_places_area_districts', url, params or None)

    async def get_beautiful_places_categoria(self) -> dict[str, Any]:
        """
        🏛️ Категории интересных мест.

        Endpoint: GET /beautiful_places/categoria/
        """
        url = f'{self.api_site}/beautiful_places/categoria/'
        return await self._get_request('get_beautiful_places_categoria', url)

    async def get_beautiful_places_keywords(self) -> dict[str, Any]:
        """
        🏛️ Ключевые слова интересных мест.

        Endpoint: GET /beautiful_places/keywords/
        """
        url = f'{self.api_site}/beautiful_places/keywords/'
        return await self._get_request('get_beautiful_places_keywords', url)

    async def get_beautiful_place_routes(
        self,
        theme: str | list[str] | None = None,
        route_type: str | None = None,
        access_for_disabled: bool | None = None,
        length_km_from: int | None = None,
        length_km_to: int | None = None,
        daypart: str | None = None,
        category: str | None = None,
        price_range: str | None = None,
        distance_range: str | None = None,
        keys: str | None = None,
        order_by: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        radius_km: int | None = None,
        page: int = 1,
        count: int = 10,
        uid: str | None = None,
        expanded: bool | None = None,
        building_id: str | None = None,
        address_query: str | None = None,
    ) -> dict[str, Any]:
        """
        🚶 Туристические маршруты.

        Endpoint: GET /beautiful_places/routes/all/
        """
        url = f'{self.api_site}/beautiful_places/routes/all/'
        params: dict[str, Any] = {'count': count, 'page': page}
        if theme:
            if isinstance(theme, list):
                # TODO: множественный выбор тем (через запятую)
                params['theme'] = ','.join(theme)
            else:
                params['theme'] = theme
        if route_type:
            params['type'] = route_type
        if access_for_disabled is not None:
            params['access_for_disabled'] = str(access_for_disabled).lower()
        if length_km_from is not None:
            params['length_km_from'] = length_km_from
        if length_km_to is not None:
            params['length_km_to'] = length_km_to
        if daypart:
            params['daypart'] = daypart
        if category:
            params['category'] = category
        if price_range:
            params['price_range'] = price_range
        if distance_range:
            params['distance_range'] = distance_range
        if keys:
            params['keys'] = keys
        if order_by:
            params['order_by'] = order_by
        if uid:
            params['uid'] = uid
        if expanded is not None:
            params['expanded'] = str(expanded).lower()

        lat, lon = await self._resolve_coords(
            lat=lat,
            lon=lon,
            building_id=building_id,
            address_query=address_query,
        )
        if lat is not None:
            params['location_latitude'] = lat
        if lon is not None:
            params['location_longitude'] = lon
        if radius_km is not None:
            params['location_radius'] = radius_km

        return await self._get_request('get_beautiful_place_routes', url, params)

    async def get_beautiful_place_routes_by_id(self, ids: int) -> dict[str, Any]:
        """
        🚶 Турмаршрут по ID.

        Endpoint: GET /beautiful_places/routes/id/
        """
        url = f'{self.api_site}/beautiful_places/routes/id/'
        params = {'ids': ids}
        return await self._get_request('get_beautiful_place_routes_by_id', url, params)

    async def get_beautiful_place_routes_themes(self) -> dict[str, Any]:
        """
        🚶 Темы маршрутов.

        Endpoint: GET /beautiful_places/routes/theme/
        """
        url = f'{self.api_site}/beautiful_places/routes/theme/'
        return await self._get_request('get_beautiful_place_routes_themes', url)

    async def get_beautiful_place_routes_types(self) -> dict[str, Any]:
        """
        🚶 Типы маршрутов.

        Endpoint: GET /beautiful_places/routes/type/
        """
        url = f'{self.api_site}/beautiful_places/routes/type/'
        return await self._get_request('get_beautiful_place_routes_types', url)

    # =========================================================================
    # НОВОСТИ
    # =========================================================================

    async def get_news_role(self) -> dict[str, Any]:
        """
        📰 Типы/роли новостей.

        Endpoint: GET /news/role/
        """
        url = f'{self.api_site}/news/role/'
        return await self._get_request('get_news_role', url)

    async def get_news_districts(self) -> dict[str, Any]:
        """
        📰 Районы для новостей.

        Endpoint: GET /news/districts/
        """
        url = f'{self.api_site}/news/districts/'
        return await self._get_request('get_news_districts', url)

    async def get_news(
        self,
        district: str | None = None,
        description: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        yazzh_type: str | list[str] | None = None,
        building_id: str | None = None,
        address_query: str | None = None,
        count: int = 10,
        page: int = 1,
    ) -> dict[str, Any]:
        """
        📰 Новости.

        Endpoint: GET /news/

        Параметры:
        - building (query): building_id пользователя. Если указан building,
          district НЕ отправляем.
        - district (query): район, используется только если building не задан.
        - address_query: текстовый адрес, из которого определяется building_id.
        """
        url = f'{self.api_site}/news/'
        params: dict[str, Any] = {'count': count, 'page': page}

        if description:
            params['description'] = description
        if start_date:
            params['start_date'] = start_date
        if end_date:
            params['end_date'] = end_date

        if yazzh_type:
            if isinstance(yazzh_type, list):
                params['yazzh_type'] = ','.join(yazzh_type)
            else:
                params['yazzh_type'] = yazzh_type

        # building_id может прийти явно или из address_query
        effective_building_id = building_id
        if effective_building_id is None and address_query:
            effective_building_id, _, _ = await self._get_building_id_by_address(address_query)

        if effective_building_id:
            params['building'] = effective_building_id
        elif district:
            # building не задан — можно фильтровать по району
            params['district'] = district

        return await self._get_request('get_news', url, params)

    async def get_news_top(
        self,
        district: str,
        start_date: str | None = None,
        page: int = 1,
        count: int = 10,
    ) -> dict[str, Any]:
        """
        📰 Топ новостей по району.

        Endpoint: GET /news/top
        """
        url = f'{self.api_site}/news/top'
        params: dict[str, Any] = {
            'district': district,
            'page': page,
            'count': count,
        }
        if start_date:
            params['start_date'] = start_date
        return await self._get_request('get_news_top', url, params)

    # =========================================================================
    # ПАМЯТНЫЕ ДАТЫ
    # =========================================================================

    async def get_memorable_dates_all(self) -> dict[str, Any]:
        """
        📅 Все памятные даты.

        Endpoint: GET /memorable_dates/
        """
        url = f'{self.api_site}/memorable_dates/'
        return await self._get_request('get_memorable_dates_all', url)

    async def get_memorable_dates_by_ids(self, ids: int) -> dict[str, Any]:
        """
        📅 Памятные даты по ID (одно число).

        Endpoint: GET /memorable_dates/ids/
        """
        url = f'{self.api_site}/memorable_dates/ids/'
        params = {'ids': ids}
        return await self._get_request('get_memorable_dates_by_ids', url, params)

    async def get_memorable_dates_by_day(self, day: int, month: int) -> dict[str, Any]:
        """
        📅 Памятные даты по дню.

        Endpoint: GET /memorable_dates/date/
        """
        url = f'{self.api_site}/memorable_dates/date/'
        params = {'day': day, 'month': month}
        return await self._get_request('get_memorable_dates_by_day', url, params)

    # =========================================================================
    # ПИТОМЦЫ (расширенные MyPets)
    # =========================================================================

    async def get_mypets_all_category(
        self,
        lat: float | None = None,
        lon: float | None = None,
        radius_km: int | None = None,
        types: str | None = None,
        building_id: str | None = None,
        address_query: str | None = None,
    ) -> dict[str, Any]:
        """
        🐕 Все категории объектов для питомцев.

        Endpoint: GET /mypets/all-category/
        """
        url = f'{self.api_site}/mypets/all-category/'
        params: dict[str, Any] = {}
        if types:
            # TODO: множественный выбор типов (массив строк) (можно сделать, но зачем?)
            params['type'] = types

        lat, lon = await self._resolve_coords(
            lat=lat,
            lon=lon,
            building_id=building_id,
            address_query=address_query,
        )
        if lat is not None:
            params['location_latitude'] = lat
        if lon is not None:
            params['location_longitude'] = lon
        if radius_km is not None:
            params['location_radius'] = radius_km

        return await self._get_request('get_mypets_all_category', url, params or None)

    async def get_mypets_animal_breeds(
        self,
        specie: str | None = None,
        breed: str | None = None,
    ) -> dict[str, Any]:
        """
        🐕 Породы животных.

        Endpoint: GET /mypets/animal-breeds/
        """
        url = f'{self.api_site}/mypets/animal-breeds/'
        params: dict[str, Any] = {}
        if specie:
            params['specie'] = specie
        if breed:
            params['breed'] = breed
        return await self._get_request('get_mypets_animal_breeds', url, params or None)

    async def get_mypets_holidays(self) -> dict[str, Any]:
        """
        🐕 Праздники для питомцев.

        Endpoint: GET /mypets/holidays/
        """
        url = f'{self.api_site}/mypets/holidays/'
        return await self._get_request('get_mypets_holidays', url)

    async def get_mypets_posts(
        self,
        specie: str | None = None,
        page: int = 1,
        size: int = 10,
    ) -> dict[str, Any]:
        """
        🐕 Посты про питомцев.

        Endpoint: GET /mypets/posts/
        """
        url = f'{self.api_site}/mypets/posts/'
        params: dict[str, Any] = {'page': page, 'size': size}
        if specie:
            params['specie'] = specie
        return await self._get_request('get_mypets_posts', url, params)

    async def get_mypets_posts_id(self, posts_id: int) -> dict[str, Any]:
        """
        🐕 Пост по ID.

        Endpoint: GET /mypets/posts/id/
        """
        url = f'{self.api_site}/mypets/posts/id/'
        params = {'id': posts_id}
        return await self._get_request('get_mypets_posts_id', url, params)

    async def get_mypets_recommendations_by_page(
        self,
        page: int = 1,
        specie: str | None = None,
        size: int = 10,
    ) -> dict[str, Any]:
        """
        🐕 Рекомендации и советы.

        Endpoint: GET /mypets/recommendations/
        """
        url = f'{self.api_site}/mypets/recommendations/'
        params: dict[str, Any] = {'page': page, 'size': size}
        if specie:
            params['specie'] = specie
        return await self._get_request('get_mypets_recommendations', url, params)

    async def get_mypets_clinics_by_coord(
        self,
        services: list[str] | None = None,
        lat: float | None = None,
        lon: float | None = None,
        radius_km: int = 10,
        building_id: str | None = None,
        address_query: str | None = None,
    ) -> dict[str, Any]:
        """
        🐕 Ветклиники по координатам.

        Endpoint: GET /mypets/clinics/
        """
        url = f'{self.api_site}/mypets/clinics/'
        params: dict[str, Any] = {}

        lat, lon = await self._resolve_coords(
            lat=lat,
            lon=lon,
            building_id=building_id,
            address_query=address_query,
        )

        if lat is not None:
            params['location_latitude'] = lat
        if lon is not None:
            params['location_longitude'] = lon
        if radius_km is not None:
            params['location_radius'] = radius_km

        if services:
            params['services'] = services

        return await self._get_request('get_mypets_clinics', url, params or None)


    async def get_mypets_clinics_id(self, clinic_id: int) -> dict[str, Any]:
        """
        🐕 Ветклиника по ID.

        Endpoint: GET /mypets/clinics/id/
        """
        url = f'{self.api_site}/mypets/clinics/id/'
        params = {'id': clinic_id}
        return await self._get_request('get_mypets_clinics_id', url, params)

    async def get_mypets_parks_playground(
        self,
        lat: float | None = None,
        lon: float | None = None,
        radius_km: int | None = None,
        place_type: str | None = None,
        building_id: str | None = None,
        address_query: str | None = None,
    ) -> dict[str, Any]:
        """
        🐕 Парки и площадки для питомцев.

        Endpoint: GET /mypets/parks-playground/
        """
        url = f'{self.api_site}/mypets/parks-playground/'
        params: dict[str, Any] = {}
        if place_type:
            params['type'] = place_type

        lat, lon = await self._resolve_coords(
            lat=lat,
            lon=lon,
            building_id=building_id,
            address_query=address_query,
        )
        if lat is not None:
            params['location_latitude'] = lat
        if lon is not None:
            params['location_longitude'] = lon
        if radius_km is not None:
            params['location_radius'] = radius_km

        return await self._get_request('get_mypets_parks_playground', url, params or None)

    async def get_mypets_parks_playground_id(self, park_id: int) -> dict[str, Any]:
        """
        🐕 Парк/площадка по ID.

        Endpoint: GET /mypets/parks-playground/id/
        """
        url = f'{self.api_site}/mypets/parks-playground/id/'
        params = {'id': park_id}
        return await self._get_request('get_mypets_parks_playground_id', url, params)

    async def get_mypets_shelters(
        self,
        lat: float | None = None,
        lon: float | None = None,
        radius_km: int | None = 10,
        specialization: list[str] | None = None,
        building_id: str | None = None,
        address_query: str | None = None,
    ) -> dict[str, Any]:
        """
        🐕 Приюты для животных.

        Endpoint: GET /mypets/shelters/
        """
        url = f'{self.api_site}/mypets/shelters/'
        params: dict[str, Any] = {}

        lat, lon = await self._resolve_coords(
            lat=lat,
            lon=lon,
            building_id=building_id,
            address_query=address_query,
        )
        if lat is not None:
            params['location_latitude'] = lat
        if lon is not None:
            params['location_longitude'] = lon
        if radius_km is not None:
            params['location_radius'] = radius_km
        if specialization:
            params['specialization'] = specialization

        return await self._get_request('get_mypets_shelters', url, params or None)

    async def get_mypets_shelters_id(self, shelter_id: int) -> dict[str, Any]:
        """
        🐕 Приют по ID.

        Endpoint: GET /mypets/shelters/id/
        """
        url = f'{self.api_site}/mypets/shelters/id/'
        params = {'id': shelter_id}
        return await self._get_request('get_mypets_shelters_id', url, params)

    # =========================================================================
    # СПОРТ (расширенные)
    # =========================================================================

    async def get_sport_event_by_id(self, sport_event_id: int) -> dict[str, Any]:
        """
        🏅 Спортивное событие по ID.

        Endpoint: GET /sport-events/id/
        """
        url = f'{self.api_site}/sport-events/id/'
        params = {'id': sport_event_id}
        return await self._get_request('get_sport_event_by_id', url, params)

    async def get_sport_events_categoria(
        self,
        district: str,
        service: str | None = None,
    ) -> dict[str, Any]:
        """
        🏅 Категории спортсобытий по району.

        Endpoint: GET /sport-events/categoria/
        """
        url = f'{self.api_site}/sport-events/categoria/'
        params: dict[str, Any] = {'district': district}
        if service:
            params['service'] = service
        return await self._get_request('get_sport_events_categoria', url, params)

    async def get_sport_events_map(
        self,
        categoria: str | list[str] | None = None,
        district: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        radius_km: int | None = None,
        building_id: str | None = None,
        address_query: str | None = None,
    ) -> dict[str, Any]:
        """
        🏅 Карта спортсобытий.

        Endpoint: GET /sport-events/map
        """
        url = f'{self.api_site}/sport-events/map'
        params: dict[str, Any] = {}
        if categoria:
            if isinstance(categoria, list):
                # TODO: множественный выбор категорий (через запятую)
                params['categoria'] = ','.join(categoria)
            else:
                params['categoria'] = categoria
        if district:
            params['district'] = district
        if start_date:
            params['start_date'] = start_date
        if end_date:
            params['end_date'] = end_date

        lat, lon = await self._resolve_coords(
            lat=lat,
            lon=lon,
            building_id=building_id,
            address_query=address_query,
        )
        if lat is not None:
            params['location_latitude'] = lat
        if lon is not None:
            params['location_longitude'] = lon
        if radius_km is not None:
            params['location_radius'] = radius_km

        self._drop_district_if_coords(params, lat, lon, district_keys=('district',))

        return await self._get_request('get_sport_events_map', url, params or None)

    # =========================================================================
    # СПОРТПЛОЩАДКИ (расширенные)
    # =========================================================================

    async def get_sportgrounds_by_id(self, sportgrounds_id: int) -> dict[str, Any]:
        """
        🏟️ Спортплощадка по ID.

        Endpoint: GET /sportgrounds/id/
        """
        url = f'{self.api_site}/sportgrounds/id/'
        params = {'id': sportgrounds_id}
        return await self._get_request('get_sportgrounds_by_id', url, params)

    async def get_sportgrounds_count_district(
        self,
        district: str | None = None,
    ) -> dict[str, Any]:
        """
        🏟️ Количество спортплощадок по району.

        Endpoint: GET /sportgrounds/count/district/
        """
        url = f'{self.api_site}/sportgrounds/count/district/'
        params: dict[str, Any] = {}
        if district:
            params['district'] = district
        return await self._get_request('get_sportgrounds_count_district', url, params or None)

    async def get_sportgrounds_types(self) -> dict[str, Any]:
        """
        🏟️ Типы спортплощадок.

        Endpoint: GET /sportgrounds/types/
        """
        url = f'{self.api_site}/sportgrounds/types/'
        return await self._get_request('get_sportgrounds_types', url)

    async def get_sportgrounds_map(
        self,
        types: str | list[str] | None = None,
        district: str | None = None,
        season: str | None = None,
        ovz: bool | None = None,
        light: bool | None = None,
        cover: str | None = None,
        zone: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        radius_km: int | None = None,
        building_id: str | None = None,
        address_query: str | None = None,
    ) -> dict[str, Any]:
        """
        🏟️ Карта спортплощадок.

        Endpoint: GET /sportgrounds/map/
        """
        url = f'{self.api_site}/sportgrounds/map/'
        params: dict[str, Any] = {}
        if types:
            if isinstance(types, list):
                # TODO: множественный выбор типов (через запятую)
                params['types'] = ','.join(types)
            else:
                params['types'] = types
        if district:
            params['district'] = district
        if season:
            params['season'] = season
        if ovz is not None:
            params['ovz'] = str(ovz).lower()
        if light is not None:
            params['light'] = str(light).lower()
        if cover:
            params['cover'] = cover
        if zone:
            params['zone'] = zone

        lat, lon = await self._resolve_coords(
            lat=lat,
            lon=lon,
            building_id=building_id,
            address_query=address_query,
        )
        if lat is not None:
            params['location_latitude'] = lat
        if lon is not None:
            params['location_longitude'] = lon
        if radius_km is not None:
            params['location_radius'] = radius_km

        self._drop_district_if_coords(params, lat, lon, district_keys=('district',))

        return await self._get_request('get_sportgrounds_map', url, params or None)

    # =========================================================================
    # ГЕО - ДОПОЛНИТЕЛЬНО
    # =========================================================================

    async def get_municipality(self) -> dict[str, Any]:
        """
        📍 Муниципалитеты.

        Endpoint: GET /geo/municipality/
        """
        url = f'{self.api_geo}/geo/municipality/'
        return await self._get_request('get_municipality', url)

    # =========================================================================
    # ГАТИ
    # =========================================================================

    async def get_gati_orders_map(
        self,
        district: str | None = None,
        work_type: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        radius_km: int | None = None,
        page: int = 1,
        count: int = 50,
        building_id: str | None = None,
        address_query: str | None = None,
    ) -> dict[str, Any]:
        """
        🚧 Ордера ГАТИ на карте.

        Endpoint: GET /gati/orders/map/

        Поддерживает:
        - фильтр по району (district)
        - фильтр по типу работ (work_type)
        - поиск по координатам (location_latitude/longitude/radius)
          с разрешением по building_id или address_query.
        """
        url = f'{self.api_site}/gati/orders/map/'
        params: dict[str, Any] = {'page': page, 'count': count}

        if district:
            params['district'] = district
        if work_type:
            params['work_type'] = work_type

        lat, lon = await self._resolve_coords(
            lat=lat,
            lon=lon,
            building_id=building_id,
            address_query=address_query,
        )
        if lat is not None:
            params['location_latitude'] = lat
        if lon is not None:
            params['location_longitude'] = lon
        if radius_km is not None:
            params['location_radius'] = radius_km

        return await self._get_request('get_gati_orders_map', url, params)

    async def get_gati_order_by_id(self, order_id: int) -> dict[str, Any]:
        """
        🚧 Ордер ГАТИ по ID.

        Endpoint: GET /gati/orders/{id}
        """
        url = f'{self.api_site}/gati/orders/{order_id}'
        return await self._get_request('get_gati_order_by_id', url)

    async def get_gati_work_types(self) -> dict[str, Any]:
        """
        🚧 Типы работ (нормализованные).

        Endpoint: GET /gati/orders/work-type/
        """
        url = f'{self.api_site}/gati/orders/work-type/'
        return await self._get_request('get_gati_work_types', url)

    async def get_gati_work_types_raw(self) -> dict[str, Any]:
        """
        🚧 Типы работ (сырые).

        Endpoint: GET /gati/orders/work-type-all/
        """
        url = f'{self.api_site}/gati/orders/work-type-all/'
        return await self._get_request('get_gati_work_types_raw', url)

    async def get_gati_orders_district_stats(self) -> dict[str, Any]:
        """
        🚧 Статистика ордеров по районам.

        Endpoint: GET /gati/orders/district/
        """
        url = f'{self.api_site}/gati/orders/district/'
        return await self._get_request('get_gati_orders_district_stats', url)

    async def get_gati_road_info(self) -> dict[str, Any]:
        """
        🚧 Информация о дорожных работах.

        Endpoint: GET /gati/info/
        """
        url = f'{self.api_site}/gati/info/'
        return await self._get_request('get_gati_road_info', url)

    # =========================================================================
    # IPARENT
    # =========================================================================

    async def get_iparent_places_categories(self) -> dict[str, Any]:
        """
        👨‍👩‍👧 Категории мест (iParent).

        Endpoint: GET /iparent/places/categoria/
        """
        url = f'{self.api_site}/iparent/places/categoria/'
        return await self._get_request('get_iparent_places_categories', url)

    async def get_iparent_places(
        self,
        categoria: str | None = None,
        count: int = 10,
        page: int = 1,
    ) -> dict[str, Any]:
        """
        👨‍👩‍👧 Места (iParent).

        Endpoint: GET /iparent/places/all/
        """
        url = f'{self.api_site}/iparent/places/all/'
        params: dict[str, Any] = {'count': count, 'page': page}
        if categoria:
            # TODO: множественный выбор категорий (через запятую) (Возможно)
            params['categoria'] = categoria
        return await self._get_request('get_iparent_places', url, params)

    async def get_iparent_place_by_id(self, place_id: int) -> dict[str, Any]:
        """
        👨‍👩‍👧 Место по ID (iParent).

        Endpoint: GET /iparent/places/by_id/
        """
        url = f'{self.api_site}/iparent/places/by_id/'
        params = {'place_id': place_id}
        return await self._get_request('get_iparent_place_by_id', url, params)

    async def get_iparent_recreations_categories(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """
        👨‍👩‍👧 Категории детских активностей.

        Endpoint: GET /iparent/recreations/categoria/
        """
        url = f'{self.api_site}/iparent/recreations/categoria/'
        params: dict[str, Any] = {}
        if start_date:
            params['start_date'] = start_date
        if end_date:
            params['end_date'] = end_date
        return await self._get_request('get_iparent_recreations_categories', url, params or None)

    async def get_iparent_recreations(
        self,
        categoria: str | list[str] | None = None,
        free: bool | None = None,
        min_age: int | None = None,
        max_age: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        radius_km: int | None = None,
        page: int = 1,
        count: int = 10,
        building_id: str | None = None,
        address_query: str | None = None,
    ) -> dict[str, Any]:
        """
        👨‍👩‍👧 Мероприятия для детей (iParent).

        Endpoint: GET /iparent/recreations/all/
        """
        url = f'{self.api_site}/iparent/recreations/all/'
        params: dict[str, Any] = {'page': page, 'count': count}
        if categoria:
            if isinstance(categoria, list):
                # TODO: множественный выбор категорий (через запятую)
                params['categoria'] = ','.join(categoria)
            else:
                params['categoria'] = categoria
        if free is not None:
            params['free'] = str(free).lower()
        if min_age is not None:
            params['min_age'] = min_age
        if max_age is not None:
            params['max_age'] = max_age
        if start_date:
            params['start_date'] = start_date
        if end_date:
            params['end_date'] = end_date

        lat, lon = await self._resolve_coords(
            lat=lat,
            lon=lon,
            building_id=building_id,
            address_query=address_query,
        )
        if lat is not None:
            params['location_latitude'] = lat
        if lon is not None:
            params['location_longitude'] = lon
        if radius_km is not None:
            params['location_radius'] = radius_km

        return await self._get_request('get_iparent_recreations', url, params)

    async def get_iparent_recreation_by_id(
        self,
        recreation_id: int,
        region_id: str | None = None,
    ) -> dict[str, Any]:
        """
        👨‍👩‍👧 Мероприятие по ID (iParent).

        Endpoint: GET /iparent/recreations/{id}
        """
        url = f'{self.api_site}/iparent/recreations/{recreation_id}'
        params: dict[str, Any] = {}
        if region_id:
            params['region_id'] = region_id
        return await self._get_request('get_iparent_recreation_by_id', url, params or None)

    # =========================================================================
    # GOSSTROY
    # =========================================================================

    async def get_gosstroy_map(
        self,
        gos_type: str | None = None,
        category: str | None = None,
        status: str | None = None,
        assignment: str | None = None,
        supervised_law_214: bool | None = None,
        date_start_planned: str | None = None,
        date_start_actual: str | None = None,
        date_end_planned: str | None = None,
        date_end_actual: str | None = None,
        district: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        radius_km: int | None = None,
        building_id: str | None = None,
        address_query: str | None = None,
    ) -> dict[str, Any]:
        """
        🏗️ Объекты Госстройнадзора на карте.

        Endpoint: GET /gosstroy/map/
        """
        url = f'{self.api_site}/gosstroy/map/'
        params: dict[str, Any] = {}
        if gos_type:
            params['type'] = gos_type
        if category:
            params['category'] = category
        if status:
            params['status'] = status
        if assignment:
            params['assignment'] = assignment
        if supervised_law_214 is not None:
            params['supervised_law_214'] = str(supervised_law_214).lower()
        if date_start_planned:
            params['date_start_planned'] = date_start_planned
        if date_start_actual:
            params['date_start_actual'] = date_start_actual
        if date_end_planned:
            params['date_end_planned'] = date_end_planned
        if date_end_actual:
            params['date_end_actual'] = date_end_actual
        if district:
            params['district'] = district

        lat, lon = await self._resolve_coords(
            lat=lat,
            lon=lon,
            building_id=building_id,
            address_query=address_query,
        )
        if lat is not None:
            params['location_latitude'] = lat
        if lon is not None:
            params['location_longitude'] = lon
        if radius_km is not None:
            params['location_radius'] = radius_km

        self._drop_district_if_coords(params, lat, lon, district_keys=('district',))

        return await self._get_request('get_gosstroy_map', url, params or None)

    async def get_gosstroy_types(self) -> dict[str, Any]:
        """
        🏗️ Типы объектов Госстройнадзора.

        Endpoint: GET /gosstroy/type/
        """
        url = f'{self.api_site}/gosstroy/type/'
        return await self._get_request('get_gosstroy_types', url)

    async def get_gosstroy_categories(self) -> dict[str, Any]:
        """
        🏗️ Категории объектов Госстройнадзора.

        Endpoint: GET /gosstroy/category/
        """
        url = f'{self.api_site}/gosstroy/category/'
        return await self._get_request('get_gosstroy_categories', url)

    async def get_gosstroy_statuses(self) -> dict[str, Any]:
        """
        🏗️ Статусы объектов Госстройнадзора.

        Endpoint: GET /gosstroy/status/
        """
        url = f'{self.api_site}/gosstroy/status/'
        return await self._get_request('get_gosstroy_statuses', url)

    async def get_gosstroy_assignments(self) -> dict[str, Any]:
        """
        🏗️ Назначения объектов Госстройнадзора.

        Endpoint: GET /gosstroy/assignment/
        """
        url = f'{self.api_site}/gosstroy/assignment/'
        return await self._get_request('get_gosstroy_assignments', url)

    async def get_gosstroy_info(self) -> dict[str, Any]:
        """
        🏗️ Общая информация по Госстройнадзору.

        Endpoint: GET /gosstroy/info/
        """
        url = f'{self.api_site}/gosstroy/info/'
        return await self._get_request('get_gosstroy_info', url)

    async def get_gosstroy_by_id(self, gosstroy_id: int) -> dict[str, Any]:
        """
        🏗️ Объект Госстройнадзора по ID.

        Endpoint: GET /gosstroy/{id}
        """
        url = f'{self.api_site}/gosstroy/{gosstroy_id}'
        return await self._get_request('get_gosstroy_by_id', url)

    async def get_gosstroy_district_stats(
        self,
        district: str | None = None,
    ) -> dict[str, Any]:
        """
        🏗️ Статистика объектов по районам.

        Endpoint: GET /gosstroy/stats/district/
        """
        url = f'{self.api_site}/gosstroy/stats/district/'
        params: dict[str, Any] = {}
        if district:
            params['district'] = district
        return await self._get_request('get_gosstroy_district_stats', url, params or None)

        # ------------------------------------------------------------------

    # Экология — пункты приёма вторсырья (с поддержкой адреса)
    # ------------------------------------------------------------------
    async def get_recycling_points(
        self,
        *,
        category: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        radius_km: int | None = None,
        building_id: str | None = None,
        address_query: str | None = None,
    ) -> dict[str, Any]:
        """
        ♻ Пункты приёма вторсырья — список точек на карте.

        Endpoint: GET /api/v2/recycling/map/

        Параметры:
        - category: категория вторсырья.
        - lat / lon / radius_km: координаты и радиус поиска (в км).
        - building_id: ID здания (будет преобразован в координаты).
        - address_query: текстовый адрес (будет преобразован в координаты).
        """
        url = f'{self.api_site}/api/v2/recycling/map/'
        params: dict[str, Any] = {}

        if category:
            params['category'] = category

        # Унифицированное разрешение координат
        lat, lon = await self._resolve_coords(
            lat=lat,
            lon=lon,
            building_id=building_id,
            address_query=address_query,
        )

        if lat is not None:
            params['location_latitude'] = lat
        if lon is not None:
            params['location_longitude'] = lon
        if radius_km is not None:
            params['location_radius'] = radius_km

        return await self._get_request('get_recycling_points', url, params or None)

    async def get_recycling_point_by_id(self, point_id: int) -> dict[str, Any]:
        """
        ♻ Пункт приёма вторсырья по id.

        Endpoint: GET /api/v2/recycling/map/{id}
        """
        url = f'{self.api_site}/api/v2/recycling/map/{point_id}'
        return await self._get_request('get_recycling_point_by_id', url, {})

    async def get_recycling_categories(self) -> dict[str, Any]:
        """
        ♻ Категории пунктов приёма вторсырья.

        Endpoint: GET /api/v2/recycling/map/category/
        """
        url = f'{self.api_site}/api/v2/recycling/map/category/'
        return await self._get_request('get_recycling_categories', url, {})

    async def get_recycling_counts(self) -> dict[str, Any]:
        """
        ♻ Сводные количества пунктов приёма вторсырья.

        Endpoint: GET /api/v2/recycling/map/counts/
        """
        url = f'{self.api_site}/api/v2/recycling/map/counts/'
        return await self._get_request('get_recycling_counts', url, {})

    async def get_recycling_nearest(
        self,
        *,
        lat: float | None = None,
        lon: float | None = None,
        count: int | None = None,
        building_id: str | None = None,
        address_query: str | None = None,
    ) -> dict[str, Any]:
        """
        ♻ Ближайшие пункты приёма вторсырья.

        Endpoint: GET /api/v2/external/recycling/nearest

        Параметры:
        - lat / lon: координаты пользователя.
        - building_id: ID здания (будет преобразован в координаты).
        - address_query: текстовый адрес (будет преобразован в координаты).
        - count: сколько точек вернуть.
        """
        url = f'{self.api_site}/api/v2/external/recycling/nearest'
        params: dict[str, Any] = {}

        lat, lon = await self._resolve_coords(
            lat=lat,
            lon=lon,
            building_id=building_id,
            address_query=address_query,
        )

        if lat is not None:
            params['latitude'] = lat
        if lon is not None:
            params['longitude'] = lon
        if count is not None:
            params['count'] = count

        return await self._get_request('get_recycling_nearest', url, params or None)
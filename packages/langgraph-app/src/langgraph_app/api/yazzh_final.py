__api__ = 'work in progress'


import json
from typing import Any

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from langgraph_app.api.utils import _log_error, _log_json

### LEGACY
from langgraph_app.api.yazzh_models import AddressNotFoundError, BuildingSearchResult, YazzhAPIError

console = Console()


API_GEO = 'https://yazzh-geo.gate.petersburg.ru'
API_SITE = 'https://yazzh.gate.petersburg.ru'
REGION_ID = '78'


### LEGACY
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

    Каждый метод выводит:
    - URL запроса
    - Параметры запроса
    - Полный JSON ответа (все поля)
    - Status code
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
        Выполняет HTTP запрос с полным логированием.

        Returns:
            dict с ключами: status_code, json, raw_text, url
        """
        if self.verbose:
            console.rule(f'[bold cyan]📡 {method_name}[/bold cyan]')

            # логгируем запрос
            table = Table(title='Request', show_header=False, box=None)
            table.add_row('[dim]URL:[/dim]', url)
            if params:
                table.add_row('[dim]Params:[/dim]', str(params))
            if headers:
                table.add_row('[dim]Headers:[/dim]', str(headers))
            console.print(table)

        try:
            # делаем GET запрос через httpx
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

    # ----------------------------------------
    # ГЕОКОДИНГ - Фундаментальные функции     |
    # ----------------------------------------
    async def search_building_full_text_search(
        self,
        query: str,
        count: int = 5,
    ) -> dict[str, Any]:
        """
        🔍 Ищет здания по адресу (полнотекстовый поиск) и возвращает результаты.

        Endpoint: GET /geo/buildings/search/

        Возвращает ВСЕ найденные здания с похожим адресом.
        Неточный поиск! но даёт разнообразие вариантов.
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
        🏠 Возвращает информацию о здании по ID.

        Endpoint: GET /geo/buildings/{building_id}
        """
        url = f'{self.api_geo}/geo/buildings/{building_id}'
        params = {'format': output_format}
        return await self._get_request('get_building_info', url, params)

    async def get_districts(self) -> dict[str, Any]:
        """
        📍 Возвращает список всех районов СПб.

        Endpoint: GET /geo/district/
        """
        url = f'{self.api_geo}/geo/district/'
        return await self._get_request('get_districts', url)

    # =========================================================================
    # УПРАВЛЯЮЩИЕ КОМПАНИИ
    # =========================================================================

    async def get_management_company(self, building_id: str) -> dict[str, Any]:
        """
        🏢 Возвращает управляющую компанию по ID здания.

        Endpoint: GET /api/v1/mancompany/{building_id}
        """
        url = f'{self.api_geo_v1}/mancompany/{building_id}'
        params = {'region_of_search': self.region_id}
        return await self._get_request('get_management_company', url, params)

    # =========================================================================
    # МФЦ
    # =========================================================================

    async def get_mfc_by_building(self, building_id: str) -> dict[str, Any]:
        """
        📋 Возвращает ближайший МФЦ по ID здания.

        Endpoint: GET /mfc/
        """
        url = f'{self.api_site}/mfc/'
        params = {'id_building': building_id}
        return await self._get_request('get_mfc_by_building', url, params)

    async def get_all_mfc(self) -> dict[str, Any]:
        """
        📋 Возвращает список всех МФЦ.

        Endpoint: GET /mfc/all/
        """
        url = f'{self.api_site}/mfc/all/'
        return await self._get_request('get_all_mfc', url)

    async def get_mfc_by_district(self, district: str) -> dict[str, Any]:
        """
        📋 Находит и возвращает все МФЦ по району.

        Endpoint: GET /mfc/district/
        """
        url = f'{self.api_site}/mfc/district/'
        params = {'district': district}
        return await self._get_request('get_mfc_by_district', url, params)

    async def get_mfc_nearest_by_coords(
        self,
        lat: float,
        lon: float,
        distance_km: int = 5,  # TODO: использовать разумное значение по умолчанию
    ) -> dict[str, Any]:
        """
        📋 Возвращает ближайший МФЦ по координатам.

        Endpoint: GET /mfc/nearest/
        """
        url = f'{self.api_site}/mfc/nearest/'
        params = {
            'lat': lat,
            'lon': lon,
            'distance': distance_km,
        }
        return await self._get_request('get_mfc_nearest_by_coords', url, params)

    # =========================================================================
    # ПОЛИКЛИНИКИ
    # =========================================================================

    async def get_polyclinics_by_building(self, building_id: str) -> dict[str, Any]:
        """
        🏥 Возвращает ПРИКРЕПЛЁННЫЕ поликлиники по ID здания.

        Endpoint: GET /polyclinics/
        """
        url = f'{self.api_site}/polyclinics/'
        params = {'id': building_id}
        return await self._get_request('get_polyclinics_by_building', url, params)

    # =========================================================================
    # ШКОЛЫ
    # =========================================================================

    async def get_linked_schools(
        self,
        building_id: str,
        scheme: int = 1,
    ) -> dict[str, Any]:
        """
        🏫 Возвращает ПРИКРЕПЛЁННЫЕ школы по прописке.

        Endpoint: GET /school/linked/{building_id}
        """
        url = f'{self.api_site}/school/linked/{building_id}'
        params = {'scheme': scheme}
        return await self._get_request('get_linked_schools', url, params)

    async def get_school_by_id(self, school_id: int) -> dict[str, Any]:
        """
        🏫 Возвращает школу по ID.

        Endpoint: GET /school/id/
        """
        url = f'{self.api_site}/school/id/'
        params = {'id': school_id}
        return await self._get_request('get_school_by_id', url, params)

    async def get_schools_map(
        self,
        district: str | None = None,
        org_type: str | None = None,
    ) -> dict[str, Any]:
        """
        🏫 Возвращает карту школ.

        Endpoint: GET /school/map/
        """
        url = f'{self.api_site}/school/map/'
        params = {}
        if district:
            params['district'] = district
        if org_type:
            params['org_type'] = org_type
        return await self._get_request('get_schools_map', url, params or None)

    # =========================================================================
    # ДЕТСКИЕ САДЫ
    # =========================================================================

    async def get_kindergartens(
        self,
        district: str,
        age_year: int = 3,
        age_month: int = 0,
        count: int = 10,
    ) -> dict[str, Any]:
        """
        👶 Возвращает детские сады.

        Endpoint: GET /dou/
        """
        url = f'{self.api_site}/dou/'
        params = {
            'district': district,
            'legal_form': 'Государственная',
            'age_year': age_year,
            'age_month': age_month,
            'doo_status': 'Функционирует',
            'count': count,
            'page': 1,
        }
        return await self._get_request('get_kindergartens', url, params)

    # LEGACY
    # - TODO: удалить в будущем, когда будут готовы функции возвращающие Pydantic модели
    async def search_building_legacy(
        self,
        query: str,
        count: int = 5,
    ) -> list[BuildingSearchResult]:
        """
        Поиск здания по адресу (полнотекстовый поиск).

        Args:
            query: Адрес для поиска (например: "Невский проспект 1" или "Большевиков 68")
            count: Максимальное количество результатов (по умолчанию 5, макс 12)

        Returns:
            Список найденных зданий

        Raises:
            AddressNotFoundError: Если ничего не найдено
        """
        async with ApiClientUnified() as client:
            res = await client.search_building_full_text_search(query=query, count=10)
        if res['status_code'] != 200:
            raise YazzhAPIError(
                f'Ошибка API при поиске адреса: {res["status_code"]}',
                status_code=res['status_code'],
            )

        data = res['json']
        buildings_data = (data['data'], data)

        if not buildings_data:
            # logger.info('api_empty_result', method='search_building', query=query)
            raise AddressNotFoundError(f'Адрес не найден: {query}')

        results = [BuildingSearchResult.model_validate(b) for b in buildings_data]
        # logger.info('api_result', method='search_building', count=len(results))
        return results

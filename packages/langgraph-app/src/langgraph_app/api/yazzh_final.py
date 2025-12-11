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

    # =========================================================================
    # РАЙОН - СПРАВКА
    # =========================================================================

    async def get_district_info_by_building(self, building_id: str) -> dict[str, Any]:
        """
        📊 Справка по району (по building_id).

        Endpoint: GET /districts-info/building-id/{building_id}
        """
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

    async def get_disconnections(self, building_id: str) -> dict[str, Any]:
        """
        ⚡ Получить отключения по ID здания.

        Endpoint: GET /disconnection/
        """
        url = f'{self.api_site}/disconnection/'
        params = {'building_id': building_id}
        return await self._get_request('get_disconnections', url, params)

    # =========================================================================
    # СПОРТ
    # =========================================================================

    async def get_sport_events(
        self,
        district: str | None = None,
        categoria: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        count: int = 10,
    ) -> dict[str, Any]:
        """
        🏅 Получить спортивные мероприятия.

        Endpoint: GET /sport-events/
        """
        url = f'{self.api_site}/sport-events/'
        params: dict[str, Any] = {'count': count, 'page': 1}
        if district:
            params['district'] = district
        if categoria:
            params['categoria'] = categoria
        if start_date:
            params['start_date'] = start_date
        if end_date:
            params['end_date'] = end_date
        return await self._get_request('get_sport_events', url, params)

    async def get_sportgrounds(
        self,
        district: str | None = None,
        object_type: str | None = None,
        count: int = 10,
    ) -> dict[str, Any]:
        """
        🏟️ Получить спортивные площадки.

        Endpoint: GET /sportgrounds/
        """
        url = f'{self.api_site}/sportgrounds/'
        params: dict[str, Any] = {'count': count, 'page': 1}
        if district:
            params['district'] = district
        if object_type:
            params['object_type'] = object_type
        return await self._get_request('get_sportgrounds', url, params)

    async def get_sportgrounds_count(self) -> dict[str, Any]:
        """
        🏟️ Статистика спортивных площадок.

        Endpoint: GET /sportgrounds/map/count/
        """
        url = f'{self.api_site}/sportgrounds/map/count/'
        return await self._get_request('get_sportgrounds_count', url)

    # =========================================================================
    # АФИША / МЕРОПРИЯТИЯ
    # =========================================================================

    async def get_events(
        self,
        start_date: str,
        end_date: str,
        categoria: str | None = None,
        free: bool | None = None,
        kids: bool | None = None,
        count: int = 10,
    ) -> dict[str, Any]:
        """
        🎭 Получить мероприятия (афиша).

        Endpoint: GET /afisha/all/
        """
        url = f'{self.api_site}/afisha/all/'
        params = {
            'start_date': start_date,
            'end_date': end_date,
            'count': count,
            'page': 1,
        }
        if categoria:
            params['categoria'] = categoria
        if free is not None:
            params['free'] = str(free).lower()
        if kids is not None:
            params['kids'] = str(kids).lower()
        return await self._get_request('get_events', url, params)

    async def get_event_categories(
        self,
        start_date: str,
        end_date: str,
    ) -> dict[str, Any]:
        """
        🎭 Категории мероприятий.

        Endpoint: GET /afisha/category/all/
        """
        url = f'{self.api_site}/afisha/category/all/'
        params = {
            'start_date': start_date,
            'end_date': end_date,
        }
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
        district: str,
        category: str | None = None,
        count: int = 10,
    ) -> dict[str, Any]:
        """
        👴 Услуги для пенсионеров.

        Endpoint: GET /pensioner/services/
        """
        url = f'{self.api_site}/pensioner/services/'
        params = {
            'district': district,
            'count': count,
            'page': 1,
        }
        if category:
            params['category'] = category
        return await self._get_request('get_pensioner_services', url, params)

    # =========================================================================
    # ПАМЯТНЫЕ ДАТЫ
    # =========================================================================

    async def get_memorable_dates(self, date: str) -> dict[str, Any]:
        """
        📅 Памятные даты.

        Endpoint: GET /memorable-dates/
        """
        url = f'{self.api_site}/memorable-dates/'
        params = {'date': date}
        return await self._get_request('get_memorable_dates', url, params)

    # =========================================================================
    # ДОРОЖНЫЕ РАБОТЫ
    # =========================================================================

    async def get_road_works_stats(self) -> dict[str, Any]:
        """
        🚧 Статистика дорожных работ.

        Endpoint: GET /road-works/stats/
        """
        url = f'{self.api_site}/road-works/stats/'
        return await self._get_request('get_road_works_stats', url)

    async def get_road_works(
        self,
        district: str | None = None,
        count: int = 10,
    ) -> dict[str, Any]:
        """
        🚧 Дорожные работы.

        Endpoint: GET /road-works/
        """
        url = f'{self.api_site}/road-works/'
        params: dict[str, Any] = {'count': count, 'page': 1}
        if district:
            params['district'] = district
        return await self._get_request('get_road_works', url, params)

    # =========================================================================
    # ПИТОМЦЫ
    # =========================================================================

    async def get_vet_clinics(
        self,
        lat: float | None = None,
        lon: float | None = None,
        radius: int = 5,
    ) -> dict[str, Any]:
        """
        🐕 Ветеринарные клиники.

        Endpoint: GET /mypets/all-category/
        """
        url = f'{self.api_site}/mypets/all-category/'
        params: dict[str, Any] = {'type': 'Ветклиника'}
        if lat and lon:
            params['location_latitude'] = lat
            params['location_longitude'] = lon
            params['location_radius'] = radius
        return await self._get_request('get_vet_clinics', url, params)

    async def get_pet_parks(
        self,
        lat: float | None = None,
        lon: float | None = None,
        radius: int = 5,
    ) -> dict[str, Any]:
        """
        🐕 Парки для питомцев.

        Endpoint: GET /mypets/all-category/
        """
        url = f'{self.api_site}/mypets/all-category/'
        params: dict[str, Any] = {'type': 'Парк'}
        if lat and lon:
            params['location_latitude'] = lat
            params['location_longitude'] = lon
            params['location_radius'] = radius
        return await self._get_request('get_pet_parks', url, params)

    # =========================================================================
    # КРАСИВЫЕ МЕСТА
    # =========================================================================

    async def get_beautiful_places(
        self,
        district: str | None = None,
        categoria: str | None = None,
        count: int = 10,
    ) -> dict[str, Any]:
        """
        🏛️ Красивые места.

        Endpoint: GET /beautiful_places/
        """
        url = f'{self.api_site}/beautiful_places/'
        params: dict[str, Any] = {'count': count, 'page': 1}
        if district:
            params['district'] = district
        if categoria:
            params['categoria'] = categoria
        return await self._get_request('get_beautiful_places', url, params)

    async def get_beautiful_place_routes(
        self,
        theme: str | None = None,
        route_type: str | None = None,
        count: int = 10,
    ) -> dict[str, Any]:
        """
        🚶 Туристические маршруты.

        Endpoint: GET /beautiful_places/routes/
        """
        url = f'{self.api_site}/beautiful_places/routes/'
        params: dict[str, Any] = {'count': count, 'page': 1}
        if theme:
            params['theme'] = theme
        if route_type:
            params['route_type'] = route_type
        return await self._get_request('get_beautiful_place_routes', url, params)

    async def get_beautiful_places_area(self) -> dict[str, Any]:
        """
        🏛️ Области интересных мест (СПб, ЛО и т.д.)

        Endpoint: GET /beautiful_places/area/
        """
        url = f'{self.api_site}/beautiful_places/area/'
        return await self._get_request('get_beautiful_places_area', url)

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
        count: int = 10,
        page: int = 1,
    ) -> dict[str, Any]:
        """
        📰 Получить новости.

        Endpoint: GET /news/
        """
        url = f'{self.api_site}/news/'
        params: dict = {'count': count, 'page': page}
        if district:
            params['district'] = district
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
        return await self._get_request('get_news', url, params)

    # =========================================================================
    # ПАМЯТНЫЕ ДАТЫ (дополнительные)
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
        📅 Памятные даты по ID.

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
    # ПИТОМЦЫ (MyPets) - расширенные
    # =========================================================================

    async def get_mypets_all_category(
        self,
        lat: float | None = None,
        lon: float | None = None,
        radius: int | None = None,
        types: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        🐕 Все категории объектов для питомцев (Мой питомец).

        Endpoint: GET /mypets/all-category/
        """
        url = f'{self.api_site}/mypets/all-category/'
        params: dict = {}
        if lat is not None:
            params['location_latitude'] = lat
        if lon is not None:
            params['location_longitude'] = lon
        if radius is not None:
            params['location_radius'] = radius
        if types:
            params['type'] = types
        return await self._get_request('get_mypets_all_category', url, params or None)

    async def get_mypets_animal_breeds(
        self,
        specie: str | None = None,
        breed: str | None = None,
    ) -> dict[str, Any]:
        """
        🐕 Породы животных (Мой питомец).

        Endpoint: GET /mypets/animal-breeds/
        """
        url = f'{self.api_site}/mypets/animal-breeds/'
        params: dict = {}
        if specie:
            params['specie'] = specie
        if breed:
            params['breed'] = breed
        return await self._get_request('get_mypets_animal_breeds', url, params or None)

    async def get_mypets_holidays(self) -> dict[str, Any]:
        """
        🐕 Праздники для питомцев (Мой питомец).

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
        🐕 Посты про питомцев (Мой питомец).

        Endpoint: GET /mypets/posts/
        """
        url = f'{self.api_site}/mypets/posts/'
        params: dict = {'page': page, 'size': size}
        if specie:
            params['specie'] = specie
        return await self._get_request('get_mypets_posts', url, params)

    async def get_mypets_posts_id(self, posts_id: int) -> dict[str, Any]:
        """
        🐕 Пост по ID (Мой питомец).

        Endpoint: GET /mypets/posts/id/
        """
        url = f'{self.api_site}/mypets/posts/id/'
        params = {'id': posts_id}
        return await self._get_request('get_mypets_posts_id', url, params)

    async def get_mypets_recommendations_by_page(  # TODO: реализовать пагинацию ???
        self,
        page: int = 1,
        specie: str | None = None,
        size: int = 10,
    ) -> dict[str, Any]:
        """
        🐕 Рекомендации и советы для разных видов питомцев (Мой питомец).

        Endpoint: GET /mypets/recommendations/
        """
        url = f'{self.api_site}/mypets/recommendations/'
        params: dict = {'page': page, 'size': size}
        if specie:
            params['specie'] = specie
        return await self._get_request('get_mypets_recommendations', url, params)

    async def get_mypets_clinics_by_coord(
        self,
        lat: float | None = None,
        lon: float | None = None,
        radius: int = 10,  # TODO: использовать разумные значения по умолчанию
        services: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        🐕 Ветеринарные клиники (ветклиники) по координатам (Мой питомец).

        Endpoint: GET /mypets/clinics/
        """
        url = f'{self.api_site}/mypets/clinics/'
        params: dict = {}
        if lat is not None:
            params['location_latitude'] = lat
        if lon is not None:
            params['location_longitude'] = lon
        if radius:
            params['location_radius'] = radius
        if services:
            params['services'] = services
        return await self._get_request('get_mypets_clinics', url, params or None)

    async def get_mypets_clinics_id(self, clinic_id: int) -> dict[str, Any]:
        """
        🐕 Ветеринарная клиника (ветклиника) по ID (Мой питомец).

        Endpoint: GET /mypets/clinics/id/
        """
        url = f'{self.api_site}/mypets/clinics/id/'
        params = {'id': clinic_id}
        return await self._get_request('get_mypets_clinics_id', url, params)

    async def get_mypets_parks_playground(
        self,
        lat: float | None = None,
        lon: float | None = None,
        radius: int | None = None,
        place_type: str | None = None,
    ) -> dict[str, Any]:
        """
        🐕 Парки и площадки для питомцев (Мой питомец).

        Endpoint: GET /mypets/parks-playground/
        """
        url = f'{self.api_site}/mypets/parks-playground/'
        params: dict = {}
        if lat is not None:
            params['location_latitude'] = lat
        if lon is not None:
            params['location_longitude'] = lon
        if radius is not None:
            params['location_radius'] = radius
        if place_type:
            params['type'] = place_type
        return await self._get_request('get_mypets_parks_playground', url, params or None)

    async def get_mypets_parks_playground_id(self, park_id: int) -> dict[str, Any]:
        """
        🐕 Парк/площадка по ID (Мой питомец).

        Endpoint: GET /mypets/parks-playground/id/
        """
        url = f'{self.api_site}/mypets/parks-playground/id/'
        params = {'id': park_id}
        return await self._get_request('get_mypets_parks_playground_id', url, params)

    async def get_mypets_shelters(
        self,
        lat: float | None = None,
        lon: float | None = None,
        radius: int | None = None,
        specialization: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        🐕 Приюты (шелтеры) для животных (Мой питомец).

        Endpoint: GET /mypets/shelters/
        """
        url = f'{self.api_site}/mypets/shelters/'
        params: dict = {}
        if lat is not None:
            params['location_latitude'] = lat
        if lon is not None:
            params['location_longitude'] = lon
        if radius is not None:
            params['location_radius'] = radius
        if specialization:
            params['specialization'] = specialization
        return await self._get_request('get_mypets_shelters', url, params or None)

    async def get_mypets_shelters_id(self, shelter_id: int) -> dict[str, Any]:
        """
        🐕 Приют (шелтер) по ID.

        Endpoint: GET /mypets/shelters/id/
        """
        url = f'{self.api_site}/mypets/shelters/id/'
        params = {'id': shelter_id}
        return await self._get_request('get_mypets_shelters_id', url, params)

    # =========================================================================
    # СПОРТ - расширенные
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
        🏅 Категории спортивных событий по району.

        Endpoint: GET /sport-events/categoria/
        """
        url = f'{self.api_site}/sport-events/categoria/'
        params: dict = {'district': district}
        if service:
            params['service'] = service
        return await self._get_request('get_sport_events_categoria', url, params)

    async def get_sport_events_map(
        self,
        categoria: str | None = None,
        district: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """
        🏅 Карта спортивных событий.

        Endpoint: GET /sport-events/map
        """
        url = f'{self.api_site}/sport-events/map'
        params: dict = {}
        if categoria:
            params['categoria'] = categoria
        if district:
            params['district'] = district
        if start_date:
            params['start_date'] = start_date
        if end_date:
            params['end_date'] = end_date
        return await self._get_request('get_sport_events_map', url, params or None)

    # =========================================================================
    # СПОРТПЛОЩАДКИ - расширенные
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
        🏟️ Количество спортивных площадок (спортплощадок) по району.

        Endpoint: GET /sportgrounds/count/district/
        """
        url = f'{self.api_site}/sportgrounds/count/district/'
        params: dict = {}
        if district:
            params['district'] = district
        return await self._get_request('get_sportgrounds_count_district', url, params or None)

    async def get_sportgrounds_types(self) -> dict[str, Any]:
        """
        🏟️ Типы спортивных площадок (спортплощадок).

        Endpoint: GET /sportgrounds/types/
        """
        url = f'{self.api_site}/sportgrounds/types/'
        return await self._get_request('get_sportgrounds_types', url)

    async def get_sportgrounds_map(
        self,
        types: str | None = None,
        district: str | None = None,
        season: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        radius: int | None = None,
    ) -> dict[str, Any]:
        """
        🏟️ Карта спортивных площадок (спортплощадок).

        Endpoint: GET /sportgrounds/map/
        """
        url = f'{self.api_site}/sportgrounds/map/'
        params: dict = {}
        if types:
            params['types'] = types
        if district:
            params['district'] = district
        if season:
            params['season'] = season
        if lat is not None:
            params['location_latitude'] = lat
        if lon is not None:
            params['location_longitude'] = lon
        if radius is not None:
            params['location_radius'] = radius
        return await self._get_request('get_sportgrounds_map', url, params or None)

    # =========================================================================
    # ГЕО - расширенные
    # =========================================================================

    async def get_municipality(self) -> dict[str, Any]:
        """
        📍 Муниципалитеты (районные администрации).

        Endpoint: GET /geo/municipality/
        """
        url = f'{self.api_geo}/geo/municipality/'
        return await self._get_request('get_municipality', url)

    async def get_management_company_company(
        self,
        company_id: str | None = None,
        company_name: str | None = None,
        company_inn: str | None = None,
    ) -> dict[str, Any]:
        """
        🏢 Информация об управляющей компании по ID / названию / ИНН.

        Endpoint: GET /api/v1/mancompany/company/
        """
        url = f'{self.api_geo_v1}/mancompany/company/'
        params: dict = {}
        if company_id:
            params['company_id'] = company_id
        if company_name:
            params['company_name'] = company_name
        if company_inn:
            params['company_inn'] = company_inn
        return await self._get_request('get_management_company_company', url, params or None)

    # =========================================================================
    # ГАТИ (дорожные работы) - расширенные
    # =========================================================================

    async def get_gati_orders_map(
        self,
        work_type: str | None = None,
        organization: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """
        🚧 Ордера ГАТИ на карте.

        Endpoint: GET /gati/orders/map/
        """
        url = f'{self.api_site}/gati/orders/map/'
        params: dict = {}
        if work_type:
            params['work_type'] = work_type
        if organization:
            params['organization'] = organization
        if start_date:
            params['start_date'] = start_date
        if end_date:
            params['end_date'] = end_date
        return await self._get_request('get_gati_orders_map', url, params or None)

    async def get_gati_order_by_id(self, order_id: int) -> dict[str, Any]:
        """
        🚧 Ордер ГАТИ по ID.

        Endpoint: GET /gati/orders/{id}
        """
        url = f'{self.api_site}/gati/orders/{order_id}'
        return await self._get_request('get_gati_order_by_id', url)

    async def get_gati_work_types(self) -> dict[str, Any]:
        """
        🚧 Типы работ ГАТИ (нормализованные по типу).

        Endpoint: GET /gati/orders/work-type/
        """
        url = f'{self.api_site}/gati/orders/work-type/'
        return await self._get_request('get_gati_work_types', url)

    async def get_gati_work_types_raw(self) -> dict[str, Any]:
        """
        🚧 Типы работ ГАТИ (сырые).

        Endpoint: GET /gati/orders/work-type-all/
        """
        url = f'{self.api_site}/gati/orders/work-type-all/'
        return await self._get_request('get_gati_work_types_raw', url)

    async def get_gati_organizations(self) -> dict[str, Any]:
        """
        🚧 Организации ГАТИ.

        Endpoint: GET /gati/info/
        """
        url = f'{self.api_site}/gati/info/'
        return await self._get_request('get_gati_organizations', url)

    async def get_gati_orders_district_stats(self) -> dict[str, Any]:
        """
        🚧 Статистика ордеров ГАТИ по районам.

        Endpoint: GET /gati/orders/district/
        """
        url = f'{self.api_site}/gati/orders/district/'
        return await self._get_request('get_gati_orders_district_stats', url)

    async def get_gati_road_info(self, district: str | None = None) -> dict[str, Any]:
        """
        🚧 Информация о дорожных работах.

        Endpoint: GET /gati/
        """
        url = f'{self.api_site}/gati/'
        params: dict = {}
        if district:
            params['district'] = district
        return await self._get_request('get_gati_road_info', url, params or None)

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
            query: Адрес для поиска (например: "Невский проспект 1" или "Большевиков дом 10 корпус 2")
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

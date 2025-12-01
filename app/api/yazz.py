import requests
from pprint import pprint
from app.config import API_GEO as api_geo, API_SITE as api_site, REGION_ID as DEFAULT_REGION_ID


class CityAppClient:
    def __init__(self, api_geo=api_geo, api_site=api_site, region_id: str = DEFAULT_REGION_ID):
        self.api_geo = f'{api_geo.rstrip("/")}/api/v2'
        self.api_site = api_site.rstrip('/')
        self.region_id = region_id

    # ---------------- Базовые geo-хелперы ----------------

    # Определяет ID здания и координаты по адресу пользователя
    def _get_building_id_by_address(self, user_address):
        resp = requests.get(
            f'{self.api_geo}/geo/buildings/search/',
            params={
                'query': user_address,
                'count': 1,
                'region_of_search': self.region_id,
            },
            headers={'region': self.region_id},
        )

        result = resp.json()
        data = result.get('data', [])

        if not data:
            return None

        first_building = data[0]
        return (
            first_building.get('id'),
            first_building.get('full_address'),
            (first_building.get('latitude'), first_building.get('longitude')),
        )

    def _get_district(self):
        resp = requests.get(f'{self.api_geo}/geo/district/')
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    # ---------------- МФЦ (2.2) ----------------

    def find_nearest_mfc(self, user_address):
        res = self._get_building_id_by_address(user_address)
        if res is None:
            return None

        building_id, building_address, building_coords = res
        if building_id is None:
            return None

        resp = requests.get(
            f'{self.api_site}/mfc/',
            params={
                'id_building': building_id,
                'region': self.region_id,
            },
        )

        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None

        payload = resp.json()

        mfc = None
        if isinstance(payload, dict):
            data = payload.get('data')
            if isinstance(data, list) and data:
                mfc = data[0]
            else:
                mfc = payload
        elif isinstance(payload, list) and payload:
            mfc = payload[0]

        if not mfc:
            return None

        return {
            'name': mfc.get('name'),
            'address': mfc.get('address'),
            'metro': mfc.get('nearest_metro'),
            'phones': mfc.get('phone'),
            'hours': mfc.get('working_hours'),
            'coords': mfc.get('coordinates'),
            'distance_km': mfc.get('distance'),
            'link': mfc.get('link'),
            'chat_bot': mfc.get('chat_bot'),
        }

    def get_mfc_by_district(self, district: str):
        """
        МФЦ по району — сценарий 2.2 (графики, контакты).
        """
        resp = requests.get(
            f'{self.api_site}/mfc/district/',
            params={'district': district},
        )

        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None

        data = resp.json()
        items = data.get('data', [])
        result = []

        for item in items:
            result.append(
                {
                    'name': item.get('name'),
                    'address': item.get('address'),
                    'hours': item.get('working_hours'),
                    'phones': item.get('phone'),
                }
            )
        return result

    # ---------------- ПОЛИКЛИНИКИ (2.2 / 2.3) ----------------

    def get_polyclinics_by_address(self, user_address: str):
        """
        Поликлиники по адресу — для вопросов о мед. учреждениях и соцподдержке.
        """
        building_data = self._get_building_id_by_address(user_address)
        if building_data is None:
            return None

        building_id, _, _ = building_data

        resp = requests.get(
            f'{self.api_site}/polyclinics/',
            params={'id': building_id},
            headers={'region': self.region_id},
        )

        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None

        polyclinics = resp.json()
        result = []
        for clinic in polyclinics:
            result.append(
                {
                    'name': clinic.get('clinic_name'),
                    'address': clinic.get('clinic_address'),
                    'phones': clinic.get('phone') or [],
                    'url': clinic.get('url'),
                }
            )
        return result

    # ---------------- ШКОЛЫ / ДЕТСАДЫ (2.1 / 2.2 / 2.3) ----------------

    def get_schools_by_district(self, district: str):
        """
        Школы по району — справочная инфа о госуслугах в образовании.
        """
        resp = requests.get(f'{self.api_site}/school/map/')
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None

        data = resp.json()
        schools = data.get('data', [])
        return [s for s in schools if s.get('district') == district]

    def get_linked_schools(self, user_address: str):
        """
        Школы, привязанные к конкретному дому пользователя.
        """
        building_data = self._get_building_id_by_address(user_address)
        if building_data is None:
            return None

        building_id, _, _ = building_data

        resp = requests.get(f'{self.api_site}/school/linked/{building_id}')
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None

        return resp.json()

    def get_dou(self, district: str, age_year: int = 0, age_month: int = 0):
        """
        Детские сады (гос. форма) по району и возрасту ребёнка — соцподдержка семей.
        """
        params: dict[str, str | int] = {
            'district': district,
            'legal_form': 'Государственная',
            'age_year': age_year,
            'age_month': age_month,
            'doo_status': 'Функционирует',
        }

        resp = requests.get(f'{self.api_site}/dou/', params=params)
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None

        return resp.json()

    # ---------------- АФИША ПЕНСИОНЕРОВ (2.3) ----------------

    def pensioner_service_category(self):
        resp = requests.get(f'{self.api_site}/pensioner/services/category/')
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    def pensioner_services(self, district, category: list[str], count: int = 10, page: int = 1):
        resp = requests.get(
            f'{self.api_site}/pensioner/services/',
            params={
                'category': ','.join(category),
                'district': district,
                'count': count,
                'page': page,
            },
        )
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    # ---------------- АФИША ГОРОДА (2.5) ----------------

    def afisha_categories(self, start_date: str, end_date: str):
        """
        Категории мероприятий за период — сценарий 2.5.
        Формат дат: '2025-11-21T00:00:00'
        """
        resp = requests.get(
            f'{self.api_site}/afisha/category/all/',
            params={
                'start_date': start_date,
                'end_date': end_date,
            },
        )
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    def afisha_events(
        self,
        start_date: str,
        end_date: str,
        categoria: str = '',
        kids: bool | None = None,
        free: bool | None = None,
    ):
        """
        События афиши за период — сценарий 2.5 (культурные мероприятия).
        """
        params = {
            'start_date': start_date,
            'end_date': end_date,
            'categoria': categoria,
            'kids': kids,
            'free': free,
        }
        resp = requests.get(f'{self.api_site}/afisha/all/', params=params)
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    # ---------------- НОВОСТИ ----------------

    def get_news_role(self):
        resp = requests.get(
            f'{self.api_site}/news/role/',
            headers={'region': self.region_id},
        )
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    def take_news_district(self):
        resp = requests.get(
            f'{self.api_site}/news/districts/',
            headers={'region': self.region_id},
        )
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    def take_news(
        self,
        district: str | None = None,
        description: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        yazzh_type: str | list[str] | None = None,
        count: int = 10,
        page: int = 1,
    ):
        params: dict[str, str | int] = {
            'count': count,
            'page': page,
        }

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

        resp = requests.get(
            f'{self.api_site}/news/',
            params=params,
            headers={'region': self.region_id},
        )

        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None

        return resp.json()

    # ---------------- Интересные места (beautiful_places) -----------------

    def _get_beautiful_places_area(self):
        resp = requests.get(
            f'{self.api_site}/beautiful_places/area/',
            headers={'region': self.region_id},
        )
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    def _get_beautiful_places_categoria(self):
        resp = requests.get(
            f'{self.api_site}/beautiful_places/categoria/',
            headers={'region': self.region_id},
        )
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    def _get_beautiful_places_keywords(self):
        resp = requests.get(
            f'{self.api_site}/beautiful_places/keywords/',
            headers={'region': self.region_id},
        )
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    def _get_beautiful_places_districts(self, area: str | None = None) -> list[str]:
        data = self._get_beautiful_places_area()
        if not data:
            return []

        result: list[str] = []
        for block in data.get('mocDistricts', []):
            if area is not None and block.get('area') != area:
                continue
            for d in block.get('areaDistricts', []):
                if d and d != 'Все':
                    result.append(d)
        return result

    def get_beautiful_places_by_address(
        self,
        user_address: str | None,
        area: str | None,
        categoria: str | None,
        keyword: str | None,
        district: str | None,
        location_latitude: int | float | None,
        location_longitude: int | float | None,
        location_radius: int | None = 5,
        page: int = 1,
        count: int = 10,
    ):
        params: dict[str, int | float | str] = {
            'page': page,
            'count': count,
        }

        has_address = bool(user_address)
        has_coords = location_latitude is not None and location_longitude is not None

        # 1) Приоритет: адрес пользователя → игнорируем area / district / вручную переданные координаты
        if has_address:
            res = self._get_building_id_by_address(user_address)
            if res is None:
                return None
            _, _, building_coords = res
            if (
                building_coords
                and building_coords[0] is not None
                and building_coords[1] is not None
            ):
                params['location_latitude'] = building_coords[0]
                params['location_longitude'] = building_coords[1]
                if location_radius is not None:
                    params['location_radius'] = location_radius

        # 2) Если адреса нет, но есть координаты → игнорируем area / district / user_address
        elif has_coords:
            params['location_latitude'] = location_latitude
            params['location_longitude'] = location_longitude
            if location_radius is not None:
                params['location_radius'] = location_radius

        # 3) Если ни адреса, ни координат → используем area / district (если заданы)
        else:
            if area:
                area_data = self._get_beautiful_places_area()
                if area_data and area in area_data.get('area', []):
                    params['area'] = area

            if district:
                valid_districts = self._get_beautiful_places_districts(area)
                if district in valid_districts:
                    params['district'] = district

        # Остальные фильтры (не зависят от того, что выбрали в качестве "места")
        if categoria:
            cat_data = self._get_beautiful_places_categoria()
            if cat_data and categoria in cat_data.get('category', []):
                params['categoria'] = categoria

        if keyword:
            kw_data = self._get_beautiful_places_keywords()
            if kw_data and keyword in kw_data.get('keywords', []):
                params['keywords'] = keyword

        print(params)

        resp = requests.get(
            f'{self.api_site}/beautiful_places/',
            params=params,
            headers={'region': self.region_id},
        )

        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None

        return resp.json()

    # ---------------- Памятные даты -----------------

    def get_memorable_dates(self):
        resp = requests.get(f'{self.api_site}/memorable_dates/')
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    def get_memorable_dates_by_ids(self, ids: int):
        if ids is None:
            print("параметр 'ids' обязателен для /memorable_dates/ids/")
            return None

        resp = requests.get(
            f'{self.api_site}/memorable_dates/ids/',
            params={'ids': ids},
        )
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    def get_memorable_dates_by_date(self, day: int, month: int):
        resp = requests.get(
            f'{self.api_site}/memorable_dates/date/',
            params={'day': day, 'month': month},
        )
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    # ---------------- MyPets (основной сервис) -----------------

    def get_mypets_all_category(
        self,
        location_latitude: float | None = None,
        location_longitude: float | None = None,
        location_radius: int | None = None,
        types: list[str] | None = None,
    ):
        params: dict[str, float | int | str | list[str]] = {
            'location_latitude': location_latitude,
            'location_longitude': location_longitude,
            'location_radius': location_radius,
            'type': types,
        }
        params = {k: v for k, v in params.items() if v is not None}

        resp = requests.get(
            f'{self.api_site}/mypets/all-category/',
            params=params,
            headers={'region': self.region_id},
        )
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    def get_mypets_animal_breeds(
        self,
        specie: str | None = None,
        breed: str | None = None,
    ):
        if breed is not None and len(breed) < 3:
            print("параметр 'breed' должен быть не короче 3 символов")
            return None

        params: dict[str, str] = {}
        if specie:
            params['specie'] = specie
        if breed:
            params['breed'] = breed

        resp = requests.get(
            f'{self.api_site}/mypets/animal-breeds/',
            params=params,
            headers={'region': self.region_id},
        )
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    def get_mypets_holidays(self):
        resp = requests.get(f'{self.api_site}/mypets/holidays/')
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    def get_mypets_posts(
        self,
        specie: str | None = None,
        page: int = 1,
        size: int = 10,
    ):
        params: dict[str, int | str] = {
            'page': page,
            'size': size,
        }
        if specie:
            params['specie'] = specie

        resp = requests.get(
            f'{self.api_site}/mypets/posts/',
            params=params,
            headers={'region': self.region_id},
        )
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    def get_mypets_posts_id(
        self,
        posts_id: int | None = None,
        app_version: str | None = None,
        user_id: str | None = None,
    ):
        if posts_id is None:
            return None

        params = {'id': posts_id}
        headers: dict[str, str] = {'region': self.region_id}
        if app_version:
            headers['app-version'] = app_version
        if user_id:
            headers['user-id'] = user_id

        resp = requests.get(
            f'{self.api_site}/mypets/posts/id/',
            params=params,
            headers=headers,
        )
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    def get_mypets_recommendations(
        self,
        specie: str | None = None,
        page: int = 1,
        size: int = 10,
    ):
        params: dict[str, int | str] = {
            'page': page,
            'size': size,
        }
        if specie:
            params['specie'] = specie

        resp = requests.get(
            f'{self.api_site}/mypets/recommendations/',
            params=params,
        )
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    # ---------------- MyPets EGS (клиники, парки, приюты) -----------------

    def get_mypets_clinics_id(
        self,
        post_id: int | None = None,
        app_version: str | None = None,
        user_id: str | None = None,
    ):
        if post_id is None:
            return None

        params = {'id': post_id}
        headers: dict[str, str] = {}
        if app_version:
            headers['app-version'] = app_version
        if user_id:
            headers['user-id'] = user_id
        headers['region'] = self.region_id

        resp = requests.get(
            f'{self.api_site}/mypets/clinics/id/',
            params=params,
            headers=headers,
        )
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    def get_mypets_clinics(
        self,
        location_latitude: float | None = None,
        location_longitude: float | None = None,
        location_radius: int | None = 5,
        services: list[str] | None = None,
        user_address: str | None = None,
    ):
        if (location_latitude is None or location_longitude is None) and user_address:
            building_data = self._get_building_id_by_address(user_address)
            if building_data is None:
                return None

            _, _, coords = building_data
            if coords and coords[0] is not None and coords[1] is not None:
                location_latitude, location_longitude = coords

        params: dict[str, float | int | list[str]] = {
            'location_latitude': location_latitude,
            'location_longitude': location_longitude,
            'location_radius': location_radius,
            'services': services,
        }
        params = {k: v for k, v in params.items() if v is not None}

        resp = requests.get(
            f'{self.api_site}/mypets/clinics/',
            params=params,
        )
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    def get_mypets_parks_playground(
        self,
        location_latitude: float | None = None,
        location_longitude: float | None = None,
        location_radius: int | None = None,
        place_type: str | None = None,
    ):
        params: dict[str, float | int | str] = {
            'location_latitude': location_latitude,
            'location_longitude': location_longitude,
            'location_radius': location_radius,
        }
        if place_type:
            params['type'] = place_type

        params = {k: v for k, v in params.items() if v is not None}

        resp = requests.get(
            f'{self.api_site}/mypets/parks-playground/',
            params=params,
        )
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    def get_mypets_parks_playground_id(
        self,
        park_id: int | None = None,
        app_version: str | None = None,
        user_id: str | None = None,
    ):
        if park_id is None:
            return None

        params = {'id': park_id}
        headers: dict[str, str] = {}
        if app_version:
            headers['app-version'] = app_version
        if user_id:
            headers['user-id'] = user_id
        headers['region'] = self.region_id

        resp = requests.get(
            f'{self.api_site}/mypets/parks-playground/id/',
            params=params,
            headers=headers,
        )
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    def get_mypets_shelters(
        self,
        location_latitude: float | None = None,
        location_longitude: float | None = None,
        location_radius: int | None = None,
        specialization: list[str] | None = None,
    ):
        params: dict[str, float | int | list[str]] = {
            'location_latitude': location_latitude,
            'location_longitude': location_longitude,
            'location_radius': location_radius,
            'specialization': specialization,
        }
        params = {k: v for k, v in params.items() if v is not None}

        resp = requests.get(
            f'{self.api_site}/mypets/shelters/',
            params=params,
        )
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    def get_mypets_shelters_id(
        self,
        shelter_id: int | None = None,
        app_version: str | None = None,
        user_id: str | None = None,
    ):
        if shelter_id is None:
            return None

        params = {'id': shelter_id}
        headers: dict[str, str] = {}
        if app_version:
            headers['app-version'] = app_version
        if user_id:
            headers['user-id'] = user_id
        headers['region'] = self.region_id

        resp = requests.get(
            f'{self.api_site}/mypets/shelters/id/',
            params=params,
            headers=headers,
        )
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    # ---------------- Спорт (SportCity) -----------------

    def get_sport_events(
        self,
        categoria: str | None = None,
        type_municipality: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        district: str | None = None,
        ovz: str | None = None,
        family_hour: str | None = None,
        page: int = 1,
        count: int = 10,
        service: str | None = None,
    ):
        params: dict[str, str | int] = {
            'page': page,
            'count': count,
        }
        if categoria:
            params['categoria'] = categoria
        if type_municipality:
            params['type_municipality'] = type_municipality
        if start_date:
            params['start_date'] = start_date
        if end_date:
            params['end_date'] = end_date
        if district:
            params['district'] = district
        if ovz:
            params['ovz'] = ovz
        if family_hour:
            params['family_hour'] = family_hour
        if service:
            params['service'] = service

        headers = {'region': self.region_id}

        resp = requests.get(
            f'{self.api_site}/sport-events/',
            params=params,
            headers=headers,
        )
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    def get_sport_event_by_id(
        self,
        sport_even_id: int | None = None,
        user_id: str | None = None,
    ):
        if sport_even_id is None:
            return None

        params = {'id': sport_even_id}
        headers: dict[str, str] = {'region': self.region_id}
        if user_id:
            headers['user-id'] = user_id

        resp = requests.get(
            f'{self.api_site}/sport-events/id/',
            params=params,
            headers=headers,
        )
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    def get_sport_events_categoria(
        self,
        district: str | None = None,
        service: str | None = None,
        user_id: str | None = None,
    ):
        if district is None:
            return None

        params: dict[str, str] = {'district': district}
        if service:
            params['service'] = service

        headers: dict[str, str] = {'region': self.region_id}
        if user_id:
            headers['user-id'] = user_id

        resp = requests.get(
            f'{self.api_site}/sport-events/categoria/',
            params=params,
            headers=headers,
        )
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    def get_sport_events_map(
        self,
        categoria: str | None = None,
        type_municipality: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        district: str | None = None,
        ovz: str | None = None,
        family_hour: str | None = None,
        service: str | None = None,
    ):
        params: dict[str, str] = {}
        if categoria:
            params['categoria'] = categoria
        if type_municipality:
            params['type_municipality'] = type_municipality
        if start_date:
            params['start_date'] = start_date
        if end_date:
            params['end_date'] = end_date
        if district:
            params['district'] = district
        if ovz:
            params['ovz'] = ovz
        if family_hour:
            params['family_hour'] = family_hour
        if service:
            params['service'] = service

        headers = {'region': self.region_id}

        resp = requests.get(
            f'{self.api_site}/sport-events/map',
            params=params,
            headers=headers,
        )
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    # ---------------- Спортплощадки (SportGrounds) -----------------

    def get_sportgrounds(
        self,
        types: str | None = None,
        ovz: bool | None = None,
        light: bool | None = None,
        district: str | None = None,
        season: str | None = 'Все',
        location_latitude: float | None = None,
        location_longitude: float | None = None,
        location_radius: int | None = None,
        page: int = 1,
        count: int = 10,
    ):
        params: dict[str, float | int | str | bool] = {
            'page': page,
            'count': count,
        }
        if types:
            params['types'] = types
        if ovz is not None:
            params['ovz'] = ovz
        if light is not None:
            params['light'] = light
        if district:
            params['district'] = district
        if season:
            params['season'] = season
        if location_latitude is not None:
            params['location_latitude'] = location_latitude
        if location_longitude is not None:
            params['location_longitude'] = location_longitude
        if location_radius is not None:
            params['location_radius'] = location_radius

        headers = {'region': self.region_id}

        resp = requests.get(
            f'{self.api_site}/sportgrounds/',
            params=params,
            headers=headers,
        )
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    def get_sportgrounds_by_id(
        self,
        sportgrounds_id: int | None = None,
        app_version: str | None = None,
        user_id: str | None = None,
    ):
        if sportgrounds_id is None:
            return None

        params = {'id': sportgrounds_id}
        headers: dict[str, str] = {'region': self.region_id}
        if app_version:
            headers['app-version'] = app_version
        if user_id:
            headers['user-id'] = user_id

        resp = requests.get(
            f'{self.api_site}/sportgrounds/id/',
            params=params,
            headers=headers,
        )
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    def get_sportgrounds_count(self):
        headers = {'region': self.region_id}
        resp = requests.get(
            f'{self.api_site}/sportgrounds/count/',
            headers=headers,
        )
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    def get_sportgrounds_count_district(self, district: str | None = None):
        params: dict[str, str] = {}
        if district:
            params['district'] = district

        headers = {'region': self.region_id}

        resp = requests.get(
            f'{self.api_site}/sportgrounds/count/district/',
            params=params,
            headers=headers,
        )
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    def get_sportgrounds_types(self):
        headers = {'region': self.region_id}
        resp = requests.get(
            f'{self.api_site}/sportgrounds/types/',
            headers=headers,
        )
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    def get_sportgrounds_map(
        self,
        types: str | None = None,
        ovz: bool | None = None,
        light: bool | None = None,
        season: str | None = None,
        location_latitude: float | None = None,
        location_longitude: float | None = None,
        location_radius: int | None = None,
    ):
        params: dict[str, float | int | str | bool] = {}
        if types:
            params['types'] = types
        if ovz is not None:
            params['ovz'] = ovz
        if light is not None:
            params['light'] = light
        if season:
            params['season'] = season
        if location_latitude is not None:
            params['location_latitude'] = location_latitude
        if location_longitude is not None:
            params['location_longitude'] = location_longitude
        if location_radius is not None:
            params['location_radius'] = location_radius

        headers = {'region': self.region_id}

        resp = requests.get(
            f'{self.api_site}/sportgrounds/map/',
            params=params,
            headers=headers,
        )
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    def get_municipality(self):
        resp = requests.get(f'{self.api_geo}/geo/municipality/', headers={'region': self.region_id})
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    def get_district(self):
        resp = requests.get(f'{self.api_geo}/geo/district/', headers={'region': self.region_id})
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None
        return resp.json()

    def get_buildings_info(self, user_address: str):
        res = self._get_building_id_by_address(user_address)
        if res is None:
            return None

        building_id, _, _ = res

        resp = requests.get(
            f'{self.api_geo}/geo/buildings/{building_id}/',
            params={'region_of_search': self.region_id},
            headers={'region': self.region_id},
        )
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None

        return resp.json()

    def get_info_mancompany_by_address(self, user_address: str):
        res = self._get_building_id_by_address(user_address)
        if res is None:
            return None

        building_id, _, _ = res

        base_geo = api_geo.rstrip('/')
        resp = requests.get(
            f'{base_geo}/api/v1/mancompany/{building_id}',
            headers={'region': self.region_id},
        )
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None

        return resp.json()

    def get_info_mancompany_company(
        self,
        user_address: str | None = None,
        company_name: str | None = None,
        company_inn: str | None = None,
    ):
        base_geo = api_geo.rstrip('/')
        params: dict[str, str] = {}

        if user_address:
            mancompany = self.get_info_mancompany_by_address(user_address)
            if not mancompany or 'data' not in mancompany:
                return None

            company_id = mancompany['data'].get('id')
            if not company_id:
                return None

            params['company_id'] = str(company_id)

        if company_name:
            params['company_name'] = company_name
        if company_inn:
            params['company_inn'] = company_inn

        resp = requests.get(
            f'{base_geo}/api/v1/mancompany/company/',
            params=params or None,
            headers={'region': self.region_id},
        )
        if resp.status_code != 200:
            print(f'код ошибки {resp.status_code}')
            return None

        return resp.json()


if __name__ == '__main__':

    client = CityAppClient()
    user_address = 'ул. Танкиста Хрустицкого, д. 62, л. А'
    district = 'Кировский'

    def section(title: str) -> None:
        print('\n' + '=' * 80)
        print(title)
        print('=' * 80)

    # 1. Базовая геоинформация по адресу
    section('1. Гео по адресу')
    building = client._get_building_id_by_address(user_address)
    print('Результат _get_building_id_by_address:')
    pprint(building)
    coords = None
    if building:
        building_id, full_address, coords = building
        print('ID здания:', building_id)
        print('Полный адрес:', full_address)
        print('Координаты:', coords)
    else:
        print('Здание по адресу не найдено')

    # 2. МФЦ
    section('2. МФЦ по адресу и по району')
    print('Ближайший МФЦ к адресу:')
    pprint(client.find_nearest_mfc(user_address))

    mfc_list = client.get_mfc_by_district(district)
    print(f'\nМФЦ в районе {district}: всего {len(mfc_list) if mfc_list else 0}')
    if mfc_list:
        print('Первый МФЦ:')
        pprint(mfc_list[0])

    # 3. Поликлиники
    section('3. Поликлиники по адресу')
    poly = client.get_polyclinics_by_address(user_address)
    print('Поликлиники:', f'найдено {len(poly)}' if poly else 'ничего не найдено')
    if poly:
        pprint(poly[0])

    # 4. Школы и детсады
    section('4. Школы и детские сады')
    schools = client.get_schools_by_district(district)
    print(f'Школы в районе {district}:', f'{len(schools)} шт.' if schools else 'нет данных')
    if schools:
        pprint(schools[0])

    linked = client.get_linked_schools(user_address)
    print('\nШколы, привязанные к адресу:')
    pprint(linked)

    dou = client.get_dou(district=district, age_year=3)
    print(f'\nДетские сады в районе {district} для 3 лет:')
    pprint(dou)

    # 5. Услуги для пенсионеров
    section('5. Услуги для пенсионеров')
    print('Категории услуг:')
    pprint(client.pensioner_service_category())

    print(f'\nУслуги для пенсионеров в районе {district}:')
    pprint(client.pensioner_services(district=district, category=['Вокал'], count=5))

    # 6. Афиша города
    section('6. Афиша города')
    start_date = '2024-11-01T00:00:00'
    end_date = '2024-12-31T23:59:59'

    print('Категории афиши:')
    pprint(client.afisha_categories(start_date, end_date))

    print('\nСобытия афиши (театры, для детей):')
    pprint(client.afisha_events(start_date, end_date, categoria='Театр', kids=True))

    # 7. Новости
    section('7. Новости')
    print('Роли новостей:')
    pprint(client.get_news_role())

    print('\nРайоны для новостей:')
    pprint(client.take_news_district())

    print(f'\nНовости по району {district} (первые 5):')
    news = client.take_news(district=district, count=5, page=1)
    if isinstance(news, list):
        print(f'Всего новостей: {len(news)}')
        if news:
            pprint(news[0])
    else:
        pprint(news)

    # 8. Интересные места
    section('8. Интересные места (beautiful_places)')
    bp = client.get_beautiful_places_by_address(
        user_address=user_address,
        area=None,
        categoria=None,
        keyword=None,
        district=district,
        location_latitude=None,
        location_longitude=None,
        location_radius=5,
        page=1,
        count=5,
    )
    print('Интересные места около адреса / в районе:')
    pprint(bp)

    # 9. Памятные даты
    section('9. Памятные даты')
    md_all = client.get_memorable_dates()
    print('Все памятные даты (фрагмент):')
    if isinstance(md_all, list) and md_all:
        pprint(md_all[:3])
    else:
        pprint(md_all)

    print('\nПамятные даты на 1 января:')
    pprint(client.get_memorable_dates_by_date(day=1, month=1))

    # 10. MyPets (основной сервис)
    section('10. MyPets: категории рядом с адресом')
    lat, lon = (coords or (None, None))
    pets_all = client.get_mypets_all_category(
        location_latitude=lat,
        location_longitude=lon,
        location_radius=3,
    )
    pprint(pets_all)

    print('\nПороды животных (пример, specie=собака):')
    pprint(client.get_mypets_animal_breeds(specie='собака', breed=None))

    print('\nПраздники MyPets:')
    pprint(client.get_mypets_holidays())

    print('\nПосты MyPets:')
    pprint(client.get_mypets_posts(page=1, size=5))

    # 11. MyPets EGS (клиники, парки, приюты)
    section('11. MyPets EGS: клиники / парки / приюты')
    print('Клиники MyPets по адресу (через user_address):')
    clinics = client.get_mypets_clinics(
        user_address=user_address,
        location_radius=3,
    )
    pprint(clinics)

    print('\nПарки / площадки MyPets по координатам:')
    parks = client.get_mypets_parks_playground(
        location_latitude=lat,
        location_longitude=lon,
        location_radius=3,
    )
    pprint(parks)

    print('\nПриюты MyPets по координатам:')
    shelters = client.get_mypets_shelters(
        location_latitude=lat,
        location_longitude=lon,
        location_radius=5,
    )
    pprint(shelters)

    # 12. Спорт и спортплощадки
    section('12. Спорт и спортплощадки')
    print('Спортивные события в районе / городе:')
    sport_events = client.get_sport_events(
        district=district,
        page=1,
        count=5,
    )
    pprint(sport_events)

    print('\nСпортивные площадки рядом с адресом:')
    sportgrounds = client.get_sportgrounds(
        district=district,
        location_latitude=lat,
        location_longitude=lon,
        location_radius=3,
        page=1,
        count=5,
    )
    pprint(sportgrounds)

    print('\nСчётчики спортплощадок по району:')
    pprint(client.get_sportgrounds_count_district(district=district))

    print('\nТипы спортплощадок:')
    pprint(client.get_sportgrounds_types())

    print('\nКарта спортплощадок (фильтр по району):')
    pprint(
        client.get_sportgrounds_map(
            district if 'district' in client.get_sportgrounds_count_district(district) else None
        )
    )

    # 13. Муниципалитеты и районы
    section('13. Муниципалитеты и районы')
    print('Муниципалитеты региона:')
    pprint(client.get_municipality())

    print('\nРайоны региона:')
    pprint(client.get_district())

    # 14. Здание и управляющая компания
    section('14. Здание и управляющая компания (mancompany)')
    print('Информация о здании по адресу:')
    try:
        pprint(client.get_buildings_info(user_address))
    except Exception as e:
        print('Ошибка при вызове get_buildings_info:', e)

    print('\nУправляющая компания по адресу:')
    try:
        pprint(client.get_info_mancompany_by_address(user_address))
    except Exception as e:
        print('Ошибка при вызове get_info_mancompany_by_address:', e)

    print('\nКомпании, связанные с адресом (company_id по адресу):')
    try:
        pprint(client.get_info_mancompany_company(user_address=user_address))
    except Exception as e:
        print('Ошибка при вызове get_info_mancompany_company(user_address=...):', e)


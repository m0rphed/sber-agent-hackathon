from typing import Any
import requests

from app.config import API_GEO as api_geo, API_SITE as api_site, REGION_ID as DEFAULT_REGION_ID


class CityAppClient:
    def __init__(self, api_geo=api_geo, api_site=api_site, region_id: str = DEFAULT_REGION_ID):
        # чуть нормализуем, чтобы не было `//` в середине
        self.api_geo = f'{api_geo.rstrip("/")}/api/v2'
        self.api_site = api_site.rstrip('/')
        self.region_id = region_id

    # Определяет ID здания по адресу пользователя
    def _get_building_id_by_address(self, user_address):
        resp = requests.get(
            f'{self.api_geo}/geo/buildings/search/',
            params={
                'query': user_address,
                'count': 5,
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
        )

    # ---------------- МФЦ (2.2) ----------------
    def find_nearest_mfc(self, user_address):
        res = self._get_building_id_by_address(user_address)
        if res is None:
            return None

        building_id, building_address = res
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

        building_id, _ = building_data

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

        building_id, _ = building_data

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
        resp.raise_for_status()
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
        resp.raise_for_status()
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

    def afisha_events(self, start_date: str, end_date: str,
                      categoria: str = '', kids: bool | None = None, free: bool | None = None):
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
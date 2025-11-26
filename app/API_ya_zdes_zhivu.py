from cfg import API_GEO as api_geo, API_SITE as api_site, REGION_ID as DEFAULT_REGION_ID
import requests


class CityAppClient:
    def __init__(self, api_geo=api_geo, api_site=api_site, region_id: str = DEFAULT_REGION_ID):
        self.api_geo = f'{api_geo}/api/v2'
        self.api_site = f'{api_site}/'
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

    def find_nearest_mfc(self, user_address):
        building_id, building_address = self._get_building_id_by_address(
            user_address
        )
        if building_id is None:
            return None

        resp = requests.get(
            f'{self.api_site}/mfc/',
            params={
                'id_building': building_id,
                'region': self.region_id,
            }
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


if __name__ == '__main__':
    app = CityAppClient()
    print(app.find_nearest_mfc('Большевиков 68 к1'))

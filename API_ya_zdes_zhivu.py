import requests

api_geo = 'https://yazzh-geo.gate.petersburg.ru'
api_site = 'https://yazzh.gate.petersburg.ru'

region_id = '78'

def geo_building_search(user_address: str):
    url = f"{api_geo}/api/v2/geo/buildings/search/"
    parametrs = {
        'query': user_address,
        'count': 3,
        'region_of_search': region_id
    }
    header = {
        'region': region_id
    }

    response = requests.get(url, params=parametrs, headers=header)
    result = response.json()
    data = result.get('data', [])

    return data
    

def find_an_MFC_by_address(user_address):
    MFC_address = geo_building_search(user_address)
    return MFC_address #.get('full_address',[])

if __name__ == '__main__':
    #print(geo_building_search(user_address = 'Невский 1'))
    print(find_an_MFC_by_address('Невский 1'))
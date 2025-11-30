import pytest
from datetime import datetime

from app.api.yazz import CityAppClient
from app.config import REGION_ID as DEFAULT_REGION_ID

from pprint import pprint

@pytest.fixture
def client():
    """
    Fixture для создания клиента API
    """
    return CityAppClient()


class TestYazzRequestsV2:
    def test_all(self, client: CityAppClient):
        _other_test_addr_1 = 'ул. Танкиста Хрустицкого, д. 60'
        _other_test_addr_2 = 'Ботаническая д. 3, к. 3, литера А'
        user_address = 'пр. Большевиков, д. 68, к. 1, стр. 1'
        district = 'Невский'

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

        print('\nПороды животных (пример, specie=dog):')
        pprint(client.get_mypets_animal_breeds(specie='dog', breed=None))

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
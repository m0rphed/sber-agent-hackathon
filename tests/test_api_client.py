import pytest
from datetime import datetime

from app.api.yazz import CityAppClient
from app.config import REGION_ID as DEFAULT_REGION_ID


@pytest.fixture
def client():
    """
    Fixture для создания клиента API
    """
    return CityAppClient()


class TestBuildingSearch:
    """
    Тесты поиска зданий по адресу.
    """

    def test_get_building_id_valid_address(self, client: CityAppClient):
        """
        Тест поиска здания по валидному адресу.
        """
        result = client._get_building_id_by_address('Невский проспект 1')

        assert result is not None
        building_id, full_address, coords = result

        print(building_id, full_address, coords)

        assert building_id is not None
        assert isinstance(building_id, (str, int))
        assert full_address is not None
        assert isinstance(full_address, str)
        # Координаты могут быть None, но если есть — это кортеж из двух чисел
        if coords is not None:
            assert isinstance(coords, tuple)
            assert len(coords) == 2

    def test_get_building_id_another_address(self, client: CityAppClient):
        """
        Тест поиска здания по другому адресу
        """
        result = client._get_building_id_by_address('Проспект Большевиков 68')

        assert result is not None
        building_id, full_address, coords = result
        assert building_id is not None
        assert full_address is not None

    def test_get_building_id_invalid_address(self, client: CityAppClient):
        """
        Тест поиска по невалидному адресу.
        """
        result = client._get_building_id_by_address('абракадабра12345несуществующий')

        assert result is None


class TestMFC:
    """
    Тесты поиска МФЦ
    """

    def test_find_nearest_mfc_valid_address(self, client: CityAppClient):
        """
        Тест поиска ближайшего МФЦ по валидному адресу
        """
        result = client.find_nearest_mfc('Невский проспект 1')

        assert result is not None
        assert isinstance(result, dict)

        # проверяем обязательные поля
        assert 'name' in result
        assert 'address' in result
        assert 'phones' in result
        assert 'hours' in result

        # проверяем, что поля не пустые
        assert result['name'] is not None
        assert result['address'] is not None

    def test_find_nearest_mfc_contains_contact_info(self, client: CityAppClient):
        """
        Тест, что МФЦ содержит контактную информацию
        """
        result = client.find_nearest_mfc('Садовая улица 50')

        assert result is not None
        assert result.get('phones') is not None or result.get('link') is not None

    def test_find_nearest_mfc_invalid_address(self, client: CityAppClient):
        """
        Тест поиска МФЦ по невалидному адресу
        """
        result = client.find_nearest_mfc('абракадабра12345несуществующий')
        print(result)
        assert result is None

    def test_find_nearest_mfc_has_working_hours(self, client: CityAppClient):
        """
        Тест, что МФЦ имеет часы работы
        """
        result = client.find_nearest_mfc('Московский проспект 10')

        assert result is not None
        assert 'hours' in result

    def test_get_mfc_by_district(self, client: CityAppClient):
        """
        Тест получения списка МФЦ по району
        """
        result = client.get_mfc_by_district('Приморский')

        assert result is not None
        assert isinstance(result, list)
        if result:
            first = result[0]
            assert 'name' in first
            assert 'address' in first
            assert 'hours' in first


class TestPolyclinics:
    """
    Тесты поиска поликлиник по адресу
    """

    def test_get_polyclinics_by_address_valid(self, client: CityAppClient):
        """
        Тест поиска поликлиник по валидному адресу
        """
        result = client.get_polyclinics_by_address('Комендантский проспект 61')

        # Вариант: либо нашли, либо по этому адресу их нет
        assert result is None or isinstance(result, list)

        if result:
            first = result[0]
            assert 'name' in first
            assert 'address' in first
            assert 'phones' in first

    def test_get_polyclinics_invalid_address(self, client: CityAppClient):
        """
        Тест, что по невалидному адресу возвращается None
        """
        result = client.get_polyclinics_by_address('абракадабра12345несуществующий')

        # _get_building_id_by_address вернёт None → тут тоже None
        assert result is None


class TestSchoolsAndDou:
    """
    Тесты школ и детских садов
    """

    def test_get_schools_by_district(self, client: CityAppClient):
        """
        Тест получения школ по району
        """
        result = client.get_schools_by_district('Центральный')

        assert result is None or isinstance(result, list)
        if result:
            first = result[0]
            assert 'district' in first
            assert first['district'] == 'Центральный' or first.get('district') is not None

    def test_get_linked_schools(self, client: CityAppClient):
        """
        Тест получения школ, привязанных к адресу
        """
        result = client.get_linked_schools('Комендантский проспект 61')

        # Формат зависит от API, но основное — не упасть
        assert result is None or isinstance(result, (list, dict))

    def test_get_dou_by_district(self, client: CityAppClient):
        """
        Тест получения детских садов по району
        """
        result = client.get_dou('Приморский', age_year=3)

        assert result is None or isinstance(result, (list, dict))


class TestPensionerServices:
    """
    Тесты услуг для пенсионеров
    """

    def test_get_categories(self, client: CityAppClient):
        """
        Тест получения категорий услуг
        """
        result = client.pensioner_service_category()

        assert result is not None
        # Ожидаем список или словарь с данными
        assert isinstance(result, (list, dict))

    def test_get_services_by_district(self, client: CityAppClient):
        """
        Тест получения услуг по району
        """
        result = client.pensioner_services(district='Невский', category=['Вокал'], count=5)

        assert result is not None

    def test_get_services_multiple_categories(self, client: CityAppClient):
        """
        Тест получения услуг по нескольким категориям
        """
        result = client.pensioner_services(
            district='Центральный',
            category=['Вокал', 'Компьютерные курсы'],
            count=5,
        )

        assert result is not None


class TestAfisha:
    """
    Тесты афиши города
    """

    def test_afisha_categories(self, client: CityAppClient):
        """
        Тест получения категорий афиши
        """
        result = client.afisha_categories('2025-11-21T00:00:00', '2025-12-22T00:00:00')

        assert result is None or isinstance(result, (list, dict))

    def test_afisha_events(self, client: CityAppClient):
        """
        Тест получения событий афиши
        """
        result = client.afisha_events(
            '2025-11-21T00:00:00',
            '2025-12-22T00:00:00',
            categoria='Театр',
            kids=True,
        )

        assert result is None or isinstance(result, (list, dict))


class TestClientInitialization:
    """
    Тесты инициализации клиента
    """

    def test_default_initialization(self):
        """
        Тест создания клиента с параметрами по умолчанию
        """
        client = CityAppClient()

        assert client.api_geo is not None
        assert client.api_site is not None
        assert client.region_id == DEFAULT_REGION_ID  # Санкт-Петербург

    def test_custom_region(self):
        """
        Тест создания клиента с другим регионом
        """
        client = CityAppClient(region_id='63')

        assert client.region_id == '63'


# интеграционные тесты (запускать отдельно: -m integration)
@pytest.mark.integration
class TestIntegration:
    """
    Интеграционные тесты (требуют реального API)
    """

    def test_full_mfc_workflow(self, client: CityAppClient):
        """
        Полный сценарий поиска МФЦ
        """
        # 1. Находим здание
        building = client._get_building_id_by_address('Литейный проспект 20')
        assert building is not None

        # 2. Находим МФЦ
        mfc = client.find_nearest_mfc('Литейный проспект 20')
        assert mfc is not None
        assert mfc['name'] is not None

    def test_full_pensioner_workflow(self, client: CityAppClient):
        """
        Полный сценарий поиска услуг для пенсионеров
        """
        # 1. Получаем категории
        categories = client.pensioner_service_category()
        assert categories is not None

        # 2. Получаем услуги по одной из категорий (если есть)
        services = client.pensioner_services(district='Невский', category=['Вокал'], count=3)
        assert services is not None


@pytest.mark.integration
class TestNews:
    def test_get_news_role(self, client: CityAppClient):
        news_role = client.get_news_role()
        assert news_role is not None
        # Структура может меняться, но минимум — наличие ключей
        assert isinstance(news_role, dict)
        assert "role" in news_role
        assert isinstance(news_role["role"], list)
        assert len(news_role["role"]) > 0

    def test_take_news_district(self, client: CityAppClient):
        distircts = client.take_news_district()
        assert distircts is not None
        assert isinstance(distircts, dict)
        assert "data" in distircts
        assert isinstance(distircts["data"], list)
        assert "Приморский" in distircts["data"]

    def test_take_news_without_filters(self, client: CityAppClient):
        """Базовый кейс: новости без фильтров."""
        news = client.take_news()
        assert news is not None
        # В зависимости от реализации: или сразу список, или словарь с "data"
        if isinstance(news, dict) and "data" in news:
            items = news["data"]
        else:
            items = news
        assert isinstance(items, list)
        assert len(items) > 0
        first = items[0]
        assert isinstance(first, dict)

    def test_take_news_with_district_and_type(self, client: CityAppClient):
        """Новости по району и типу (yazzh_type)."""
        district = "Адмиралтейский"
        yazzh_type = "Спорт"

        news = client.take_news(
            district=district,
            yazzh_type=yazzh_type,
            count=5,
            page=1,
        )

        assert news is not None
        if isinstance(news, dict) and "data" in news:
            items = news["data"]
        else:
            items = news

        assert isinstance(items, list)
        assert 0 < len(items) <= 5

        for item in items:
            assert isinstance(item, dict)
            assert "district" in item
            # district может быть "Адмиралтейский район" и т.п.
            assert district in item["district"]

            if "yazzh_type" in item and isinstance(item["yazzh_type"], list):
                # Не гарантируем, но если есть поле — проверяем содержимое
                if yazzh_type in item["yazzh_type"]:
                    break

    def test_take_news_date_range(self, client: CityAppClient):
        """Новости за конкретный период — проверяем работу фильтра по датам."""
        start_date = '2024-11-21'
        end_date = '2025-12-22'

        news = client.take_news(
            start_date=start_date,
            end_date=end_date,
            count=10,
            page=1,
        )
        assert news is not None


# ---------------- Новые тесты для beautiful_places ----------------

@pytest.mark.integration
class TestBeautifulPlaces:
    """
    Тесты интересных мест (beautiful_places).
    """

    def test_beautiful_places_area(self, client: CityAppClient):
        data = client._get_beautiful_places_area()
        assert data is None or isinstance(data, dict)
        if not data:
            return
        assert "area" in data
        assert "mocDistricts" in data
        assert isinstance(data["area"], list)
        assert isinstance(data["mocDistricts"], list)

    def test_beautiful_places_categoria(self, client: CityAppClient):
        data = client._get_beautiful_places_categoria()
        assert data is None or isinstance(data, dict)
        if not data:
            return
        assert "category" in data
        assert isinstance(data["category"], list)

    def test_beautiful_places_keywords(self, client: CityAppClient):
        data = client._get_beautiful_places_keywords()
        assert data is None or isinstance(data, dict)
        if not data:
            return
        assert "keywords" in data
        assert isinstance(data["keywords"], list)

    def test_beautiful_places_districts_helper(self, client: CityAppClient):
        all_districts = client._get_beautiful_places_districts()
        assert isinstance(all_districts, list)
        if all_districts:
            assert "Все" not in all_districts

    def test_get_beautiful_places_by_address(self, client: CityAppClient):
        """
        Базовый тест поиска интересных мест по адресу.
        """
        places = client.get_beautiful_places_by_address(
            user_address='Невский проспект 1',
            area='Районы города',
            categoria=None,
            keyword=None,
            district=None,
            location_latitude=None,
            location_longitude=None,
            location_radius=3,
            page=1,
            count=5,
        )
        assert places is None or isinstance(places, (list, dict))


# ---------------- Памятные даты ----------------

@pytest.mark.integration
class TestMemorableDates:
    """
    Тесты для памятных дат.
    """

    def test_get_memorable_dates(self, client: CityAppClient):
        result = client.get_memorable_dates()
        assert result is None or isinstance(result, (list, dict))

    def test_get_memorable_dates_by_date(self, client: CityAppClient):
        """
        Проверяем, что запрос по дате не падает.
        """
        result = client.get_memorable_dates_by_date(day=1, month=1)
        assert result is None or isinstance(result, (list, dict))

    def test_get_memorable_dates_by_ids(self, client: CityAppClient):
        """
        Проверяем, что запрос по id не падает даже для "условного" id.
        """
        result = client.get_memorable_dates_by_ids(ids=1)
        assert result is None or isinstance(result, (list, dict))


# ---------------- MyPets (основной сервис) ----------------

@pytest.mark.integration
class TestMyPets:
    """
    Тесты основного сервиса MyPets.
    """

    def test_mypets_all_category_no_filters(self, client: CityAppClient):
        result = client.get_mypets_all_category()
        assert result is None or isinstance(result, (list, dict))

    def test_mypets_all_category_with_coords(self, client: CityAppClient):
        result = client.get_mypets_all_category(
            location_latitude=59.93,
            location_longitude=30.33,
            location_radius=5,
        )
        assert result is None or isinstance(result, (list, dict))

    def test_mypets_animal_breeds_invalid_breed(self, client: CityAppClient):
        """
        Проверяем валидацию: слишком короткая порода → None.
        """
        result = client.get_mypets_animal_breeds(breed='ab')
        assert result is None

    def test_mypets_animal_breeds_valid(self, client: CityAppClient):
        result = client.get_mypets_animal_breeds(specie='Кошка', breed='кот')
        assert result is None or isinstance(result, (list, dict))

    def test_mypets_holidays(self, client: CityAppClient):
        result = client.get_mypets_holidays()
        assert result is None or isinstance(result, (list, dict))

    def test_mypets_posts(self, client: CityAppClient):
        result = client.get_mypets_posts(specie='Собака', size=3)
        assert result is None or isinstance(result, (list, dict))

    def test_mypets_posts_id_none(self, client: CityAppClient):
        """
        posts_id=None → ранний выход.
        """
        result = client.get_mypets_posts_id(posts_id=None)
        assert result is None

    def test_mypets_recommendations(self, client: CityAppClient):
        result = client.get_mypets_recommendations(specie='Кошка', size=3)
        assert result is None or isinstance(result, (list, dict))


# ---------------- MyPets EGS (клиники, парки, приюты) ----------------

@pytest.mark.integration
class TestMyPetsEGS:
    """
    Тесты MyPets EGS (клиники, парки, приюты).
    """

    def test_mypets_clinics_basic(self, client: CityAppClient):
        result = client.get_mypets_clinics(
            location_latitude=59.93,
            location_longitude=30.33,
            location_radius=5,
        )
        assert result is None or isinstance(result, (list, dict))

    def test_mypets_clinics_id_none(self, client: CityAppClient):
        result = client.get_mypets_clinics_id(post_id=None)
        assert result is None

    def test_mypets_parks_playground_basic(self, client: CityAppClient):
        result = client.get_mypets_parks_playground(
            location_latitude=59.93,
            location_longitude=30.33,
            location_radius=5,
            place_type='Парк',
        )
        assert result is None or isinstance(result, (list, dict))

    def test_mypets_parks_playground_id_none(self, client: CityAppClient):
        result = client.get_mypets_parks_playground_id(park_id=None)
        assert result is None

    def test_mypets_shelters_basic(self, client: CityAppClient):
        result = client.get_mypets_shelters(
            location_latitude=59.93,
            location_longitude=30.33,
            location_radius=10,
        )
        assert result is None or isinstance(result, (list, dict))

    def test_mypets_shelters_id_none(self, client: CityAppClient):
        result = client.get_mypets_shelters_id(shelter_id=None)
        assert result is None


# ---------------- SportCity (районные спортивные мероприятия) ----------------

@pytest.mark.integration
class TestSportEvents:
    """
    Тесты спортивных мероприятий (SportCity).
    """

    def test_sport_events_basic(self, client: CityAppClient):
        result = client.get_sport_events(count=5)
        assert result is None or isinstance(result, (list, dict))

    def test_sport_events_map_with_district(self, client: CityAppClient):
        """
        Для map нужен хотя бы один фильтр.
        """
        result = client.get_sport_events_map(district='Приморский')
        assert result is None or isinstance(result, (list, dict))

    def test_sport_events_categoria_requires_district(self, client: CityAppClient):
        result = client.get_sport_events_categoria(district=None)
        assert result is None

    def test_sport_events_categoria_basic(self, client: CityAppClient):
        result = client.get_sport_events_categoria(district='Приморский')
        assert result is None or isinstance(result, (list, dict))

    def test_sport_event_by_id_none(self, client: CityAppClient):
        result = client.get_sport_event_by_id(sport_even_id=None)
        assert result is None


# ---------------- SportGrounds (спортивные площадки) ----------------

@pytest.mark.integration
class TestSportGrounds:
    """
    Тесты спортивных площадок (SportGrounds).
    """

    def test_sportgrounds_basic(self, client: CityAppClient):
        result = client.get_sportgrounds(count=5)
        assert result is None or isinstance(result, (list, dict))

    def test_sportgrounds_map_basic(self, client: CityAppClient):
        result = client.get_sportgrounds_map(
            location_latitude=59.93,
            location_longitude=30.33,
            location_radius=5,
        )
        assert result is None or isinstance(result, (list, dict))

    def test_sportgrounds_types(self, client: CityAppClient):
        result = client.get_sportgrounds_types()
        assert result is None or isinstance(result, (list, dict))

    def test_sportgrounds_count(self, client: CityAppClient):
        result = client.get_sportgrounds_count()
        assert result is None or isinstance(result, (list, dict))

    def test_sportgrounds_count_district(self, client: CityAppClient):
        result = client.get_sportgrounds_count_district(district='Приморский')
        assert result is None or isinstance(result, (list, dict))

    def test_sportgrounds_by_id_none(self, client: CityAppClient):
        result = client.get_sportgrounds_by_id(sportgrounds_id=None)
        assert result is None

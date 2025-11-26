"""Тесты для API клиента 'Я Здесь Живу'."""

import pytest

from app.api.yazz import CityAppClient
from app.config import API_GEO as api_geo, API_SITE as api_site, REGION_ID as DEFAULT_REGION_ID


@pytest.fixture
def client():
    """
    Fixture для создания клиента API.
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
        building_id, full_address = result

        print(building_id, full_address)

        assert building_id is not None
        assert isinstance(building_id, (str, int))
        assert full_address is not None
        assert isinstance(full_address, str)

    def test_get_building_id_another_address(self, client: CityAppClient):
        """Тест поиска здания по другому адресу."""
        result = client._get_building_id_by_address('Проспект Большевиков 68')

        assert result is not None
        building_id, full_address = result
        assert building_id is not None
        assert full_address is not None

    def test_get_building_id_invalid_address(self, client: CityAppClient):
        """
        Тест поиска по невалидному адресу.
        """
        result = client._get_building_id_by_address('абракадабра12345несуществующий')

        assert result is None


class TestMFC:
    """Тесты поиска МФЦ."""

    def test_find_nearest_mfc_valid_address(self, client: CityAppClient):
        """Тест поиска ближайшего МФЦ по валидному адресу."""
        result = client.find_nearest_mfc('Невский проспект 1')

        assert result is not None
        assert isinstance(result, dict)

        # Проверяем обязательные поля
        assert 'name' in result
        assert 'address' in result
        assert 'phones' in result
        assert 'hours' in result

        # Проверяем, что поля не пустые
        assert result['name'] is not None
        assert result['address'] is not None

    def test_find_nearest_mfc_contains_contact_info(self, client: CityAppClient):
        """Тест, что МФЦ содержит контактную информацию."""
        result = client.find_nearest_mfc('Садовая улица 50')

        assert result is not None
        assert result.get('phones') is not None or result.get('link') is not None

    def test_find_nearest_mfc_invalid_address(self, client: CityAppClient):
        """Тест поиска МФЦ по невалидному адресу."""
        result = client.find_nearest_mfc('абракадабра12345несуществующий')
        print(result)
        assert result is None

    def test_find_nearest_mfc_has_working_hours(self, client: CityAppClient):
        """Тест, что МФЦ имеет часы работы."""
        result = client.find_nearest_mfc('Московский проспект 10')

        assert result is not None
        assert 'hours' in result 

    def test_get_mfc_by_district(self, client: CityAppClient):
        """Тест получения списка МФЦ по району."""
        result = client.get_mfc_by_district('Приморский')

        assert result is not None
        assert isinstance(result, list)
        if result:
            first = result[0]
            assert 'name' in first
            assert 'address' in first
            assert 'hours' in first


class TestPolyclinics:
    """Тесты поиска поликлиник по адресу."""

    def test_get_polyclinics_by_address_valid(self, client: CityAppClient):
        """Тест поиска поликлиник по валидному адресу."""
        result = client.get_polyclinics_by_address('Комендантский проспект 61')

        # Вариант: либо нашли, либо по этому адресу их нет
        assert result is None or isinstance(result, list)

        if result:
            first = result[0]
            assert 'name' in first
            assert 'address' in first
            assert 'phones' in first

    def test_get_polyclinics_invalid_address(self, client: CityAppClient):
        """Тест, что по невалидному адресу возвращается None."""
        result = client.get_polyclinics_by_address('абракадабра12345несуществующий')

        # _get_building_id_by_address вернёт None → тут тоже None
        assert result is None


class TestSchoolsAndDou:
    """Тесты школ и детских садов."""

    def test_get_schools_by_district(self, client: CityAppClient):
        """Тест получения школ по району."""
        result = client.get_schools_by_district('Центральный')

        assert result is None or isinstance(result, list)
        if result:
            first = result[0]
            assert 'district' in first
            assert first['district'] == 'Центральный' or first.get('district') is not None

    def test_get_linked_schools(self, client: CityAppClient):
        """Тест получения школ, привязанных к адресу."""
        result = client.get_linked_schools('Комендантский проспект 61')

        # Формат зависит от API, но основное — не упасть
        assert result is None or isinstance(result, (list, dict))

    def test_get_dou_by_district(self, client: CityAppClient):
        """Тест получения детских садов по району."""
        result = client.get_dou('Приморский', age_year=3)

        assert result is None or isinstance(result, (list, dict))


class TestPensionerServices:
    """Тесты услуг для пенсионеров."""

    def test_get_categories(self, client: CityAppClient):
        """Тест получения категорий услуг."""
        result = client.pensioner_service_category()

        assert result is not None
        # Ожидаем список или словарь с данными
        assert isinstance(result, (list, dict))

    def test_get_services_by_district(self, client: CityAppClient):
        """Тест получения услуг по району."""
        result = client.pensioner_services(district='Невский', category=['Вокал'], count=5)

        assert result is not None

    def test_get_services_multiple_categories(self, client: CityAppClient):
        """Тест получения услуг по нескольким категориям."""
        result = client.pensioner_services(
            district='Центральный',
            category=['Вокал', 'Компьютерные курсы'],
            count=5,
        )

        assert result is not None


class TestAfisha:
    """Тесты афиши города."""

    def test_afisha_categories(self, client: CityAppClient):
        """Тест получения категорий афиши."""
        result = client.afisha_categories('2025-11-21T00:00:00', '2025-12-22T00:00:00')

        assert result is None or isinstance(result, (list, dict))

    def test_afisha_events(self, client: CityAppClient):
        """Тест получения событий афиши."""
        result = client.afisha_events(
            '2025-11-21T00:00:00',
            '2025-12-22T00:00:00',
            categoria='Театр',
            kids=True,
        )

        assert result is None or isinstance(result, (list, dict))


class TestClientInitialization:
    """Тесты инициализации клиента."""

    def test_default_initialization(self):
        """Тест создания клиента с параметрами по умолчанию."""
        client = CityAppClient()

        assert client.api_geo is not None
        assert client.api_site is not None
        assert client.region_id == DEFAULT_REGION_ID  # Санкт-Петербург

    def test_custom_region(self):
        """Тест создания клиента с другим регионом."""
        client = CityAppClient(region_id='63')

        assert client.region_id == '63'


# Интеграционные тесты (можно запускать отдельно: -m integration)
@pytest.mark.integration
class TestIntegration:
    """Интеграционные тесты (требуют реального API)."""

    def test_full_mfc_workflow(self, client: CityAppClient):
        """Полный сценарий поиска МФЦ."""
        # 1. Находим здание
        building = client._get_building_id_by_address('Литейный проспект 20')
        assert building is not None

        # 2. Находим МФЦ
        mfc = client.find_nearest_mfc('Литейный проспект 20')
        assert mfc is not None
        assert mfc['name'] is not None

    def test_full_pensioner_workflow(self, client: CityAppClient):
        """
        Полный сценарий поиска услуг для пенсионеров.
        """
        # 1. Получаем категории
        categories = client.pensioner_service_category()
        assert categories is not None

        # 2. Получаем услуги по одной из категорий (если есть)
        services = client.pensioner_services(district='Невский', category=['Вокал'], count=3)
        assert services is not None

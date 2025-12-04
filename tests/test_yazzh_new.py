"""
Тесты для нового асинхронного клиента YAZZH API.

Запуск:
    pytest tests/test_yazzh_new.py -v
"""

import pytest
import pytest_asyncio

from app.api.yazzh_new import (
    AddressNotFoundError,
    BuildingSearchResult,
    MFCInfo,
    PolyclinicInfo,
    SchoolInfo,
    YazzhAsyncClient,
    format_building_search_for_chat,
    format_mfc_for_chat,
    format_polyclinics_for_chat,
    format_schools_for_chat,
)

# ============================================================================
# Тестовые адреса (известные адреса Санкт-Петербурга)
# ============================================================================

KNOWN_ADDRESSES = [
    'Невский проспект 1',
    'Большевиков 68',
    'Лиговский проспект 50',
    'Московский проспект 100',
]

INVALID_ADDRESS = 'АбраКадабра 999999'


# ============================================================================
# Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def client():
    """Создаёт асинхронный клиент для тестов"""
    async with YazzhAsyncClient() as client:
        yield client


# ============================================================================
# Тесты поиска зданий
# ============================================================================


class TestBuildingSearch:
    """Тесты поиска зданий по адресу"""

    @pytest.mark.asyncio
    async def test_search_building_valid_address(self, client):
        """Поиск по известному адресу должен вернуть результаты"""
        results = await client.search_building('Невский проспект 1')

        assert len(results) > 0
        assert isinstance(results[0], BuildingSearchResult)
        assert results[0].id is not None
        assert results[0].full_address is not None

    @pytest.mark.asyncio
    async def test_search_building_first(self, client):
        """search_building_first должен вернуть один результат"""
        result = await client.search_building_first('Большевиков 68')

        assert isinstance(result, BuildingSearchResult)
        assert result.id is not None
        assert 'Большевиков' in result.full_address.lower() or '68' in result.full_address

    @pytest.mark.asyncio
    async def test_search_building_invalid_address(self, client):
        """Поиск по несуществующему адресу должен вызвать AddressNotFoundError"""
        with pytest.raises(AddressNotFoundError):
            await client.search_building(INVALID_ADDRESS)

    @pytest.mark.asyncio
    async def test_search_building_limit_count(self, client):
        """count должен ограничивать количество результатов"""
        results = await client.search_building('Невский', count=3)

        assert len(results) <= 3

    @pytest.mark.asyncio
    async def test_building_coords(self, client):
        """Результат должен содержать координаты"""
        result = await client.search_building_first('Невский 10')

        assert result.latitude is not None
        assert result.longitude is not None
        assert result.coords is not None
        assert isinstance(result.coords, tuple)
        assert len(result.coords) == 2


# ============================================================================
# Тесты МФЦ
# ============================================================================


class TestMFC:
    """Тесты поиска МФЦ"""

    @pytest.mark.asyncio
    async def test_get_nearest_mfc_by_address(self, client):
        """Поиск МФЦ по адресу должен вернуть результат"""
        mfc = await client.get_nearest_mfc_by_address('Невский проспект 10')

        assert mfc is not None
        assert isinstance(mfc, MFCInfo)
        # Проверяем наличие основных полей
        assert mfc.name is not None or mfc.address is not None

    @pytest.mark.asyncio
    async def test_get_mfc_by_building(self, client):
        """Поиск МФЦ по building_id"""
        # Сначала получаем building_id
        building = await client.search_building_first('Лиговский 50')

        mfc = await client.get_mfc_by_building(building.building_id)

        # МФЦ может не быть для некоторых адресов
        if mfc is not None:
            assert isinstance(mfc, MFCInfo)

    @pytest.mark.asyncio
    async def test_get_all_mfc(self, client):
        """Получение списка всех МФЦ"""
        mfc_list = await client.get_all_mfc()

        assert isinstance(mfc_list, list)
        # В СПб должно быть несколько МФЦ
        assert len(mfc_list) > 0
        assert all(isinstance(m, MFCInfo) for m in mfc_list)

    @pytest.mark.asyncio
    async def test_get_mfc_by_district(self, client):
        """Получение МФЦ по району"""
        mfc_list = await client.get_mfc_by_district('Центральный')

        assert isinstance(mfc_list, list)
        # В Центральном районе должен быть МФЦ
        if mfc_list:
            assert all(isinstance(m, MFCInfo) for m in mfc_list)

    @pytest.mark.asyncio
    async def test_mfc_format_for_human(self, client):
        """Тест форматирования МФЦ для человека"""
        mfc = await client.get_nearest_mfc_by_address('Московский проспект 100')

        if mfc:
            formatted = mfc.format_for_human()
            assert isinstance(formatted, str)
            assert len(formatted) > 0
            # Должен содержать emoji
            assert '📍' in formatted or '🚇' in formatted or '📞' in formatted


# ============================================================================
# Тесты поликлиник
# ============================================================================


class TestPolyclinics:
    """Тесты поиска поликлиник"""

    @pytest.mark.asyncio
    async def test_get_polyclinics_by_address(self, client):
        """Поиск поликлиник по адресу"""
        clinics = await client.get_polyclinics_by_address('Невский проспект 10')

        assert isinstance(clinics, list)
        # Поликлиники должны быть для адресов в СПб
        if clinics:
            assert all(isinstance(c, PolyclinicInfo) for c in clinics)

    @pytest.mark.asyncio
    async def test_polyclinic_format_for_human(self, client):
        """Тест форматирования поликлиники"""
        clinics = await client.get_polyclinics_by_address('Лиговский 50')

        if clinics:
            formatted = clinics[0].format_for_human()
            assert isinstance(formatted, str)
            assert '🏥' in formatted


# ============================================================================
# Тесты школ
# ============================================================================


class TestSchools:
    """Тесты поиска школ"""

    @pytest.mark.asyncio
    async def test_get_linked_schools_by_address(self, client):
        """Получение прикреплённых школ по адресу"""
        schools = await client.get_linked_schools_by_address('Большевиков 68')

        assert isinstance(schools, list)
        if schools:
            assert all(isinstance(s, SchoolInfo) for s in schools)

    @pytest.mark.asyncio
    async def test_school_format_for_human(self):
        """Тест форматирования школы"""
        school = SchoolInfo(
            id=1,
            full_name='Школа №123',
            short_name='Школа 123',
            address='ул. Тестовая, 1',
            district='Невский',
            available_spots=10,
            priority_order=1,
        )

        formatted = school.format_for_human()
        assert '🏫' in formatted
        assert 'Школа' in formatted


# ============================================================================
# Тесты районов
# ============================================================================


class TestDistricts:
    """Тесты работы с районами"""

    @pytest.mark.asyncio
    async def test_get_districts(self, client):
        """Получение списка районов СПб"""
        districts = await client.get_districts()

        assert isinstance(districts, list)
        assert len(districts) > 0  # В СПб 18 районов

        # Проверим наличие известных районов
        district_names = [d.name for d in districts]
        assert any('Невский' in name for name in district_names)


# ============================================================================
# Тесты УК (управляющих компаний)
# ============================================================================


class TestManagementCompany:
    """Тесты получения информации об УК"""

    @pytest.mark.asyncio
    async def test_get_management_company_by_address(self, client):
        """Получение УК по адресу жилого дома"""
        uk = await client.get_management_company_by_address('Большевиков 68')

        # УК может не быть для некоторых адресов (нежилые здания)
        if uk is not None:
            assert uk.name is not None or uk.address is not None


# ============================================================================
# Тесты форматтеров
# ============================================================================


class TestFormatters:
    """Тесты функций форматирования"""

    def test_format_mfc_none(self):
        """Форматтер МФЦ должен обработать None"""
        result = format_mfc_for_chat(None)
        assert 'не удалось' in result.lower()

    def test_format_polyclinics_empty(self):
        """Форматтер поликлиник должен обработать пустой список"""
        result = format_polyclinics_for_chat([])
        assert 'не найдено' in result.lower()

    def test_format_schools_empty(self):
        """Форматтер школ должен обработать пустой список"""
        result = format_schools_for_chat([])
        assert 'не найдено' in result.lower()

    def test_format_building_search_empty(self):
        """Форматтер поиска должен обработать пустой список"""
        result = format_building_search_for_chat([])
        assert 'не найден' in result.lower()

    def test_format_building_search_single(self):
        """
        Форматтер поиска с одним результатом
        """
        building = BuildingSearchResult(
            id='123',
            full_address='г. Санкт-Петербург, Невский пр., д. 1',
            latitude=59.93,
            longitude=30.31,
        )
        result = format_building_search_for_chat([building])
        assert 'Найден адрес' in result
        assert 'Невский' in result

    def test_format_building_search_multiple(self):
        """
        Форматтер поиска с несколькими результатами
        """
        buildings = [
            BuildingSearchResult(id='1', full_address='Невский 1'),
            BuildingSearchResult(id='2', full_address='Невский 2'),
        ]
        result = format_building_search_for_chat(buildings)
        assert 'несколько' in result.lower()
        assert '1.' in result
        assert '2.' in result


# ============================================================================
# Интеграционные тесты
# ============================================================================


class TestIntegration:
    """Интеграционные тесты полного цикла"""

    @pytest.mark.asyncio
    async def test_full_address_to_services_flow(self, client):
        """
        Полный цикл: адрес → здание → услуги (МФЦ, поликлиники, школы)
        """
        # 1. Поиск здания
        building = await client.search_building_first('Московский проспект 100')
        assert building.id is not None

        # 2. Получаем услуги параллельно (используем building_id для API)
        mfc = await client.get_mfc_by_building(building.building_id)
        clinics = await client.get_polyclinics_by_building(building.building_id)
        schools = await client.get_linked_schools(building.building_id)

        # Хотя бы что-то должно найтись
        assert mfc is not None or len(clinics) > 0 or len(schools) > 0

        # Хотя бы что-то должно найтись
        assert mfc is not None or len(clinics) > 0 or len(schools) > 0

    @pytest.mark.asyncio
    async def test_district_info(self, client):
        """Тест получения районной справки"""
        building = await client.search_building_first('Невский проспект 10')
        info = await client.get_district_info_by_building(building.building_id)

        # API может вернуть dict или list
        assert isinstance(info, (dict, list))

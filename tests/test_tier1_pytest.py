"""
Pytest тесты для Tier 1 API методов.

Тестируем данные которые предсказуемы и стабильны:
- Категории услуг Долголетие (9 штук)
- Типы спортплощадок (структура summer/winter/all)
- Количество районов (18)
- Структуры возвращаемых данных
"""

import pytest

from app.api.yazzh_new import (
    MemorableDateInfo,
    PensionerServiceInfo,
    SportgroundCountInfo,
    YazzhAsyncClient,
)


# Ожидаемые категории услуг Долголетие
EXPECTED_PENSIONER_CATEGORIES = [
    'Вокал',
    'Здоровье',
    'Иностранные языки',
    'Клубы по интересам',
    'Компьютерные курсы',
    'Мероприятия',
    'Рукоделие',
    'Спорт',
    'Танцы',
]

# Ожидаемые 18 районов СПб
EXPECTED_DISTRICTS = [
    'Адмиралтейский',
    'Василеостровский',
    'Выборгский',
    'Калининский',
    'Кировский',
    'Колпинский',
    'Красногвардейский',
    'Красносельский',
    'Кронштадтский',
    'Курортный',
    'Московский',
    'Невский',
    'Петроградский',
    'Петродворцовый',
    'Приморский',
    'Пушкинский',
    'Фрунзенский',
    'Центральный',
]


class TestPensionerServices:
    """Тесты для услуг Долголетие"""

    @pytest.mark.asyncio
    async def test_get_categories_returns_nine(self):
        """Проверяем что возвращается 9 категорий"""
        async with YazzhAsyncClient() as client:
            categories = await client.get_pensioner_service_categories()

        assert len(categories) == 9
        assert sorted(categories) == sorted(EXPECTED_PENSIONER_CATEGORIES)

    @pytest.mark.asyncio
    async def test_get_categories_contents(self):
        """Проверяем что все ожидаемые категории присутствуют"""
        async with YazzhAsyncClient() as client:
            categories = await client.get_pensioner_service_categories()

        for expected in EXPECTED_PENSIONER_CATEGORIES:
            assert expected in categories, f'Категория "{expected}" отсутствует'

    @pytest.mark.asyncio
    async def test_get_services_returns_pydantic_models(self):
        """Проверяем что сервисы возвращаются как Pydantic модели"""
        async with YazzhAsyncClient() as client:
            services = await client.get_pensioner_services(
                district='Невский',
                count=2,
            )

        assert len(services) > 0
        for service in services:
            assert isinstance(service, PensionerServiceInfo)
            assert service.title
            assert service.category
            assert service.district

    @pytest.mark.asyncio
    async def test_get_services_by_category(self):
        """Проверяем фильтрацию по категории"""
        async with YazzhAsyncClient() as client:
            services = await client.get_pensioner_services(
                district='Центральный',
                categories=['Здоровье'],
                count=5,
            )

        for service in services:
            # category это список категорий
            assert 'Здоровье' in service.category

    @pytest.mark.asyncio
    async def test_service_has_format_method(self):
        """Проверяем что модель имеет метод форматирования"""
        async with YazzhAsyncClient() as client:
            services = await client.get_pensioner_services(
                district='Невский',
                count=1,
            )

        assert len(services) > 0
        formatted = services[0].format_for_human()
        assert isinstance(formatted, str)
        assert len(formatted) > 0


class TestSportgrounds:
    """Тесты для спортплощадок"""

    @pytest.mark.asyncio
    async def test_get_total_count(self):
        """Проверяем что возвращается общее количество"""
        async with YazzhAsyncClient() as client:
            total = await client.get_sportgrounds_count()

        assert isinstance(total, SportgroundCountInfo)
        assert total.count > 1000  # Известно что > 1600 площадок

    @pytest.mark.asyncio
    async def test_get_count_by_all_districts(self):
        """Проверяем что возвращается 18 районов"""
        async with YazzhAsyncClient() as client:
            by_district = await client.get_sportgrounds_count_by_district()

        assert len(by_district) == 18

        district_names = [d.district for d in by_district]
        for expected in EXPECTED_DISTRICTS:
            assert expected in district_names, f'Район "{expected}" отсутствует'

    @pytest.mark.asyncio
    async def test_get_count_single_district(self):
        """Проверяем получение по одному району"""
        async with YazzhAsyncClient() as client:
            result = await client.get_sportgrounds_count_by_district('Невский')

        assert len(result) == 1
        assert result[0].district == 'Невский'
        assert result[0].count > 100  # Известно что > 160

    @pytest.mark.asyncio
    async def test_get_types_structure(self):
        """Проверяем структуру типов площадок"""
        async with YazzhAsyncClient() as client:
            types = await client.get_sportgrounds_types()

        assert 'summer' in types
        assert 'winter' in types
        assert 'all' in types

        assert len(types['summer']) > 20
        assert len(types['winter']) > 5
        assert len(types['all']) > 100

    @pytest.mark.asyncio
    async def test_types_contain_known_sports(self):
        """Проверяем наличие известных видов спорта"""
        async with YazzhAsyncClient() as client:
            types = await client.get_sportgrounds_types()

        # Летние
        assert 'Футбол' in types['summer']
        assert 'Баскетбол' in types['summer']
        assert 'Плавание' in types['summer']

        # Зимние
        assert 'Хоккей' in types['winter']
        assert 'Лыжный спорт' in types['winter']

    @pytest.mark.asyncio
    async def test_count_info_has_format_method(self):
        """Проверяем что модель имеет метод форматирования"""
        async with YazzhAsyncClient() as client:
            total = await client.get_sportgrounds_count()

        formatted = total.format_for_human()
        assert isinstance(formatted, str)
        assert '1' in formatted  # Должно содержать число

    @pytest.mark.asyncio
    async def test_get_sportgrounds_by_district(self):
        """Проверяем получение списка площадок по району"""
        from app.api.yazzh_new import SportgroundInfo

        async with YazzhAsyncClient() as client:
            sportgrounds, total = await client.get_sportgrounds(
                district='Невский',
                count=5,
            )

        assert total > 100  # В Невском > 160 площадок
        assert len(sportgrounds) == 5
        for sg in sportgrounds:
            assert isinstance(sg, SportgroundInfo)
            assert sg.id
            assert sg.address
            assert 'Невский' in sg.district

    @pytest.mark.asyncio
    async def test_get_sportgrounds_by_sport_type(self):
        """Проверяем фильтрацию по типу спорта"""
        async with YazzhAsyncClient() as client:
            sportgrounds, total = await client.get_sportgrounds(
                district='Центральный',
                sport_types='Футбол',
                count=10,
            )

        assert total > 0
        for sg in sportgrounds:
            # Футбол должен быть в категориях
            assert 'Футбол' in sg.categories

    @pytest.mark.asyncio
    async def test_sportground_has_format_method(self):
        """Проверяем что SportgroundInfo имеет метод форматирования"""
        from app.api.yazzh_new import SportgroundInfo

        async with YazzhAsyncClient() as client:
            sportgrounds, _ = await client.get_sportgrounds(count=1)

        assert len(sportgrounds) > 0
        formatted = sportgrounds[0].format_for_human()
        assert isinstance(formatted, str)
        assert len(formatted) > 0


class TestMemorableDates:
    """Тесты для памятных дат"""

    @pytest.mark.asyncio
    async def test_get_dates_by_date_returns_list(self):
        """Проверяем что возвращается список"""
        async with YazzhAsyncClient() as client:
            # 1 января - известно что есть событие
            dates = await client.get_memorable_dates_by_date(day=1, month=1)

        assert isinstance(dates, list)
        assert len(dates) > 0

    @pytest.mark.asyncio
    async def test_date_info_is_pydantic_model(self):
        """Проверяем что дата возвращается как Pydantic модель"""
        async with YazzhAsyncClient() as client:
            dates = await client.get_memorable_dates_by_date(day=27, month=5)

        assert len(dates) > 0
        for date in dates:
            assert isinstance(date, MemorableDateInfo)
            assert date.title
            assert date.date  # ISO дата
            assert date.description  # описание

    @pytest.mark.asyncio
    async def test_date_info_has_format_method(self):
        """Проверяем что модель имеет метод форматирования"""
        async with YazzhAsyncClient() as client:
            dates = await client.get_memorable_dates_by_date(day=1, month=1)

        assert len(dates) > 0
        formatted = dates[0].format_for_human()
        assert isinstance(formatted, str)
        assert len(formatted) > 0

    @pytest.mark.asyncio
    async def test_jan_1_has_radio_event(self):
        """Проверяем что 1 января есть событие про радио"""
        async with YazzhAsyncClient() as client:
            dates = await client.get_memorable_dates_by_date(day=1, month=1)

        assert len(dates) > 0
        # Известно что 1 января 1926 - начало передачи сигналов точного времени
        titles = [d.title.lower() for d in dates]
        assert any('время' in t or 'радио' in t for t in titles)

    @pytest.mark.asyncio
    async def test_may_27_has_library_event(self):
        """Проверяем что 27 мая есть событие про библиотеку"""
        async with YazzhAsyncClient() as client:
            dates = await client.get_memorable_dates_by_date(day=27, month=5)

        assert len(dates) > 0
        # 27 мая 1795 - основана РНБ
        found = False
        for d in dates:
            if 'библиотек' in d.title.lower() or 'библиотек' in d.text.lower():
                found = True
                break
        assert found, '27 мая должно быть событие про библиотеку'

    @pytest.mark.asyncio
    async def test_get_today_returns_list(self):
        """Проверяем что get_today возвращает список"""
        async with YazzhAsyncClient() as client:
            dates = await client.get_memorable_dates_today()

        # Может быть пустой список если на сегодня нет дат
        assert isinstance(dates, list)


class TestFormatters:
    """Тесты для форматеров"""

    @pytest.mark.asyncio
    async def test_format_pensioner_services_empty(self):
        """Проверяем форматирование пустого списка"""
        from app.api.yazzh_new import format_pensioner_services_for_chat

        result = format_pensioner_services_for_chat([])
        # Сообщение о том что услуги не найдены
        assert len(result) > 0
        assert 'Услуги' in result or 'услуги' in result.lower()

    @pytest.mark.asyncio
    async def test_format_memorable_dates_empty(self):
        """Проверяем форматирование пустого списка"""
        from app.api.yazzh_new import format_memorable_dates_for_chat

        result = format_memorable_dates_for_chat([])
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_format_sportgrounds_empty(self):
        """Проверяем форматирование пустого списка"""
        from app.api.yazzh_new import format_sportgrounds_count_for_chat

        result = format_sportgrounds_count_for_chat([])
        assert len(result) > 0

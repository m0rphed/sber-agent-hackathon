"""
Pydantic модели для инструментов (tools).

Определяют:
- Args schemas для валидации входных параметров
- Return schemas для структурированного вывода (опционально)
- Few-shot examples для GigaChat

Используются в city_tools_v3.py и city_tools_v3_giga.py
"""

from typing import Annotated

from pydantic import BaseModel, Field

# =============================================================================
# Константы и типы для параметров
# =============================================================================

# Список районов СПб для валидации
SPB_DISTRICTS = [
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

# Аннотированные типы для параметров tools
DistrictParam = Annotated[
    str,
    Field(
        description=(
            'Название РАЙОНА Санкт-Петербурга (НЕ адрес!). '
            "Примеры: 'Невский', 'Центральный', 'Калининский', 'Приморский'. "
            'Это административная единица города, а не улица.'
        )
    ),
]

DistrictOptionalParam = Annotated[
    str,
    Field(
        default='',
        description=(
            'Название РАЙОНА СПб (опционально). '
            "Примеры: 'Невский', 'Центральный'. Пустая строка = весь город."
        ),
    ),
]

AddressParam = Annotated[
    str,
    Field(
        description=(
            "АДРЕС в формате 'улица номер_дома'. "
            "Примеры: 'Невский проспект 1', 'ул. Садовая 50', 'Большевиков 68'. "
            'НЕ путать с названием района!'
        )
    ),
]

LocationParam = Annotated[
    str,
    Field(
        description=(
            'Локация пользователя: АДРЕС (улица + дом) ИЛИ станция метро. '
            "Примеры: 'Невский проспект 1', 'метро Пионерская', 'ст. м. Василеостровская'."
        )
    ),
]


# =============================================================================
# Few-shot examples для GigaChat (@giga_tool)
#
# Формат: [{"request": "...", "params": {...}}]
# =============================================================================


class FewShotExamples:
    """Коллекция few-shot examples для каждого инструмента."""

    # === Address / Geo ===
    SEARCH_ADDRESS = [
        {'request': 'найди адрес Невский 10', 'params': {'query': 'Невский 10'}},
        {
            'request': 'проверь адрес Большевиков 68 корпус 1',
            'params': {'query': 'Большевиков 68 к1'},
        },
        {
            'request': 'где находится Лиговский проспект 50',
            'params': {'query': 'Лиговский проспект 50'},
        },
    ]

    GET_DISTRICTS_LIST = [
        {'request': 'какие районы есть в Петербурге?', 'params': {}},
        {'request': 'список всех районов СПб', 'params': {}},
    ]

    GET_DISTRICT_INFO = [
        {'request': 'расскажи про Невский район', 'params': {'district': 'Невский'}},
        {'request': 'информация о Центральном районе', 'params': {'district': 'Центральный'}},
    ]

    GET_DISTRICT_INFO_BY_ADDRESS = [
        {
            'request': 'в каком районе находится Невский 1?',
            'params': {'address': 'Невский проспект 1'},
        },
        {'request': 'какой район у дома на Садовой 50?', 'params': {'address': 'Садовая 50'}},
    ]

    # === MFC ===
    FIND_NEAREST_MFC = [
        {'request': 'МФЦ рядом с Невским 10', 'params': {'location': 'Невский проспект 10'}},
        {
            'request': 'ближайший МФЦ от метро Пионерская',
            'params': {'location': 'метро Пионерская'},
        },
        {
            'request': 'где оформить документы около Большевиков 68',
            'params': {'location': 'Большевиков 68'},
        },
        {
            'request': 'МФЦ у станции Василеостровская',
            'params': {'location': 'метро Василеостровская'},
        },
    ]

    GET_MFC_BY_DISTRICT = [
        {'request': 'все МФЦ в Невском районе', 'params': {'district': 'Невский'}},
        {'request': 'МФЦ Центрального района', 'params': {'district': 'Центральный'}},
        {'request': 'список МФЦ в Калининском', 'params': {'district': 'Калининский'}},
    ]

    # === Healthcare ===
    GET_POLYCLINICS = [
        {
            'request': 'моя поликлиника по адресу Невский 1',
            'params': {'address': 'Невский проспект 1'},
        },
        {
            'request': 'к какой поликлинике прикреплён дом на Садовой 50?',
            'params': {'address': 'Садовая 50'},
        },
    ]

    GET_VET_CLINICS = [
        {'request': 'ветеринарные клиники в Невском районе', 'params': {'district': 'Невский'}},
        {'request': 'ветклиники в Центральном', 'params': {'district': 'Центральный'}},
    ]

    # === Education ===
    GET_SCHOOLS_BY_ADDRESS = [
        {'request': 'школа по прописке Невский 10', 'params': {'address': 'Невский проспект 10'}},
        {
            'request': 'к какой школе прикреплён дом на Большевиков 68?',
            'params': {'address': 'Большевиков 68'},
        },
    ]

    GET_SCHOOLS_BY_DISTRICT = [
        {'request': 'школы в Невском районе', 'params': {'district': 'Невский'}},
        {'request': 'список школ Центрального района', 'params': {'district': 'Центральный'}},
    ]

    GET_KINDERGARTENS = [
        {
            'request': 'детские сады в Невском районе для ребёнка 3 лет',
            'params': {'district': 'Невский', 'age_years': 3, 'age_months': 0},
        },
        {
            'request': 'садики в Центральном для малыша 2,5 года',
            'params': {'district': 'Центральный', 'age_years': 2, 'age_months': 6},
        },
    ]

    # === Housing ===
    GET_MANAGEMENT_COMPANY = [
        {
            'request': 'управляющая компания для Невский 1',
            'params': {'address': 'Невский проспект 1'},
        },
        {'request': 'какая УК обслуживает дом на Садовой 50?', 'params': {'address': 'Садовая 50'}},
    ]

    GET_DISCONNECTIONS = [
        {'request': 'отключения воды на Невском 1', 'params': {'address': 'Невский проспект 1'}},
        {
            'request': 'когда включат горячую воду на Садовой 50?',
            'params': {'address': 'Садовая 50'},
        },
    ]

    # === Events ===
    GET_CITY_EVENTS = [
        {'request': 'мероприятия в Петербурге на эти выходные', 'params': {'district': ''}},
        {'request': 'события в Невском районе', 'params': {'district': 'Невский'}},
    ]

    GET_EVENT_CATEGORIES = [
        {'request': 'какие категории мероприятий есть?', 'params': {}},
        {'request': 'типы событий в городе', 'params': {}},
    ]

    GET_SPORT_EVENTS = [
        {'request': 'спортивные события в Невском районе', 'params': {'district': 'Невский'}},
        {'request': 'спортивные мероприятия в Петербурге', 'params': {'district': ''}},
    ]

    GET_MEMORABLE_DATES = [
        {'request': 'какие праздники сегодня?', 'params': {}},
        {'request': 'памятные даты на сегодня', 'params': {}},
    ]

    # === Recreation ===
    GET_SPORTGROUNDS = [
        {'request': 'спортплощадки в Невском районе', 'params': {'district': 'Невский'}},
        {
            'request': 'где позаниматься спортом в Центральном?',
            'params': {'district': 'Центральный'},
        },
    ]

    GET_SPORTGROUNDS_COUNT = [
        {'request': 'сколько спортплощадок в Невском районе?', 'params': {'district': 'Невский'}},
        {'request': 'количество площадок во всём городе', 'params': {'district': ''}},
    ]

    GET_SPORT_CATEGORIES = [
        {'request': 'виды спорта в Невском районе', 'params': {'district': 'Невский'}},
        {'request': 'какие секции есть в Центральном?', 'params': {'district': 'Центральный'}},
    ]

    GET_BEAUTIFUL_PLACES = [
        {
            'request': 'достопримечательности в Центральном районе',
            'params': {'district': 'Центральный'},
        },
        {'request': 'интересные места в Петроградском', 'params': {'district': 'Петроградский'}},
    ]

    GET_BEAUTIFUL_PLACE_ROUTES = [
        {'request': 'туристические маршруты по Петербургу', 'params': {}},
        {'request': 'экскурсионные маршруты в Центральном', 'params': {'district': 'Центральный'}},
    ]

    GET_PET_PARKS = [
        {'request': 'площадки для собак в Невском районе', 'params': {'district': 'Невский'}},
        {'request': 'где выгулять собаку в Центральном?', 'params': {'district': 'Центральный'}},
    ]

    # === Pensioner ===
    GET_PENSIONER_CATEGORIES = [
        {'request': 'категории услуг для пенсионеров', 'params': {}},
        {'request': 'какие услуги есть для пожилых?', 'params': {}},
    ]

    GET_PENSIONER_SERVICES = [
        {'request': 'услуги для пенсионеров в Невском районе', 'params': {'district': 'Невский'}},
        {'request': 'помощь пожилым в Центральном', 'params': {'district': 'Центральный'}},
    ]

    # === Infrastructure ===
    GET_ROAD_WORKS = [
        {'request': 'дорожные работы в Невском районе', 'params': {'district': 'Невский'}},
        {'request': 'ремонт дорог в Центральном', 'params': {'district': 'Центральный'}},
    ]


# =============================================================================
# Pydantic Return Schemas (опционально - для структурированного вывода)
# =============================================================================


class MfcInfo(BaseModel):
    """Информация об МФЦ."""

    name: str = Field(description='Название МФЦ')
    address: str = Field(description='Адрес МФЦ')
    phones: list[str] = Field(default_factory=list, description='Телефоны')
    working_hours: str = Field(default='', description='Часы работы')
    services: list[str] = Field(default_factory=list, description='Доступные услуги')


class PolyclinicInfo(BaseModel):
    """Информация о поликлинике."""

    name: str = Field(description='Название поликлиники')
    address: str = Field(description='Адрес')
    phones: list[str] = Field(default_factory=list, description='Телефоны')
    specializations: list[str] = Field(default_factory=list, description='Специализации')


class SchoolInfo(BaseModel):
    """Информация о школе."""

    name: str = Field(description='Название школы')
    address: str = Field(description='Адрес')
    available_places: int | None = Field(default=None, description='Свободные места')
    profile: str = Field(default='', description='Профиль школы')


class DistrictInfo(BaseModel):
    """Информация о районе."""

    name: str = Field(description='Название района')
    population: int | None = Field(default=None, description='Население')
    area_km2: float | None = Field(default=None, description='Площадь в км²')
    municipalities: list[str] = Field(default_factory=list, description='Муниципалитеты')


class AddressSearchResult(BaseModel):
    """Результат поиска адреса."""

    full_address: str = Field(description='Полный адрес')
    building_id: int | None = Field(default=None, description='ID здания в API')
    district: str = Field(default='', description='Район')
    coordinates: tuple[float, float] | None = Field(
        default=None, description='Координаты (lat, lon)'
    )


class EventInfo(BaseModel):
    """Информация о мероприятии."""

    title: str = Field(description='Название мероприятия')
    date: str = Field(description='Дата проведения')
    location: str = Field(default='', description='Место проведения')
    category: str = Field(default='', description='Категория')
    description: str = Field(default='', description='Описание')

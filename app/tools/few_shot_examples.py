"""
Few-shot examples для LangChain tools.

Эти примеры помогают GigaChat лучше понимать:
1. Когда вызывать какой tool
2. Как извлекать параметры из запроса пользователя

Использование с @giga_tool:
```python
from langchain_gigachat.tools.giga_tool import giga_tool

@giga_tool(few_shot_examples=FEW_SHOT_EXAMPLES["find_nearest_mfc"])
def find_nearest_mfc_v2(address: str) -> str:
    ...
```
"""

from typing import TypedDict


class FewShotExample(TypedDict):
    """Структура few-shot примера."""
    request: str  # Пример запроса пользователя
    params: dict[str, str | int | None]  # Ожидаемые параметры


# ============================================================================
# МФЦ (Многофункциональные центры)
# ============================================================================

MFC_EXAMPLES: list[FewShotExample] = [
    {"request": "Найди МФЦ рядом с Невским проспектом 1",
     "params": {"address": "Невский проспект 1"}},
    {"request": "Где ближайший МФЦ около метро Пионерская?",
     "params": {"address": "метро Пионерская"}},
    {"request": "МФЦ возле Большевиков 68",
     "params": {"address": "Большевиков 68"}},
    {"request": "Покажи многофункциональный центр у Гостиного двора",
     "params": {"address": "Гостиный двор"}},
]

MFC_BY_DISTRICT_EXAMPLES: list[FewShotExample] = [
    {"request": "Список всех МФЦ в Невском районе",
     "params": {"district": "Невский"}},
    {"request": "Какие МФЦ есть в Центральном районе?",
     "params": {"district": "Центральный"}},
    {"request": "МФЦ Калининского района",
     "params": {"district": "Калининский"}},
]

# ============================================================================
# Поликлиники
# ============================================================================

POLYCLINIC_EXAMPLES: list[FewShotExample] = [
    {"request": "Какая поликлиника обслуживает адрес Невский 100?",
     "params": {"address": "Невский 100"}},
    {"request": "Найди поликлинику рядом с Ленина 5",
     "params": {"address": "Ленина 5"}},
    {"request": "К какой поликлинике я прикреплён? Живу на Большевиков 10",
     "params": {"address": "Большевиков 10"}},
]

# ============================================================================
# Школы
# ============================================================================

SCHOOL_EXAMPLES: list[FewShotExample] = [
    {"request": "Какая школа по прописке на Невском 50?",
     "params": {"address": "Невский 50"}},
    {"request": "К какой школе относится адрес Садовая 25?",
     "params": {"address": "Садовая 25"}},
    {"request": "Школы рядом с Московским проспектом 100",
     "params": {"address": "Московский проспект 100"}},
]

SCHOOL_BY_DISTRICT_EXAMPLES: list[FewShotExample] = [
    {"request": "Список школ в Невском районе",
     "params": {"district": "Невский"}},
    {"request": "Какие школы есть в Центральном районе?",
     "params": {"district": "Центральный"}},
]

# ============================================================================
# Детские сады
# ============================================================================

KINDERGARTEN_EXAMPLES: list[FewShotExample] = [
    {"request": "Детские сады в Невском районе для ребёнка 3 лет",
     "params": {"district": "Невский", "age_years": 3, "age_months": 0}},
    {"request": "Садики в Центральном районе, ребёнку 2.5 года",
     "params": {"district": "Центральный", "age_years": 2, "age_months": 6}},
    {"request": "Куда отдать ребёнка 4 лет в Калининском?",
     "params": {"district": "Калининский", "age_years": 4, "age_months": 0}},
]

# ============================================================================
# Управляющие компании
# ============================================================================

MANAGEMENT_COMPANY_EXAMPLES: list[FewShotExample] = [
    {"request": "Какая управляющая компания обслуживает Невский 1?",
     "params": {"address": "Невский 1"}},
    {"request": "УК по адресу Большевиков 68",
     "params": {"address": "Большевиков 68"}},
    {"request": "Кто управляет домом на Садовой 50?",
     "params": {"address": "Садовая 50"}},
]

# ============================================================================
# Пенсионеры
# ============================================================================

PENSIONER_CATEGORIES_EXAMPLES: list[FewShotExample] = [
    {"request": "Какие услуги есть для пенсионеров?",
     "params": {}},
    {"request": "Категории занятий для пожилых",
     "params": {}},
    {"request": "Что доступно пенсионерам?",
     "params": {}},
]

PENSIONER_SERVICES_EXAMPLES: list[FewShotExample] = [
    {"request": "Занятия для пенсионеров в Невском районе",
     "params": {"district": "Невский", "category": ""}},
    {"request": "Компьютерные курсы для пожилых в Центральном районе",
     "params": {"district": "Центральный", "category": "Компьютерные курсы"}},
    {"request": "Где записаться на йогу для пенсионеров в Калининском?",
     "params": {"district": "Калининский", "category": "Йога"}},
]

# ============================================================================
# Мероприятия
# ============================================================================

EVENTS_EXAMPLES: list[FewShotExample] = [
    {"request": "Какие мероприятия будут в эти выходные?",
     "params": {"category": None, "district": None}},
    {"request": "Концерты в Невском районе",
     "params": {"category": "Концерты", "district": "Невский"}},
    {"request": "Выставки в центре города",
     "params": {"category": "Выставки", "district": "Центральный"}},
]

SPORT_EVENTS_EXAMPLES: list[FewShotExample] = [
    {"request": "Спортивные соревнования в выходные",
     "params": {"category": None}},
    {"request": "Футбольные матчи в Санкт-Петербурге",
     "params": {"category": "Футбол"}},
]

# ============================================================================
# Отключения
# ============================================================================

DISCONNECTIONS_EXAMPLES: list[FewShotExample] = [
    {"request": "Будут ли отключения воды на Невском 1?",
     "params": {"address": "Невский 1"}},
    {"request": "Отключение электричества по адресу Садовая 50",
     "params": {"address": "Садовая 50"}},
    {"request": "Когда отключат горячую воду на Большевиков 68?",
     "params": {"address": "Большевиков 68"}},
]

# ============================================================================
# Дорожные работы
# ============================================================================

ROAD_WORKS_EXAMPLES: list[FewShotExample] = [
    {"request": "Какие дорожные работы сейчас идут?",
     "params": {"district": None}},
    {"request": "Ремонт дорог в Невском районе",
     "params": {"district": "Невский"}},
    {"request": "Где перекрыты улицы из-за ремонта?",
     "params": {"district": None}},
]

# ============================================================================
# Спортплощадки
# ============================================================================

SPORTGROUNDS_EXAMPLES: list[FewShotExample] = [
    {"request": "Где есть спортивные площадки рядом с Невским 50?",
     "params": {"address": "Невский 50"}},
    {"request": "Спортплощадки в Центральном районе",
     "params": {"district": "Центральный"}},
    {"request": "Где поиграть в баскетбол около метро Ладожская?",
     "params": {"address": "метро Ладожская"}},
]

# ============================================================================
# Питомцы
# ============================================================================

PET_PARKS_EXAMPLES: list[FewShotExample] = [
    {"request": "Где погулять с собакой около Невского 1?",
     "params": {"address": "Невский 1"}},
    {"request": "Парки для выгула собак в Центральном районе",
     "params": {"district": "Центральный"}},
    {"request": "Площадка для собак рядом с Большевиков 68",
     "params": {"address": "Большевиков 68"}},
]

VET_CLINICS_EXAMPLES: list[FewShotExample] = [
    {"request": "Ветклиника рядом с Невским проспектом",
     "params": {"address": "Невский проспект"}},
    {"request": "Ветеринарные клиники в Калининском районе",
     "params": {"district": "Калининский"}},
    {"request": "Куда отвезти кота? Живу на Садовой 10",
     "params": {"address": "Садовая 10"}},
]

# ============================================================================
# Красивые места и маршруты
# ============================================================================

BEAUTIFUL_PLACES_EXAMPLES: list[FewShotExample] = [
    {"request": "Какие красивые места есть в Петербурге?",
     "params": {}},
    {"request": "Достопримечательности в центре",
     "params": {"district": "Центральный"}},
    {"request": "Интересные места для прогулки",
     "params": {}},
]

TOURIST_ROUTES_EXAMPLES: list[FewShotExample] = [
    {"request": "Пешеходные маршруты по Петербургу",
     "params": {}},
    {"request": "Туристические маршруты в центре города",
     "params": {"district": "Центральный"}},
    {"request": "Маршруты с аудиогидом",
     "params": {"with_audio": True}},
    {"request": "Доступные маршруты для маломобильных",
     "params": {"accessible": True}},
    {"request": "Короткие прогулки до 2 часов",
     "params": {"max_duration_hours": 2}},
]

# ============================================================================
# Информация о районе
# ============================================================================

DISTRICT_INFO_EXAMPLES: list[FewShotExample] = [
    {"request": "Информация о Невском районе",
     "params": {"district": "Невский"}},
    {"request": "Расскажи про Центральный район",
     "params": {"district": "Центральный"}},
    {"request": "В каком районе находится Невский проспект 1?",
     "params": {"address": "Невский проспект 1"}},
]

# ============================================================================
# Агрегированный словарь для удобного доступа
# ============================================================================

FEW_SHOT_EXAMPLES: dict[str, list[FewShotExample]] = {
    # МФЦ
    "find_nearest_mfc": MFC_EXAMPLES,
    "get_mfc_list_by_district": MFC_BY_DISTRICT_EXAMPLES,
    
    # Поликлиники
    "get_polyclinics_by_address": POLYCLINIC_EXAMPLES,
    
    # Школы
    "get_linked_schools_by_address": SCHOOL_EXAMPLES,
    "get_schools_by_district": SCHOOL_BY_DISTRICT_EXAMPLES,
    
    # Детсады
    "get_kindergartens": KINDERGARTEN_EXAMPLES,
    
    # УК
    "get_management_company_by_address": MANAGEMENT_COMPANY_EXAMPLES,
    
    # Пенсионеры
    "get_pensioner_service_categories": PENSIONER_CATEGORIES_EXAMPLES,
    "get_pensioner_services": PENSIONER_SERVICES_EXAMPLES,
    
    # Мероприятия
    "get_city_events": EVENTS_EXAMPLES,
    "get_sport_events": SPORT_EVENTS_EXAMPLES,
    
    # Отключения
    "get_disconnections_by_address": DISCONNECTIONS_EXAMPLES,
    
    # Дороги
    "get_road_works": ROAD_WORKS_EXAMPLES,
    
    # Спорт
    "get_sportgrounds": SPORTGROUNDS_EXAMPLES,
    
    # Питомцы
    "get_pet_parks": PET_PARKS_EXAMPLES,
    "get_vet_clinics": VET_CLINICS_EXAMPLES,
    
    # Туризм
    "get_beautiful_places": BEAUTIFUL_PLACES_EXAMPLES,
    "get_beautiful_place_routes": TOURIST_ROUTES_EXAMPLES,
    
    # Район
    "get_district_info_by_address": DISTRICT_INFO_EXAMPLES,
}


def get_examples_for_tool(tool_name: str) -> list[FewShotExample]:
    """
    Получить few-shot примеры для tool по имени.
    
    Args:
        tool_name: Имя tool без суффикса _v2
        
    Returns:
        Список примеров или пустой список
    """
    # Убираем суффикс _v2 если есть
    clean_name = tool_name.replace("_v2", "").replace("_tool", "")
    return FEW_SHOT_EXAMPLES.get(clean_name, [])

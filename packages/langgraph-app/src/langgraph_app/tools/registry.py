"""
Реестр инструментов — группировка tools по категориям.

Группирует tools по категориям используя объекты, а не строки.
Поддерживает как базовые tools (для OpenRouter), так и giga_tools (для GigaChat).

Использование:
    from langgraph_app.tools.registry import get_tools_for_category, ToolCategory

    # Для GigaChat
    tools = get_tools_for_category(ToolCategory.MFC, provider="gigachat")

    # Для OpenRouter
    tools = get_tools_for_category(ToolCategory.MFC, provider="openrouter")
"""

from typing import TYPE_CHECKING, Literal

from langchain_core.tools import BaseTool

if TYPE_CHECKING:
    from langgraph_app.agent.models import ToolCategory

from langgraph_app.logging_config import get_logger

logger = get_logger(__name__)

# Type alias для провайдера
ProviderType = Literal['gigachat', 'openrouter', 'default']


def _get_tools_by_provider(provider: ProviderType = 'default') -> dict[str, BaseTool]:
    """
    Получить все tools в зависимости от провайдера.

    Args:
        provider: "gigachat" для @giga_tool, "openrouter" или "default" для @tool

    Returns:
        Dict с tools по именам
    """
    if provider == 'gigachat':
        from langgraph_app.tools.city_tools_v3_giga import (
            find_nearest_mfc,
            get_all_mfc,
            get_beautiful_places,
            get_city_events,
            get_disconnections,
            get_district_info,
            get_district_info_by_address,
            get_districts_list,
            get_kindergartens_by_district,
            get_management_company,
            get_mfc_by_district,
            get_pensioner_hotlines,
            get_pensioner_services,
            get_pet_parks,
            get_pet_shelters,
            get_polyclinics_by_address,
            get_recycling_points,
            get_road_works,
            get_school_by_id,
            get_schools_by_address,
            get_schools_in_district,
            get_sport_events,
            get_sportgrounds,
            get_tourist_routes,
            get_vet_clinics,
            search_address,
        )
    else:
        from langgraph_app.tools.city_tools_v3 import (
            find_nearest_mfc,
            get_all_mfc,
            get_beautiful_places,
            get_city_events,
            get_disconnections,
            get_district_info,
            get_district_info_by_address,
            get_districts_list,
            get_kindergartens_by_district,
            get_management_company,
            get_mfc_by_district,
            get_pensioner_hotlines,
            get_pensioner_services,
            get_pet_parks,
            get_pet_shelters,
            get_polyclinics_by_address,
            get_recycling_points,
            get_road_works,
            get_school_by_id,
            get_schools_by_address,
            get_schools_in_district,
            get_sport_events,
            get_sportgrounds,
            get_tourist_routes,
            get_vet_clinics,
            search_address,
        )

    return {
        # Address / Geo
        'search_address': search_address,
        'get_districts_list': get_districts_list,
        'get_district_info': get_district_info,
        'get_district_info_by_address': get_district_info_by_address,
        # MFC
        'find_nearest_mfc': find_nearest_mfc,
        'get_mfc_by_district': get_mfc_by_district,
        'get_all_mfc': get_all_mfc,
        # Healthcare
        'get_polyclinics_by_address': get_polyclinics_by_address,
        'get_vet_clinics': get_vet_clinics,
        # Education
        'get_schools_by_address': get_schools_by_address,
        'get_schools_in_district': get_schools_in_district,
        'get_school_by_id': get_school_by_id,
        'get_kindergartens_by_district': get_kindergartens_by_district,
        # Housing
        'get_management_company': get_management_company,
        'get_disconnections': get_disconnections,
        # Pets
        'get_pet_parks': get_pet_parks,
        'get_pet_shelters': get_pet_shelters,
        # Events
        'get_city_events': get_city_events,
        'get_sport_events': get_sport_events,
        # Pensioner
        'get_pensioner_services': get_pensioner_services,
        'get_pensioner_hotlines': get_pensioner_hotlines,
        # Recreation / Sport
        'get_sportgrounds': get_sportgrounds,
        'get_beautiful_places': get_beautiful_places,
        'get_tourist_routes': get_tourist_routes,
        # Infrastructure
        'get_road_works': get_road_works,
        'get_recycling_points': get_recycling_points,
    }


def _get_tools_by_category(
    provider: ProviderType = 'default',
) -> dict[ToolCategory, list[BaseTool]]:
    """
    Получить маппинг категорий на tools.

    Использует ОБЪЕКТЫ tools, а не строки!

    Args:
        provider: "gigachat" или "openrouter"/"default"

    Returns:
        Dict[ToolCategory, list[BaseTool]]
    """
    # Lazy import чтобы избежать circular dependency
    from langgraph_app.agent.models import ToolCategory

    tools = _get_tools_by_provider(provider)

    return {
        # === Geo / Address ===
        ToolCategory.ADDRESS: [
            tools['search_address'],
        ],
        ToolCategory.DISTRICT: [
            tools['get_districts_list'],
            tools['get_district_info'],
            tools['get_district_info_by_address'],
        ],
        # === Городские сервисы ===
        ToolCategory.MFC: [
            tools['find_nearest_mfc'],
            tools['get_mfc_by_district'],
            tools['get_all_mfc'],
        ],
        ToolCategory.POLYCLINIC: [
            tools['get_polyclinics_by_address'],
        ],
        ToolCategory.SCHOOL: [
            tools['get_schools_by_address'],
            tools['get_schools_in_district'],
            tools['get_school_by_id'],
        ],
        ToolCategory.KINDERGARTEN: [
            tools['get_kindergartens_by_district'],
        ],
        ToolCategory.HOUSING: [
            tools['get_management_company'],
            tools['get_disconnections'],
        ],
        # === Питомцы (ВСЁ про животных) ===
        # search_address нужен чтобы получить lat/lon для остальных tools
        ToolCategory.PETS: [
            tools['search_address'],  # Для получения координат
            tools['get_pet_parks'],
            tools['get_vet_clinics'],
            tools['get_pet_shelters'],
        ],
        # === Активности и отдых ===
        ToolCategory.PENSIONER: [
            tools['get_pensioner_services'],
            tools['get_pensioner_hotlines'],
        ],
        ToolCategory.EVENTS: [
            tools['get_city_events'],
            tools['get_sport_events'],
        ],
        ToolCategory.RECREATION: [
            tools['get_sportgrounds'],
            tools['get_beautiful_places'],
            tools['get_tourist_routes'],
        ],
        # === Инфраструктура ===
        # search_address нужен для get_recycling_points (требует lat/lon)
        ToolCategory.INFRASTRUCTURE: [
            tools['search_address'],  # Для получения координат
            tools['get_road_works'],
            tools['get_recycling_points'],
        ],
    }


def get_tools_for_category(
    category: ToolCategory,
    provider: ProviderType = 'default',
) -> list[BaseTool]:
    """
    Получить tools для конкретной категории.

    Args:
        category: Категория инструментов
        provider: "gigachat" или "openrouter"/"default"

    Returns:
        Список tools для данной категории
    """
    tools_by_category = _get_tools_by_category(provider)
    return tools_by_category.get(category, [])


def get_all_tools(provider: ProviderType = 'default') -> list[BaseTool]:
    """
    Получить все tools для провайдера.

    Args:
        provider: "gigachat" или "openrouter"/"default"

    Returns:
        Список всех tools
    """
    tools = _get_tools_by_provider(provider)
    return list(tools.values())


def get_tools_for_categories(
    categories: list[ToolCategory],
    provider: ProviderType = 'default',
) -> list[BaseTool]:
    """
    Получить tools для нескольких категорий.

    Args:
        categories: Список категорий
        provider: "gigachat" или "openrouter"/"default"

    Returns:
        Объединённый список tools (без дубликатов)
    """
    tools_by_category = _get_tools_by_category(provider)
    result: list[BaseTool] = []
    seen: set[str] = set()

    for category in categories:
        for tool in tools_by_category.get(category, []):
            if tool.name not in seen:
                result.append(tool)
                seen.add(tool.name)

    return result


def get_category_names() -> dict[ToolCategory, list[str]]:
    """
    Быстрый доступ к именам tools по категориям.

    Returns:
        Dict[ToolCategory, list[str]] - маппинг категории на имена tools
    """
    from langgraph_app.agent.models import ToolCategory

    return {
        # Geo / Address
        ToolCategory.ADDRESS: ['search_address'],
        ToolCategory.DISTRICT: [
            'get_districts_list',
            'get_district_info',
            'get_district_info_by_address',
        ],
        # Городские сервисы
        ToolCategory.MFC: ['find_nearest_mfc', 'get_mfc_by_district', 'get_all_mfc'],
        ToolCategory.POLYCLINIC: ['get_polyclinics_by_address'],
        ToolCategory.SCHOOL: [
            'get_schools_by_address',
            'get_schools_in_district',
            'get_school_by_id',
        ],
        ToolCategory.KINDERGARTEN: ['get_kindergartens_by_district'],
        ToolCategory.HOUSING: ['get_management_company', 'get_disconnections'],
        # Питомцы (search_address для получения lat/lon)
        ToolCategory.PETS: [
            'search_address',
            'get_pet_parks',
            'get_vet_clinics',
            'get_pet_shelters',
        ],
        # Активности
        ToolCategory.PENSIONER: ['get_pensioner_services', 'get_pensioner_hotlines'],
        ToolCategory.EVENTS: ['get_city_events', 'get_sport_events'],
        ToolCategory.RECREATION: ['get_sportgrounds', 'get_beautiful_places', 'get_tourist_routes'],
        # Инфраструктура (search_address для get_recycling_points)
        ToolCategory.INFRASTRUCTURE: ['search_address', 'get_road_works', 'get_recycling_points'],
    }


# Для обратной совместимости - lazy-initialized
CATEGORY_NAMES: dict[ToolCategory, list[str]] | None = None


def _get_category_names_compat() -> dict[ToolCategory, list[str]]:
    """Обратная совместимость для CATEGORY_NAMES."""
    global CATEGORY_NAMES
    if CATEGORY_NAMES is None:
        CATEGORY_NAMES = get_category_names()
    return CATEGORY_NAMES

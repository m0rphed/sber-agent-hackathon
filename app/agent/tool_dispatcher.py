"""
Tool Dispatcher — централизованный вызов LangChain tools.

Этот модуль:
1. Собирает все tools в один маппинг по имени
2. Предоставляет единый API для вызова tool по intent
3. Обрабатывает валидацию параметров
4. Генерирует сообщения об уточнении

Использование:
    from app.agent.tool_dispatcher import dispatch_tool, get_clarification_for_intent

    # Вызов tool по intent
    result = dispatch_tool("search_mfc", {"address": "Невский 1"})

    # Получить сообщение уточнения
    message = get_clarification_for_intent("search_mfc")
"""

from typing import Any

from app.agent.intent_classifier import (
    INTENT_REQUIRED_SLOTS,
    INTENT_TO_TOOL_NAME,
)
from app.logging_config import get_logger

logger = get_logger(__name__)


# =============================================================================
# Tool Registry
# =============================================================================

# Lazy-loaded registry — заполняется при первом вызове
_TOOL_REGISTRY: dict[str, Any] | None = None


def _get_tool_registry() -> dict[str, Any]:
    """
    Возвращает маппинг tool_name → tool object.

    Lazy initialization чтобы избежать циклических импортов.
    """
    global _TOOL_REGISTRY

    if _TOOL_REGISTRY is None:
        from app.tools.city_tools_v2 import city_tools_v2

        _TOOL_REGISTRY = {tool.name: tool for tool in city_tools_v2}
        logger.debug("tool_registry_initialized", count=len(_TOOL_REGISTRY))

    return _TOOL_REGISTRY


def get_tool_by_name(tool_name: str) -> Any | None:
    """Получить tool object по имени."""
    registry = _get_tool_registry()
    return registry.get(tool_name)


# =============================================================================
# Clarification Messages
# =============================================================================

_CLARIFICATION_MESSAGES: dict[str, str] = {
    # Требуют адрес
    "search_mfc": "Для поиска ближайшего МФЦ укажите ваш адрес. Например: «Невский проспект 1»",
    "search_polyclinic": "Укажите ваш адрес для поиска поликлиники. Например: «Садовая 50»",
    "search_school": "Укажите адрес для поиска школы по прописке. Например: «Большевиков 68»",
    "search_management_company": "Укажите адрес для поиска управляющей компании.",
    "disconnections": "Укажите адрес для проверки отключений. Например: «Невский 100»",
    "pet_parks": "Укажите адрес или район для поиска площадок выгула собак.",
    "vet_clinics": "Укажите адрес или район для поиска ветклиник.",
    "sportgrounds": "Укажите адрес или район для поиска спортплощадок.",

    # Требуют район
    "search_kindergarten": "Укажите район для поиска детских садов. Например: «Невский», «Центральный»",
    "pensioner_services": "Укажите район для поиска занятий. Например: «Калининский район»",
}


def get_clarification_for_intent(intent: str) -> str:
    """
    Получить сообщение уточнения для intent.

    Если intent не требует параметров — возвращает пустую строку.
    """
    return _CLARIFICATION_MESSAGES.get(intent, "")


# =============================================================================
# Parameter Validation
# =============================================================================


def validate_params_for_intent(intent: str, params: dict[str, Any]) -> tuple[bool, str]:
    """
    Проверяет, заполнены ли все обязательные параметры.

    Args:
        intent: Тип намерения
        params: Извлечённые параметры

    Returns:
        (is_valid, clarification_message)
        - is_valid=True если все параметры заполнены
        - clarification_message содержит текст уточнения если is_valid=False
    """
    required = INTENT_REQUIRED_SLOTS.get(intent, [])

    for slot in required:
        if slot == "address" and not params.get("address"):
            return False, get_clarification_for_intent(intent)
        if slot == "district" and not params.get("district"):
            return False, get_clarification_for_intent(intent)

    return True, ""


# =============================================================================
# Tool Dispatch
# =============================================================================


def dispatch_tool(intent: str, params: dict[str, Any]) -> str:
    """
    Вызывает tool по intent с переданными параметрами.

    Args:
        intent: Тип намерения (например: "search_mfc", "search_polyclinic")
        params: Параметры для tool (address, district, category, etc.)

    Returns:
        Результат вызова tool (строка) или сообщение об ошибке
    """
    tool_name = INTENT_TO_TOOL_NAME.get(intent)

    if not tool_name:
        logger.warning("unknown_intent", intent=intent)
        return f"Неизвестный тип запроса: {intent}"

    tool = get_tool_by_name(tool_name)

    if not tool:
        logger.error("tool_not_found", tool_name=tool_name, intent=intent)
        return f"Инструмент {tool_name} не найден."

    logger.info("dispatch_tool", intent=intent, tool_name=tool_name, params=params)

    try:
        # Вызываем tool с параметрами
        result = _invoke_tool(tool, tool_name, params)
        return result

    except Exception as e:
        logger.error("tool_dispatch_error", tool_name=tool_name, error=str(e), exc_info=True)
        return f"Ошибка при вызове {tool_name}: {e}"


def _invoke_tool(tool: Any, tool_name: str, params: dict[str, Any]) -> str:
    """
    Вызывает tool с правильными параметрами.

    Разные tools принимают разные аргументы — этот метод
    преобразует params в нужный формат.
    """
    # Tools которые принимают только address (строку)
    address_only_tools = {
        "find_nearest_mfc_v2",
        "get_polyclinics_by_address_v2",
        "get_linked_schools_by_address_v2",
        "get_management_company_by_address_v2",
        "get_disconnections_by_address_v2",
        "get_district_info_by_address_v2",
    }

    # Tools без параметров
    no_params_tools = {
        "get_pensioner_service_categories_v2",
        "get_memorable_dates_today_v2",
    }

    # Tools с district только
    district_only_tools = {
        "get_kindergartens_v2",
    }

    if tool_name in address_only_tools:
        address = params.get("address", "")
        return tool.invoke(address)

    elif tool_name in no_params_tools:
        return tool.invoke({})

    elif tool_name in district_only_tools:
        district = params.get("district", "")
        return tool.invoke({"district": district, "age_years": 3, "age_months": 0})

    elif tool_name == "get_pensioner_services_v2":
        district = params.get("district", "")
        category = params.get("category", "")
        return tool.invoke({"district": district, "category": category})

    elif tool_name == "get_pet_parks_v2":
        return tool.invoke({
            "address": params.get("address", ""),
            "radius": 5000,
        })

    elif tool_name == "get_vet_clinics_v2":
        return tool.invoke({
            "address": params.get("address", ""),
            "radius": 5000,
        })

    elif tool_name == "get_road_works_v2":
        return tool.invoke({
            "district": params.get("district"),
            "count": 10,
        })

    elif tool_name == "get_beautiful_places_v2":
        return tool.invoke({
            "district": params.get("district"),
            "category": params.get("category"),
            "count": 10,
        })

    elif tool_name == "get_beautiful_place_routes_v2":
        return tool.invoke({})

    elif tool_name == "get_sportgrounds_v2":
        return tool.invoke({
            "district": params.get("district", ""),
            "count": 10,
        })

    elif tool_name == "get_city_events_v2":
        return tool.invoke({
            "days_ahead": 7,
            "category": params.get("category", ""),
        })

    elif tool_name == "get_sport_events_v2":
        return tool.invoke({
            "district": params.get("district", ""),
            "days_ahead": 14,
            "category": params.get("category", ""),
        })

    else:
        # Fallback — пробуем передать все params как dict
        logger.warning("unknown_tool_signature", tool_name=tool_name)
        return tool.invoke(params)


# =============================================================================
# High-Level API
# =============================================================================


def handle_api_intent(intent: str, params: dict[str, Any]) -> tuple[str, bool]:
    """
    Высокоуровневый API для обработки API intent.

    Args:
        intent: Тип намерения
        params: Извлечённые параметры

    Returns:
        (result, needs_clarification)
        - result: результат tool или сообщение уточнения
        - needs_clarification: True если нужно уточнение
    """
    # Проверяем параметры
    is_valid, clarification = validate_params_for_intent(intent, params)

    if not is_valid:
        return clarification, True

    # Вызываем tool
    result = dispatch_tool(intent, params)
    return result, False

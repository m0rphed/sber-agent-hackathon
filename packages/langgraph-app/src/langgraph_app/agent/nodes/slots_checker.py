"""
Нода проверки заполненности слотов (параметров).

Определяет, есть ли все необходимые параметры для выполнения запроса.
Если параметров не хватает — формирует уточняющий вопрос.
"""

from langchain_core.prompts import ChatPromptTemplate

from langgraph_app.agent.llm import get_llm_for_intent_routing
from langgraph_app.agent.models import SlotsCheck, ToolCategory
from langgraph_app.agent.state import get_chat_history, get_last_user_message
from langgraph_app.agent.state_v2 import HybridStateV2
from langgraph_app.logging_config import get_logger

logger = get_logger(__name__)


# Какие параметры нужны для каждой категории
# Все API-категории должны быть здесь!
# ВАЖНО: Соответствует ToolCategory в models.py
REQUIRED_PARAMS_BY_CATEGORY: dict[ToolCategory, list[str]] = {
    # === Geo / Address ===
    ToolCategory.ADDRESS: [],  # Поиск адреса — нужен только текст запроса
    ToolCategory.DISTRICT: [],  # Информация о районах — можно без параметров

    # === Городские сервисы ===
    ToolCategory.MFC: ["address"],  # find_nearest_mfc требует адрес
    ToolCategory.POLYCLINIC: ["address"],  # get_polyclinics_by_address
    ToolCategory.SCHOOL: ["address"],  # get_schools_by_address (или district)
    ToolCategory.KINDERGARTEN: ["district"],  # get_kindergartens_by_district
    ToolCategory.HOUSING: ["address"],  # get_management_company, get_disconnections

    # === Питомцы (требуют координаты!) ===
    ToolCategory.PETS: ["address"],  # Нужен адрес для получения lat/lon

    # === Активности ===
    ToolCategory.PENSIONER: ["district"],  # get_pensioner_services требует район
    ToolCategory.EVENTS: [],  # Можно без параметров
    ToolCategory.RECREATION: [],  # district опционален

    # === Инфраструктура ===
    ToolCategory.INFRASTRUCTURE: [],  # Можно без параметров
}


SLOTS_CHECKER_PROMPT = """Ты — анализатор запросов городского помощника.

Категория запроса: {category}
Обязательные параметры для этой категории: {required_params}

Проанализируй запрос пользователя и историю диалога.
Определи:
1. Есть ли все обязательные параметры в запросе или истории?
2. Какие параметры отсутствуют?
3. Извлеки адрес и район если они указаны.

ВАЖНО:
- Адрес — это улица + номер дома (например: "Невский проспект 1", "Большевиков 68")
- Район — это административная единица (например: "Невский", "Центральный", "Приморский")
- НЕ путай адрес и район!

Если параметров не хватает — сформулируй ВЕЖЛИВЫЙ уточняющий вопрос.

Примеры:
- "Найди ближайший МФЦ" → не хватает адреса → "Уточните, пожалуйста, ваш адрес"
- "МФЦ на Невском 100" → адрес есть → is_clear=True, extracted_address="Невский 100"
- "Кружки для пенсионеров" → не хватает района → "В каком районе искать занятия?"
- "Кружки в Невском районе" → район есть → is_clear=True, extracted_district="Невский"
"""


def check_slots_node(state: HybridStateV2) -> dict:
    """
    Проверяет наличие обязательных параметров.

    Args:
        state: Текущее состояние графа

    Returns:
        Dict с обновлениями для state:
        - is_slots_complete: bool
        - missing_params: list[str]
        - extracted_address: str | None
        - extracted_district: str | None
        - awaiting_clarification: bool
        - clarification_question: str | None
    """
    query = get_last_user_message(state)
    category = state.get("category", ToolCategory.RAG)
    history = get_chat_history(state, max_messages=4)

    # Для RAG и conversation не нужны параметры
    if category in (ToolCategory.RAG, ToolCategory.CONVERSATION):
        return {
            "is_slots_complete": True,
            "missing_params": [],
            "awaiting_clarification": False,
        }

    required_params = REQUIRED_PARAMS_BY_CATEGORY.get(category, [])

    # Если нет обязательных параметров — сразу ok
    if not required_params:
        return {
            "is_slots_complete": True,
            "missing_params": [],
            "awaiting_clarification": False,
        }

    logger.info(
        "check_slots_start",
        category=category.value if category else "none",
        required=required_params,
    )

    try:
        llm = get_llm_for_intent_routing().with_structured_output(SlotsCheck)

        prompt = ChatPromptTemplate.from_messages([
            ("system", SLOTS_CHECKER_PROMPT),
            ("human", "История:\n{history}\n\nЗапрос: {query}"),
        ])

        history_text = "\n".join(
            f"{getattr(msg, 'type', 'human')}: {msg.content}"
            for msg in history[-4:]
        ) or "(пусто)"

        result: SlotsCheck = (prompt | llm).invoke({
            "category": category.value if category else "unknown",
            "required_params": ", ".join(required_params) or "нет",
            "history": history_text,
            "query": query,
        })

        logger.info(
            "slots_checked",
            is_clear=result.is_clear,
            missing=result.missing_params,
            extracted_address=result.extracted_address,
            extracted_district=result.extracted_district,
        )

        return {
            "is_slots_complete": result.is_clear,
            "missing_params": result.missing_params,
            "extracted_address": result.extracted_address,
            "extracted_district": result.extracted_district,
            "awaiting_clarification": not result.is_clear,
            "clarification_question": result.clarification_question,
            "clarification_type": "missing_params" if not result.is_clear else None,
        }

    except Exception as e:
        logger.exception("slots_check_failed", error=str(e))

        # Fallback — считаем что всё ok, пусть tool agent разберётся
        return {
            "is_slots_complete": True,
            "missing_params": [],
            "awaiting_clarification": False,
        }

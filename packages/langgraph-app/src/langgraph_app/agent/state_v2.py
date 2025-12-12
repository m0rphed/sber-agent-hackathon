"""
Расширенное состояние для Hybrid V2 графа.

Наследует от AgentState и добавляет поля для:
- категорий инструментов (вместо простого intent)
- clarification loop (awaiting_clarification, clarification_question)
- address validation (address_candidates, selected_candidate_index)
- slot filling (extracted_address, extracted_district, missing_params)
"""

from typing import Any

from langgraph_app.agent.models import AddressCandidate, ToolCategory
from langgraph_app.agent.state import AgentState


class HybridStateV2(AgentState):
    """
    Состояние для Hybrid V2 графа.

    Расширяет базовый AgentState с поддержкой:
    - категорий инструментов (category вместо простого intent)
    - clarification loop для уточнения параметров
    - address validation с показом кандидатов
    - slot filling для извлечения параметров из запроса

    Поля наследуются от AgentState:
        messages: list[BaseMessage]  # история сообщений
        is_toxic: bool               # флаг токсичности
        toxicity_response: str       # ответ на токсичный запрос
        intent: str                  # базовый intent (для совместимости)
        intent_confidence: float     # уверенность классификации
        tool_result: str             # результат выполнения tool
        final_response: str          # финальный ответ
        metadata: dict               # метаданные
    """

    # =========================================================================
    # Category classification (вместо простого intent)
    # =========================================================================

    category: ToolCategory | None
    """
    Категория запроса (mfc, pensioner, healthcare, rag, conversation, и т.д.).
    Определяет какой набор tools будет использоваться.
    """

    category_confidence: float
    """
    Уверенность классификации категории (0.0 - 1.0)
    """

    # =========================================================================
    # Slot filling (извлечение параметров)
    # =========================================================================

    is_slots_complete: bool
    """
    True если все обязательные параметры для категории заполнены
    """

    missing_params: list[str]
    """
    Список недостающих параметров.
    Например: ["address"], ["district", "category_id"]
    """

    extracted_address: str | None
    """
    Адрес, извлечённый из запроса пользователя.
    Например: "Невский проспект 1", "Большевиков 68 к1"
    """

    extracted_district: str | None
    """
    Район, извлечённый из запроса пользователя.
    Например: "Невский", "Центральный", "Калининский"
    """

    # =========================================================================
    # Address validation
    # =========================================================================

    address_validated: bool
    """
    True если адрес успешно прошёл валидацию через API
    """

    address_candidates: list[AddressCandidate]
    """
    Список кандидатов адреса (если API вернул несколько вариантов).
    Пустой список если адрес не найден или найден однозначно.
    """

    selected_candidate_index: int | None
    """
    Индекс выбранного пользователем кандидата (0-based).
    None если пользователь ещё не выбрал или выбор не требуется.
    """

    validated_building_id: int | None
    """
    ID здания (building id) в "Я Здесь Живу" (yazzh) API после успешной валидации.
    Используется для дальнейших запросов к API.
    """

    # =========================================================================
    # Clarification loop
    # =========================================================================

    awaiting_clarification: bool
    """
    True если агент ожидает уточнения от пользователя.
    Используется для реализации clarification loop.
    """

    clarification_question: str | None
    """
    Вопрос для уточнения, который нужно задать пользователю.
    Например: "Уточните, пожалуйста, ваш адрес"
    """

    clarification_type: str | None
    """
    Тип уточнения: "missing_params", "address_candidates", "other"
    Помогает понять, как обрабатывать следующий ответ пользователя.
    """

    # =========================================================================
    # Tool execution
    # =========================================================================

    tool_outputs: list[dict[str, Any]]
    """
    Результаты выполнения tools (если вызывалось несколько).
    Каждый элемент: {"tool_name": str, "output": Any, "success": bool}
    """


# =============================================================================
# Helper Functions для HybridStateV2
# =============================================================================


def get_default_hybrid_v2_state() -> dict[str, Any]:
    """
    Возвращает значения по умолчанию для полей HybridStateV2.

    Используется при инициализации state.
    """
    from langgraph_app.agent.state import get_default_state_values

    base_defaults = get_default_state_values()

    hybrid_v2_defaults: dict[str, Any] = {
        # Category
        'category': None,
        'category_confidence': 0.0,
        # Slot filling
        'is_slots_complete': False,
        'missing_params': [],
        'extracted_address': None,
        'extracted_district': None,
        # Address validation
        'address_validated': False,
        'address_candidates': [],
        'selected_candidate_index': None,
        'validated_building_id': None,
        # Clarification
        'awaiting_clarification': False,
        'clarification_question': None,
        'clarification_type': None,
        # Tool execution
        'tool_outputs': [],
    }

    return {**base_defaults, **hybrid_v2_defaults}


def is_awaiting_user_input(state: HybridStateV2) -> bool:
    """
    Проверяет, ожидает ли агент ввода от пользователя.

    Args:
        state: Текущее состояние

    Returns:
        True если нужен ввод пользователя (clarification или выбор адреса)
    """
    return state.get('awaiting_clarification', False)


def get_address_from_state(state: HybridStateV2) -> str | None:
    """
    Возвращает прошедший валидацию адрес из state.

    Приоритет:
    1. Выбранный кандидат (если был выбор)
    2. Первый кандидат (если один результат)
    3. extracted_address (если не было валидации)

    Args:
        state: Текущее состояние

    Returns:
        Адрес или None
    """
    candidates = state.get('address_candidates', [])
    selected_idx = state.get('selected_candidate_index')

    # если есть выбранный кандидат
    if selected_idx is not None and candidates:
        if 0 <= selected_idx < len(candidates):
            candidate = candidates[selected_idx]
            if isinstance(candidate, AddressCandidate):
                return candidate.full_address
            elif isinstance(candidate, dict):
                return candidate.get('full_address')

    # если есть единственный кандидат
    if len(candidates) == 1:
        candidate = candidates[0]
        if isinstance(candidate, AddressCandidate):
            return candidate.full_address
        elif isinstance(candidate, dict):
            return candidate.get('full_address')

    # Fallback на extracted_address
    return state.get('extracted_address')


def get_building_id_from_state(state: HybridStateV2) -> int | None:
    """
    Возвращает building_id из state.

    Args:
        state: Текущее состояние

    Returns:
        building_id или None
    """
    # сначала проверяем validated_building_id
    if state.get('validated_building_id'):
        return state['validated_building_id']

    # пробуем получить из кандидатов
    candidates = state.get('address_candidates', [])
    selected_idx = state.get('selected_candidate_index')

    if selected_idx is not None and candidates:
        if 0 <= selected_idx < len(candidates):
            candidate = candidates[selected_idx]
            if isinstance(candidate, AddressCandidate):
                return candidate.building_id
            elif isinstance(candidate, dict):
                return candidate.get('building_id')

    if len(candidates) == 1:
        candidate = candidates[0]
        if isinstance(candidate, AddressCandidate):
            return candidate.building_id
        elif isinstance(candidate, dict):
            return candidate.get('building_id')

    return None

"""
Hybrid Agent Graph V2 — с категориями и clarification loop.

Архитектура:
    START
      ↓
    check_toxicity ──[toxic]──→ toxic_response → END
      ↓ [safe]
    classify_category (LLM: mfc/pensioner/geo/events/rag/conversation)
      ↓
    ┌─────────────────────┬──────────────────┐
    ↓                     ↓                  ↓
    [rag]            [conversation]     [api_category]
      ↓                   ↓                  ↓
    rag_search       conversation       check_slots
      ↓                   ↓                  ↓
      ↓                   ↓         ┌────────┴────────┐
      ↓                   ↓         ↓ [unclear]       ↓ [clear]
      ↓                   ↓    ask_clarification   validate_address
      ↓                   ↓         ↓                  ↓
      ↓                   ↓         ↓         ┌───────┴────────┐
      ↓                   ↓         ↓         ↓ [invalid]      ↓ [valid]
      ↓                   ↓         ↓    ask_clarification   execute_tools
      ↓                   ↓         ↓         ↓                  ↓
      └─────────────────────────────┴─────────┴──────────────────┘
                                  ↓
                          generate_response
                                  ↓
                                 END

Отличия от hybrid.py (v1):
- Используем категории вместо 3 интентов
- Подмножество tools по категории (не все 26+)
- Clarification loop для уточнения параметров
- Address validation с показом кандидатов
"""
# =============================================================================
# Import nodes
# =============================================================================

# Общие ноды (toxicity, rag, conversation, response)
# Специализированные ноды для V2
from langgraph.graph import END, START, StateGraph

from langgraph_app.agent.models import ToolCategory
from langgraph_app.agent.nodes.address_validator import validate_address_node
from langgraph_app.agent.nodes.category_classifier import classify_category_node
from langgraph_app.agent.nodes.common import (
    check_toxicity_node,
    conversation_node,
    generate_response_node,
    rag_search_node,
    toxic_response_node,
)
from langgraph_app.agent.nodes.slots_checker import check_slots_node
from langgraph_app.agent.nodes.tool_executor import execute_tools_node
from langgraph_app.agent.state import create_ai_response
from langgraph_app.agent.state_v2 import HybridStateV2
from langgraph_app.logging_config import get_logger

logger = get_logger(__name__)

# Максимальное количество попыток уточнения СЛОТОВ перед fallback на RAG
MAX_CLARIFICATION_ATTEMPTS = 2

# Максимальное количество попыток валидации АДРЕСА перед fallback на RAG
MAX_ADDRESS_VALIDATION_ATTEMPTS = 2

# =============================================================================
# New nodes
# =============================================================================


def ask_clarification_node(state: HybridStateV2) -> dict:
    """
    Возвращает уточняющий вопрос пользователю.

    Этот узел завершает текущий run графа.
    Пользователь должен ответить, и следующий run продолжит обработку.

    Также:
    - Инкрементит ПРАВИЛЬНЫЙ счётчик в зависимости от типа уточнения:
      - address → address_validation_attempts
      - остальные → clarification_attempts
    - Добавляет контекст о том, что пытается сделать агент
    - При последней попытке предупреждает о fallback на общую информацию
    """
    clarification_type = state.get('clarification_type')
    is_address_clarification = clarification_type in ('address', 'address_candidates', 'address_not_found')

    # Выбираем правильный счётчик
    if is_address_clarification:
        attempts = state.get('address_validation_attempts', 0) + 1
        max_attempts = MAX_ADDRESS_VALIDATION_ATTEMPTS
    else:
        attempts = state.get('clarification_attempts', 0) + 1
        max_attempts = MAX_CLARIFICATION_ATTEMPTS

    base_question = state.get('clarification_question') or 'Уточните, пожалуйста, детали запроса.'
    category = state.get('category')
    missing = state.get('missing_params', [])

    # Формируем контекстное сообщение
    if attempts == 1:
        # Первая попытка — объясняем что хотим сделать и какие параметры нужны
        context = _get_category_context(category)
        if context:
            if missing:
                missing_str = ', '.join(missing)
                question = f'{context}\n\nНе хватает: {missing_str}.\n\n{base_question}'
            else:
                question = f'{context}\n\n{base_question}'
        else:
            question = base_question
    elif attempts >= max_attempts:
        # Последняя попытка — предупреждаем о fallback
        question = (
            f'{base_question}\n\n'
            'Если вам сложно указать эти данные, я могу предоставить '
            'общую справочную информацию по вашему вопросу.'
        )
    else:
        question = base_question

    logger.info(
        'ask_clarification',
        clarification_type=clarification_type,
        attempt=attempts,
        max_attempts=max_attempts,
        is_address=is_address_clarification,
    )

    # Возвращаем правильный счётчик
    if is_address_clarification:
        return {
            **create_ai_response(question),
            'address_validation_attempts': attempts,
        }
    else:
        return {
            **create_ai_response(question),
            'clarification_attempts': attempts,
        }


def _get_category_context(category: ToolCategory | None) -> str:
    """
    Возвращает объяснение, что пытается сделать агент для данной категории.
    """
    if category is None:
        return ''

    contexts = {
        ToolCategory.MFC: 'Чтобы найти ближайший МФЦ, мне нужно знать ваш адрес.',
        ToolCategory.POLYCLINIC: 'Чтобы найти поликлинику, обслуживающую ваш дом, мне нужен адрес.',
        ToolCategory.SCHOOL: 'Для поиска школ мне нужен ваш адрес или район.',
        ToolCategory.KINDERGARTEN: 'Для поиска детских садов мне нужно знать район.',
        ToolCategory.HOUSING: 'Для информации о вашем доме мне нужен точный адрес.',
        ToolCategory.PETS: 'Для поиска ветклиник и площадок мне нужен ваш адрес.',
        ToolCategory.PENSIONER: 'Для поиска услуг для пенсионеров мне нужен район.',
    }
    return contexts.get(category, '')


# =============================================================================
# Routers
# =============================================================================


def toxicity_router(state: HybridStateV2) -> str:
    """Роутер после проверки токсичности."""
    if state.get('is_toxic', False):
        return 'toxic'
    return 'safe'


def category_router(state: HybridStateV2) -> str:
    """Роутер по категории."""
    category = state.get('category')

    if category == ToolCategory.RAG:
        return 'rag'
    elif category == ToolCategory.CONVERSATION:
        return 'conversation'
    else:
        # Все остальные категории — API tools
        return 'api'


def slots_router(state: HybridStateV2) -> str:
    """
    Роутер после проверки слотов.

    Защита от бесконечного цикла:
    - После MAX_CLARIFICATION_ATTEMPTS переключаемся на RAG
    - Это даёт пользователю хоть какой-то ответ, а не зависание
    """
    if state.get('is_slots_complete', False):
        # Есть все параметры — проверяем адрес если есть
        if state.get('extracted_address'):
            return 'validate_address'
        return 'execute'

    # Защита от бесконечного цикла уточнений
    attempts = state.get('clarification_attempts', 0)
    if attempts >= MAX_CLARIFICATION_ATTEMPTS:
        logger.warning(
            'clarification_limit_reached',
            attempts=attempts,
            missing_params=state.get('missing_params'),
            category=state.get('category'),
        )
        # Fallback на RAG — дадим общую информацию
        return 'fallback_rag'

    return 'clarify'


def address_router(state: HybridStateV2) -> str:
    """
    Роутер после валидации адреса.

    Защита от бесконечного цикла:
    - После MAX_ADDRESS_VALIDATION_ATTEMPTS переключаемся на RAG
    - Это отдельный счётчик от clarification_attempts (слоты)
    """
    if state.get('address_validated', False):
        return 'execute'

    # Защита от бесконечного цикла валидации адреса
    attempts = state.get('address_validation_attempts', 0)
    if attempts >= MAX_ADDRESS_VALIDATION_ATTEMPTS:
        logger.warning(
            'address_validation_limit_reached',
            attempts=attempts,
            address=state.get('extracted_address'),
        )
        return 'fallback_address'

    return 'clarify'


def fallback_rag_node(state: HybridStateV2) -> dict:
    """
    Fallback на RAG когда не удалось получить нужные параметры.

    Вместо бесконечного цикла уточнений — даём общую информацию
    и объясняем пользователю ситуацию.
    """
    category = state.get('category')
    missing = state.get('missing_params', [])

    logger.info(
        'fallback_to_rag',
        category=category,
        missing_params=missing,
        attempts=state.get('clarification_attempts', 0),
    )

    # Добавляем контекст о том, почему мы переключились на RAG
    context_note = (
        f'К сожалению, без указания {", ".join(missing) if missing else "дополнительных данных"} '
        f'я не могу выполнить точный поиск. Вот общая информация по вашему вопросу:\n\n'
    )

    return {
        'fallback_context': context_note,
        'clarification_attempts': 0,  # Сбрасываем счётчик
    }


def fallback_address_node(state: HybridStateV2) -> dict:
    """
    Fallback на RAG когда не удалось валидировать адрес после N попыток.

    Отдельный от fallback_rag — объясняет проблему с адресом.
    """
    address = state.get('extracted_address')
    attempts = state.get('address_validation_attempts', 0)

    logger.info(
        'fallback_address_to_rag',
        address=address,
        attempts=attempts,
    )

    # Объясняем пользователю ситуацию с адресом
    context_note = (
        f"К сожалению, мне не удалось найти адрес '{address}' в базе данных. "
        f'Возможно, адрес указан неточно или отсутствует в системе. '
        f'Вот общая информация по вашему вопросу:\n\n'
    )

    return {
        'fallback_context': context_note,
        'address_validation_attempts': 0,  # Сбрасываем счётчик
    }


# =============================================================================
# Graph Builder
# =============================================================================


def create_hybrid_v2_graph(checkpointer=None):
    """
    Создаёт Hybrid V2 граф.

    Args:
        checkpointer: Optional checkpointer для персистентности.
                      Если None — граф работает in-memory.

    Returns:
        Скомпилированный StateGraph
    """
    from langgraph_app.agent.resilience import get_api_retry_policy, get_llm_retry_policy

    logger.info('hybrid_v2_graph_build_start', with_checkpointer=checkpointer is not None)

    builder = StateGraph(HybridStateV2)

    # Retry policies
    llm_retry = get_llm_retry_policy()
    api_retry = get_api_retry_policy()

    # === Nodes ===

    # Toxicity check (без retry — быстрая проверка)
    builder.add_node('check_toxicity', check_toxicity_node)
    builder.add_node('toxic_response', toxic_response_node)

    # Classification (с LLM retry)
    builder.add_node('classify_category', classify_category_node, retry=llm_retry)

    # Slot checking (с LLM retry)
    builder.add_node('check_slots', check_slots_node, retry=llm_retry)

    # Address validation (с API retry)
    builder.add_node('validate_address', validate_address_node, retry=api_retry)

    # Clarification (без retry — просто возврат текста)
    builder.add_node('ask_clarification', ask_clarification_node)

    # Tool execution (с API retry)
    builder.add_node('execute_tools', execute_tools_node, retry=api_retry)

    # RAG and conversation (с LLM retry)
    builder.add_node('rag_search', rag_search_node, retry=llm_retry)
    builder.add_node('conversation', conversation_node, retry=llm_retry)

    # Fallback RAG (когда не удалось получить параметры)
    builder.add_node('fallback_rag', fallback_rag_node)

    # Fallback для адреса (когда не удалось валидировать адрес)
    builder.add_node('fallback_address', fallback_address_node)

    # Response generation (без retry)
    builder.add_node('generate_response', generate_response_node)

    # === Edges ===

    # Start → check_toxicity
    builder.add_edge(START, 'check_toxicity')

    # Toxicity routing
    builder.add_conditional_edges(
        'check_toxicity',
        toxicity_router,
        {
            'toxic': 'toxic_response',
            'safe': 'classify_category',
        },
    )

    builder.add_edge('toxic_response', END)

    # Category routing
    builder.add_conditional_edges(
        'classify_category',
        category_router,
        {
            'rag': 'rag_search',
            'conversation': 'conversation',
            'api': 'check_slots',
        },
    )

    # Slots routing
    builder.add_conditional_edges(
        'check_slots',
        slots_router,
        {
            'clarify': 'ask_clarification',
            'validate_address': 'validate_address',
            'execute': 'execute_tools',
            'fallback_rag': 'fallback_rag',
        },
    )

    # Address routing
    builder.add_conditional_edges(
        'validate_address',
        address_router,
        {
            'execute': 'execute_tools',
            'clarify': 'ask_clarification',
            'fallback_address': 'fallback_address',
        },
    )

    # Clarification завершает граф — ждём ответа пользователя
    builder.add_edge('ask_clarification', END)

    # Fallback RAG → обычный RAG поиск
    builder.add_edge('fallback_rag', 'rag_search')

    # Fallback Address → обычный RAG поиск
    builder.add_edge('fallback_address', 'rag_search')

    # Все пути сходятся в generate_response
    builder.add_edge('execute_tools', 'generate_response')
    builder.add_edge('rag_search', 'generate_response')
    builder.add_edge('conversation', 'generate_response')

    builder.add_edge('generate_response', END)

    # === Compile ===
    graph = builder.compile(checkpointer=checkpointer)

    logger.info('hybrid_v2_graph_built')

    return graph


# =============================================================================
# Entry point for direct usage (CLI scripts, tests)
# =============================================================================

_cached_graph = None


def get_hybrid_v2_graph():
    """
    Возвращает скомпилированный граф с checkpointer.

    Checkpointer выбирается автоматически:
    - PostgreSQL если POSTGRES_CHECKPOINTER_URL указан
    - MemorySaver fallback иначе

    Используется для CLI скриптов и тестов.
    Для LangGraph Server используйте graphs.py:hybrid() (без checkpointer).
    """
    global _cached_graph

    if _cached_graph is None:
        from langgraph_app.agent.persistent_memory import get_checkpointer

        checkpointer = get_checkpointer()
        _cached_graph = create_hybrid_v2_graph(checkpointer=checkpointer)

    return _cached_graph


# Ленивый alias для обратной совместимости
# ВАЖНО: Создаётся только при первом обращении через get_hybrid_v2_graph()
class _LazyGraph:
    """Lazy proxy для графа — создаётся только при первом доступе."""

    def __getattr__(self, name):
        return getattr(get_hybrid_v2_graph(), name)

    def __repr__(self):
        return repr(get_hybrid_v2_graph())


hybrid_v2_graph = _LazyGraph()

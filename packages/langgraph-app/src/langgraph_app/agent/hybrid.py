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

from langgraph.graph import END, START, StateGraph

from langgraph_app.agent.models import ToolCategory
from langgraph_app.agent.state import create_ai_response
from langgraph_app.agent.state_v2 import HybridStateV2
from langgraph_app.logging_config import get_logger

logger = get_logger(__name__)


# =============================================================================
# Import nodes
# =============================================================================

# Общие ноды (toxicity, rag, conversation, response)
from langgraph_app.agent.nodes.common import (
    check_toxicity_node,
    conversation_node,
    generate_response_node,
    rag_search_node,
    toxic_response_node,
)

# Специализированные ноды для V2
from langgraph_app.agent.nodes.address_validator import validate_address_node
from langgraph_app.agent.nodes.category_classifier import classify_category_node
from langgraph_app.agent.nodes.slots_checker import check_slots_node
from langgraph_app.agent.nodes.tool_executor import execute_tools_node

# =============================================================================
# New nodes
# =============================================================================


def ask_clarification_node(state: HybridStateV2) -> dict:
    """
    Возвращает уточняющий вопрос пользователю.

    Этот узел завершает текущий run графа.
    Пользователь должен ответить, и следующий run продолжит обработку.
    """
    question = state.get("clarification_question") or "Уточните, пожалуйста, детали запроса."

    logger.info(
        "ask_clarification",
        clarification_type=state.get("clarification_type"),
        question_length=len(question),
    )

    return create_ai_response(question)


# =============================================================================
# Routers
# =============================================================================


def toxicity_router(state: HybridStateV2) -> str:
    """Роутер после проверки токсичности."""
    if state.get("is_toxic", False):
        return "toxic"
    return "safe"


def category_router(state: HybridStateV2) -> str:
    """Роутер по категории."""
    category = state.get("category")

    if category == ToolCategory.RAG:
        return "rag"
    elif category == ToolCategory.CONVERSATION:
        return "conversation"
    else:
        # Все остальные категории — API tools
        return "api"


def slots_router(state: HybridStateV2) -> str:
    """Роутер после проверки слотов."""
    if state.get("is_slots_complete", False):
        # Есть все параметры — проверяем адрес если есть
        if state.get("extracted_address"):
            return "validate_address"
        return "execute"
    return "clarify"


def address_router(state: HybridStateV2) -> str:
    """Роутер после валидации адреса."""
    if state.get("address_validated", False):
        return "execute"
    return "clarify"


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

    logger.info("hybrid_v2_graph_build_start", with_checkpointer=checkpointer is not None)

    builder = StateGraph(HybridStateV2)

    # Retry policies
    llm_retry = get_llm_retry_policy()
    api_retry = get_api_retry_policy()

    # === Nodes ===

    # Toxicity check (без retry — быстрая проверка)
    builder.add_node("check_toxicity", check_toxicity_node)
    builder.add_node("toxic_response", toxic_response_node)

    # Classification (с LLM retry)
    builder.add_node("classify_category", classify_category_node, retry=llm_retry)

    # Slot checking (с LLM retry)
    builder.add_node("check_slots", check_slots_node, retry=llm_retry)

    # Address validation (с API retry)
    builder.add_node("validate_address", validate_address_node, retry=api_retry)

    # Clarification (без retry — просто возврат текста)
    builder.add_node("ask_clarification", ask_clarification_node)

    # Tool execution (с API retry)
    builder.add_node("execute_tools", execute_tools_node, retry=api_retry)

    # RAG and conversation (с LLM retry)
    builder.add_node("rag_search", rag_search_node, retry=llm_retry)
    builder.add_node("conversation", conversation_node, retry=llm_retry)

    # Response generation (без retry)
    builder.add_node("generate_response", generate_response_node)

    # === Edges ===

    # Start → check_toxicity
    builder.add_edge(START, "check_toxicity")

    # Toxicity routing
    builder.add_conditional_edges(
        "check_toxicity",
        toxicity_router,
        {
            "toxic": "toxic_response",
            "safe": "classify_category",
        },
    )

    builder.add_edge("toxic_response", END)

    # Category routing
    builder.add_conditional_edges(
        "classify_category",
        category_router,
        {
            "rag": "rag_search",
            "conversation": "conversation",
            "api": "check_slots",
        },
    )

    # Slots routing
    builder.add_conditional_edges(
        "check_slots",
        slots_router,
        {
            "clarify": "ask_clarification",
            "validate_address": "validate_address",
            "execute": "execute_tools",
        },
    )

    # Address routing
    builder.add_conditional_edges(
        "validate_address",
        address_router,
        {
            "execute": "execute_tools",
            "clarify": "ask_clarification",
        },
    )

    # Clarification завершает граф — ждём ответа пользователя
    builder.add_edge("ask_clarification", END)

    # Все пути сходятся в generate_response
    builder.add_edge("execute_tools", "generate_response")
    builder.add_edge("rag_search", "generate_response")
    builder.add_edge("conversation", "generate_response")

    builder.add_edge("generate_response", END)

    # === Compile ===
    graph = builder.compile(checkpointer=checkpointer)

    logger.info("hybrid_v2_graph_built")

    return graph


# =============================================================================
# Entry point for langgraph.json
# =============================================================================

# Создаём граф для использования в langgraph dev/up
hybrid_v2_graph = create_hybrid_v2_graph()


def get_hybrid_v2_graph():
    """Возвращает скомпилированный граф (кэшированный на уровне модуля)."""
    return hybrid_v2_graph

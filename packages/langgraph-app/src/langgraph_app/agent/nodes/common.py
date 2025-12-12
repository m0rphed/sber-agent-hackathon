"""
Общие ноды для графов агентов.

Содержит базовые ноды, используемые в разных вариантах графов:
- check_toxicity_node — проверка токсичности
- toxic_response_node — ответ на токсичный запрос
- rag_search_node — RAG поиск
- conversation_node — разговорный ответ
- generate_response_node — финальная генерация ответа
"""

from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage

from langgraph_app.agent.state import (
    AgentState,
    create_ai_response,
    create_error_response,
    get_chat_history,
    get_last_user_message,
)
from langgraph_app.config import get_agent_config
from langgraph_app.logging_config import get_logger
from langgraph_app.rag.config import get_rag_config

logger = get_logger(__name__)


# =============================================================================
# Toxicity Nodes
# =============================================================================


def check_toxicity_node(state: AgentState) -> dict[str, Any]:
    """
    Проверка токсичности запроса.

    Args:
        state: Состояние агента (HybridState или HybridStateV2)

    Returns:
        Dict с is_toxic, toxicity_response, metadata
    """
    from langgraph_app.services.toxicity import get_toxicity_filter

    query = get_last_user_message(state)

    logger.info("check_toxicity", query_length=len(query))

    toxicity_filter = get_toxicity_filter()
    result = toxicity_filter.check(query)

    if result.should_block:
        response = toxicity_filter.get_response(result)
        logger.warning("toxicity_blocked", level=result.level.value)
        return {
            "is_toxic": True,
            "toxicity_response": response,
            "metadata": {**state.get("metadata", {}), "toxicity_blocked": True},
        }

    return {
        "is_toxic": False,
        "toxicity_response": None,
        "metadata": {**state.get("metadata", {}), "toxicity_blocked": False},
    }


def toxic_response_node(state: AgentState) -> dict[str, Any]:
    """
    Ответ на токсичный запрос.

    Args:
        state: Состояние агента

    Returns:
        AIMessage с ответом
    """
    response = state.get("toxicity_response") or "Извините, я не могу обработать этот запрос."
    return create_ai_response(response)


# =============================================================================
# RAG Node
# =============================================================================


def rag_search_node(state: AgentState) -> dict[str, Any]:
    """
    RAG поиск по документам госуслуг.

    Args:
        state: Состояние агента

    Returns:
        Dict с tool_result и metadata
    """
    from langgraph_app.rag.graph import search_with_graph

    rag_config = get_rag_config()
    query = get_last_user_message(state)

    logger.info("rag_search", query=query[:100])

    try:
        documents, metadata = search_with_graph(
            query=query,
            k=rag_config.search.k,
            min_relevant=rag_config.search.min_relevant,
            use_toxicity_check=False,  # Уже проверили
        )

        if not documents:
            result = "К сожалению, не удалось найти информацию по вашему запросу."
        else:
            result_parts = ["Вот что я нашёл:\n"]
            content_preview_limit = rag_config.search.content_preview_limit
            for i, doc in enumerate(documents, 1):
                title = doc.metadata.get("title", "Документ")
                url = doc.metadata.get("url", "")
                preview = (
                    doc.page_content[:content_preview_limit] + "..."
                    if len(doc.page_content) > content_preview_limit
                    else doc.page_content
                )
                result_parts.append(f"\n**{i}. {title}**")
                if url:
                    result_parts.append(f"\nИсточник: {url}")
                result_parts.append(f"\n{preview}\n")
            result = "\n".join(result_parts)

        logger.info("rag_search_complete", documents_count=len(documents))

        return {
            "tool_result": result,
            "metadata": {
                **state.get("metadata", {}),
                "handler": "rag",
                "documents_count": len(documents),
            },
        }

    except Exception as e:
        return create_error_response(e, "Ошибка поиска. Попробуйте переформулировать запрос.")


# =============================================================================
# Conversation Node
# =============================================================================


def conversation_node(state: AgentState) -> dict[str, Any]:
    """
    Разговорный ответ (small talk).

    Args:
        state: Состояние агента

    Returns:
        Dict с tool_result и metadata
    """
    from langgraph_app.agent.llm import get_llm_for_conversation

    agent_config = get_agent_config()
    query = get_last_user_message(state)
    chat_history = get_chat_history(state, max_messages=agent_config.memory.context_window_size)

    logger.info("conversation", query=query[:100])

    llm = get_llm_for_conversation()

    messages = [
        HumanMessage(
            content="""[SYSTEM] Ты — дружелюбный городской помощник Санкт-Петербурга.
Помогаешь жителям с информацией о госуслугах, МФЦ и городских сервисах.
Отвечай кратко и вежливо."""
        )
    ]

    # Добавляем историю
    for msg in chat_history:
        if isinstance(msg, BaseMessage):
            messages.append(HumanMessage(content=f"[{msg.type.upper()}] {msg.content}"))

    messages.append(HumanMessage(content=query))

    try:
        response = llm.invoke(messages)
        result = response.content

        logger.info("conversation_complete", response_length=len(result))

        return {
            "tool_result": result,
            "metadata": {**state.get("metadata", {}), "handler": "conversation"},
        }

    except Exception as e:
        return create_error_response(e, "Ошибка обработки. Попробуйте позже.")


# =============================================================================
# Response Generation Node
# =============================================================================


def generate_response_node(state: AgentState) -> dict[str, Any]:
    """
    Финальная генерация ответа.

    Берёт tool_result или final_response и формирует AIMessage.

    Args:
        state: Состояние агента

    Returns:
        AIMessage с ответом
    """
    tool_result = state.get("tool_result") or state.get("final_response") or ""

    # Защита от None
    if tool_result is None:
        tool_result = "Извините, не удалось обработать запрос."

    logger.info("generate_response", result_length=len(tool_result))

    return create_ai_response(tool_result)

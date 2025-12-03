"""
Единый State для всех агентов.

Базируется на MessagesState из LangGraph для совместимости с:
- LangGraph Studio
- Agent Server (langgraph dev/up)
- LangSmith tracing
- Streaming
- Checkpointer

Использование:
    from app.agent.state import AgentState, get_last_user_message

    class MyState(AgentState):
        my_field: str
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import MessagesState

from app.logging_config import get_logger

logger = get_logger(__name__)


# =============================================================================
# Base State
# =============================================================================


class AgentState(MessagesState):
    """
    Базовый State для всех агентов.

    Наследует от MessagesState, который уже содержит:
        messages: Annotated[list[BaseMessage], add_messages]

    Добавляет общие поля для наших агентов.
    """

    # === Toxicity ===
    is_toxic: bool  # True если запрос токсичный
    toxicity_response: str | None  # Ответ для токсичного запроса

    # === Intent ===
    intent: str  # Классифицированное намерение
    intent_confidence: float  # Уверенность классификации

    # === Results ===
    tool_result: str | None  # Результат вызова tool/RAG
    final_response: str | None  # Финальный ответ

    # === Metadata ===
    metadata: dict[str, Any]  # Статистика, логирование


# =============================================================================
# Helper Functions
# =============================================================================


def get_last_user_message(state: AgentState) -> str:
    """
    Извлекает текст последнего сообщения пользователя из messages.

    Обрабатывает разные форматы content:
    - str: "текст сообщения"
    - list[str]: ["текст"]
    - list[dict]: [{"type": "text", "text": "текст"}]

    Args:
        state: Состояние агента

    Returns:
        Текст последнего user message или пустая строка
    """
    messages = state.get('messages', [])

    # Ищем последнее HumanMessage
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            content = msg.content
            return _extract_text_from_content(content)

    return ''


def _extract_text_from_content(content) -> str:
    """
    Извлекает текст из разных форматов content.

    Форматы:
    - str: возвращает как есть
    - list[str]: возвращает первый элемент
    - list[dict]: ищет {"type": "text", "text": "..."} и возвращает text
    - dict: ищет "text" ключ
    """
    if isinstance(content, str):
        return content

    if isinstance(content, dict):
        # {"type": "text", "text": "..."}
        if 'text' in content:
            return str(content['text'])
        return str(content)

    if isinstance(content, list):
        if not content:
            return ''

        first_item = content[0]

        # list[str]
        if isinstance(first_item, str):
            return first_item

        # list[dict] - формат от LangGraph Studio
        if isinstance(first_item, dict):
            if 'text' in first_item:
                return str(first_item['text'])
            return str(first_item)

        return str(first_item)

    return str(content)


def get_chat_history(state: AgentState, max_messages: int | None = None) -> list[BaseMessage]:
    """
    Извлекает историю сообщений (без последнего user message).

    Args:
        state: Состояние агента
        max_messages: Максимум сообщений (None = все)

    Returns:
        Список сообщений истории
    """
    messages = state.get('messages', [])

    if not messages:
        return []

    # Все кроме последнего
    history = messages[:-1] if messages else []

    if max_messages is not None:
        history = history[-max_messages:]

    return history


def create_ai_response(content: str) -> dict:
    """
    Создаёт update для state с AI ответом.

    Args:
        content: Текст ответа

    Returns:
        Dict для обновления state
    """
    # Защита от None
    if content is None:
        content = ''

    return {
        'messages': [AIMessage(content=content)],
        'final_response': content,
    }


def create_error_response(error: Exception, fallback_message: str | None = None) -> dict:
    """
    Создаёт update для state при ошибке.

    Args:
        error: Исключение
        fallback_message: Сообщение по умолчанию

    Returns:
        Dict для обновления state
    """
    message = fallback_message or 'Извините, произошла ошибка при обработке запроса.'

    logger.error('agent_error', error=str(error), exc_info=True)

    return {
        'messages': [AIMessage(content=message)],
        'final_response': message,
        'metadata': {'error': str(error), 'error_type': type(error).__name__},
    }


# =============================================================================
# State Defaults
# =============================================================================


def get_default_state_values() -> dict:
    """
    Возвращает значения по умолчанию для полей state.

    Используется при инициализации state.
    """
    return {
        'is_toxic': False,
        'toxicity_response': None,
        'intent': '',
        'intent_confidence': 0.0,
        'tool_result': None,
        'final_response': None,
        'metadata': {},
    }

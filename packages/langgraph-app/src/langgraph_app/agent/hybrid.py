"""
Hybrid Agent Graph - Вариант 3: Agent внутри Graph.

Архитектура:
    START → check_toxicity → classify_intent → [router]
                                                  ↓
                   ┌──────────────────────────────┼──────────────────────────────┐
                   ↓                              ↓                              ↓
            tool_agent_node               rag_subgraph                   conversation
            (ReAct с API tools)           (RAG pipeline)                 (простой ответ)
                   ↓                              ↓                              ↓
                   └──────────────────────────────┼──────────────────────────────┘
                                                  ↓
                                           generate_response → END

Отличия от Supervisor (Вариант 2):
- tool_agent_node использует ReAct агента для сложных API запросов
- Агент может делать несколько tool calls в цепочке
- Более гибкий, но дороже по API вызовам

Когда использовать:
- Когда нужны сложные цепочки API вызовов
- Когда агент должен сам решать какой tool использовать
- Когда важна гибкость, а не скорость
"""

from enum import Enum
from typing import Literal

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field

from langgraph_app.agent.state import (
    AgentState,
    create_ai_response,
    create_error_response,
    get_chat_history,
    get_default_state_values,
    get_last_user_message,
)
from langgraph_app.config import get_agent_config
from langgraph_app.logging_config import get_logger

# from langgraph_app.rag.config import get_rag_config
from prompts import load_prompt

logger = get_logger(__name__)


# =============================================================================
# Enums & Constants
# =============================================================================


# System prompt для ReAct агента с детальными инструкциями по slot-filling
# Загружаем из файла prompts/tool_agent_system.txt
TOOL_AGENT_SYSTEM_PROMPT = load_prompt("tool_agent_system.txt")


class HybridIntent(str, Enum):
    """
    Типы намерений для гибридного агента
    """

    TOOL_AGENT = 'tool_agent'  # Требует ReAct агента с tools
    RAG_SEARCH = 'rag_search'  # Поиск по госуслугам
    CONVERSATION = 'conversation'  # Обычный разговор

class IntentLLMOutput(BaseModel):
    """
    Структура ответа от LLM-роутера
    """
    intent: Literal['tool_agent', 'rag_search', 'conversation']
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


# Порог уверенности, ниже которого считаем, что лучше отправить запрос в RAG
INTENT_CONFIDENCE_THRESHOLD: float = 0.6

# Сколько сообщений истории отдаём роутеру
INTENT_HISTORY_MESSAGES: int = 4

# Ключевые слова для классификации
HYBRID_INTENT_KEYWORDS = {
    HybridIntent.TOOL_AGENT: [
        # МФЦ
        'мфц',
        'многофункциональный центр',
        'ближайший мфц',
        'адрес мфц',
        'где мфц',
        'часы работы мфц',
        # Пенсионеры
        'услуги для пенсионеров',
        'занятия для пенсионеров',
        'кружки для пенсионеров',
        'категории для пенсионеров',
        'пенсионер район',
        'секции для пожилых',
    ],
    HybridIntent.RAG_SEARCH: [
        'как получить',
        'как оформить',
        'какие документы',
        'где оформить',
        'госуслуг',
        'паспорт',
        'прописка',
        'регистрация',
        'справка',
        'пособие',
        'субсидия',
        'льгота',
        'заявление',
        'выплата',
        'порядок оформления',
    ],
    HybridIntent.CONVERSATION: [
        'привет',
        'здравствуй',
        'добрый день',
        'спасибо',
        'благодарю',
        'пока',
        'до свидания',
        'как дела',
        'кто ты',
        'что ты умеешь',
    ],
}


# =============================================================================
# State Definition
# =============================================================================


class HybridState(AgentState):
    """
    Состояние Hybrid графа.

    Наследует от AgentState (MessagesState + общие поля).
    Добавляет специфичные для Hybrid агента поля.
    """

    # Hybrid-specific: параметры из запроса
    extracted_params: dict  # Извлечённые параметры (адрес, район и т.д.)


# =============================================================================
# Node Functions
# =============================================================================


def check_toxicity_node(state: HybridState) -> dict:
    """Узел 1: Проверка токсичности."""
    from langgraph_app.services.toxicity import get_toxicity_filter

    query = get_last_user_message(state)

    logger.info('hybrid_node', node='check_toxicity', query_length=len(query))

    toxicity_filter = get_toxicity_filter()
    result = toxicity_filter.check(query)

    if result.should_block:
        response = toxicity_filter.get_response(result)
        logger.warning('toxicity_blocked', level=result.level.value)
        return {
            'is_toxic': True,
            'toxicity_response': response,
            'metadata': {**state.get('metadata', {}), 'toxicity_blocked': True},
        }

    return {
        'is_toxic': False,
        'toxicity_response': None,
        'metadata': {**state.get('metadata', {}), 'toxicity_blocked': False},
    }

def _classify_intent_with_llm(
    query: str,
    history: list[BaseMessage],
) -> IntentLLMOutput | None:
    """
    Классификация намерения с помощью GigaChat (LLM-роутера).

    Parameters
    ----------
    query : str
        Последний запрос пользователя (как он есть).
    history : list[BaseMessage]
        История диалога.

    Returns
    -------
    IntentLLMOutput | None
        Структурированный ответ или None, если произошла ошибка.
    """
    try:
        from langchain_core.prompts import ChatPromptTemplate

        from langgraph_app.agent.llm import get_llm_for_intent_routing

        # Загружаем prompt из файла
        hybrid_intent_prompt = load_prompt("hybrid_intent_classifier.txt")

        llm = get_llm_for_intent_routing().with_structured_output(IntentLLMOutput)
        prompt = ChatPromptTemplate.from_messages(
            [
                ('system', hybrid_intent_prompt),
                (
                    'human',
                    """Ниже приведена часть диалога (от старых сообщений к новым):

{dialog}

Последнее сообщение пользователя:
{last_message}""",
                ),
            ]
        )

        # Собираем компактное текстовое представление истории
        dialog_lines: list[str] = []
        for msg in history[-INTENT_HISTORY_MESSAGES:]:
            role = getattr(msg, 'type', 'human')
            dialog_lines.append(f'{role}: {msg.content}')

        dialog_text = '\n'.join(dialog_lines) if dialog_lines else '(диалог пуст)'

        chain = prompt | llm
        result: IntentLLMOutput = chain.invoke(
            {
                'dialog': dialog_text,
                'last_message': query
            }
        )
        return result

    except Exception as e:
        logger.exception('intent_llm_failed', error=str(e))
        return None


def classify_intent_node(state: HybridState) -> dict:
    """
    Узел 2: Классификация намерения (упрощённая для гибрида)
    """
    query_raw = get_last_user_message(state).lower()
    logger.info('hybrid_node', node='classify_intent', query=query_raw[:100])

    # классификация с помощью обращению к LLM
    # INFO: detected_intent = HybridIntent.RAG_SEARCH  # default
    chat_history = get_chat_history(state, max_messages=INTENT_HISTORY_MESSAGES)

    # LLM не ответил / не распарсился — безопасный fallback
    intent = HybridIntent.RAG_SEARCH.value
    confidence = 0.5
    reason = 'llm_error_or_parse_failed'
    method = 'fallback'

    llm_result = _classify_intent_with_llm(query_raw, chat_history)

    if llm_result is not None:
        intent = llm_result.intent
        confidence = float(llm_result.confidence)
        reason = llm_result.reason
        method = 'llm'
    # else:

    logger.info(
        'intent_classified',
        intent=intent,
        method=method,
        confidence=confidence,
    )

    return {
        'intent': intent,
        'intent_confidence': confidence,
        'metadata': {
            **state.get('metadata', {}),
            'classification_method': method,
            'intent_reason': reason,
        },
    }

def tool_agent_node(state: HybridState) -> dict:
    """
    Узел: ReAct агент с API tools.

    Использует полноценный ReAct агент из langgraph.prebuilt для обработки
    запросов, требующих вызова API (МФЦ, пенсионеры и т.д.)
    """
    from langgraph_app.agent.llm import get_llm_for_tools
    from langgraph_app.tools.yazzh_tools import yazzh_tools as API_TOOLS

    agent_config = get_agent_config()
    query = get_last_user_message(state)
    chat_history = get_chat_history(state, max_messages=agent_config.memory.context_window_size)

    logger.info('hybrid_node', node='tool_agent', query=query[:100])

    try:
        llm = get_llm_for_tools()

        # Используем create_react_agent из langgraph.prebuilt
        # Это создаёт готовый граф с ReAct логикой
        react_agent = create_react_agent(
            model=llm,
            tools=API_TOOLS,
            prompt=TOOL_AGENT_SYSTEM_PROMPT,
        )

        # Формируем сообщения для агента
        # Количество сообщений из истории: context_window_size - 2 (для системного и текущего)
        history_limit = max(1, agent_config.memory.context_window_size - 2)
        messages = []
        for msg in chat_history[-history_limit:]:
            messages.append(msg)
        messages.append(HumanMessage(content=query))

        # Вызываем агента с ограничением рекурсии из конфига
        result = react_agent.invoke(
            {'messages': messages},
            config={'recursion_limit': agent_config.memory.recursion_limit},
        )

        # Извлекаем последний AI ответ
        output = 'Не удалось обработать запрос.'
        if result.get('messages'):
            for msg in reversed(result['messages']):
                if hasattr(msg, 'content') and msg.content:
                    content = msg.content
                    # content может быть str или list
                    if isinstance(content, list):
                        content = str(content[0]) if content else ''
                    if hasattr(msg, 'type') and msg.type == 'ai':
                        output = str(content)
                        break
                    elif msg.__class__.__name__ == 'AIMessage':
                        output = str(content)
                        break

        logger.info('tool_agent_complete', output_length=len(output))

        return {
            'tool_result': output,
            'metadata': {
                **state.get('metadata', {}),
                'handler': 'tool_agent',
            },
        }

    except Exception as e:
        return create_error_response(e, 'Ошибка API. Попробуйте позже.')


# def rag_search_node(state: HybridState) -> dict:
#     """Узел: RAG поиск (использует существующий RAG Graph)."""
#     from langgraph_app.rag.graph import search_with_graph

#     rag_config = get_rag_config()
#     query = get_last_user_message(state)

#     logger.info('hybrid_node', node='rag_search', query=query[:100])

#     try:
#         documents, metadata = search_with_graph(
#             query=query,
#             k=rag_config.search.k,
#             min_relevant=rag_config.search.min_relevant,
#             use_toxicity_check=False,  # Уже проверили
#         )

#         if not documents:
#             result = 'К сожалению, не удалось найти информацию по вашему запросу.'
#         else:
#             result_parts = ['Вот что я нашёл:\n']
#             content_preview_limit = rag_config.search.content_preview_limit
#             for i, doc in enumerate(documents, 1):
#                 title = doc.metadata.get('title', 'Документ')
#                 url = doc.metadata.get('url', '')
#                 preview = doc.page_content[:content_preview_limit] + '...' if len(doc.page_content) > content_preview_limit else doc.page_content
#                 result_parts.append(f'\n**{i}. {title}**')
#                 if url:
#                     result_parts.append(f'\nИсточник: {url}')
#                 result_parts.append(f'\n{preview}\n')
#             result = '\n'.join(result_parts)

#         logger.info('rag_search_complete', documents_count=len(documents))

#         return {
#             'tool_result': result,
#             'metadata': {
#                 **state.get('metadata', {}),
#                 'handler': 'rag',
#                 'documents_count': len(documents),
#             },
#         }

#     except Exception as e:
#         return create_error_response(e, 'Ошибка поиска. Попробуйте переформулировать запрос.')


def conversation_node(state: HybridState) -> dict:
    """Узел: Разговорный ответ."""
    from langgraph_app.agent.llm import get_llm_for_conversation

    agent_config = get_agent_config()
    query = get_last_user_message(state)
    chat_history = get_chat_history(state, max_messages=agent_config.memory.context_window_size)

    logger.info('hybrid_node', node='conversation', query=query[:100])

    llm = get_llm_for_conversation()

    messages = [
        HumanMessage(content="""[SYSTEM] Ты — дружелюбный городской помощник Санкт-Петербурга.
Помогаешь жителям с информацией о госуслугах, МФЦ и городских сервисах.
Отвечай кратко и вежливо.""")
    ]

    # Добавляем историю
    for msg in chat_history:
        if isinstance(msg, BaseMessage):
            messages.append(HumanMessage(content=f'[{msg.type.upper()}] {msg.content}'))

    messages.append(HumanMessage(content=query))

    try:
        response = llm.invoke(messages)
        result = response.content

        logger.info('conversation_complete', response_length=len(result))

        return {
            'tool_result': result,
            'metadata': {**state.get('metadata', {}), 'handler': 'conversation'},
        }

    except Exception as e:
        return create_error_response(e, 'Ошибка обработки. Попробуйте позже.')


def generate_response_node(state: HybridState) -> dict:
    """Узел: Финальная генерация ответа."""
    tool_result = state.get('tool_result') or state.get('final_response') or ''
    # Защита от None
    if tool_result is None:
        tool_result = 'Извините, не удалось обработать запрос.'

    logger.info('hybrid_node', node='generate_response', result_length=len(tool_result))

    return create_ai_response(tool_result)


def toxic_response_node(state: HybridState) -> dict:
    """Узел для ответа на токсичный запрос."""
    response = state.get('toxicity_response') or 'Извините, я не могу обработать этот запрос.'
    return create_ai_response(response)


# =============================================================================
# Router Functions
# =============================================================================


def toxicity_router(state: HybridState) -> str:
    """Роутер после проверки токсичности."""
    if state.get('is_toxic', False):
        return 'toxic'
    return 'safe'


def intent_router(state: HybridState) -> str:
    """Роутер по намерению."""
    intent = state.get('intent', '')

    if intent == HybridIntent.TOOL_AGENT.value:
        return 'tool_agent'
    elif intent == HybridIntent.RAG_SEARCH.value:
        return 'rag'
    elif intent == HybridIntent.CONVERSATION.value:
        return 'conversation'
    else:
        return 'rag'  # fallback


# =============================================================================
# Graph Builder
# =============================================================================


def create_hybrid_graph(checkpointer=None):
    """
    Создаёт Hybrid Agent Graph.

    Args:
        checkpointer: Optional checkpointer для персистентности.
                      Если None — граф работает in-memory.

    Returns:
        Скомпилированный граф
    """
    from langgraph_app.agent.resilience import get_api_retry_policy, get_llm_retry_policy

    logger.info('hybrid_graph_build_start', with_checkpointer=checkpointer is not None)

    builder = StateGraph(HybridState)

    # Retry policies
    llm_retry = get_llm_retry_policy()
    api_retry = get_api_retry_policy()

    # Узлы с retry policies
    builder.add_node('check_toxicity', check_toxicity_node)  # Без retry
    builder.add_node('toxic_response', toxic_response_node)  # Без retry
    builder.add_node('classify_intent', classify_intent_node)  # Без retry - только keywords
    builder.add_node('tool_agent', tool_agent_node, retry_policy=api_retry)  # ReAct + API
    # builder.add_node('rag_search', rag_search_node, retry_policy=llm_retry)  # RAG pipeline
    builder.add_node('conversation', conversation_node, retry_policy=llm_retry)  # LLM
    builder.add_node('generate_response', generate_response_node)  # Без retry

    # Рёбра — начинаем сразу с check_toxicity
    builder.add_edge(START, 'check_toxicity')

    builder.add_conditional_edges(
        'check_toxicity',
        toxicity_router,
        {'toxic': 'toxic_response', 'safe': 'classify_intent'},
    )

    builder.add_edge('toxic_response', END)

    builder.add_conditional_edges(
        'classify_intent',
        intent_router,
        {'tool_agent': 'tool_agent', 'rag': 'rag_search', 'conversation': 'conversation'},
    )

    builder.add_edge('tool_agent', 'generate_response')
    # builder.add_edge('rag_search', 'generate_response')
    builder.add_edge('conversation', 'generate_response')

    builder.add_edge('generate_response', END)

    # Компилируем с checkpointer если передан
    graph = builder.compile(checkpointer=checkpointer)

    logger.info(
        'hybrid_graph_build_complete',
        nodes=list(graph.nodes.keys()),
        with_checkpointer=checkpointer is not None,
    )

    return graph


# =============================================================================
# Cache & Convenience Functions
# =============================================================================

# Кэш для Hybrid Graph (по типу: in-memory / persistent)
_hybrid_graph_cache: dict[str, object] = {}


def get_hybrid_graph(with_persistence: bool = False):
    """
    Возвращает singleton Hybrid Graph.

    Args:
        with_persistence: Если True, создаёт граф с SqliteSaver для персистентности

    Returns:
        Скомпилированный граф
    """
    cache_key = 'persistent' if with_persistence else 'memory'

    if cache_key not in _hybrid_graph_cache:
        checkpointer = None
        if with_persistence:
            from langgraph_app.agent.persistent_memory import get_checkpointer

            checkpointer = get_checkpointer()

        _hybrid_graph_cache[cache_key] = create_hybrid_graph(checkpointer=checkpointer)

    return _hybrid_graph_cache[cache_key]


def invoke_hybrid(
    query: str,
    session_id: str = 'default',
    chat_history: list[BaseMessage] | None = None,
    with_persistence: bool = False,
) -> tuple[str, dict]:
    """
    Вызывает Hybrid Agent Graph.

    Args:
        query: Запрос пользователя
        session_id: ID сессии (thread_id для checkpointer)
        chat_history: История диалога (добавляется в messages)
        with_persistence: Использовать персистентную память

    Returns:
        Кортеж (ответ, метаданные)
    """
    graph = get_hybrid_graph(with_persistence=with_persistence)

    # Формируем messages: история + текущий запрос
    messages: list[BaseMessage] = []
    if chat_history:
        messages.extend(chat_history)
    messages.append(HumanMessage(content=query))

    # Initial state с default values
    initial_state = {
        'messages': messages,
        'is_toxic': False,
        'toxicity_response': None,
        'intent': '',
        'intent_confidence': 0.0,
        'tool_result': None,
        'final_response': None,
        'metadata': {},
        'extracted_params': {},
    }

    logger.info(
        'hybrid_invoke_start',
        query=query[:100],
        session_id=session_id,
        with_persistence=with_persistence,
    )

    # Если с персистентностью — передаём thread_id в config
    config = {'configurable': {'thread_id': session_id}} if with_persistence else {}
    result = graph.invoke(initial_state, config=config)

    response = result.get('final_response', 'Извините, не удалось обработать запрос.')
    metadata = result.get('metadata', {})

    logger.info(
        'hybrid_invoke_complete',
        response_length=len(response),
        intent=result.get('intent'),
        handler=metadata.get('handler'),
    )

    return response, metadata

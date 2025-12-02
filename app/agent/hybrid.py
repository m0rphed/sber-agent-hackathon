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
from typing import TypedDict

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import create_react_agent

from app.logging_config import get_logger

logger = get_logger(__name__)


# =============================================================================
# Enums & Constants
# =============================================================================


class HybridIntent(str, Enum):
    """Типы намерений для гибридного агента."""

    TOOL_AGENT = 'tool_agent'  # Требует ReAct агента с tools
    RAG_SEARCH = 'rag_search'  # Поиск по госуслугам
    CONVERSATION = 'conversation'  # Обычный разговор


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


class HybridState(TypedDict):
    """Состояние гибридного графа."""

    # Входные данные
    query: str
    session_id: str
    chat_history: list[BaseMessage]

    # Toxicity
    is_toxic: bool
    toxicity_response: str | None

    # Intent
    intent: str
    intent_confidence: float

    # Результаты
    tool_result: str | None
    final_response: str | None

    # Метаданные
    metadata: dict


# =============================================================================
# Node Functions
# =============================================================================


def check_toxicity_node(state: HybridState) -> dict:
    """Узел 1: Проверка токсичности."""
    from app.services.toxicity import get_toxicity_filter

    query = state['query']
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


def classify_intent_node(state: HybridState) -> dict:
    """Узел 2: Классификация намерения (упрощённая для гибрида)."""
    query = state['query'].lower()

    logger.info('hybrid_node', node='classify_intent', query=query[:100])

    # Простая классификация по ключевым словам
    detected_intent = HybridIntent.RAG_SEARCH  # default

    for intent, keywords in HYBRID_INTENT_KEYWORDS.items():
        for keyword in keywords:
            if keyword in query:
                detected_intent = intent
                break
        if detected_intent != HybridIntent.RAG_SEARCH:
            break

    logger.info('intent_classified', intent=detected_intent.value, method='keywords')

    return {
        'intent': detected_intent.value,
        'intent_confidence': 0.8,
        'metadata': {**state.get('metadata', {}), 'classification_method': 'keywords'},
    }


def tool_agent_node(state: HybridState) -> dict:
    """
    Узел: ReAct агент с API tools.

    Использует полноценный ReAct агент из langgraph.prebuilt для обработки
    запросов, требующих вызова API (МФЦ, пенсионеры и т.д.)
    """
    from app.agent.llm import get_llm
    from app.agent.resilience import create_error_state_update
    from app.tools.city_tools import ALL_TOOLS as API_TOOLS

    query = state['query']
    chat_history = state.get('chat_history', [])

    logger.info('hybrid_node', node='tool_agent', query=query[:100])

    try:
        llm = get_llm(temperature=0.3)

        # Используем create_react_agent из langgraph.prebuilt
        # Это создаёт готовый граф с ReAct логикой
        react_agent = create_react_agent(
            model=llm,
            tools=API_TOOLS,
            prompt="""Ты — городской помощник Санкт-Петербурга.
У тебя есть доступ к API для поиска МФЦ и услуг для пенсионеров.
Используй инструменты для ответа на вопросы пользователя.
Отвечай кратко и по делу на русском языке.""",
        )

        # Формируем сообщения для агента
        messages = []
        for msg in chat_history[-4:]:  # Последние 4 сообщения
            messages.append(msg)
        messages.append(HumanMessage(content=query))

        # Вызываем агента с ограничением рекурсии
        result = react_agent.invoke(
            {'messages': messages},
            config={'recursion_limit': 5},
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
        logger.error('tool_agent_error', error=str(e), exc_info=True)
        error_update = create_error_state_update(e, handler='tool_agent')
        error_update['metadata'] = {**state.get('metadata', {}), **error_update['metadata']}
        return error_update


def rag_search_node(state: HybridState) -> dict:
    """Узел: RAG поиск (использует существующий RAG Graph)."""
    from app.agent.resilience import create_error_state_update
    from app.rag.graph import search_with_graph

    query = state['query']

    logger.info('hybrid_node', node='rag_search', query=query[:100])

    try:
        documents, metadata = search_with_graph(
            query=query,
            k=5,
            min_relevant=2,
            use_toxicity_check=False,  # Уже проверили
        )

        if not documents:
            result = 'К сожалению, не удалось найти информацию по вашему запросу.'
        else:
            result_parts = ['Вот что я нашёл:\n']
            for i, doc in enumerate(documents, 1):
                title = doc.metadata.get('title', 'Документ')
                url = doc.metadata.get('url', '')
                preview = doc.page_content[:300] + '...' if len(doc.page_content) > 300 else doc.page_content
                result_parts.append(f'\n**{i}. {title}**')
                if url:
                    result_parts.append(f'\nИсточник: {url}')
                result_parts.append(f'\n{preview}\n')
            result = '\n'.join(result_parts)

        logger.info('rag_search_complete', documents_count=len(documents))

        return {
            'tool_result': result,
            'metadata': {
                **state.get('metadata', {}),
                'handler': 'rag',
                'documents_count': len(documents),
            },
        }

    except Exception as e:
        logger.error('rag_search_error', error=str(e), exc_info=True)
        error_update = create_error_state_update(e, handler='rag')
        error_update['metadata'] = {**state.get('metadata', {}), **error_update['metadata']}
        return error_update


def conversation_node(state: HybridState) -> dict:
    """Узел: Разговорный ответ."""
    from app.agent.llm import get_llm
    from app.agent.resilience import create_error_state_update

    query = state['query']
    chat_history = state.get('chat_history', [])

    logger.info('hybrid_node', node='conversation', query=query[:100])

    llm = get_llm(temperature=0.7, max_tokens=512)

    messages = [
        HumanMessage(content="""[SYSTEM] Ты — дружелюбный городской помощник Санкт-Петербурга.
Помогаешь жителям с информацией о госуслугах, МФЦ и городских сервисах.
Отвечай кратко и вежливо.""")
    ]

    for msg in chat_history[-6:]:
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
        logger.error('conversation_error', error=str(e), exc_info=True)
        error_update = create_error_state_update(e, handler='conversation')
        error_update['metadata'] = {**state.get('metadata', {}), **error_update['metadata']}
        return error_update


def generate_response_node(state: HybridState) -> dict:
    """Узел: Финальная генерация ответа."""
    tool_result = state.get('tool_result', '')

    logger.info('hybrid_node', node='generate_response')

    return {
        'final_response': tool_result,
        'metadata': {**state.get('metadata', {}), 'response_generated': True},
    }


def toxic_response_node(state: HybridState) -> dict:
    """Узел для ответа на токсичный запрос."""
    return {
        'final_response': state.get('toxicity_response', 'Извините, я не могу обработать этот запрос.'),
    }


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


def create_hybrid_graph():
    """
    Создаёт Hybrid Agent Graph.

    Returns:
        Скомпилированный граф
    """
    from app.agent.resilience import get_api_retry_policy, get_llm_retry_policy

    logger.info('hybrid_graph_build_start')

    builder = StateGraph(HybridState)

    # Retry policies
    llm_retry = get_llm_retry_policy()
    api_retry = get_api_retry_policy()

    # Узлы с retry policies
    builder.add_node('check_toxicity', check_toxicity_node)  # Без retry
    builder.add_node('toxic_response', toxic_response_node)  # Без retry
    builder.add_node('classify_intent', classify_intent_node)  # Без retry - только keywords
    builder.add_node('tool_agent', tool_agent_node, retry_policy=api_retry)  # ReAct + API
    builder.add_node('rag_search', rag_search_node, retry_policy=llm_retry)  # RAG pipeline
    builder.add_node('conversation', conversation_node, retry_policy=llm_retry)  # LLM
    builder.add_node('generate_response', generate_response_node)  # Без retry

    # Рёбра
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
    builder.add_edge('rag_search', 'generate_response')
    builder.add_edge('conversation', 'generate_response')

    builder.add_edge('generate_response', END)

    graph = builder.compile()

    logger.info('hybrid_graph_build_complete', nodes=list(graph.nodes.keys()))

    return graph


# =============================================================================
# Cache & Convenience Functions
# =============================================================================

_hybrid_graph = None


def get_hybrid_graph():
    """Возвращает кэшированный Hybrid Graph."""
    global _hybrid_graph
    if _hybrid_graph is None:
        _hybrid_graph = create_hybrid_graph()
    return _hybrid_graph


def invoke_hybrid(
    query: str,
    session_id: str = 'default',
    chat_history: list[BaseMessage] | None = None,
) -> tuple[str, dict]:
    """
    Вызывает Hybrid Agent Graph.

    Args:
        query: Запрос пользователя
        session_id: ID сессии
        chat_history: История диалога

    Returns:
        Кортеж (ответ, метаданные)
    """
    graph = get_hybrid_graph()

    initial_state: HybridState = {
        'query': query,
        'session_id': session_id,
        'chat_history': chat_history or [],
        'is_toxic': False,
        'toxicity_response': None,
        'intent': '',
        'intent_confidence': 0.0,
        'tool_result': None,
        'final_response': None,
        'metadata': {},
    }

    logger.info('hybrid_invoke_start', query=query[:100], session_id=session_id)

    result = graph.invoke(initial_state)

    response = result.get('final_response', 'Извините, не удалось обработать запрос.')
    metadata = result.get('metadata', {})

    logger.info(
        'hybrid_invoke_complete',
        response_length=len(response),
        intent=result.get('intent'),
        handler=metadata.get('handler'),
    )

    return response, metadata


# =============================================================================
# CLI для тестирования
# =============================================================================


if __name__ == '__main__':
    import os

    os.environ['LOG_LEVEL'] = 'INFO'
    from app.logging_config import configure_logging

    configure_logging()

    test_queries = [
        'Привет!',
        'Где ближайший МФЦ к Невскому проспекту 1?',
        'Какие услуги есть для пенсионеров?',
        'Как получить загранпаспорт?',
        'Ты идиот!',
        'Спасибо!',
    ]

    print('\n' + '=' * 70)
    print('ТЕСТИРОВАНИЕ HYBRID AGENT GRAPH')
    print('=' * 70)

    for query in test_queries:
        print(f"\n{'─' * 70}")
        print(f'Запрос: {query}')
        print('─' * 70)

        response, meta = invoke_hybrid(query)

        print(f'Handler: {meta.get("handler", "N/A")}')
        print(f'Ответ: {response[:200]}{"..." if len(response) > 200 else ""}')

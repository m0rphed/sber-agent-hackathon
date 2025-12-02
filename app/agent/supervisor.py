"""
Supervisor Graph - унифицированный агент с роутингом.

Архитектура:
    START → check_toxicity → classify_intent → [router]
                                                  ↓
                        ┌─────────────────────────┼─────────────────────────┐
                        ↓                         ↓                         ↓
                  api_handler              rag_search                 conversation
                  (MFC, пенсионеры)        (госуслуги)               (chitchat)
                        ↓                         ↓                         ↓
                        └─────────────────────────┼─────────────────────────┘
                                                  ↓
                                           generate_response → END

Преимущества:
- Явный роутинг через intent classification
- Меньше API вызовов (не нужен ReAct для каждого запроса)
- Полный контроль над потоком данных
- Чистая визуализация и трейсинг
"""

from enum import Enum
from typing import Any, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import END, START, StateGraph

from app.logging_config import get_logger

logger = get_logger(__name__)


# =============================================================================
# Enums & Constants
# =============================================================================


class Intent(str, Enum):
    """Типы намерений пользователя."""

    MFC_SEARCH = 'mfc_search'  # Поиск МФЦ
    PENSIONER_CATEGORIES = 'pensioner_categories'  # Категории для пенсионеров
    PENSIONER_SERVICES = 'pensioner_services'  # Услуги для пенсионеров
    RAG_SEARCH = 'rag_search'  # Поиск по госуслугам
    CONVERSATION = 'conversation'  # Обычный разговор
    UNKNOWN = 'unknown'  # Неизвестное намерение


# Ключевые слова для простой классификации (fallback)
INTENT_KEYWORDS = {
    Intent.MFC_SEARCH: [
        'мфц',
        'многофункциональный центр',
        'ближайший мфц',
        'адрес мфц',
        'где мфц',
        'часы работы мфц',
        'время работы мфц',
        'телефон мфц',
    ],
    Intent.PENSIONER_CATEGORIES: [
        'категории для пенсионеров',
        'какие услуги для пенсионеров',
        'список категорий пенсионер',
        'виды услуг пенсионер',
    ],
    Intent.PENSIONER_SERVICES: [
        'услуги для пенсионеров',
        'занятия для пенсионеров',
        'кружки для пенсионеров',
        'пенсионер район',
        'секции для пожилых',
        'курсы для пенсионеров',
    ],
    Intent.RAG_SEARCH: [
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
        'компенсация',
        'сертификат',
        'удостоверение',
        'свидетельство',
        'лицензия',
        'разрешение',
        'порядок оформления',
        'срок получения',
        'стоимость услуги',
        'госпошлина',
    ],
    Intent.CONVERSATION: [
        'привет',
        'здравствуй',
        'добрый день',
        'добрый вечер',
        'доброе утро',
        'спасибо',
        'благодарю',
        'пока',
        'до свидания',
        'как дела',
        'кто ты',
        'что ты умеешь',
        'помоги',
        'помощь',
        'что ты можешь',
    ],
}


# =============================================================================
# State Definition
# =============================================================================


class SupervisorState(TypedDict):
    """
    Состояние Supervisor графа.

    Передаётся между всеми узлами.
    """

    # Входные данные
    query: str  # Исходный запрос пользователя
    session_id: str  # ID сессии для памяти
    chat_history: list[BaseMessage]  # История диалога

    # Toxicity
    is_toxic: bool
    toxicity_response: str | None

    # Intent classification
    intent: str  # Intent enum value
    intent_confidence: float
    extracted_params: dict[str, Any]  # Извлечённые параметры (адрес, район и т.д.)

    # Результаты обработки
    tool_result: str | None  # Результат вызова tool/RAG
    final_response: str | None  # Финальный ответ пользователю

    # Метаданные
    metadata: dict


# =============================================================================
# Node Functions
# =============================================================================


def check_toxicity_node(state: SupervisorState) -> dict:
    """
    Узел 1: Проверка токсичности запроса.
    """
    from app.services.toxicity import get_toxicity_filter

    query = state['query']

    logger.info('supervisor_node', node='check_toxicity', query_length=len(query))

    toxicity_filter = get_toxicity_filter()
    result = toxicity_filter.check(query)

    if result.should_block:
        response = toxicity_filter.get_response(result)
        logger.warning(
            'toxicity_blocked',
            level=result.level.value,
            patterns_count=len(result.matched_patterns),
        )
        return {
            'is_toxic': True,
            'toxicity_response': response,
            'metadata': {**state.get('metadata', {}), 'toxicity_blocked': True},
        }

    logger.debug('toxicity_passed')
    return {
        'is_toxic': False,
        'toxicity_response': None,
        'metadata': {**state.get('metadata', {}), 'toxicity_blocked': False},
    }


def classify_intent_node(state: SupervisorState) -> dict:
    """
    Узел 2: Классификация намерения пользователя.

    Использует LLM для точной классификации и извлечения параметров.
    """
    from app.agent.llm import get_llm

    query = state['query'].lower()

    logger.info('supervisor_node', node='classify_intent', query=query[:100])

    # Сначала пробуем простую классификацию по ключевым словам
    detected_intent = _keyword_classification(query)

    if detected_intent != Intent.UNKNOWN:
        logger.info(
            'intent_classified',
            method='keywords',
            intent=detected_intent.value,
        )
        return {
            'intent': detected_intent.value,
            'intent_confidence': 0.8,
            'extracted_params': _extract_params_simple(query, detected_intent),
            'metadata': {**state.get('metadata', {}), 'classification_method': 'keywords'},
        }

    # Если не удалось - используем LLM
    llm = get_llm(temperature=0.0, max_tokens=256)

    classification_prompt = f"""Ты - классификатор намерений пользователя для городского помощника Санкт-Петербурга.

Категории:
1. mfc_search - пользователь ищет МФЦ (многофункциональный центр), адрес МФЦ, часы работы МФЦ
2. pensioner_categories - пользователь спрашивает о категориях услуг для пенсионеров
3. pensioner_services - пользователь ищет конкретные услуги/занятия для пенсионеров в районе
4. rag_search - вопросы о госуслугах, документах, процедурах оформления, льготах, справках
5. conversation - приветствия, благодарности, общие вопросы о боте, прощания

Запрос пользователя: "{state['query']}"

Ответь ОДНИМ словом - название категории (mfc_search, pensioner_categories, pensioner_services, rag_search или conversation):"""

    try:
        response = llm.invoke(classification_prompt)
        content = response.content
        # Обработка разных типов content
        if isinstance(content, list):
            content = str(content[0]) if content else ''
        intent_str = content.strip().lower()

        # Маппинг ответа LLM на Intent
        intent_map = {
            'mfc_search': Intent.MFC_SEARCH,
            'pensioner_categories': Intent.PENSIONER_CATEGORIES,
            'pensioner_services': Intent.PENSIONER_SERVICES,
            'rag_search': Intent.RAG_SEARCH,
            'conversation': Intent.CONVERSATION,
        }

        detected_intent = intent_map.get(intent_str, Intent.RAG_SEARCH)

        logger.info(
            'intent_classified',
            method='llm',
            intent=detected_intent.value,
            llm_response=intent_str,
        )

        return {
            'intent': detected_intent.value,
            'intent_confidence': 0.9,
            'extracted_params': _extract_params_simple(query, detected_intent),
            'metadata': {**state.get('metadata', {}), 'classification_method': 'llm'},
        }

    except Exception as e:
        logger.error('intent_classification_failed', error=str(e))
        # Fallback на RAG
        return {
            'intent': Intent.RAG_SEARCH.value,
            'intent_confidence': 0.5,
            'extracted_params': {},
            'metadata': {**state.get('metadata', {}), 'classification_method': 'fallback'},
        }


def _keyword_classification(query: str) -> Intent:
    """Простая классификация по ключевым словам."""
    query_lower = query.lower()

    for intent, keywords in INTENT_KEYWORDS.items():
        for keyword in keywords:
            if keyword in query_lower:
                return intent

    return Intent.UNKNOWN


def _extract_params_simple(query: str, intent: Intent) -> dict:
    """Извлечение параметров из запроса (простая версия)."""
    params = {}

    if intent == Intent.MFC_SEARCH:
        # Пытаемся найти адрес в запросе
        # Упрощённая логика - просто берём часть после "около", "рядом с", "у"
        for marker in ['около ', 'рядом с ', 'у ', 'возле ', 'на ']:
            if marker in query.lower():
                idx = query.lower().find(marker)
                params['address'] = query[idx + len(marker) :].strip()
                break

    elif intent == Intent.PENSIONER_SERVICES:
        # Ищем район
        districts = [
            'адмиралтейский',
            'василеостровский',
            'выборгский',
            'калининский',
            'кировский',
            'колпинский',
            'красногвардейский',
            'красносельский',
            'кронштадтский',
            'курортный',
            'московский',
            'невский',
            'петроградский',
            'петродворцовый',
            'приморский',
            'пушкинский',
            'фрунзенский',
            'центральный',
        ]
        for district in districts:
            if district in query.lower():
                params['district'] = district.capitalize()
                break

    return params


# =============================================================================
# Handler Nodes
# =============================================================================


def api_handler_node(state: SupervisorState) -> dict:
    """
    Узел: Обработка API запросов (МФЦ, пенсионеры).
    """
    from app.agent.resilience import create_error_state_update

    intent = state['intent']
    params = state.get('extracted_params', {})

    logger.info('supervisor_node', node='api_handler', intent=intent, params=params)

    try:
        if intent == Intent.MFC_SEARCH.value:
            result = _handle_mfc_search(params)
        elif intent == Intent.PENSIONER_CATEGORIES.value:
            result = _handle_pensioner_categories()
        elif intent == Intent.PENSIONER_SERVICES.value:
            result = _handle_pensioner_services(params)
        else:
            result = 'Не удалось определить тип запроса к API.'

        logger.info('api_handler_complete', result_length=len(result))
        return {
            'tool_result': result,
            'metadata': {**state.get('metadata', {}), 'handler': 'api'},
        }

    except Exception as e:
        logger.error('api_handler_error', error=str(e), exc_info=True)
        # Используем resilience для graceful error handling
        error_update = create_error_state_update(e, handler='api')
        # Сохраняем существующие метаданные
        error_update['metadata'] = {**state.get('metadata', {}), **error_update['metadata']}
        return error_update


def _handle_mfc_search(params: dict) -> str:
    """Поиск ближайшего МФЦ."""
    from app.tools.city_tools import find_nearest_mfc_tool

    address = params.get('address', '')

    if not address:
        return (
            'Для поиска ближайшего МФЦ укажите, пожалуйста, ваш адрес. '
            'Например: "Найди МФЦ рядом с Невским проспектом 1"'
        )

    return find_nearest_mfc_tool.invoke(address)


def _handle_pensioner_categories() -> str:
    """Получение категорий услуг для пенсионеров."""
    from app.tools.city_tools import get_pensioner_categories_tool

    return get_pensioner_categories_tool.invoke({})


def _handle_pensioner_services(params: dict) -> str:
    """Поиск услуг для пенсионеров."""
    from app.tools.city_tools import get_pensioner_services_tool

    district = params.get('district', '')

    if not district:
        return (
            'Для поиска услуг для пенсионеров укажите район. '
            'Например: "Какие занятия для пенсионеров есть в Невском районе?"'
        )

    # По умолчанию ищем все категории
    return get_pensioner_services_tool.invoke({'district': district, 'categories': ''})


def rag_search_node(state: SupervisorState) -> dict:
    """
    Узел: Поиск по RAG (база знаний госуслуг).
    """
    from app.agent.resilience import create_error_state_update
    from app.rag.graph import search_with_graph

    query = state['query']

    logger.info('supervisor_node', node='rag_search', query=query[:100])

    try:
        # Используем существующий RAG Graph (без toxicity check, т.к. уже проверили)
        documents, metadata = search_with_graph(
            query=query,
            k=5,
            min_relevant=2,
            use_toxicity_check=False,  # Уже проверили в supervisor
        )

        if not documents:
            result = 'К сожалению, не удалось найти информацию по вашему запросу в базе знаний.'
        else:
            # Форматируем результаты
            result_parts = ['Вот что я нашёл по вашему запросу:\n']
            for i, doc in enumerate(documents, 1):
                title = doc.metadata.get('title', 'Документ')
                url = doc.metadata.get('url', '')
                content_preview = doc.page_content[:300] + '...' if len(doc.page_content) > 300 else doc.page_content

                result_parts.append(f'\n**{i}. {title}**')
                if url:
                    result_parts.append(f'\nИсточник: {url}')
                result_parts.append(f'\n{content_preview}\n')

            result = '\n'.join(result_parts)

        logger.info('rag_search_complete', documents_count=len(documents))
        return {
            'tool_result': result,
            'metadata': {
                **state.get('metadata', {}),
                'handler': 'rag',
                'documents_count': len(documents),
                'rag_metadata': metadata,
            },
        }

    except Exception as e:
        logger.error('rag_search_error', error=str(e), exc_info=True)
        error_update = create_error_state_update(e, handler='rag')
        error_update['metadata'] = {**state.get('metadata', {}), **error_update['metadata']}
        return error_update


def conversation_node(state: SupervisorState) -> dict:
    """
    Узел: Обработка разговорных запросов.
    """
    from app.agent.llm import get_llm
    from app.agent.resilience import create_error_state_update

    query = state['query']
    chat_history = state.get('chat_history', [])

    logger.info('supervisor_node', node='conversation', query=query[:100])

    llm = get_llm(temperature=0.7, max_tokens=512)

    # Формируем контекст с историей
    messages = []

    # System prompt
    system_message = """Ты — дружелюбный городской помощник Санкт-Петербурга.
Ты помогаешь жителям города с информацией о госуслугах, МФЦ и городских сервисах.
Отвечай кратко, вежливо и по делу. Если не знаешь ответ — честно скажи об этом."""

    messages.append(HumanMessage(content=f'[SYSTEM] {system_message}'))

    # Добавляем историю (последние 6 сообщений)
    for msg in chat_history[-6:]:
        if isinstance(msg, BaseMessage):
            messages.append(HumanMessage(content=f'[{msg.type.upper()}] {msg.content}'))
        else:
            messages.append(HumanMessage(content=str(msg)))

    # Текущий вопрос
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


def generate_response_node(state: SupervisorState) -> dict:
    """
    Узел: Финальная генерация ответа.

    Может использовать LLM для улучшения ответа или просто передать tool_result.
    """
    tool_result = state.get('tool_result', '')
    intent = state.get('intent', '')

    logger.info('supervisor_node', node='generate_response', intent=intent)

    # Для разговорных запросов - ответ уже готов
    if intent == Intent.CONVERSATION.value:
        return {'final_response': tool_result}

    # Для API и RAG - можно добавить вежливое обрамление
    # Пока просто возвращаем результат
    return {
        'final_response': tool_result,
        'metadata': {**state.get('metadata', {}), 'response_generated': True},
    }


# =============================================================================
# Router Functions
# =============================================================================


def toxicity_router(state: SupervisorState) -> str:
    """Роутер после проверки токсичности."""
    if state.get('is_toxic', False):
        return 'toxic'
    return 'safe'


def intent_router(state: SupervisorState) -> str:
    """Роутер по намерению пользователя."""
    intent = state.get('intent', Intent.UNKNOWN.value)

    if intent in [Intent.MFC_SEARCH.value, Intent.PENSIONER_CATEGORIES.value, Intent.PENSIONER_SERVICES.value]:
        return 'api'
    elif intent == Intent.RAG_SEARCH.value:
        return 'rag'
    elif intent == Intent.CONVERSATION.value:
        return 'conversation'
    else:
        # Fallback на RAG
        return 'rag'


# =============================================================================
# Toxic Response Node
# =============================================================================


def toxic_response_node(state: SupervisorState) -> dict:
    """Узел для ответа на токсичный запрос."""
    return {
        'final_response': state.get('toxicity_response', 'Извините, я не могу обработать этот запрос.'),
    }


# =============================================================================
# Graph Builder
# =============================================================================


def create_supervisor_graph(checkpointer=None):
    """
    Создаёт Supervisor Graph.

    Args:
        checkpointer: Optional checkpointer для персистентности.
                      Если None — граф работает in-memory.

    Returns:
        Скомпилированный граф
    """
    from app.agent.resilience import get_api_retry_policy, get_llm_retry_policy

    logger.info('supervisor_graph_build_start', with_checkpointer=checkpointer is not None)

    builder = StateGraph(SupervisorState)

    # Retry policies для разных типов узлов
    llm_retry = get_llm_retry_policy()
    api_retry = get_api_retry_policy()

    # Добавляем узлы с retry policies
    builder.add_node('check_toxicity', check_toxicity_node)  # Без retry - локальная логика
    builder.add_node('toxic_response', toxic_response_node)  # Без retry - просто возврат
    builder.add_node('classify_intent', classify_intent_node, retry_policy=llm_retry)  # LLM вызов
    builder.add_node('api_handler', api_handler_node, retry_policy=api_retry)  # Внешние API
    builder.add_node('rag_search', rag_search_node, retry_policy=llm_retry)  # LLM + embeddings
    builder.add_node('conversation', conversation_node, retry_policy=llm_retry)  # LLM вызов
    builder.add_node('generate_response', generate_response_node)  # Без retry - форматирование

    # Рёбра
    builder.add_edge(START, 'check_toxicity')

    # После toxicity check
    builder.add_conditional_edges(
        'check_toxicity',
        toxicity_router,
        {
            'toxic': 'toxic_response',
            'safe': 'classify_intent',
        },
    )

    builder.add_edge('toxic_response', END)

    # После классификации intent
    builder.add_conditional_edges(
        'classify_intent',
        intent_router,
        {
            'api': 'api_handler',
            'rag': 'rag_search',
            'conversation': 'conversation',
        },
    )

    # Все обработчики идут к generate_response
    builder.add_edge('api_handler', 'generate_response')
    builder.add_edge('rag_search', 'generate_response')
    builder.add_edge('conversation', 'generate_response')

    builder.add_edge('generate_response', END)

    # Компилируем с checkpointer если передан
    graph = builder.compile(checkpointer=checkpointer)

    logger.info(
        'supervisor_graph_build_complete',
        nodes=list(graph.nodes.keys()),
        with_checkpointer=checkpointer is not None,
    )

    return graph


# =============================================================================
# Convenience Functions
# =============================================================================

# Кэш для Supervisor Graph (по типу: in-memory / persistent)
_supervisor_graph_cache: dict[str, object] = {}


def get_supervisor_graph(with_persistence: bool = False):
    """
    Возвращает singleton Supervisor Graph.

    Args:
        with_persistence: Если True, создаёт граф с SqliteSaver для персистентности

    Returns:
        Скомпилированный граф
    """
    cache_key = 'persistent' if with_persistence else 'memory'

    if cache_key not in _supervisor_graph_cache:
        checkpointer = None
        if with_persistence:
            from app.agent.persistent_memory import get_checkpointer

            checkpointer = get_checkpointer()

        _supervisor_graph_cache[cache_key] = create_supervisor_graph(checkpointer=checkpointer)

    return _supervisor_graph_cache[cache_key]


def invoke_supervisor(
    query: str,
    session_id: str = 'default',
    chat_history: list[BaseMessage] | None = None,
    with_persistence: bool = False,
) -> tuple[str, dict]:
    """
    Вызывает Supervisor Graph.

    Args:
        query: Запрос пользователя
        session_id: ID сессии (thread_id для checkpointer)
        chat_history: История диалога (игнорируется при with_persistence=True)
        with_persistence: Использовать персистентную память

    Returns:
        Кортеж (ответ, метаданные)
    """
    graph = get_supervisor_graph(with_persistence=with_persistence)

    initial_state: SupervisorState = {
        'query': query,
        'session_id': session_id,
        'chat_history': chat_history or [],
        'is_toxic': False,
        'toxicity_response': None,
        'intent': '',
        'intent_confidence': 0.0,
        'extracted_params': {},
        'tool_result': None,
        'final_response': None,
        'metadata': {},
    }

    logger.info(
        'supervisor_invoke_start',
        query=query[:100],
        session_id=session_id,
        with_persistence=with_persistence,
    )

    # Если с персистентностью — передаём thread_id в config
    if with_persistence:
        config = {'configurable': {'thread_id': session_id}}
        result = graph.invoke(initial_state, config=config)
    else:
        result = graph.invoke(initial_state)

    response = result.get('final_response', 'Извините, не удалось обработать запрос.')
    metadata = result.get('metadata', {})

    logger.info(
        'supervisor_invoke_complete',
        response_length=len(response),
        intent=result.get('intent'),
        metadata=metadata,
    )

    return response, metadata


# =============================================================================
# CLI для тестирования
# =============================================================================


if __name__ == '__main__':
    import os

    os.environ['LOG_LEVEL'] = 'DEBUG'
    from app.logging_config import configure_logging

    configure_logging()

    test_queries = [
        'Привет!',
        'Где ближайший МФЦ к Невскому проспекту 1?',
        'Какие услуги есть для пенсионеров?',
        'Как получить загранпаспорт?',
        'Ты идиот!',  # токсичный
        'Спасибо за помощь!',
    ]

    print('\n' + '=' * 70)
    print('ТЕСТИРОВАНИЕ SUPERVISOR GRAPH')
    print('=' * 70)

    for query in test_queries:
        print(f"\n{'─' * 70}")
        print(f'Запрос: {query}')
        print('─' * 70)

        response, meta = invoke_supervisor(query)

        print(f'Intent: {meta.get("handler", "N/A")}')
        print(f'Ответ: {response[:200]}{"..." if len(response) > 200 else ""}')

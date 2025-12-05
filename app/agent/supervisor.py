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
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import END, START, StateGraph

from app.agent.state import (
    AgentState,
    create_ai_response,
    create_error_response,
    get_chat_history,
    get_last_user_message,
)
from app.config import get_agent_config
from app.logging_config import get_logger
from app.rag.config import get_rag_config
from prompts import load_prompt

logger = get_logger(__name__)


# =============================================================================
# Enums & Constants
# =============================================================================


# Максимальное количество попыток уточнения
MAX_CLARIFICATION_ATTEMPTS = 2

# Загружаем prompt для conversation fallback
CONVERSATION_SYSTEM_PROMPT = load_prompt("conversation.txt")


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


class SupervisorState(AgentState):
    """
    Состояние Supervisor графа.

    Наследует от AgentState (MessagesState + общие поля).
    Добавляет специфичные для Supervisor поля.
    """

    # Supervisor-specific: извлечённые параметры
    extracted_params: dict[str, Any]  # Адрес, район, категория и т.д.

    # Clarification loop
    needs_clarification: bool  # True если нужно уточнение
    clarification_message: str | None  # Сообщение для уточнения
    clarification_attempts: int  # Счётчик попыток уточнения


# =============================================================================
# Node Functions
# =============================================================================


def check_toxicity_node(state: SupervisorState) -> dict:
    """
    Узел 1: Проверка токсичности запроса.
    """
    from app.services.toxicity import get_toxicity_filter

    query = get_last_user_message(state)

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
    Узел 2: Классификация намерения пользователя с Structured Output.

    Использует Pydantic модель CityQueryClassification для точной классификации
    и извлечения сущностей (адрес, район, категория).
    """
    from app.agent.intent_classifier import (
        classify_intent_structured,
        check_required_slots,
        get_clarification_message,
        to_legacy_intent,
        to_legacy_params,
    )

    query = get_last_user_message(state)

    logger.info('supervisor_node', node='classify_intent', query=query[:100])

    try:
        # Используем structured classification
        classification = classify_intent_structured(query)

        # Проверяем, нужно ли уточнение
        if classification.needs_clarification or not check_required_slots(classification):
            clarification_msg = (
                classification.clarification_message
                or get_clarification_message(classification)
            )
            logger.info(
                'clarification_needed',
                intent=classification.intent,
                message=clarification_msg,
            )
            return {
                'intent': 'clarification',
                'intent_confidence': classification.confidence,
                'extracted_params': to_legacy_params(classification),
                'clarification_message': clarification_msg,
                'metadata': {
                    **state.get('metadata', {}),
                    'classification_method': 'structured',
                    'original_intent': classification.intent,
                },
            }

        # Всё хорошо — возвращаем результат
        logger.info(
            'intent_classified',
            method='structured',
            intent=classification.intent,
            confidence=classification.confidence,
            address=classification.address,
            district=classification.district,
        )

        return {
            'intent': to_legacy_intent(classification.intent),
            'intent_confidence': classification.confidence,
            'extracted_params': to_legacy_params(classification),
            'metadata': {
                **state.get('metadata', {}),
                'classification_method': 'structured',
                'new_intent': classification.intent,
            },
        }

    except Exception as e:
        logger.error('intent_classification_failed', error=str(e), exc_info=True)
        # Fallback на keyword classification
        detected_intent = _keyword_classification(query)
        if detected_intent == Intent.UNKNOWN:
            detected_intent = Intent.RAG_SEARCH

        return {
            'intent': detected_intent.value,
            'intent_confidence': 0.5,
            'extracted_params': _extract_params_simple(query, detected_intent),
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
    Узел: Обработка API запросов (все городские сервисы).

    Использует tool_dispatcher для централизованного вызова tools.
    """
    from app.agent.resilience import create_error_state_update
    from app.agent.tool_dispatcher import handle_api_intent

    intent = state['intent']
    params = state.get('extracted_params', {})

    logger.info('supervisor_node', node='api_handler', intent=intent, params=params)

    try:
        # Единый dispatch через tool_dispatcher
        result, needs_clarification = handle_api_intent(intent, params)

        if needs_clarification:
            # Возвращаем запрос на уточнение
            return {
                'needs_clarification': True,
                'clarification_message': result,
                'tool_result': None,
                'metadata': {**state.get('metadata', {}), 'handler': 'api', 'needs_clarification': True},
            }

        logger.info('api_handler_complete', result_length=len(result))
        return {
            'tool_result': result,
            'metadata': {**state.get('metadata', {}), 'handler': 'api'},
        }

    except Exception as e:
        logger.error('api_handler_error', error=str(e), exc_info=True)
        error_update = create_error_state_update(e, handler='api')
        error_update['metadata'] = {**state.get('metadata', {}), **error_update['metadata']}
        return error_update


def rag_search_node(state: SupervisorState) -> dict:
    """
    Узел: Поиск по RAG (база знаний госуслуг).
    """
    from app.rag.graph import search_with_graph

    query = get_last_user_message(state)
    rag_config = get_rag_config()

    logger.info('supervisor_node', node='rag_search', query=query[:100])

    try:
        # Используем существующий RAG Graph (без toxicity check, т.к. уже проверили)
        documents, metadata = search_with_graph(
            query=query,
            k=rag_config.search.k,
            min_relevant=rag_config.search.min_relevant,
            use_toxicity_check=False,  # Уже проверили в supervisor
        )

        if not documents:
            result = 'К сожалению, не удалось найти информацию по вашему запросу в базе знаний.'
        else:
            # Форматируем результаты
            result_parts = ['Вот что я нашёл по вашему запросу:\n']
            content_limit = rag_config.search.content_preview_limit
            for i, doc in enumerate(documents, 1):
                title = doc.metadata.get('title', 'Документ')
                url = doc.metadata.get('url', '')
                content_preview = doc.page_content[:content_limit] + '...' if len(doc.page_content) > content_limit else doc.page_content

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
        return create_error_response(e, 'Ошибка поиска. Попробуйте переформулировать запрос.')


def conversation_node(state: SupervisorState) -> dict:
    """
    Узел: Обработка разговорных запросов.
    """
    from app.agent.llm import get_llm_for_conversation

    query = get_last_user_message(state)
    chat_history = get_chat_history(state)
    agent_config = get_agent_config()

    logger.info('supervisor_node', node='conversation', query=query[:100])

    llm = get_llm_for_conversation()

    # Формируем контекст с историей
    messages = []

    # System prompt из файла
    messages.append(HumanMessage(content=f'[SYSTEM] {CONVERSATION_SYSTEM_PROMPT}'))

    # Добавляем историю (последние N сообщений из конфига)
    context_size = agent_config.memory.context_window_size
    for msg in chat_history[-context_size:]:
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
        return create_error_response(e, 'Ошибка обработки. Попробуйте позже.')


def generate_response_node(state: SupervisorState) -> dict:
    """
    Узел: Финальная генерация ответа.

    Может использовать LLM для улучшения ответа или просто передать tool_result.
    """
    tool_result = state.get('tool_result') or ''
    intent = state.get('intent', '')

    logger.info('supervisor_node', node='generate_response', intent=intent)

    # Защита от None
    if tool_result is None:
        tool_result = 'Извините, не удалось обработать запрос.'

    return create_ai_response(tool_result)


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

    # Новый intent: уточнение
    if intent == 'clarification':
        return 'clarification'

    # API intents (legacy + новые)
    api_intents = [
        Intent.MFC_SEARCH.value,
        Intent.PENSIONER_CATEGORIES.value,
        Intent.PENSIONER_SERVICES.value,
        # Новые intents которые тоже идут в api_handler
        'search_mfc',
        'search_polyclinic',
        'search_school',
        'search_kindergarten',
        'search_management_company',
        'pet_parks',
        'vet_clinics',
        'road_works',
        'beautiful_places',
        'tourist_routes',
        'sportgrounds',
        'disconnections',
        'search_events',
        'search_sport_events',
        'pensioner_categories',
        'pensioner_services',
        'memorable_dates',
        'district_info',
    ]

    if intent in api_intents:
        return 'api'
    elif intent == Intent.RAG_SEARCH.value or intent == 'rag_search':
        return 'rag'
    elif intent == Intent.CONVERSATION.value or intent == 'conversation':
        return 'conversation'
    else:
        # Fallback на RAG
        return 'rag'


def clarification_node(state: SupervisorState) -> dict:
    """
    Узел для запроса уточнения у пользователя.

    Инкрементирует счётчик попыток и возвращает уточняющий вопрос.
    Граф ожидает следующего сообщения пользователя и снова классифицирует.
    """
    from langchain_core.messages import AIMessage

    clarification_msg = state.get('clarification_message', 'Уточните, пожалуйста, ваш запрос.')
    current_attempts = state.get('clarification_attempts', 0)
    new_attempts = current_attempts + 1

    logger.info(
        'clarification_requested',
        message=clarification_msg,
        attempt=new_attempts,
        max_attempts=MAX_CLARIFICATION_ATTEMPTS,
    )

    # Добавляем AI сообщение в историю (чтобы пользователь видел вопрос)
    return {
        'messages': [AIMessage(content=clarification_msg)],
        'clarification_attempts': new_attempts,
        'needs_clarification': True,
        'tool_result': clarification_msg,
        'metadata': {
            **state.get('metadata', {}),
            'handler': 'clarification',
            'clarification_attempt': new_attempts,
        },
    }


# =============================================================================
# Toxic Response Node
# =============================================================================


def toxic_response_node(state: SupervisorState) -> dict:
    """Узел для ответа на токсичный запрос."""
    response = state.get('toxicity_response') or 'Извините, я не могу обработать этот запрос.'
    return create_ai_response(response)


def clarification_router(state: SupervisorState) -> str:
    """
    Роутер после узла clarification.

    Определяет, продолжить ли цикл уточнения или завершить.
    """
    attempts = state.get('clarification_attempts', 0)

    if attempts >= MAX_CLARIFICATION_ATTEMPTS:
        # Достигли лимита попыток — идём в conversation для fallback ответа
        logger.warning(
            'clarification_max_attempts_reached',
            attempts=attempts,
            max=MAX_CLARIFICATION_ATTEMPTS,
        )
        return 'max_attempts'

    # Ещё есть попытки — возвращаемся к classify_intent (ждём ответ пользователя)
    return 'continue'


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
    builder.add_node('clarification', clarification_node)  # Без retry - просто возврат сообщения
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
            'clarification': 'clarification',
        },
    )

    # Все обработчики идут к generate_response
    builder.add_edge('api_handler', 'generate_response')
    builder.add_edge('rag_search', 'generate_response')
    builder.add_edge('conversation', 'generate_response')

    # Clarification loop: после уточнения либо ждём новый запрос, либо fallback
    builder.add_conditional_edges(
        'clarification',
        clarification_router,
        {
            'continue': END,  # Ждём следующего сообщения пользователя
            'max_attempts': 'conversation',  # Fallback на conversation
        },
    )

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
        chat_history: История диалога (добавляется в messages)
        with_persistence: Использовать персистентную память

    Returns:
        Кортеж (ответ, метаданные)
    """
    graph = get_supervisor_graph(with_persistence=with_persistence)

    # Формируем messages: история + текущий запрос
    messages: list[BaseMessage] = []
    if chat_history:
        messages.extend(chat_history)
    messages.append(HumanMessage(content=query))

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
        # Clarification loop
        'needs_clarification': False,
        'clarification_message': None,
        'clarification_attempts': 0,
    }

    logger.info(
        'supervisor_invoke_start',
        query=query[:100],
        session_id=session_id,
        with_persistence=with_persistence,
    )

    # Если с персистентностью — передаём thread_id в config
    config = {'configurable': {'thread_id': session_id}} if with_persistence else {}
    result = graph.invoke(initial_state, config=config)

    response = result.get('final_response') or 'Извините, не удалось обработать запрос.'
    metadata = result.get('metadata', {})

    logger.info(
        'supervisor_invoke_complete',
        response_length=len(response) if response else 0,
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

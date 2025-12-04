"""
Supervisor Graph - унифицированный агент с роутингом.

Архитектура:
    START → check_toxicity → classify_intent → [router]
                                                  ↓
                        ┌─────────────────────────┼─────────────────────────┐
                        ↓                         ↓                         ↓
                  api_handler              rag_search                 conversation
                  (городские сервисы)      (госуслуги)               (chitchat)
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
from typing import Any, Literal

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

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

logger = get_logger(__name__)


# =============================================================================
# Enums & Constants
# =============================================================================


class IntentLLMOutput(BaseModel):
    """Структура ответа от LLM-роутера для Supervisor."""

    intent: Literal[
        # Адресные сервисы
        'mfc_search',
        'polyclinic_by_address',
        'schools_by_address',
        'management_company_by_address',
        'district_info_by_address',
        'disconnections_by_address',
        # Районы
        'mfc_list_by_district',
        'kindergartens',
        'sport_events',
        'sport_categories_by_district',
        'sportgrounds',
        'sportgrounds_count',
        # Глобальные списки/афиша/история
        'districts_list',
        'city_events',
        'event_categories',
        'memorable_dates_today',
        # Пенсионеры
        'pensioner_categories',
        'pensioner_services',
        # Базовые
        'rag_search',
        'conversation',
    ]
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


# Порог уверенности: ниже этого лучше уходить в RAG как в безопасный fallback
INTENT_CONFIDENCE_THRESHOLD: float = 0.6

# Сколько последних сообщений истории отдаём роутеру
INTENT_HISTORY_MESSAGES: int = 4


class Intent(str, Enum):
    """
    Типы намерений пользователя.

    Адресные сервисы (нужен конкретный адрес):
    - MFC_SEARCH                    — поиск ближайшего МФЦ по адресу
    - POLYCLINIC_BY_ADDRESS         — поликлиники по адресу
    - SCHOOLS_BY_ADDRESS            — школы, прикреплённые к дому
    - MANAGEMENT_COMPANY_BY_ADDRESS — управляющая компания дома
    - DISTRICT_INFO_BY_ADDRESS      — справка по району по адресу
    - DISCONNECTIONS_BY_ADDRESS     — отключения воды/электричества по адресу

    Районные сервисы (нужен район):
    - MFC_LIST_BY_DISTRICT          — список МФЦ в районе
    - KINDERGARTENS                 — детские сады в районе
    - SPORT_EVENTS                  — спортивные мероприятия в районе
    - SPORT_CATEGORIES_BY_DISTRICT  — виды спорта в районе
    - SPORTGROUNDS                  — спортплощадки (опционально по району)
    - SPORTGROUNDS_COUNT            — количество спортплощадок (город/район)

    Городская информация:
    - DISTRICTS_LIST                — список районов
    - CITY_EVENTS                   — городская афиша
    - EVENT_CATEGORIES              — категории мероприятий
    - MEMORABLE_DATES_TODAY         — памятные даты сегодня

    Пенсионеры:
    - PENSIONER_CATEGORIES          — категории услуг для пенсионеров
    - PENSIONER_SERVICES            — услуги для пенсионеров в районе

    Базовые:
    - RAG_SEARCH                    — поиск по базе знаний госуслуг
    - CONVERSATION                  — обычный разговор / small talk
    - UNKNOWN                       — неизвестное намерение
    """

    # Адресные
    MFC_SEARCH = 'mfc_search'
    POLYCLINIC_BY_ADDRESS = 'polyclinic_by_address'
    SCHOOLS_BY_ADDRESS = 'schools_by_address'
    MANAGEMENT_COMPANY_BY_ADDRESS = 'management_company_by_address'
    DISTRICT_INFO_BY_ADDRESS = 'district_info_by_address'
    DISCONNECTIONS_BY_ADDRESS = 'disconnections_by_address'

    # Районы
    MFC_LIST_BY_DISTRICT = 'mfc_list_by_district'
    KINDERGARTENS = 'kindergartens'
    SPORT_EVENTS = 'sport_events'
    SPORT_CATEGORIES_BY_DISTRICT = 'sport_categories_by_district'
    SPORTGROUNDS = 'sportgrounds'
    SPORTGROUNDS_COUNT = 'sportgrounds_count'

    # Город
    DISTRICTS_LIST = 'districts_list'
    CITY_EVENTS = 'city_events'
    EVENT_CATEGORIES = 'event_categories'
    MEMORABLE_DATES_TODAY = 'memorable_dates_today'

    # Пенсионеры
    PENSIONER_CATEGORIES = 'pensioner_categories'
    PENSIONER_SERVICES = 'pensioner_services'

    # Базовые
    RAG_SEARCH = 'rag_search'
    CONVERSATION = 'conversation'
    UNKNOWN = 'unknown'


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


def _classify_intent_with_llm(
    query: str,
    history: list[BaseMessage],
) -> IntentLLMOutput | None:
    """
    Классификация намерения с помощью LLM-роутера (тот же, что в Hybrid-графе).
    """
    try:
        from textwrap import dedent
        from langchain_core.prompts import ChatPromptTemplate
        from app.agent.llm import get_llm_for_intent_routing

        llm = get_llm_for_intent_routing().with_structured_output(IntentLLMOutput)

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    'system',
                    dedent(
                        """\
                        Ты — классификатор намерений городского помощника Санкт-Петербурга.

                        Твоя задача — по диалогу и последнему сообщению пользователя выбрать,
                        какой обработчик нужно вызвать.

                        Категории intent (кратко):

                        Адресные сервисы:
                        - "mfc_search" — ближайший МФЦ по адресу.
                        - "polyclinic_by_address" — поликлиники по адресу.
                        - "schools_by_address" — школы, прикреплённые к дому.
                        - "management_company_by_address" — управляющая компания дома.
                        - "district_info_by_address" — справка по району по адресу.
                        - "disconnections_by_address" — отключения воды/света по адресу.

                        Районные сервисы:
                        - "mfc_list_by_district" — список МФЦ в районе.
                        - "kindergartens" — детские сады в районе.
                        - "sport_events" — спортивные мероприятия (обычно с районом).
                        - "sport_categories_by_district" — виды спорта в районе.
                        - "sportgrounds" — спортплощадки города/района.
                        - "sportgrounds_count" — количество спортплощадок.

                        Городская информация:
                        - "districts_list" — список районов города.
                        - "city_events" — афиша мероприятий.
                        - "event_categories" — категории мероприятий.
                        - "memorable_dates_today" — памятные даты сегодня.

                        Пенсионеры:
                        - "pensioner_categories" — общие категории услуг для пенсионеров.
                        - "pensioner_services" — конкретные занятия/услуги для пенсионеров в районе.

                        Базовые:
                        - "rag_search" — если вопрос про оформление документов, льготы, порядок действий,
                          требования, госпошлины и т.п. (формальные госуслуги).
                        - "conversation" — приветствия, благодарности, small talk, вопросы о самом боте.

                        Всегда возвращай СТРОГИЙ JSON со следующими полями:
                        - intent: одно из перечисленных значений
                        - confidence: число от 0 до 1 (насколько ты уверен)
                        - reason: короткое объяснение, почему выбран именно этот intent.
                        """
                    ),
                ),
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
                'last_message': query,
            }
        )
        return result

    except Exception as e:
        logger.exception('intent_llm_failed', error=str(e))
        return None


def classify_intent_node(state: SupervisorState) -> dict:
    """
    Узел 2: Классификация намерения пользователя.

    Использует LLM-роутер со структурированным выводом.
    При любой ошибке LLM — безопасный fallback в RAG.
    """
    query_raw = get_last_user_message(state)
    logger.info('supervisor_node', node='classify_intent', query=query_raw[:100])

    # История для контекста
    chat_history = get_chat_history(state, max_messages=INTENT_HISTORY_MESSAGES)

    # Значения по умолчанию (безопасный fallback)
    detected_intent: Intent = Intent.RAG_SEARCH
    confidence: float = 0.5
    reason: str = 'llm_error_or_parse_failed'
    method: str = 'fallback'

    llm_result = _classify_intent_with_llm(query_raw, chat_history)

    if llm_result is not None:
        # Пробуем замапить строку на Enum Intent
        intent_map: dict[str, Intent] = {
            # Адресные
            'mfc_search': Intent.MFC_SEARCH,
            'polyclinic_by_address': Intent.POLYCLINIC_BY_ADDRESS,
            'schools_by_address': Intent.SCHOOLS_BY_ADDRESS,
            'management_company_by_address': Intent.MANAGEMENT_COMPANY_BY_ADDRESS,
            'district_info_by_address': Intent.DISTRICT_INFO_BY_ADDRESS,
            'disconnections_by_address': Intent.DISCONNECTIONS_BY_ADDRESS,
            # Районы
            'mfc_list_by_district': Intent.MFC_LIST_BY_DISTRICT,
            'kindergartens': Intent.KINDERGARTENS,
            'sport_events': Intent.SPORT_EVENTS,
            'sport_categories_by_district': Intent.SPORT_CATEGORIES_BY_DISTRICT,
            'sportgrounds': Intent.SPORTGROUNDS,
            'sportgrounds_count': Intent.SPORTGROUNDS_COUNT,
            # Город
            'districts_list': Intent.DISTRICTS_LIST,
            'city_events': Intent.CITY_EVENTS,
            'event_categories': Intent.EVENT_CATEGORIES,
            'memorable_dates_today': Intent.MEMORABLE_DATES_TODAY,
            # Пенсионеры
            'pensioner_categories': Intent.PENSIONER_CATEGORIES,
            'pensioner_services': Intent.PENSIONER_SERVICES,
            # Базовые
            'rag_search': Intent.RAG_SEARCH,
            'conversation': Intent.CONVERSATION,
        }
        detected_intent = intent_map.get(llm_result.intent, Intent.RAG_SEARCH)
        confidence = float(llm_result.confidence)
        reason = llm_result.reason
        method = 'llm'

        # Если уверенность низкая — отправляем в RAG как самый безопасный обработчик
        if confidence < INTENT_CONFIDENCE_THRESHOLD:
            detected_intent = Intent.RAG_SEARCH
            method = 'llm_low_confidence'

    extracted_params = _extract_params_simple(query_raw, detected_intent)

    logger.info(
        'intent_classified',
        method=method,
        intent=detected_intent.value,
        confidence=confidence,
        reason=reason,
        extracted_params=extracted_params,
    )

    return {
        'intent': detected_intent.value,
        'intent_confidence': confidence,
        'extracted_params': extracted_params,
        'metadata': {
            **state.get('metadata', {}),
            'classification_method': method,
            'intent_reason': reason,
        },
    }


def _extract_params_simple(query: str, intent: Intent) -> dict:
    """Извлечение параметров из запроса (простая версия, не для классификации)."""
    params: dict[str, Any] = {}

    query_lower = query.lower()

    # Набор intent-ов, где нам нужен адрес
    address_intents = {
        Intent.MFC_SEARCH,
        Intent.POLYCLINIC_BY_ADDRESS,
        Intent.SCHOOLS_BY_ADDRESS,
        Intent.MANAGEMENT_COMPANY_BY_ADDRESS,
        Intent.DISTRICT_INFO_BY_ADDRESS,
        Intent.DISCONNECTIONS_BY_ADDRESS,
    }

    # Набор intent-ов, где нам нужен район
    district_intents = {
        Intent.MFC_LIST_BY_DISTRICT,
        Intent.KINDERGARTENS,
        Intent.SPORT_EVENTS,
        Intent.SPORT_CATEGORIES_BY_DISTRICT,
        Intent.SPORTGROUNDS,
        Intent.SPORTGROUNDS_COUNT,
        Intent.PENSIONER_SERVICES,
    }

    if intent in address_intents:
        # Упрощённая логика — берём текст после маркера "около/рядом/у/возле/на"
        for marker in ['около ', 'рядом с ', 'у ', 'возле ', 'на ']:
            if marker in query_lower:
                idx = query_lower.find(marker)
                params['address'] = query[idx + len(marker):].strip()
                break
        # Если маркер не найден — можно в будущем добавить более умный парсер;
        # сейчас просто оставляем address пустым и хендлер сам попросит уточнить.

    if intent in district_intents:
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
            if district in query_lower:
                params['district'] = district.capitalize()
                break

    # Для событий/спорта можно в будущем вытаскивать категорию, бесплатность и т.п.
    # Пока оставляем это на дефолты в хендлерах.

    return params


# =============================================================================
# Handler Nodes
# =============================================================================


def api_handler_node(state: SupervisorState) -> dict:
    """
    Узел: Обработка API запросов (городские сервисы).
    """
    from app.agent.resilience import create_error_state_update

    intent = state['intent']
    params = state.get('extracted_params', {})

    logger.info('supervisor_node', node='api_handler', intent=intent, params=params)

    try:
        if intent == Intent.MFC_SEARCH.value:
            result = _handle_mfc_search(params)
        elif intent == Intent.POLYCLINIC_BY_ADDRESS.value:
            result = _handle_polyclinic_by_address(params)
        elif intent == Intent.SCHOOLS_BY_ADDRESS.value:
            result = _handle_schools_by_address(params)
        elif intent == Intent.MANAGEMENT_COMPANY_BY_ADDRESS.value:
            result = _handle_management_company_by_address(params)
        elif intent == Intent.DISTRICT_INFO_BY_ADDRESS.value:
            result = _handle_district_info_by_address(params)
        elif intent == Intent.DISCONNECTIONS_BY_ADDRESS.value:
            result = _handle_disconnections_by_address(params)

        elif intent == Intent.MFC_LIST_BY_DISTRICT.value:
            result = _handle_mfc_list_by_district(params)
        elif intent == Intent.KINDERGARTENS.value:
            result = _handle_kindergartens(params)
        elif intent == Intent.SPORT_EVENTS.value:
            result = _handle_sport_events(params)
        elif intent == Intent.SPORT_CATEGORIES_BY_DISTRICT.value:
            result = _handle_sport_categories_by_district(params)
        elif intent == Intent.SPORTGROUNDS.value:
            result = _handle_sportgrounds(params)
        elif intent == Intent.SPORTGROUNDS_COUNT.value:
            result = _handle_sportgrounds_count(params)

        elif intent == Intent.DISTRICTS_LIST.value:
            result = _handle_districts_list()
        elif intent == Intent.CITY_EVENTS.value:
            result = _handle_city_events()
        elif intent == Intent.EVENT_CATEGORIES.value:
            result = _handle_event_categories()
        elif intent == Intent.MEMORABLE_DATES_TODAY.value:
            result = _handle_memorable_dates_today()

        elif intent == Intent.PENSIONER_CATEGORIES.value:
            result = _handle_pensioner_categories()
        elif intent == Intent.PENSIONER_SERVICES.value:
            result = _handle_pensioner_services(params)

        else:
            result = 'Не удалось определить тип запроса к городским сервисам.'

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


# ==========================
# Отдельные хендлеры
# ==========================


def _handle_mfc_search(params: dict) -> str:
    """Поиск ближайшего МФЦ по адресу."""
    from app.tools.city_tools_v2 import find_nearest_mfc_v2

    address = params.get('address', '')

    if not address:
        return (
            'Для поиска ближайшего МФЦ укажите, пожалуйста, ваш адрес. '
            'Например: "Найди МФЦ рядом с Невским проспектом 1".'
        )

    return find_nearest_mfc_v2.invoke(address)


def _handle_polyclinic_by_address(params: dict) -> str:
    """Поликлиники по адресу."""
    from app.tools.city_tools_v2 import get_polyclinics_by_address_v2

    address = params.get('address', '')

    if not address:
        return (
            'Чтобы найти поликлинику по вашему адресу, укажите полный адрес. '
            'Например: "Моя поликлиника по адресу Невский проспект 100".'
        )

    return get_polyclinics_by_address_v2.invoke(address)


def _handle_schools_by_address(params: dict) -> str:
    """Школы, прикреплённые к дому по адресу."""
    from app.tools.city_tools_v2 import get_linked_schools_by_address_v2

    address = params.get('address', '')

    if not address:
        return (
            'Чтобы найти школы, прикреплённые к вашему дому, укажите адрес. '
            'Например: "К какой школе прикреплён дом по адресу Ленинский проспект 50?".'
        )

    return get_linked_schools_by_address_v2.invoke(address)


def _handle_management_company_by_address(params: dict) -> str:
    """Управляющая компания по адресу дома."""
    from app.tools.city_tools_v2 import get_management_company_by_address_v2

    address = params.get('address', '')

    if not address:
        return (
            'Чтобы узнать управляющую компанию, укажите адрес дома. '
            'Например: "Какая УК у дома по адресу Проспект Ветеранов 75?".'
        )

    return get_management_company_by_address_v2.invoke(address)


def _handle_district_info_by_address(params: dict) -> str:
    """Справочная информация о районе по адресу."""
    from app.tools.city_tools_v2 import get_district_info_by_address_v2

    address = params.get('address', '')

    if not address:
        return (
            'Чтобы получить информацию по району, укажите адрес. '
            'Например: "Полезные телефоны для района по адресу Бухарестская 100".'
        )

    return get_district_info_by_address_v2.invoke(address)


def _handle_disconnections_by_address(params: dict) -> str:
    """Отключения воды/электричества по адресу."""
    from app.tools.city_tools_v2 import get_disconnections_by_address_v2

    address = params.get('address', '')

    if not address:
        return (
            'Чтобы проверить отключения по вашему дому, укажите адрес. '
            'Например: "Будут ли отключения воды по адресу Комендантский проспект 12?".'
        )

    return get_disconnections_by_address_v2.invoke(address)


def _handle_mfc_list_by_district(params: dict) -> str:
    """Список МФЦ в районе."""
    from app.tools.city_tools_v2 import get_mfc_list_by_district_v2

    district = params.get('district', '')

    if not district:
        return (
            'Для получения списка МФЦ укажите район. '
            'Например: "Список МФЦ в Невском районе".'
        )

    return get_mfc_list_by_district_v2.invoke(district)


def _handle_kindergartens(params: dict) -> str:
    """Детские сады в районе (по умолчанию возраст ~3 года)."""
    from app.tools.city_tools_v2 import get_kindergartens_v2

    district = params.get('district', '')

    if not district:
        return (
            'Для поиска детских садов укажите район. '
            'Например: "Детские сады в Приморском районе".'
        )

    # Пока используем дефолтный возраст 3 года
    return get_kindergartens_v2.invoke({'district': district, 'age_years': 3, 'age_months': 0})


def _handle_sport_events(params: dict) -> str:
    """Спортивные мероприятия (опционально по району)."""
    from app.tools.city_tools_v2 import get_sport_events_v2

    district = params.get('district', '')
    # Можно добавить фильтры (категория, ОВЗ, семейный час) через более умный парсинг
    payload: dict[str, Any] = {}
    if district:
        payload['district'] = district

    return get_sport_events_v2.invoke(payload or {})


def _handle_sport_categories_by_district(params: dict) -> str:
    """Виды спорта, доступные в районе."""
    from app.tools.city_tools_v2 import get_sport_categories_by_district_v2

    district = params.get('district', '')

    if not district:
        return (
            'Чтобы узнать виды спорта в районе, укажите его. '
            'Например: "Какие виды спорта есть в Калининском районе?".'
        )

    return get_sport_categories_by_district_v2.invoke(district)


def _handle_sportgrounds_count(params: dict) -> str:
    """Количество спортплощадок в городе или районе."""
    from app.tools.city_tools_v2 import get_sportgrounds_count_v2

    district = params.get('district', '')
    return get_sportgrounds_count_v2.invoke({'district': district} if district else {})


def _handle_sportgrounds(params: dict) -> str:
    """Список спортплощадок (город/район)."""
    from app.tools.city_tools_v2 import get_sportgrounds_v2

    district = params.get('district', '')
    # Пока не вытаскиваем виды спорта из текста
    payload: dict[str, Any] = {
        'district': district or '',
        'sport_types': '',
        'count': 10,
    }
    return get_sportgrounds_v2.invoke(payload)


def _handle_districts_list() -> str:
    """Список районов города."""
    from app.tools.city_tools_v2 import get_districts_list

    return get_districts_list.invoke({})


def _handle_city_events() -> str:
    """Городская афиша мероприятий (несколько дней вперёд)."""
    from app.tools.city_tools_v2 import get_city_events_v2

    # Дефолт: 7 дней вперёд, без фильтров
    return get_city_events_v2.invoke({'days_ahead': 7, 'category': '', 'free_only': False, 'for_kids': False})


def _handle_event_categories() -> str:
    """Категории мероприятий в афише."""
    from app.tools.city_tools_v2 import get_event_categories_v2

    return get_event_categories_v2.invoke({})


def _handle_memorable_dates_today() -> str:
    """Памятные даты в истории города на сегодня."""
    from app.tools.city_tools_v2 import get_memorable_dates_today_v2

    return get_memorable_dates_today_v2.invoke({})


def _handle_pensioner_categories() -> str:
    """Категории услуг для пенсионеров (программа 'Долголетие')."""
    from app.tools.city_tools_v2 import get_pensioner_service_categories_v2

    return get_pensioner_service_categories_v2.invoke({})


def _handle_pensioner_services(params: dict) -> str:
    """Поиск услуг для пенсионеров в районе."""
    from app.tools.city_tools_v2 import get_pensioner_services_v2

    district = params.get('district', '')

    if not district:
        return (
            'Для поиска услуг для пенсионеров укажите район. '
            'Например: "Какие занятия для пенсионеров есть в Невском районе?".'
        )

    # По умолчанию ищем все категории
    payload = {'district': district, 'category': ''}
    return get_pensioner_services_v2.invoke(payload)


# =============================================================================
# RAG, conversation, generate_response — без изменений
# =============================================================================


def rag_search_node(state: SupervisorState) -> dict:
    """
    Узел: Поиск по RAG (база знаний госуслуг).
    """
    from app.rag.graph import search_with_graph

    query = get_last_user_message(state)
    rag_config = get_rag_config()

    logger.info('supervisor_node', node='rag_search', query=query[:100])

    try:
        documents, metadata = search_with_graph(
            query=query,
            k=rag_config.search.k,
            min_relevant=rag_config.search.min_relevant,
            use_toxicity_check=False,
        )

        if not documents:
            result = 'К сожалению, не удалось найти информацию по вашему запросу в базе знаний.'
        else:
            result_parts = ['Вот что я нашёл по вашему запросу:\n']
            content_limit = rag_config.search.content_preview_limit
            for i, doc in enumerate(documents, 1):
                title = doc.metadata.get('title', 'Документ')
                url = doc.metadata.get('url', '')
                content_preview = (
                    doc.page_content[:content_limit] + '...'
                    if len(doc.page_content) > content_limit
                    else doc.page_content
                )

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

    messages = []

    system_message = """Ты — дружелюбный городской помощник Санкт-Петербурга.
Ты помогаешь жителям города с информацией о госуслугах, МФЦ и городских сервисах.
Отвечай кратко, вежливо и по делу. Если не знаешь ответ — честно скажи об этом."""

    messages.append(HumanMessage(content=f'[SYSTEM] {system_message}'))

    context_size = agent_config.memory.context_window_size
    for msg in chat_history[-context_size:]:
        if isinstance(msg, BaseMessage):
            messages.append(HumanMessage(content=f'[{msg.type.upper()}] {msg.content}'))
        else:
            messages.append(HumanMessage(content=str(msg)))

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
    """
    tool_result = state.get('tool_result') or ''
    intent = state.get('intent', '')

    logger.info('supervisor_node', node='generate_response', intent=intent)

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

    api_intents = {
        # Адресные
        Intent.MFC_SEARCH.value,
        Intent.POLYCLINIC_BY_ADDRESS.value,
        Intent.SCHOOLS_BY_ADDRESS.value,
        Intent.MANAGEMENT_COMPANY_BY_ADDRESS.value,
        Intent.DISTRICT_INFO_BY_ADDRESS.value,
        Intent.DISCONNECTIONS_BY_ADDRESS.value,
        # Районы
        Intent.MFC_LIST_BY_DISTRICT.value,
        Intent.KINDERGARTENS.value,
        Intent.SPORT_EVENTS.value,
        Intent.SPORT_CATEGORIES_BY_DISTRICT.value,
        Intent.SPORTGROUNDS.value,
        Intent.SPORTGROUNDS_COUNT.value,
        # Город
        Intent.DISTRICTS_LIST.value,
        Intent.CITY_EVENTS.value,
        Intent.EVENT_CATEGORIES.value,
        Intent.MEMORABLE_DATES_TODAY.value,
        # Пенсионеры
        Intent.PENSIONER_CATEGORIES.value,
        Intent.PENSIONER_SERVICES.value,
    }

    if intent in api_intents:
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
    response = state.get('toxicity_response') or 'Извините, я не могу обработать этот запрос.'
    return create_ai_response(response)


# =============================================================================
# Graph Builder
# =============================================================================


def create_supervisor_graph(checkpointer=None):
    """
    Создаёт Supervisor Graph.
    """
    from app.agent.resilience import get_api_retry_policy, get_llm_retry_policy

    logger.info('supervisor_graph_build_start', with_checkpointer=checkpointer is not None)

    builder = StateGraph(SupervisorState)

    llm_retry = get_llm_retry_policy()
    api_retry = get_api_retry_policy()

    builder.add_node('check_toxicity', check_toxicity_node)
    builder.add_node('toxic_response', toxic_response_node)
    builder.add_node('classify_intent', classify_intent_node, retry_policy=llm_retry)
    builder.add_node('api_handler', api_handler_node, retry_policy=api_retry)
    builder.add_node('rag_search', rag_search_node, retry_policy=llm_retry)
    builder.add_node('conversation', conversation_node, retry_policy=llm_retry)
    builder.add_node('generate_response', generate_response_node)

    builder.add_edge(START, 'check_toxicity')

    builder.add_conditional_edges(
        'check_toxicity',
        toxicity_router,
        {
            'toxic': 'toxic_response',
            'safe': 'classify_intent',
        },
    )

    builder.add_edge('toxic_response', END)

    builder.add_conditional_edges(
        'classify_intent',
        intent_router,
        {
            'api': 'api_handler',
            'rag': 'rag_search',
            'conversation': 'conversation',
        },
    )

    builder.add_edge('api_handler', 'generate_response')
    builder.add_edge('rag_search', 'generate_response')
    builder.add_edge('conversation', 'generate_response')

    builder.add_edge('generate_response', END)

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

_supervisor_graph_cache: dict[str, object] = {}


def get_supervisor_graph(with_persistence: bool = False):
    """
    Возвращает singleton Supervisor Graph.
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
    """
    graph = get_supervisor_graph(with_persistence=with_persistence)

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
    }

    logger.info(
        'supervisor_invoke_start',
        query=query[:100],
        session_id=session_id,
        with_persistence=with_persistence,
    )

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
        'Какая управляющая компания у дома по адресу Проспект Большевиков 68 к1?',
        'Какие спортплощадки есть в Невском районе?',
        'Памятные даты на сегодня',
        'Спасибо за помощь!',
    ]

    print('\n' + '=' * 70)
    print('ТЕСТИРОВАНИЕ SUPERVISOR GRAPH')
    print('=' * 70)

    for query in test_queries:
        print(f'\n{"─" * 70}')
        print(f'Запрос: {query}')
        print('─' * 70)

        response, meta = invoke_supervisor(query)

        print(f'Handler: {meta.get("handler", "N/A")}')
        print(f'Ответ: {response[:200]}{"..." if len(response) > 200 else ""}')

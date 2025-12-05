"""
Structured Intent Classification с Pydantic.

Использует GigaChat с with_structured_output для точной классификации
намерений и извлечения сущностей из запросов пользователя.
"""

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.logging_config import get_logger
from prompts import load_prompt, render_prompt

logger = get_logger(__name__)


# =============================================================================
# Enums
# =============================================================================


class IntentType(str, Enum):
    """Типы намерений пользователя — расширенный набор для 26 tools."""

    # Городские сервисы
    SEARCH_MFC = "search_mfc"
    SEARCH_POLYCLINIC = "search_polyclinic"
    SEARCH_SCHOOL = "search_school"
    SEARCH_KINDERGARTEN = "search_kindergarten"
    SEARCH_MANAGEMENT_COMPANY = "search_management_company"

    # Мероприятия
    SEARCH_EVENTS = "search_events"
    SEARCH_SPORT_EVENTS = "search_sport_events"

    # Питомцы
    PET_PARKS = "pet_parks"
    VET_CLINICS = "vet_clinics"

    # Инфраструктура
    ROAD_WORKS = "road_works"
    DISCONNECTIONS = "disconnections"
    SPORTGROUNDS = "sportgrounds"

    # Туризм
    BEAUTIFUL_PLACES = "beautiful_places"
    TOURIST_ROUTES = "tourist_routes"

    # Пенсионеры
    PENSIONER_CATEGORIES = "pensioner_categories"
    PENSIONER_SERVICES = "pensioner_services"

    # Прочее
    MEMORABLE_DATES = "memorable_dates"
    DISTRICT_INFO = "district_info"

    # Fallback
    RAG_SEARCH = "rag_search"
    CONVERSATION = "conversation"


# Literal для Pydantic (GigaChat не поддерживает Enum в with_structured_output)
IntentLiteral = Literal[
    # Городские сервисы
    "search_mfc",
    "search_polyclinic",
    "search_school",
    "search_kindergarten",
    "search_management_company",
    # Мероприятия
    "search_events",
    "search_sport_events",
    # Питомцы
    "pet_parks",
    "vet_clinics",
    # Инфраструктура
    "road_works",
    "disconnections",
    "sportgrounds",
    # Туризм
    "beautiful_places",
    "tourist_routes",
    # Пенсионеры
    "pensioner_categories",
    "pensioner_services",
    # Прочее
    "memorable_dates",
    "district_info",
    # Fallback
    "rag_search",
    "conversation",
]


# =============================================================================
# Pydantic Models
# =============================================================================


class CityQueryClassification(BaseModel):
    """Результат классификации городского запроса."""

    intent: IntentLiteral = Field(
        description="Тип намерения пользователя"
    )

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        default=0.8,
        description="Уверенность в классификации (0.0 - 1.0)"
    )

    # Извлечённые сущности
    address: Optional[str] = Field(
        default=None,
        description="Адрес из запроса (улица, дом). Например: 'Невский проспект 1'"
    )

    district: Optional[str] = Field(
        default=None,
        description="Район города. Например: 'Невский', 'Центральный', 'Калининский'"
    )

    category: Optional[str] = Field(
        default=None,
        description="Категория услуги/мероприятия. Например: 'Концерты', 'Йога', 'Компьютерные курсы'"
    )

    # Флаг уточнения
    needs_clarification: bool = Field(
        default=False,
        description="Требуется ли уточнение от пользователя (например, не указан адрес)"
    )

    clarification_message: Optional[str] = Field(
        default=None,
        description="Вопрос для уточнения, если needs_clarification=True"
    )


# =============================================================================
# Two-Step Classification Models
# =============================================================================


class IntentOnly(BaseModel):
    """Результат классификации только intent (шаг 1 из 2)."""

    intent: IntentLiteral = Field(
        description="Тип намерения пользователя"
    )

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        default=0.8,
        description="Уверенность в классификации (0.0 - 1.0)"
    )

    reasoning: Optional[str] = Field(
        default=None,
        description="Краткое обоснование выбора intent"
    )


class ExtractedEntities(BaseModel):
    """Извлечённые сущности из запроса (шаг 2 из 2)."""

    address: Optional[str] = Field(
        default=None,
        description="Адрес из запроса (улица, дом). Например: 'Невский проспект 1'"
    )

    district: Optional[str] = Field(
        default=None,
        description="Район города. Например: 'Невский', 'Центральный', 'Калининский'"
    )

    category: Optional[str] = Field(
        default=None,
        description="Категория услуги/мероприятия. Например: 'Концерты', 'Йога'"
    )

    needs_clarification: bool = Field(
        default=False,
        description="Требуется ли уточнение от пользователя"
    )

    clarification_message: Optional[str] = Field(
        default=None,
        description="Вопрос для уточнения, если needs_clarification=True"
    )


# =============================================================================
# Intent → Tool Mapping
# =============================================================================


INTENT_TO_TOOL_NAME: dict[str, str] = {
    "search_mfc": "find_nearest_mfc_v2",
    "search_polyclinic": "get_polyclinics_by_address_v2",
    "search_school": "get_linked_schools_by_address_v2",
    "search_kindergarten": "get_kindergartens_v2",
    "search_management_company": "get_management_company_by_address_v2",
    "pet_parks": "get_pet_parks_v2",
    "vet_clinics": "get_vet_clinics_v2",
    "road_works": "get_road_works_v2",
    "beautiful_places": "get_beautiful_places_v2",
    "tourist_routes": "get_beautiful_place_routes_v2",
    "sportgrounds": "get_sportgrounds_v2",
    "disconnections": "get_disconnections_by_address_v2",
    "search_events": "get_city_events_v2",
    "search_sport_events": "get_sport_events_v2",
    "pensioner_categories": "get_pensioner_service_categories_v2",
    "pensioner_services": "get_pensioner_services_v2",
    "memorable_dates": "get_memorable_dates_today_v2",
    "district_info": "get_district_info_by_address_v2",
}


# Какие slots (параметры) нужны для каждого intent
INTENT_REQUIRED_SLOTS: dict[str, list[str]] = {
    # Требуют адрес
    "search_mfc": ["address"],
    "search_polyclinic": ["address"],
    "search_school": ["address"],
    "search_management_company": ["address"],
    "disconnections": ["address"],
    "pet_parks": ["address"],  # или district
    "vet_clinics": ["address"],  # или district
    "sportgrounds": ["address"],  # или district

    # Требуют район
    "search_kindergarten": ["district"],
    "pensioner_services": ["district"],

    # Не требуют обязательных параметров
    "road_works": [],
    "beautiful_places": [],
    "tourist_routes": [],
    "search_events": [],
    "search_sport_events": [],
    "pensioner_categories": [],
    "memorable_dates": [],
    "district_info": [],
    "rag_search": [],
    "conversation": [],
}


# =============================================================================
# Classification Prompt
# =============================================================================

# Загружаем prompt из файла prompts/intent_classifier.txt
CLASSIFICATION_SYSTEM_PROMPT = load_prompt("intent_classifier.txt")


# =============================================================================
# Classification Function
# =============================================================================


def classify_intent_structured(
    query: str,
    model_name: str = "GigaChat-2-Max"
) -> CityQueryClassification:
    """
    Классифицирует запрос пользователя с использованием Structured Output.

    Args:
        query: Запрос пользователя
        model_name: Название модели GigaChat

    Returns:
        CityQueryClassification с intent, сущностями и флагом уточнения
    """
    from langchain_gigachat import GigaChat

    logger.info("classify_intent_structured", query=query[:100])

    try:
        llm = GigaChat(
            model=model_name,
            verify_ssl_certs=False,
            timeout=30,
        )

        # Используем with_structured_output с method="format_instructions"
        # для лучшего качества на GigaChat
        structured_llm = llm.with_structured_output(
            CityQueryClassification,
            method="format_instructions"
        )

        # Формируем промпт
        full_prompt = f"""{CLASSIFICATION_SYSTEM_PROMPT}

Запрос пользователя: "{query}"

Классифицируй запрос и извлеки сущности."""

        result = structured_llm.invoke(full_prompt)

        logger.info(
            "classification_result",
            intent=result.intent,
            confidence=result.confidence,
            address=result.address,
            district=result.district,
            needs_clarification=result.needs_clarification,
        )

        return result

    except Exception as e:
        logger.error("classification_error", error=str(e), exc_info=True)
        # Fallback на RAG
        return CityQueryClassification(
            intent="rag_search",
            confidence=0.3,
            needs_clarification=False,
        )


def check_required_slots(classification: CityQueryClassification) -> bool:
    """
    Проверяет, заполнены ли все обязательные slots для данного intent.

    Returns:
        True если все slots заполнены, False если чего-то не хватает
    """
    required = INTENT_REQUIRED_SLOTS.get(classification.intent, [])

    for slot in required:
        if slot == "address" and not classification.address:
            return False
        if slot == "district" and not classification.district:
            return False

    return True


def get_clarification_message(classification: CityQueryClassification) -> str:
    """
    Генерирует сообщение для уточнения недостающих данных.
    """
    required = INTENT_REQUIRED_SLOTS.get(classification.intent, [])

    if "address" in required and not classification.address:
        return "Для поиска укажите, пожалуйста, ваш адрес. Например: 'Невский проспект 1'"

    if "district" in required and not classification.district:
        return "Укажите, пожалуйста, район. Например: 'Невский', 'Центральный', 'Калининский'"

    return "Уточните, пожалуйста, ваш запрос."


# =============================================================================
# Legacy Compatibility
# =============================================================================


def to_legacy_intent(intent: str) -> str:
    """
    Конвертирует новый intent в legacy Intent enum value для совместимости.

    Старые значения:
    - mfc_search
    - pensioner_categories
    - pensioner_services
    - rag_search
    - conversation
    """
    legacy_map = {
        "search_mfc": "mfc_search",
        "pensioner_categories": "pensioner_categories",
        "pensioner_services": "pensioner_services",
        "rag_search": "rag_search",
        "conversation": "conversation",
    }

    # Для новых intents которых нет в legacy — используем специальные значения
    # которые api_handler_node будет обрабатывать
    return legacy_map.get(intent, intent)


def to_legacy_params(classification: CityQueryClassification) -> dict:
    """
    Конвертирует CityQueryClassification в legacy extracted_params dict.
    """
    params = {}

    if classification.address:
        params["address"] = classification.address

    if classification.district:
        params["district"] = classification.district

    if classification.category:
        params["category"] = classification.category

    return params


# =============================================================================
# Two-Step Classification (Alternative)
# =============================================================================

# Загружаем промпты из файлов
INTENT_ONLY_PROMPT = load_prompt("intent_only.txt")

# entity_extraction.jinja2 — шаблон с подстановкой, используем render_prompt


# Описания intents для контекста
INTENT_DESCRIPTIONS: dict[str, str] = {
    "search_mfc": "ближайший МФЦ (многофункциональный центр)",
    "search_polyclinic": "поликлинику или медучреждение",
    "search_school": "школу по прописке",
    "search_kindergarten": "детский сад",
    "search_management_company": "управляющую компанию",
    "pet_parks": "парк или площадку для выгула собак",
    "vet_clinics": "ветеринарную клинику",
    "road_works": "информацию о дорожных работах",
    "beautiful_places": "достопримечательности и красивые места",
    "tourist_routes": "туристические маршруты",
    "sportgrounds": "спортивные площадки",
    "disconnections": "информацию об отключениях воды/света/отопления",
    "search_events": "городские мероприятия",
    "search_sport_events": "спортивные соревнования",
    "pensioner_categories": "категории услуг для пенсионеров",
    "pensioner_services": "услуги для пенсионеров в районе",
    "memorable_dates": "памятные даты",
    "district_info": "информацию о районе",
    "rag_search": "информацию о госуслугах",
    "conversation": "общение с ботом",
}


def classify_intent_only(
    query: str,
    model_name: str = "GigaChat-2-Max"
) -> IntentOnly:
    """
    Шаг 1: Классифицирует ТОЛЬКО intent (без извлечения сущностей).

    Args:
        query: Запрос пользователя
        model_name: Название модели GigaChat

    Returns:
        IntentOnly с intent и confidence
    """
    from langchain_gigachat import GigaChat

    logger.info("classify_intent_only", query=query[:100])

    try:
        llm = GigaChat(
            model=model_name,
            verify_ssl_certs=False,
            timeout=30,
        )

        structured_llm = llm.with_structured_output(
            IntentOnly,
            method="format_instructions"
        )

        full_prompt = f"""{INTENT_ONLY_PROMPT}

Запрос пользователя: "{query}"

Определи intent."""

        result = structured_llm.invoke(full_prompt)

        logger.info(
            "intent_only_result",
            intent=result.intent,
            confidence=result.confidence,
            reasoning=result.reasoning,
        )

        return result

    except Exception as e:
        logger.error("intent_only_error", error=str(e), exc_info=True)
        return IntentOnly(
            intent="rag_search",
            confidence=0.3,
            reasoning="Ошибка классификации, fallback на RAG",
        )


def extract_entities_for_intent(
    query: str,
    intent: str,
    model_name: str = "GigaChat-2-Max"
) -> ExtractedEntities:
    """
    Шаг 2: Извлекает сущности из запроса с учётом известного intent.

    Args:
        query: Запрос пользователя
        intent: Уже определённый intent
        model_name: Название модели GigaChat

    Returns:
        ExtractedEntities с address, district, category и флагом уточнения
    """
    from langchain_gigachat import GigaChat

    logger.info("extract_entities_for_intent", query=query[:100], intent=intent)

    # Получаем описание intent и required slots
    intent_description = INTENT_DESCRIPTIONS.get(intent, "информацию")
    required_slots = INTENT_REQUIRED_SLOTS.get(intent, [])

    if required_slots:
        slots_desc = ", ".join(required_slots)
        required_slots_description = f"Для intent '{intent}' ОБЯЗАТЕЛЬНО нужен: {slots_desc}"
    else:
        required_slots_description = f"Для intent '{intent}' обязательных параметров НЕТ"

    try:
        llm = GigaChat(
            model=model_name,
            verify_ssl_certs=False,
            timeout=30,
        )

        structured_llm = llm.with_structured_output(
            ExtractedEntities,
            method="format_instructions"
        )

        # Используем jinja2 шаблон для entity extraction
        entity_prompt = render_prompt(
            "entity_extraction.jinja2",
            intent_description=intent_description,
            required_slots_description=required_slots_description,
        )

        full_prompt = entity_prompt + f"""

Запрос пользователя: "{query}"

Извлеки сущности."""

        result = structured_llm.invoke(full_prompt)

        logger.info(
            "entities_extracted",
            intent=intent,
            address=result.address,
            district=result.district,
            category=result.category,
            needs_clarification=result.needs_clarification,
        )

        return result

    except Exception as e:
        logger.error("extract_entities_error", error=str(e), exc_info=True)
        return ExtractedEntities(
            needs_clarification=False,
        )


def classify_two_step(
    query: str,
    model_name: str = "GigaChat-2-Max"
) -> CityQueryClassification:
    """
    Двухэтапная классификация: сначала intent, потом entities.

    Альтернатива classify_intent_structured() — может быть точнее
    для сложных запросов за счёт двух LLM вызовов.

    Args:
        query: Запрос пользователя
        model_name: Название модели GigaChat

    Returns:
        CityQueryClassification (такой же формат как у classify_intent_structured)
    """
    logger.info("classify_two_step_start", query=query[:100])

    # Шаг 1: Определяем intent
    intent_result = classify_intent_only(query, model_name)

    # Шаг 2: Извлекаем сущности с контекстом intent
    entities = extract_entities_for_intent(query, intent_result.intent, model_name)

    # Объединяем в CityQueryClassification
    result = CityQueryClassification(
        intent=intent_result.intent,
        confidence=intent_result.confidence,
        address=entities.address,
        district=entities.district,
        category=entities.category,
        needs_clarification=entities.needs_clarification,
        clarification_message=entities.clarification_message,
    )

    logger.info(
        "classify_two_step_complete",
        intent=result.intent,
        confidence=result.confidence,
        address=result.address,
        district=result.district,
        needs_clarification=result.needs_clarification,
    )

    return result


# =============================================================================
# Unified Classification API
# =============================================================================

# Режим классификации: "single" (1 вызов) или "two_step" (2 вызова)
CLASSIFICATION_MODE: str = "single"


def classify_query(
    query: str,
    mode: str | None = None,
    model_name: str = "GigaChat-2-Max"
) -> CityQueryClassification:
    """
    Универсальная функция классификации с выбором режима.

    Args:
        query: Запрос пользователя
        mode: "single" (1 вызов) или "two_step" (2 вызова). None = CLASSIFICATION_MODE
        model_name: Название модели GigaChat

    Returns:
        CityQueryClassification

    Examples:
        # Использовать режим по умолчанию
        result = classify_query("Где ближайший МФЦ к Невскому 1?")

        # Явно указать режим
        result = classify_query("Где МФЦ?", mode="two_step")
    """
    effective_mode = mode or CLASSIFICATION_MODE

    if effective_mode == "two_step":
        return classify_two_step(query, model_name)
    else:
        return classify_intent_structured(query, model_name)

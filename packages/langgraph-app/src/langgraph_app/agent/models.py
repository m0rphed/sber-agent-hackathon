"""
Pydantic модели для структурированного вывода LLM.

Используются для:
- Классификации категорий запросов (CategoryClassification)
- Проверки заполненности слотов (SlotsCheck)
- Валидации адресов (AddressCandidate, AddressValidation)
"""

from enum import Enum

from pydantic import BaseModel, Field


class ToolCategory(str, Enum):
    """
    Категории инструментов для маршрутизации запросов.

    Каждая категория соответствует определённому набору tools,
    что позволяет передавать ReAct агенту только релевантные инструменты.
    """

    # API категории (требуют tools)
    MFC = 'mfc'  # МФЦ: поиск, информация
    PENSIONER = 'pensioner'  # Услуги для пенсионеров
    GEO = 'geo'  # География: районы, адреса
    HEALTHCARE = 'healthcare'  # Поликлиники, ветеринарные клиники
    EDUCATION = 'education'  # Школы, детсады
    HOUSING = 'housing'  # УК, ЖКХ, отключения
    EVENTS = 'events'  # Мероприятия, события
    RECREATION = 'recreation'  # Спорт, парки, достопримечательности
    INFRASTRUCTURE = 'infrastructure'  # Дорожные работы

    # Не-API категории
    RAG = 'rag'  # Справочная информация (документы, льготы)
    CONVERSATION = 'conversation'  # Small talk, вопросы о боте


class CategoryClassification(BaseModel):
    """
    Результат классификации категории запроса.

    Используется LLM для определения, к какой категории
    относится запрос пользователя.
    """

    category: ToolCategory = Field(description='Категория запроса пользователя')
    confidence: float = Field(ge=0.0, le=1.0, description='Уверенность классификации (0.0 - 1.0)')
    reasoning: str = Field(description='Краткое объяснение выбора категории')


class SlotsCheck(BaseModel):
    """
    Результат проверки наличия обязательных параметров (слотов).

    Используется для определения, достаточно ли информации
    в запросе пользователя для выполнения действия.
    """

    is_clear: bool = Field(description='True если все необходимые параметры указаны')
    missing_params: list[str] = Field(
        default_factory=list,
        description='Список недостающих параметров (address, district, category_id и т.д.)',
    )
    extracted_address: str | None = Field(
        default=None, description='Извлечённый адрес из запроса (если есть)'
    )
    extracted_district: str | None = Field(
        default=None, description='Извлечённый район из запроса (если есть)'
    )
    clarification_question: str | None = Field(
        default=None, description='Вопрос для уточнения если is_clear=False'
    )


class AddressCandidate(BaseModel):
    """
    Кандидат адреса из API поиска.

    Используется когда поиск адреса возвращает несколько вариантов.
    """

    full_address: str = Field(description='Полный адрес')
    building_id: int | None = Field(
        default=None, description='ID здания в YAZZH API (для дальнейших запросов)'
    )
    lat: float | None = Field(default=None, description='Широта')
    lon: float | None = Field(default=None, description='Долгота')


class AddressValidation(BaseModel):
    """
    Результат валидации адреса через API.

    Три возможных состояния:
    1. is_valid=True — адрес найден однозначно
    2. is_ambiguous=True — несколько кандидатов, нужен выбор
    3. is_valid=False, is_ambiguous=False — адрес не найден
    """

    is_valid: bool = Field(description='True если адрес найден однозначно')
    is_ambiguous: bool = Field(default=False, description='True если найдено несколько кандидатов')
    validated_address: str | None = Field(
        default=None, description='Подтверждённый полный адрес (если is_valid=True)'
    )
    candidates: list[AddressCandidate] = Field(
        default_factory=list, description='Список кандидатов (если is_ambiguous=True)'
    )
    error_message: str | None = Field(
        default=None, description='Сообщение об ошибке (если адрес не найден)'
    )


# =============================================================================
# Константы для работы с категориями
# =============================================================================

# категории, которые требуют API tools
API_CATEGORIES: set[ToolCategory] = {
    ToolCategory.MFC,
    ToolCategory.PENSIONER,
    ToolCategory.GEO,
    ToolCategory.HEALTHCARE,
    ToolCategory.EDUCATION,
    ToolCategory.HOUSING,
    ToolCategory.EVENTS,
    ToolCategory.RECREATION,
    ToolCategory.INFRASTRUCTURE,
}

# категории, которые НЕ требуют tools
NON_API_CATEGORIES: set[ToolCategory] = {
    ToolCategory.RAG,
    ToolCategory.CONVERSATION,
}


def is_api_category(category: ToolCategory) -> bool:
    """
    Проверяет, требует ли категория использования API tools
    """
    return category in API_CATEGORIES

"""
Нода классификации категории запроса.

Использует LLM с structured output для определения категории запроса пользователя.
Категория определяет какой набор tools будет использоваться.
"""

from langchain_core.prompts import ChatPromptTemplate

from langgraph_app.agent.llm import get_llm_for_intent_routing
from langgraph_app.agent.models import CategoryClassification, ToolCategory
from langgraph_app.agent.state import get_chat_history, get_last_user_message
from langgraph_app.agent.state_v2 import HybridStateV2
from langgraph_app.logging_config import get_logger

logger = get_logger(__name__)


CATEGORY_CLASSIFIER_PROMPT = """Ты — классификатор запросов городского помощника Санкт-Петербурга.

Определи категорию запроса пользователя. ВАЖНО: выбирай ОДНУ наиболее подходящую категорию!

## Категории:

### Geo / Адреса
- **address** — поиск адреса, валидация адреса, координаты
- **district** — информация о районах города, какие районы есть

### Городские сервисы  
- **mfc** — вопросы о МФЦ (ближайший, адрес, часы работы)
- **polyclinic** — поликлиники (медицина для ЛЮДЕЙ)
- **school** — школы, образование для детей
- **kindergarten** — детские сады
- **housing** — управляющие компании, ЖКХ, отключения воды/электричества

### Питомцы (ВСЁ про животных!)
- **pets** — ветеринарные клиники, парки для выгула собак, приюты для животных

### Активности
- **pensioner** — услуги и занятия для пенсионеров, кружки для старшего поколения
- **events** — городские мероприятия, концерты, спортивные события
- **recreation** — спортплощадки, красивые места, туристические маршруты

### Инфраструктура
- **infrastructure** — дорожные работы, пункты переработки

### Не-API категории
- **rag** — справочная информация: документы, льготы, пособия, законы, порядок оформления
- **conversation** — приветствие, благодарность, вопросы о боте, small talk

## Примеры:
- "Найди ближайший МФЦ" → mfc
- "Какие документы нужны для загранпаспорта" → rag
- "Кружки для пенсионеров в Невском районе" → pensioner
- "Какие школы есть рядом с моим домом" → school
- "Детский сад в Калининском районе" → kindergarten
- "Когда отключат воду" → housing
- "Где ветеринарка рядом" → pets
- "Парк для выгула собаки" → pets
- "Приют для кошек" → pets
- "Привет" → conversation
- "Какие льготы положены многодетным" → rag
- "Какой у меня район по адресу" → district
"""


def classify_category_node(state: HybridStateV2) -> dict:
    """
    Классифицирует категорию запроса.

    Args:
        state: Текущее состояние графа

    Returns:
        Dict с обновлениями для state:
        - category: ToolCategory
        - category_confidence: float
        - intent: str (для совместимости с v1)
        - intent_confidence: float
    """
    query = get_last_user_message(state)
    history = get_chat_history(state, max_messages=4)

    logger.info("classify_category_start", query=query[:100] if query else "")

    try:
        llm = get_llm_for_intent_routing().with_structured_output(CategoryClassification)

        prompt = ChatPromptTemplate.from_messages([
            ("system", CATEGORY_CLASSIFIER_PROMPT),
            ("human", "История диалога:\n{history}\n\nПоследний запрос: {query}"),
        ])

        history_text = "\n".join(
            f"{getattr(msg, 'type', 'human')}: {msg.content}"
            for msg in history[-4:]
        ) or "(пусто)"

        result: CategoryClassification = (prompt | llm).invoke({
            "history": history_text,
            "query": query,
        })

        logger.info(
            "category_classified",
            category=result.category.value,
            confidence=result.confidence,
            reasoning=result.reasoning,
        )

        return {
            "category": result.category,
            "category_confidence": result.confidence,
            "intent": result.category.value,  # Для совместимости с v1
            "intent_confidence": result.confidence,
            "metadata": {
                **state.get("metadata", {}),
                "classification_method": "llm",
                "classification_reasoning": result.reasoning,
            },
        }

    except Exception as e:
        logger.exception("category_classification_failed", error=str(e))

        # Fallback на RAG как безопасный вариант
        return {
            "category": ToolCategory.RAG,
            "category_confidence": 0.5,
            "intent": "rag",
            "intent_confidence": 0.5,
            "metadata": {
                **state.get("metadata", {}),
                "classification_method": "fallback",
                "classification_error": str(e),
            },
        }

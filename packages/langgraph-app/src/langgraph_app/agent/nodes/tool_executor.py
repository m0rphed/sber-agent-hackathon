"""
Нода выполнения инструментов.

Использует ReAct агента с подмножеством tools, соответствующим категории запроса.
"""

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from langgraph_app.agent.llm import get_llm_for_tools
from langgraph_app.agent.state import get_chat_history, get_last_user_message
from langgraph_app.agent.state_v2 import HybridStateV2, get_address_from_state
from langgraph_app.config import get_agent_config
from langgraph_app.logging_config import get_logger
from langgraph_app.tools.registry import get_tools_for_category
from langgraph_app.utils.time_utils import get_today_date
from prompts import load_prompt

logger = get_logger(__name__)

# Загружаем system prompt для tool agent
TOOL_AGENT_PROMPT_TEMPLATE = load_prompt('tool_agent_system.txt')


async def execute_tools_node(state: HybridStateV2) -> dict:
    """
    Выполняет tools для выбранной категории.

    Создаёт ReAct агента с ПОДМНОЖЕСТВОМ tools (не все 26+),
    что улучшает качество выбора инструментов.

    Args:
        state: Текущее состояние графа

    Returns:
        Dict с обновлениями для state:
        - tool_result: str
        - metadata: dict
    """
    category = state.get('category')
    query = get_last_user_message(state)
    agent_config = get_agent_config()

    # Получаем tools для категории (не все 26!)
    tools = get_tools_for_category(category)

    if not tools:
        logger.warning('no_tools_for_category', category=category)
        return {
            'tool_result': 'Нет доступных инструментов для этой категории.',
        }

    logger.info(
        'execute_tools_start',
        category=category.value if category else 'none',
        tools_count=len(tools),
        tool_names=[t.name for t in tools],
    )

    try:
        llm = get_llm_for_tools()

        # Формируем system prompt с контекстом
        current_date = get_today_date()
        system_prompt = TOOL_AGENT_PROMPT_TEMPLATE.format(current_date=current_date)

        # Добавляем контекст об адресе если есть
        context_parts = []
        address = get_address_from_state(state)
        if address:
            context_parts.append(f'Адрес пользователя: {address}')
        if state.get('extracted_district'):
            context_parts.append(f'Район: {state["extracted_district"]}')
        if state.get('validated_building_id'):
            context_parts.append(f'ID здания: {state["validated_building_id"]}')

        # Обогащаем запрос контекстом
        context = '\n'.join(context_parts)
        enriched_query = f'{context}\n\nЗапрос пользователя: {query}' if context else query

        # Создаём агента с langchain.agents.create_agent (новое API)
        react_agent = create_agent(
            model=llm,
            tools=tools,
            system_prompt=system_prompt,
        )

        # Формируем сообщения
        history = get_chat_history(state, max_messages=agent_config.memory.context_window_size - 2)
        messages = list(history) + [HumanMessage(content=enriched_query)]

        # Запускаем агента асинхронно (tools async!)
        result = await react_agent.ainvoke(
            {'messages': messages},
            config={'recursion_limit': agent_config.memory.recursion_limit},
        )

        # Извлекаем ответ
        output = _extract_agent_output(result)

        # Валидируем output
        output = _validate_tool_output(output)

        logger.info('execute_tools_complete', output_length=len(output))

        return {
            'tool_result': output,
            'metadata': {
                **state.get('metadata', {}),
                'handler': 'tool_agent',
                'category': category.value if category else 'none',
                'tools_available': [t.name for t in tools],
            },
        }

    except Exception as e:
        logger.exception('execute_tools_failed', error=str(e))
        return {
            'tool_result': 'Ошибка при обработке запроса. Попробуйте позже.',
            'metadata': {
                **state.get('metadata', {}),
                'handler': 'tool_agent',
                'error': str(e),
            },
        }


def _extract_agent_output(result: dict) -> str:
    """
    Извлекает текстовый ответ из результата ReAct агента.

    Args:
        result: Результат от create_react_agent

    Returns:
        Текст ответа
    """
    default_output = 'Не удалось обработать запрос.'

    messages = result.get('messages', [])
    if not messages:
        return default_output

    # Ищем последний AI message с контентом
    for msg in reversed(messages):
        # Проверяем тип сообщения
        msg_type = getattr(msg, 'type', None)
        if msg_type != 'ai':
            continue

        content = getattr(msg, 'content', None)
        if not content:
            continue

        # content может быть str или list
        if isinstance(content, list):
            content = str(content[0]) if content else ''

        if content:
            return str(content)

    return default_output


def _validate_tool_output(output: str) -> str:
    """
    Проверяет и очищает output от tool.

    Args:
        output: Сырой output

    Returns:
        Валидированный output
    """
    # Проверяем на пустоту
    if not output or output.strip() in ('', 'null', 'None', '[]', '{}'):
        return 'К сожалению, данные не найдены. Попробуйте уточнить запрос.'

    # Проверяем на API error markers
    error_markers = [
        'API_UNAVAILABLE',
        'ServiceUnavailableError',
        'TimeoutException',
        '502 Bad Gateway',
        '504 Gateway Timeout',
    ]

    for marker in error_markers:
        if marker in output:
            return 'Сервис временно недоступен. Попробуйте позже.'

    return output

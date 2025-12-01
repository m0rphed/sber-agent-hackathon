"""
Городской агент-помощник на базе GigaChat
"""

from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langgraph.graph.state import CompiledStateGraph

from app.agent.llm import get_llm
from app.agent.memory import ConversationMemory, get_memory
from app.agent.persistent_memory import get_checkpointer
from app.agent.utils import langchain_cast_sqlite_config as cast_sqlite_config
from app.config import SYSTEM_PROMPT_PATH
from app.logging_config import get_logger
from app.services.toxicity import get_toxicity_filter
from app.tools import ALL_TOOLS

logger = get_logger(__name__)

SYSTEM_PROMPT = ''
with open(SYSTEM_PROMPT_PATH, encoding='utf-8') as f:
    SYSTEM_PROMPT = f.read()


# TODO: проверить защиту от бесконечных циклов и превышения лимитов API
# max количество итераций tool calls

# TODO: перенести эту переменную в конфиг (config.py)
MAX_AGENT_ITERATIONS: int = 5

# TODO: перенести эту переменную в конфиг (config.py)
# [СЕЙЧАС] каждая итерация = 2 узла (tool call + response)
ITERATION_STEP_COST_DEFAULT: int = 2


def _get_recursion_limit(
    max_iterations: int = MAX_AGENT_ITERATIONS,
    iteration_step_cost: int = ITERATION_STEP_COST_DEFAULT,
) -> int:
    """
    Вычисляет recursion_limit для LangGraph
    """
    # расчёт recursion_limit для LangGraph
    # := (max кол-во запросов * цену одного шага итерации) +1 для финального ответа
    return max_iterations * iteration_step_cost + 1


def create_city_agent(
    with_persistence: bool = False,
) -> CompiledStateGraph:
    """
    Создаёт агента городского помощника

    Args:
        with_persistence: Если True, использует SQLite для сохранения состояния

    Returns:
        Настроенный ReAct агент с инструментами
    """
    logger.info(
        'creating_agent',
        with_persistence=with_persistence,
        tools_count=len(ALL_TOOLS),
        tools=[t.name for t in ALL_TOOLS],
    )
    logger.debug(
        'agent_system_prompt',
        system_prompt=SYSTEM_PROMPT[:500] + '...' if len(SYSTEM_PROMPT) > 500 else SYSTEM_PROMPT,
        system_prompt_length=len(SYSTEM_PROMPT),
    )

    llm = get_llm(temperature=0.3)

    # создаём ReAct агента с инструментами
    if with_persistence:
        checkpointer = get_checkpointer()
        agent: CompiledStateGraph = create_agent(
            model=llm,
            tools=ALL_TOOLS,
            system_prompt=SYSTEM_PROMPT,
            checkpointer=checkpointer,
        )
        logger.info('agent_created', mode='persistent', checkpointer_type=type(checkpointer).__name__)
        return agent

    # возвращается экземпляр агента по умолчанию (in-memory)
    _agent_default: CompiledStateGraph = create_agent(
        model=llm,
        tools=ALL_TOOLS,
        system_prompt=SYSTEM_PROMPT,
    )

    logger.info('agent_created', mode='in-memory')
    return _agent_default


def invoke_agent(
    agent: CompiledStateGraph,
    user_message: str,
    chat_history: list | None = None,
    thread_id: str | None = None,
    max_iterations: int = MAX_AGENT_ITERATIONS,
) -> str:
    """
    Вызывает агента с сообщением пользователя и историей диалога

    Args:
        agent: Экземпляр агента
        user_message: Сообщение пользователя
        chat_history: История диалога (для агента без persistence)
        thread_id: ID потока для агента с persistence
        max_iterations: Максимум итераций tool calls (защита от зацикливания)

    Returns:
        Ответ агента
    """
    if chat_history is None:
        chat_history = []

    messages = chat_history + [HumanMessage(content=user_message)]

    # конфигурация для агента (с сохранением памяти) + recursion_limit
    recursion_limit = _get_recursion_limit(max_iterations)
    config: dict[str, Any] = {'recursion_limit': recursion_limit}
    if thread_id:
        config['configurable'] = {'thread_id': thread_id}

    # DEBUG: логируем входные данные
    logger.debug(
        'invoke_agent_input',
        user_message=user_message,
        chat_history_length=len(chat_history),
        chat_history_messages=[
            {'type': m.type, 'content': m.content[:200] + '...' if len(m.content) > 200 else m.content}
            for m in chat_history[-5:]  # последние 5 сообщений
        ] if chat_history else [],
        thread_id=thread_id,
        max_iterations=max_iterations,
        recursion_limit=recursion_limit,
    )

    logger.info(
        'invoke_agent_start',
        user_message_preview=user_message[:100] + '...' if len(user_message) > 100 else user_message,
        total_messages=len(messages),
    )

    result = agent.invoke(
        {'messages': messages}, config=cast_sqlite_config(config) if thread_id else config
    )

    # DEBUG: логируем полный результат
    all_messages = result.get('messages', [])
    logger.debug(
        'invoke_agent_result',
        total_messages_in_result=len(all_messages),
        message_types=[m.type for m in all_messages],
        tool_calls=[
            {
                'tool': tc.get('name', 'unknown'),
                'args_preview': str(tc.get('args', {}))[:200],
            }
            for m in all_messages
            if hasattr(m, 'tool_calls') and m.tool_calls
            for tc in m.tool_calls
        ],
    )

    # получаем последнее сообщение от ассистента
    ai_messages = [m for m in result['messages'] if hasattr(m, 'content') and m.type == 'ai']

    if ai_messages:
        response = ai_messages[-1].content
        logger.debug(
            'invoke_agent_response',
            response_length=len(response),
            response_preview=response[:300] + '...' if len(response) > 300 else response,
        )
        logger.info(
            'invoke_agent_complete',
            response_length=len(response),
            ai_messages_count=len(ai_messages),
        )
        return response

    logger.warning('invoke_agent_no_response', total_messages=len(all_messages))
    return 'Извините, не удалось обработать ваш запрос.'


def chat_with_persistence(
    agent: CompiledStateGraph,
    user_message: str,
    thread_id: str,
    max_iterations: int = MAX_AGENT_ITERATIONS,
) -> str:
    """
    Вызывает агента с персистентной памятью (SQLite)

    История диалога автоматически сохраняется и восстанавливается
    между запусками программы

    Args:
        agent: Экземпляр агента (созданный с with_persistence=True)
        user_message: Сообщение пользователя
        thread_id: ID потока/сессии (уникальный для каждого пользователя)
        max_iterations: Максимум итераций tool calls (защита от зацикливания)

    Returns:
        Ответ агента
    """
    logger.info(
        'chat_with_persistence_start',
        thread_id=thread_id,
        user_message_preview=user_message[:100] + '...' if len(user_message) > 100 else user_message,
    )

    config = {
        'configurable': {'thread_id': thread_id},
        'recursion_limit': _get_recursion_limit(max_iterations),
    }
    _config_runnable = cast_sqlite_config(config)

    logger.debug(
        'chat_with_persistence_config',
        config=config,
        max_iterations=max_iterations,
    )

    result = agent.invoke(
        {'messages': [HumanMessage(content=user_message)]},
        config=_config_runnable,
    )

    # DEBUG: логируем результат
    all_messages = result.get('messages', [])
    logger.debug(
        'chat_with_persistence_result',
        total_messages=len(all_messages),
        message_types=[m.type for m in all_messages],
    )

    # получаем последнее сообщение от ассистента
    ai_messages = [m for m in result['messages'] if hasattr(m, 'content') and m.type == 'ai']
    if ai_messages:
        response = ai_messages[-1].content
        logger.info(
            'chat_with_persistence_complete',
            response_length=len(response),
            thread_id=thread_id,
        )
        return response

    logger.warning('chat_with_persistence_no_response', thread_id=thread_id)
    return 'Извините, не удалось обработать ваш запрос.'


def chat_with_memory(
    agent: CompiledStateGraph,
    user_message: str,
    session_id: str,
    memory: ConversationMemory | None = None,
) -> str:
    """
    Вызывает агента с учётом истории диалога

    Args:
        agent: Экземпляр агента
        user_message: Сообщение пользователя
        session_id: ID сессии для сохранения контекста
        memory: Экземпляр памяти (если None, используется глобальный)

    Returns:
        Ответ агента
    """
    if memory is None:
        memory = get_memory()

    # история диалога
    chat_history = memory.get_history(session_id)

    logger.info(
        'chat_with_memory_start',
        session_id=session_id,
        chat_history_length=len(chat_history),
        user_message_preview=user_message[:100] + '...' if len(user_message) > 100 else user_message,
    )
    logger.debug(
        'chat_with_memory_context',
        session_id=session_id,
        chat_history=[
            {'type': m.type, 'content': m.content[:150] + '...' if len(m.content) > 150 else m.content}
            for m in chat_history[-6:]  # последние 6 сообщений (3 обмена)
        ] if chat_history else [],
    )

    # вызываем агента
    response = invoke_agent(agent, user_message, chat_history)
    # сохраняем обмен в память
    memory.add_exchange(session_id, user_message, response)

    logger.info(
        'chat_with_memory_complete',
        session_id=session_id,
        response_length=len(response),
        new_history_length=len(memory.get_history(session_id)),
    )

    return response


def safe_chat(
    agent: CompiledStateGraph,
    user_message: str,
    session_id: str,
    use_persistence: bool = False,
    memory: ConversationMemory | None = None,
) -> str:
    """
    Безопасный чат с фильтрацией токсичности

    Это основная функция для взаимодействия с агентом
    Автоматически фильтрует токсичные сообщения

    Args:
        agent: Экземпляр агента
        user_message: Сообщение пользователя
        session_id: ID сессии
        use_persistence: Использовать SQLite для памяти
        memory: Экземпляр памяти (для in-memory режима)

    Returns:
        Ответ агента или сообщение об отклонении токсичного запроса
    """
    logger.info(
        'safe_chat_start',
        session_id=session_id,
        use_persistence=use_persistence,
        message_length=len(user_message),
    )

    # проверяем на токсичность
    toxicity_filter = get_toxicity_filter()
    should_process, toxic_response = toxicity_filter.filter_message(user_message)

    if not should_process:
        # DEBUG: логируем заблокированное сообщение
        toxicity_result = toxicity_filter.check(user_message)
        logger.warning(
            'safe_chat_blocked',
            session_id=session_id,
            toxicity_level=toxicity_result.level.value,
            matched_patterns_count=len(toxicity_result.matched_patterns),
            confidence=toxicity_result.confidence,
        )
        logger.debug(
            'safe_chat_toxicity_details',
            session_id=session_id,
            matched_patterns=toxicity_result.matched_patterns[:5],  # первые 5 паттернов
            message_preview=user_message[:50] + '...' if len(user_message) > 50 else user_message,
        )
        return toxic_response or 'Извините, я не могу обработать это сообщение.'

    logger.debug(
        'safe_chat_passed_toxicity',
        session_id=session_id,
    )

    # вызываем агента в зависимости от режима
    if use_persistence:
        return chat_with_persistence(agent, user_message, session_id)
    else:
        return chat_with_memory(agent, user_message, session_id, memory)


if __name__ == '__main__':
    import sys

    # выбираем режим: persistence или in-memory
    use_persistence = '--persist' in sys.argv
    thread_id = 'test_user_123'

    print(f'Режим: {"SQLite persistence" if use_persistence else "In-memory"}')
    print(f'Thread ID: {thread_id}')

    agent = create_city_agent(with_persistence=use_persistence)

    test_queries = [
        'Привет! Меня зовут Алексей.',
        'Где ближайший МФЦ к Невскому проспекту 1?',
        'Ты идиот!',  # тест фильтра токсичности
        'Напомни, как меня зовут?',
    ]

    for query in test_queries:
        print(f'\n{"=" * 50}')
        print(f'Вопрос: {query}')
        print(f'{"=" * 50}')

        response = safe_chat(agent, query, thread_id, use_persistence)
        print(f'Ответ: {response}')

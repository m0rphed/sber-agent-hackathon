"""
Городской агент-помощник на базе GigaChat
"""

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langgraph.graph.state import CompiledStateGraph

from app.agent.llm import get_llm
from app.agent.memory import ConversationMemory, get_memory
from app.agent.persistent_memory import get_checkpointer
from app.config import SYSTEM_PROMPT_PATH
from app.services.toxicity import get_toxicity_filter
from app.tools.city_tools import ALL_TOOLS

SYSTEM_PROMPT = ''
with open(SYSTEM_PROMPT_PATH, encoding='utf-8') as f:
    SYSTEM_PROMPT = f.read()


def create_city_agent(with_persistence: bool = False) -> CompiledStateGraph:
    """
    Создаёт агента городского помощника

    Args:
        with_persistence: Если True, использует SQLite для сохранения состояния

    Returns:
        Настроенный ReAct агент с инструментами
    """
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
    else:
        agent: CompiledStateGraph = create_agent(
            model=llm,
            tools=ALL_TOOLS,
            system_prompt=SYSTEM_PROMPT,
        )

    return agent


def invoke_agent(
    agent: CompiledStateGraph,
    user_message: str,
    chat_history: list | None = None,
    thread_id: str | None = None,
) -> str:
    """
    Вызывает агента с сообщением пользователя и историей диалога

    Args:
        agent: Экземпляр агента
        user_message: Сообщение пользователя
        chat_history: История диалога (для агента без persistence)
        thread_id: ID потока для агента с persistence

    Returns:
        Ответ агента
    """
    if chat_history is None:
        chat_history = []

    messages = chat_history + [HumanMessage(content=user_message)]

    # конфигурация для персистентного агента
    config = {}
    if thread_id:
        config = {'configurable': {'thread_id': thread_id}}

    result = agent.invoke({'messages': messages}, config=config if config else None)
    # получаем последнее сообщение от ассистента
    ai_messages = [m for m in result['messages'] if hasattr(m, 'content') and m.type == 'ai']

    if ai_messages:
        return ai_messages[-1].content
    return 'Извините, не удалось обработать ваш запрос.'


def chat_with_persistence(
    agent: CompiledStateGraph,
    user_message: str,
    thread_id: str,
) -> str:
    """
    Вызывает агента с персистентной памятью (SQLite)

    История диалога автоматически сохраняется и восстанавливается
    между запусками программы

    Args:
        agent: Экземпляр агента (созданный с with_persistence=True)
        user_message: Сообщение пользователя
        thread_id: ID потока/сессии (уникальный для каждого пользователя)

    Returns:
        Ответ агента
    """
    config = {'configurable': {'thread_id': thread_id}}

    result = agent.invoke(
        {'messages': [HumanMessage(content=user_message)]},
        config=config,
    )

    # получаем последнее сообщение от ассистента
    ai_messages = [m for m in result['messages'] if hasattr(m, 'content') and m.type == 'ai']
    if ai_messages:
        return ai_messages[-1].content

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
    # вызываем агента
    response = invoke_agent(agent, user_message, chat_history)
    # сохраняем обмен в память
    memory.add_exchange(session_id, user_message, response)

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
    # проверяем на токсичность
    toxicity_filter = get_toxicity_filter()
    should_process, toxic_response = toxicity_filter.filter_message(user_message)

    if not should_process:
        return toxic_response or 'Извините, я не могу обработать это сообщение.'

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

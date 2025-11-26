"""
Городской агент-помощник на базе GigaChat.
"""

# from langgraph.prebuilt import create_react_agent
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from app.agent.llm import get_llm
from app.config import SYSTEM_PROMPT_PATH
from app.tools.city_tools import ALL_TOOLS

SYSTEM_PROMPT = ''
with open(SYSTEM_PROMPT_PATH, encoding='utf-8') as f:
    SYSTEM_PROMPT = f.read()


def create_city_agent():
    """
    Создаёт агента городского помощника.

    Returns:
        Настроенный ReAct агент с инструментами
    """
    llm = get_llm(temperature=0.3)

    # создаём ReAct агента с инструментами
    agent = create_agent(
        model=llm,
        tools=ALL_TOOLS,
        prompt=SYSTEM_PROMPT,
    )

    return agent


def invoke_agent(
    agent,
    user_message: str,
    chat_history: list | None = None
) -> str:
    """
    Вызывает агента с сообщением пользователя.

    Args:
        agent: Экземпляр агента
        user_message: Сообщение пользователя
        chat_history: История диалога (опционально)

    Returns:
        Ответ агента
    """
    if chat_history is None:
        chat_history = []

    messages = chat_history + [HumanMessage(content=user_message)]
    result = agent.invoke({'messages': messages})

    # Получаем последнее сообщение от ассистента
    ai_messages = [m for m in result['messages'] if hasattr(m, 'content') and m.type == 'ai']
    if ai_messages:
        return ai_messages[-1].content

    return 'Извините, не удалось обработать ваш запрос.'


if __name__ == '__main__':
    # Простой тест агента
    agent = create_city_agent()

    test_queries = [
        'Привет! Где ближайший МФЦ к Невскому проспекту 1?',
        'Какие категории услуг есть для пенсионеров?',
    ]

    for query in test_queries:
        print(f'\n{"=" * 50}')
        print(f'Вопрос: {query}')
        print(f'{"=" * 50}')
        response = invoke_agent(agent, query)
        print(f'Ответ: {response}')

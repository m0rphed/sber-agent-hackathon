"""
проверка использования tools агентом

Запуск:
    uv run python test_tool_usage.py
"""

import logging
import sys

# настраиваем логирование для отображения в консоли
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)

# debug для LangChain - чтобы видеть вызовы tools
logging.getLogger('langchain').setLevel(logging.DEBUG)
logging.getLogger('app.tools.city_tools').setLevel(logging.INFO)


def print_messages_with_tool_content(result: dict):
    messages = result.get('messages', [])

    for msg in messages:
        msg_type = type(msg).__name__

        # tool вызовы от AI (запросы к инструментам)
        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            print(f'\n  📤 [{msg_type}] Tool Calls:')
            for tc in msg.tool_calls:
                print(f'      🔧 {tc.get("name", "?")}({tc.get("args", {})})')

        # tool messages (ответы от инструментов)
        if msg_type == 'ToolMessage':
            tool_name = getattr(msg, 'name', 'unknown')
            content = msg.content
            # обрезаем длинный контент для читаемости
            if len(content) > 500:
                content = content[:500] + '...[truncated]'
            print(f'\n  📥 [ToolMessage] from {tool_name}:')
            print(f'      {content}')

        # AI сообщения с текстом
        elif msg_type == 'AIMessage' and hasattr(msg, 'content') and msg.content:
            content = msg.content
            if len(content) > 300:
                content = content[:300] + '...'
            print(f'\n  🤖 [{msg_type}]: {content}')

        # human сообщения
        elif msg_type == 'HumanMessage':
            print(f'\n  👤 [{msg_type}]: {msg.content}')


def test_mfc_query():
    """
    запрос про МФЦ
    """
    from langchain_core.messages import HumanMessage

    from app.agent.city_agent import create_city_agent

    print('\n' + '=' * 60)
    print('=> ТЕСТ: Запрос про МФЦ')
    print('=' * 60)

    agent = create_city_agent(with_persistence=False)

    # запрос, который должен вызвать find_nearest_mfc_tool
    query = 'Где находится ближайший МФЦ к адресу Невский проспект 1?'
    print(f'\n📝 Запрос: {query}')

    try:
        result = agent.invoke({'messages': [HumanMessage(content=query)]})
        print('\n📋 Полный trace сообщений:')
        print_messages_with_tool_content(result)

    except Exception as e:
        print(f'[!] Ошибка: {e}')
        import traceback

        traceback.print_exc()


def test_pensioner_query():
    """
    запрос про услуги для пенсионеров
    """
    from langchain_core.messages import HumanMessage

    from app.agent.city_agent import create_city_agent

    print('\n' + '=' * 60)
    print('=> ТЕСТ: Запрос про услуги для пенсионеров')
    print('=' * 60)

    agent = create_city_agent(with_persistence=False)

    # запрос, который должен вызвать get_pensioner_categories_tool
    query = 'Какие есть категории услуг для пенсионеров?'
    print(f'\n📝 Запрос: {query}')

    try:
        result = agent.invoke({'messages': [HumanMessage(content=query)]})
        print('\n📋 Полный trace сообщений:')
        print_messages_with_tool_content(result)

    except Exception as e:
        print(f'[!] Ошибка: {e}')
        import traceback

        traceback.print_exc()


def test_simple_query():
    """
    простой запрос (без инструментов)
    """
    from langchain_core.messages import HumanMessage

    from app.agent.city_agent import create_city_agent

    print('\n' + '=' * 60)
    print('=> ТЕСТ: Простой запрос (без инструментов)')
    print('=' * 60)

    agent = create_city_agent(with_persistence=False)

    # простой запрос, который НЕ должен вызывать инструменты
    query = 'Привет! Как дела?'
    print(f'\n📝 Запрос: {query}')

    try:
        result = agent.invoke({'messages': [HumanMessage(content=query)]})
        print('\n📋 Полный trace сообщений:')
        print_messages_with_tool_content(result)

    except Exception as e:
        print(f'[!] Ошибка: {e}')
        import traceback

        traceback.print_exc()


if __name__ == '__main__':
    print('🚀 использования инструментов агентом')
    test_mfc_query()
    test_pensioner_query()
    test_simple_query()

    print('\n' + '=' * 60)
    print('Тестирование завершено!')
    print('=' * 60)

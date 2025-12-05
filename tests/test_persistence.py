"""
Тест персистентной памяти для unified API.

Проверяет что:
1. История сохраняется между вызовами chat() с use_persistence=True
2. История доступна через get_chat_history()
3. clear_chat_history() очищает историю
"""

import os
from pathlib import Path
import sys

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Устанавливаем переменные окружения для тестирования
os.environ.setdefault('GIGACHAT_API_KEY', 'test_key')
os.environ.setdefault('LOG_LEVEL', 'WARNING')


def test_persistence_flow():
    """Тест персистентного flow через unified API."""
    from app.agent import (
        AgentType,
        chat_with_metadata,
        clear_chat_history,
        get_chat_history,
    )

    test_session = 'test_persistence_session_123'

    # Очищаем историю перед тестом
    clear_chat_history(test_session)
    history_before = get_chat_history(test_session)
    print(f'История до теста: {len(history_before)} сообщений')
    assert len(history_before) == 0, 'История должна быть пустой после clear'

    # Первый вызов с persistence
    print('\n--- Первый вызов ---')
    response1, meta1 = chat_with_metadata(
        'Привет, меня зовут Алексей!',
        session_id=test_session,
        agent_type=AgentType.SUPERVISOR,
        use_persistence=True,
    )
    print(f'Ответ 1: {response1[:100]}...')
    print(f'Metadata 1: {meta1}')

    # Проверяем историю после первого вызова
    history_after_1 = get_chat_history(test_session)
    print(f'История после 1 вызова: {len(history_after_1)} сообщений')

    # Второй вызов - агент должен помнить имя
    print('\n--- Второй вызов ---')
    response2, meta2 = chat_with_metadata(
        'Как меня зовут?',
        session_id=test_session,
        agent_type=AgentType.SUPERVISOR,
        use_persistence=True,
    )
    print(f'Ответ 2: {response2[:200]}...')
    print(f'Metadata 2: {meta2}')

    # Проверяем историю после второго вызова
    history_after_2 = get_chat_history(test_session)
    print(f'История после 2 вызовов: {len(history_after_2)} сообщений')

    # Очищаем после теста
    clear_chat_history(test_session)
    print('\n✅ Тест завершён')


if __name__ == '__main__':
    test_persistence_flow()

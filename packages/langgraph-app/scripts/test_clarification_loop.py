#!/usr/bin/env python
"""
Тест защиты от бесконечного цикла уточнений.

Симулирует ситуацию когда пользователь не даёт нужные параметры.

Usage:
    uv run python scripts/test_clarification_loop.py
"""

import uuid

from langchain_core.messages import HumanMessage
from langgraph_app.agent.hybrid import MAX_CLARIFICATION_ATTEMPTS, create_hybrid_v2_graph
from langgraph_app.agent.persistent_memory import get_checkpointer


def test_clarification_limit():
    """Тест: агент должен перейти на fallback после N неудачных попыток."""
    print('Testing clarification loop protection...')
    print(f'MAX_CLARIFICATION_ATTEMPTS = {MAX_CLARIFICATION_ATTEMPTS}')
    print('=' * 60)

    checkpointer = get_checkpointer()
    graph = create_hybrid_v2_graph(checkpointer=checkpointer)

    thread_id = str(uuid.uuid4())
    config = {'configurable': {'thread_id': thread_id}}

    # Первый запрос - неконкретный (без района для kindergarten)
    queries = [
        'Найди детский сад',  # Attempt 0 → clarify
        'Мне нужен садик',  # Attempt 1 → clarify
        'Ну найди уже',  # Attempt 2 → fallback_rag
    ]

    for i, query in enumerate(queries):
        print(f"\n--- Turn {i + 1}: '{query}' ---")

        result = graph.invoke(
            {'messages': [HumanMessage(content=query)]},
            config=config,
        )

        # Получаем последний ответ
        last_msg = result.get('messages', [])[-1] if result.get('messages') else None
        if last_msg:
            print(f'Response: {last_msg.content[:200]}...')

        # Проверяем состояние
        attempts = result.get('clarification_attempts', 0)
        category = result.get('category')
        fallback = result.get('fallback_context')

        print(f'  Category: {category}')
        print(f'  Clarification attempts: {attempts}')
        print(f'  Fallback triggered: {fallback is not None}')

        if fallback:
            print(f'\n✓ Fallback activated after {attempts} attempts!')
            print(f'  Context: {fallback[:100]}...')
            break

    print('\n' + '=' * 60)
    print('Test complete!')


if __name__ == '__main__':
    test_clarification_limit()

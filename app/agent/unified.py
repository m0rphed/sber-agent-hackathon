"""
Унифицированный API для агентов.

Позволяет легко переключаться между архитектурами:
- supervisor: Supervisor Graph (Вариант 2) - явный роутинг, direct tool calls
- hybrid: Hybrid Agent Graph (Вариант 3) - ReAct агент для tools
- legacy: Legacy ReAct Agent - старый подход с полным ReAct

Использование:
    from app.agent.unified import chat, AgentType

    # По умолчанию - supervisor (in-memory)
    response = chat("Как получить загранпаспорт?")

    # С персистентной памятью (SQLite)
    response = chat("Где МФЦ?", session_id="user123", use_persistence=True)

    # Явный выбор архитектуры
    response = chat("Где МФЦ?", agent_type=AgentType.HYBRID)
"""

from enum import Enum

from langchain_core.messages import BaseMessage

from app.agent.memory import ConversationMemory, get_memory
from app.logging_config import get_logger

logger = get_logger(__name__)


class AgentType(str, Enum):
    """Типы агентов."""

    SUPERVISOR = 'supervisor'  # Вариант 2: Supervisor Graph
    HYBRID = 'hybrid'  # Вариант 3: Hybrid Agent Graph
    LEGACY = 'legacy'  # Старый ReAct агент


# Дефолтный тип агента
DEFAULT_AGENT_TYPE = AgentType.SUPERVISOR


def chat(
    message: str,
    session_id: str = 'default',
    agent_type: AgentType | str = DEFAULT_AGENT_TYPE,
    use_persistence: bool = False,
    memory: ConversationMemory | None = None,
) -> str:
    """
    Унифицированный интерфейс для чата с агентом.

    Args:
        message: Сообщение пользователя
        session_id: ID сессии (thread_id для checkpointer)
        agent_type: Тип агента (supervisor, hybrid, legacy)
        use_persistence: Использовать персистентную память (SQLite).
                         Если True, история сохраняется между перезапусками.
        memory: Экземпляр in-memory памяти (игнорируется при use_persistence=True)

    Returns:
        Ответ агента
    """
    # Нормализуем тип агента
    if isinstance(agent_type, str):
        try:
            agent_type = AgentType(agent_type.lower())
        except ValueError:
            logger.warning(f'Unknown agent type: {agent_type}, using default')
            agent_type = DEFAULT_AGENT_TYPE

    # Определяем источник истории
    chat_history: list[BaseMessage] = []

    if use_persistence:
        # При персистентности история загружается checkpointer'ом автоматически
        # Не нужно передавать chat_history вручную
        pass
    else:
        # In-memory режим — используем ConversationMemory
        if memory is None:
            memory = get_memory()
        chat_history = memory.get_history(session_id)

    logger.info(
        'unified_chat_start',
        agent_type=agent_type.value,
        session_id=session_id,
        use_persistence=use_persistence,
        message_preview=message[:100] + '...' if len(message) > 100 else message,
        history_length=len(chat_history),
    )

    # Вызываем нужный агент
    if agent_type == AgentType.SUPERVISOR:
        response, metadata = _invoke_supervisor(message, session_id, chat_history, use_persistence)
    elif agent_type == AgentType.HYBRID:
        response, metadata = _invoke_hybrid(message, session_id, chat_history, use_persistence)
    elif agent_type == AgentType.LEGACY:
        response, metadata = _invoke_legacy(message, session_id, chat_history, use_persistence)
    else:
        raise ValueError(f'Unknown agent type: {agent_type}')

    # Сохраняем в in-memory память только если не персистентный режим
    if not use_persistence and not metadata.get('toxicity_blocked', False):
        if memory is not None:
            memory.add_exchange(session_id, message, response)

    logger.info(
        'unified_chat_complete',
        agent_type=agent_type.value,
        response_length=len(response),
        handler=metadata.get('handler', 'unknown'),
    )

    return response


def chat_with_metadata(
    message: str,
    session_id: str = 'default',
    agent_type: AgentType | str = DEFAULT_AGENT_TYPE,
    memory: ConversationMemory | None = None,
    use_persistence: bool = False,
) -> tuple[str, dict]:
    """
    Чат с возвратом метаданных.

    Args:
        message: Сообщение пользователя
        session_id: ID сессии
        agent_type: Тип агента
        memory: Экземпляр памяти (игнорируется при use_persistence=True)
        use_persistence: Использовать персистентную память (SQLite).
            Если True, то история сохраняется в БД и доступна после перезапуска.

    Returns:
        Кортеж (ответ, метаданные)
    """
    if isinstance(agent_type, str):
        try:
            agent_type = AgentType(agent_type.lower())
        except ValueError:
            agent_type = DEFAULT_AGENT_TYPE

    # При персистентном режиме не используем in-memory память
    if use_persistence:
        chat_history: list = []
        memory = None
    else:
        if memory is None:
            memory = get_memory()
        chat_history = memory.get_history(session_id)

    if agent_type == AgentType.SUPERVISOR:
        response, metadata = _invoke_supervisor(message, session_id, chat_history, use_persistence)
    elif agent_type == AgentType.HYBRID:
        response, metadata = _invoke_hybrid(message, session_id, chat_history, use_persistence)
    elif agent_type == AgentType.LEGACY:
        response, metadata = _invoke_legacy(message, session_id, chat_history, use_persistence)
    else:
        raise ValueError(f'Unknown agent type: {agent_type}')

    # Сохраняем в in-memory память только если не персистентный режим
    if not use_persistence and memory is not None and not metadata.get('toxicity_blocked', False):
        memory.add_exchange(session_id, message, response)

    metadata['agent_type'] = agent_type.value
    return response, metadata


# =============================================================================
# Private invoke functions
# =============================================================================


def _invoke_supervisor(
    query: str,
    session_id: str,
    chat_history: list[BaseMessage],
    with_persistence: bool = False,
) -> tuple[str, dict]:
    """Вызов Supervisor Graph."""
    from app.agent.supervisor import invoke_supervisor

    return invoke_supervisor(
        query,
        session_id=session_id,
        chat_history=chat_history,
        with_persistence=with_persistence,
    )


def _invoke_hybrid(
    query: str,
    session_id: str,
    chat_history: list[BaseMessage],
    with_persistence: bool = False,
) -> tuple[str, dict]:
    """Вызов Hybrid Agent Graph."""
    from app.agent.hybrid import invoke_hybrid

    return invoke_hybrid(
        query,
        session_id=session_id,
        chat_history=chat_history,
        with_persistence=with_persistence,
    )


def _invoke_legacy(
    query: str,
    session_id: str,
    chat_history: list[BaseMessage],
    with_persistence: bool = False,
) -> tuple[str, dict]:
    """Вызов Legacy ReAct агента."""
    from app.agent.city_agent import create_city_agent, invoke_agent
    from app.services.toxicity import get_toxicity_filter

    # Проверяем токсичность
    toxicity_filter = get_toxicity_filter()
    should_process, toxic_response = toxicity_filter.filter_message(query)

    if not should_process:
        return toxic_response or 'Извините, я не могу обработать это сообщение.', {
            'toxicity_blocked': True,
            'handler': 'toxicity_filter',
        }

    # Создаём и вызываем агента (legacy поддерживает with_persistence нативно)
    agent = create_city_agent(with_persistence=with_persistence)
    response = invoke_agent(
        agent,
        query,
        chat_history=chat_history if not with_persistence else None,
        thread_id=session_id if with_persistence else None,
    )

    return response, {
        'handler': 'legacy_react',
        'toxicity_blocked': False,
    }


# =============================================================================
# Benchmark utilities
# =============================================================================


def benchmark_agents(
    queries: list[str],
    agent_types: list[AgentType] | None = None,
) -> dict:
    """
    Бенчмарк разных агентов на одинаковых запросах.

    Args:
        queries: Список запросов для тестирования
        agent_types: Список типов агентов (по умолчанию все)

    Returns:
        Словарь с результатами бенчмарка
    """
    import time

    if agent_types is None:
        agent_types = [AgentType.SUPERVISOR, AgentType.HYBRID]

    results: dict = {
        'queries': queries,
        'agents': {},
    }

    for agent_type in agent_types:
        agent_results: dict = {
            'responses': [],
            'times': [],
            'handlers': [],
            'errors': [],
        }

        for query in queries:
            start_time = time.time()
            try:
                # Используем уникальный session_id для каждого агента
                response, metadata = chat_with_metadata(
                    query,
                    session_id=f'benchmark_{agent_type.value}',
                    agent_type=agent_type,
                )
                elapsed = time.time() - start_time

                agent_results['responses'].append(response)
                agent_results['times'].append(elapsed)
                agent_results['handlers'].append(metadata.get('handler', 'unknown'))
                agent_results['errors'].append(None)

            except Exception as e:
                elapsed = time.time() - start_time
                agent_results['responses'].append(None)
                agent_results['times'].append(elapsed)
                agent_results['handlers'].append('error')
                agent_results['errors'].append(str(e))

        # Статистика
        valid_times = [t for t in agent_results['times'] if t is not None]
        agent_results['stats'] = {
            'total_time': sum(valid_times),
            'avg_time': sum(valid_times) / len(valid_times) if valid_times else 0,
            'min_time': min(valid_times) if valid_times else 0,
            'max_time': max(valid_times) if valid_times else 0,
            'error_count': len([e for e in agent_results['errors'] if e is not None]),
        }

        results['agents'][agent_type.value] = agent_results

    return results


def print_benchmark_results(results: dict) -> None:
    """Красиво выводит результаты бенчмарка."""
    print('\n' + '=' * 80)
    print('BENCHMARK RESULTS')
    print('=' * 80)

    queries = results['queries']

    for agent_name, agent_data in results['agents'].items():
        print(f"\n{'─' * 80}")
        print(f'Agent: {agent_name.upper()}')
        print('─' * 80)

        stats = agent_data['stats']
        print(f"Total time: {stats['total_time']:.2f}s")
        print(f"Avg time: {stats['avg_time']:.2f}s")
        print(f"Min/Max: {stats['min_time']:.2f}s / {stats['max_time']:.2f}s")
        print(f"Errors: {stats['error_count']}")

        print('\nDetails:')
        for i, query in enumerate(queries):
            time_taken = agent_data['times'][i]
            handler = agent_data['handlers'][i]
            error = agent_data['errors'][i]

            status = f'{time_taken:.2f}s [{handler}]' if not error else f'ERROR: {error}'
            print(f'  {i + 1}. "{query[:40]}..." → {status}')


# =============================================================================
# CLI
# =============================================================================


if __name__ == '__main__':
    import os
    import sys

    os.environ['LOG_LEVEL'] = 'INFO'
    from app.logging_config import configure_logging

    configure_logging()

    # Парсим аргументы
    agent_type = DEFAULT_AGENT_TYPE
    if '--supervisor' in sys.argv:
        agent_type = AgentType.SUPERVISOR
    elif '--hybrid' in sys.argv:
        agent_type = AgentType.HYBRID
    elif '--legacy' in sys.argv:
        agent_type = AgentType.LEGACY
    elif '--benchmark' in sys.argv:
        # Режим бенчмарка
        test_queries = [
            'Привет!',
            'Где ближайший МФЦ к Невскому проспекту?',
            'Как получить загранпаспорт?',
            'Спасибо!',
        ]
        results = benchmark_agents(test_queries)
        print_benchmark_results(results)
        sys.exit(0)

    print(f'\nИспользуется агент: {agent_type.value}')
    print('Команды: --supervisor, --hybrid, --legacy, --benchmark')
    print('=' * 60)

    test_queries = [
        'Привет!',
        'Где ближайший МФЦ к Невскому проспекту 1?',
        'Как получить загранпаспорт?',
        'Ты идиот!',
        'Спасибо!',
    ]

    for query in test_queries:
        print(f"\n{'─' * 60}")
        print(f'Запрос: {query}')
        print('─' * 60)

        response, meta = chat_with_metadata(query, agent_type=agent_type)

        print(f'Handler: {meta.get("handler", "N/A")}')
        print(f'Ответ: {response[:200]}{"..." if len(response) > 200 else ""}')

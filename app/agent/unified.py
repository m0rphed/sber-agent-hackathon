"""
Унифицированный API для агентов.

Позволяет легко переключаться между архитектурами:
- supervisor: Supervisor Graph (Вариант 2) - явный роутинг, direct tool calls
- hybrid: Hybrid Agent Graph (Вариант 3) - ReAct агент для tools
- legacy: Legacy ReAct Agent - старый подход с полным ReAct

Использование:
    from app.agent.unified import chat, AgentType

    # По умолчанию - supervisor
    response = chat("Как получить загранпаспорт?")

    # Явный выбор архитектуры
    response = chat("Где МФЦ?", agent_type=AgentType.HYBRID)

    # С историей
    response = chat("Спасибо!", session_id="user123")
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
    memory: ConversationMemory | None = None,
) -> str:
    """
    Унифицированный интерфейс для чата с агентом.

    Args:
        message: Сообщение пользователя
        session_id: ID сессии для сохранения контекста
        agent_type: Тип агента (supervisor, hybrid, legacy)
        memory: Экземпляр памяти (если None, используется глобальный)

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

    if memory is None:
        memory = get_memory()

    # Получаем историю
    chat_history = memory.get_history(session_id)

    logger.info(
        'unified_chat_start',
        agent_type=agent_type.value,
        session_id=session_id,
        message_preview=message[:100] + '...' if len(message) > 100 else message,
        history_length=len(chat_history),
    )

    # Вызываем нужный агент
    if agent_type == AgentType.SUPERVISOR:
        response, metadata = _invoke_supervisor(message, session_id, chat_history)
    elif agent_type == AgentType.HYBRID:
        response, metadata = _invoke_hybrid(message, session_id, chat_history)
    elif agent_type == AgentType.LEGACY:
        response, metadata = _invoke_legacy(message, session_id, chat_history)
    else:
        raise ValueError(f'Unknown agent type: {agent_type}')

    # Сохраняем в память (если не токсичный)
    if not metadata.get('toxicity_blocked', False):
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
) -> tuple[str, dict]:
    """
    Чат с возвратом метаданных.

    Args:
        message: Сообщение пользователя
        session_id: ID сессии
        agent_type: Тип агента
        memory: Экземпляр памяти

    Returns:
        Кортеж (ответ, метаданные)
    """
    if isinstance(agent_type, str):
        try:
            agent_type = AgentType(agent_type.lower())
        except ValueError:
            agent_type = DEFAULT_AGENT_TYPE

    if memory is None:
        memory = get_memory()

    chat_history = memory.get_history(session_id)

    if agent_type == AgentType.SUPERVISOR:
        response, metadata = _invoke_supervisor(message, session_id, chat_history)
    elif agent_type == AgentType.HYBRID:
        response, metadata = _invoke_hybrid(message, session_id, chat_history)
    elif agent_type == AgentType.LEGACY:
        response, metadata = _invoke_legacy(message, session_id, chat_history)
    else:
        raise ValueError(f'Unknown agent type: {agent_type}')

    if not metadata.get('toxicity_blocked', False):
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
) -> tuple[str, dict]:
    """Вызов Supervisor Graph."""
    from app.agent.supervisor import invoke_supervisor

    return invoke_supervisor(query, session_id, chat_history)


def _invoke_hybrid(
    query: str,
    session_id: str,
    chat_history: list[BaseMessage],
) -> tuple[str, dict]:
    """Вызов Hybrid Agent Graph."""
    from app.agent.hybrid import invoke_hybrid

    return invoke_hybrid(query, session_id, chat_history)


def _invoke_legacy(
    query: str,
    session_id: str,
    chat_history: list[BaseMessage],
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

    # Создаём и вызываем агента
    agent = create_city_agent(with_persistence=False)
    response = invoke_agent(agent, query, chat_history)

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

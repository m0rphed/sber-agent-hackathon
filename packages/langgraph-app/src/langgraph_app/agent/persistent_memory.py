"""
Единообразная персистентная (сохраняющаяся) память для llm-агента

Поддерживает два режима:
- PostgreSQL (production): если указан POSTGRES_CHECKPOINTER_URL
- MemorySaver (fallback/dev): если PostgreSQL не настроен

Предоставляет унифицированный API для получения истории чата.
"""

from pathlib import Path
import sqlite3
from typing import Union

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver

from langgraph_app.agent.utils import langchain_cast_sqlite_config as cast_sqlite_config
from langgraph_app.config import MEMORY_DB_PATH, POSTGRES_CHECKPOINTER_URL
from langgraph_app.logging_config import get_logger

logger = get_logger(__name__)

# глобальные объекты для сохранения состояния
_db_connection: sqlite3.Connection | None = None
_checkpointer: BaseCheckpointSaver | None = None
_checkpointer_type: str | None = None  # "postgres" или "memory"


def _create_postgres_checkpointer():
    """
    Создаёт PostgreSQL checkpointer.
    
    Returns:
        PostgresSaver instance
    
    Raises:
        ImportError: если langgraph-checkpoint-postgres не установлен
    """
    from langgraph.checkpoint.postgres import PostgresSaver
    
    saver = PostgresSaver.from_conn_string(POSTGRES_CHECKPOINTER_URL)
    saver.setup()  # Создаёт таблицы если не существуют
    return saver


def _create_memory_checkpointer() -> MemorySaver:
    """
    Создаёт MemorySaver checkpointer (fallback для dev).
    
    Примечание: Это in-memory хранилище, данные теряются при перезапуске.
    Для production используйте PostgreSQL через POSTGRES_CHECKPOINTER_URL.
    
    Returns:
        MemorySaver instance
    """
    return MemorySaver()


def get_db_connection() -> sqlite3.Connection:
    """
    Возвращает SQLite соединение для персистентной памяти.
    
    DEPRECATED: Используйте get_checkpointer() напрямую.

    Returns:
        sqlite3.Connection к базе данных памяти
    """
    global _db_connection

    if _db_connection is None:
        db_path = Path(MEMORY_DB_PATH)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _db_connection = sqlite3.connect(str(db_path), check_same_thread=False)

    return _db_connection


def get_checkpointer() -> BaseCheckpointSaver:
    """
    Возвращает checkpointer для персистентной памяти.
    
    Логика выбора:
    - Если POSTGRES_CHECKPOINTER_URL указан → PostgresSaver
    - Иначе → MemorySaver (fallback)

    Returns:
        BaseCheckpointSaver (PostgresSaver или MemorySaver)
    """
    global _checkpointer, _checkpointer_type

    if _checkpointer is None:
        if POSTGRES_CHECKPOINTER_URL:
            try:
                _checkpointer = _create_postgres_checkpointer()
                _checkpointer_type = "postgres"
                logger.info("checkpointer_initialized", type="postgres")
            except ImportError as e:
                logger.warning(
                    "postgres_checkpointer_import_error",
                    error=str(e),
                    fallback="memory",
                )
                _checkpointer = _create_memory_checkpointer()
                _checkpointer_type = "memory"
                logger.info("checkpointer_initialized", type="memory", reason="postgres_import_failed")
            except Exception as e:
                logger.error(
                    "postgres_checkpointer_connection_error",
                    error=str(e),
                    fallback="memory",
                )
                _checkpointer = _create_memory_checkpointer()
                _checkpointer_type = "memory"
                logger.info("checkpointer_initialized", type="memory", reason="postgres_connection_failed")
        else:
            _checkpointer = _create_memory_checkpointer()
            _checkpointer_type = "memory"
            logger.info("checkpointer_initialized", type="memory")

    return _checkpointer


def get_checkpointer_type() -> str:
    """
    Возвращает тип текущего checkpointer.
    
    Returns:
        "postgres" или "memory"
    """
    global _checkpointer_type
    
    if _checkpointer_type is None:
        get_checkpointer()  # Инициализируем если ещё не
    
    return _checkpointer_type or "unknown"


def get_chat_history(thread_id: str) -> list[BaseMessage]:
    """
    Получить историю чата из персистентного хранилища.

    Читает последний checkpoint для указанного thread_id
    и извлекает сообщения.

    Args:
        thread_id: ID потока/чата (формат: user_id_chat_id)

    Returns:
        Список сообщений LangChain (HumanMessage, AIMessage)
    """
    checkpointer = get_checkpointer()

    config = {'configurable': {'thread_id': thread_id, 'checkpoint_ns': ''}}
    _config_runnable = cast_sqlite_config(config)
    try:
        checkpoint = checkpointer.get(_config_runnable)

        if checkpoint is None:
            return []

        # извлекаем сообщения из checkpoint
        channel_values = checkpoint.get('channel_values', {})
        messages = channel_values.get('messages', [])

        # фильтруем только HumanMessage и AIMessage (без ToolMessage и т.д.)
        result: list[BaseMessage] = []
        for msg in messages:
            if isinstance(msg, (HumanMessage, AIMessage)):
                result.append(msg)
            elif hasattr(msg, 'type'):
                # для сериализованных сообщений
                if msg.type == 'human':
                    result.append(HumanMessage(content=msg.content))
                elif msg.type == 'ai' and msg.content:
                    # AI сообщения с пустым content - это вызовы инструментов
                    result.append(AIMessage(content=msg.content))

        return result

    except Exception as e:
        # база может быть пустой или повреждённой
        print(f'Ошибка чтения истории чата {thread_id}: {e}')
        return []


def clear_chat_history(thread_id: str) -> bool:
    """
    Очистить историю чата.

    ВНИМАНИЕ: SqliteSaver не имеет прямого метода удаления.
    Эта функция удаляет записи напрямую из таблиц.
    (TODO: проверить безопасное удаление записей)

    Args:
        thread_id: ID потока/чата

    Returns:
        True если очистка успешна
    """
    conn = get_db_connection()

    try:
        cursor = conn.cursor()

        # SqliteSaver хранит данные в таблицах checkpoints и writes
        # thread_id хранится в поле thread_id

        cursor.execute(
            'DELETE FROM checkpoints WHERE thread_id = ?',
            (thread_id,),
        )
        cursor.execute(
            'DELETE FROM writes WHERE thread_id = ?',
            (thread_id,),
        )

        conn.commit()
        return True

    except Exception as e:
        print(f'Ошибка очистки чата {thread_id}: {e}')
        return False


def get_all_thread_ids() -> list[str]:
    """
    Получить все thread_id из базы данных.

    Полезно для отладки и миграции данных.

    Returns:
        Список уникальных thread_id
    """
    conn = get_db_connection()

    try:
        cursor = conn.cursor()
        cursor.execute('SELECT DISTINCT thread_id FROM checkpoints')
        rows = cursor.fetchall()
        return [row[0] for row in rows]

    except Exception as e:
        print(f'Ошибка получения списка thread_id: {e}')
        return []


def get_user_thread_ids(user_id: str) -> list[str]:
    """
    Получить все thread_id для конкретного пользователя.

    Предполагает формат thread_id: {user_id}_{chat_id}

    Args:
        user_id: ID пользователя

    Returns:
        Список thread_id этого пользователя
    """
    all_threads = get_all_thread_ids()
    prefix = f'{user_id}_'
    return [tid for tid in all_threads if tid.startswith(prefix)]


def messages_to_ui_format(messages: list[BaseMessage]) -> list[dict]:
    """
    Конвертировать LangChain сообщения в формат UI.

    Args:
        messages: Список BaseMessage от LangChain

    Returns:
        Список словарей {'role': 'user'|'assistant', 'content': str}
    """
    result = []
    for msg in messages:
        if isinstance(msg, HumanMessage) or (hasattr(msg, 'type') and msg.type == 'human'):
            result.append({'role': 'user', 'content': msg.content})
        elif isinstance(msg, AIMessage) or (hasattr(msg, 'type') and msg.type == 'ai'):
            if msg.content:  # пропускаем пустые AI сообщения (вызовы tools)
                result.append({'role': 'assistant', 'content': msg.content})
    return result


# Для обратной совместимости с in-memory режимом
# можно использовать ConversationMemory из memory.py для CLI/тестов

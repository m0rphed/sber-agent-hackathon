"""
Единообразная персистентная (сохраняющаяся) память для llm-агента

- использует SqliteSaver от `langgraph` для хранения состояния агента;
- предоставляет унифицированный API для получения истории чата, которое может использовать UI;

Источником данных сообщений - с его помощью и агент, и UI получают чаты/состояние переписки.
"""

from pathlib import Path
import sqlite3
from typing import cast

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables.config import CONFIG_KEYS, COPIABLE_KEYS
from langgraph.checkpoint.sqlite import RunnableConfig, SqliteSaver
from langgraph_app.config import MEMORY_DB_PATH

# глобальные объекты для сохранения состояния
# (TODO: улучшить потоковую безопасность)
_db_connection: sqlite3.Connection | None = None
_checkpointer: SqliteSaver | None = None


def langchain_cast_sqlite_config(config: dict[str, dict | object]) -> RunnableConfig:
    res = cast(
        'RunnableConfig',
        {
            k: v.copy() if k in COPIABLE_KEYS else v  # type: ignore[attr-defined]
            for k, v in config.items()
            if v is not None and k in CONFIG_KEYS
        },
    )
    return res


def get_db_connection() -> sqlite3.Connection:
    """
    Возвращает SQLite соединение для персистентной памяти

    Returns:
        sqlite3.Connection к базе данных памяти
    """
    global _db_connection

    if _db_connection is None:
        # создаём директорию если не существует
        db_path = Path(MEMORY_DB_PATH)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # создаём подключение к SQLite
        _db_connection = sqlite3.connect(str(db_path), check_same_thread=False)

    return _db_connection


def get_checkpointer() -> SqliteSaver:
    """
    Возвращает SQLite checkpointer (`SqliteSaver`) для персистентной памяти

    Returns:
        SqliteSaver для сохранения состояния агента
    """
    global _checkpointer

    if _checkpointer is None:
        conn = get_db_connection()
        _checkpointer = SqliteSaver(conn)

    return _checkpointer


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
    _config_runnable = langchain_cast_sqlite_config(config)
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

"""
SQLite storage для данных пользователей (чаты, настройки).

Хранит:
- user_chats: список чатов каждого пользователя
- chat_messages: история сообщений (опционально, можно использовать ConversationMemory)
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sqlite3

from app.config import DATA_DIR

# путь к БД пользовательских данных
USER_DATA_DB_PATH = DATA_DIR / 'user_data.db'


@dataclass
class ChatInfo:
    """
    Информация о чате
    """

    chat_id: str
    user_id: str
    title: str
    created_at: str

    def to_dict(self) -> dict:
        return {
            'id': self.chat_id,
            'title': self.title,
            'created_at': self.created_at,
        }


class UserDataStorage:
    """
    SQLite хранилище для данных пользователей.

    Таблицы:
    - user_chats: чаты пользователей
    """

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path) if db_path else USER_DATA_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Создаёт новое соединение с БД"""
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """
        Инициализирует таблицы БД
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # таблица чатов пользователей
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS user_chats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(chat_id, user_id)
                )
            """
            )

            # индекс для быстрого поиска по user_id
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_user_chats_user_id
                ON user_chats(user_id)
            """
            )

            conn.commit()
        finally:
            conn.close()

    # CRUD для чатов в streamlit

    def create_chat(self, user_id: str, chat_id: str, title: str) -> ChatInfo:
        """
        Создаёт новый чат для пользователя.

        Args:
            user_id: ID пользователя
            chat_id: ID чата
            title: Название чата

        Returns:
            ChatInfo с данными созданного чата
        """
        created_at = datetime.now().isoformat()

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO user_chats (chat_id, user_id, title, created_at)
                VALUES (?, ?, ?, ?)
            """,
                (chat_id, user_id, title, created_at),
            )
            conn.commit()
        finally:
            conn.close()

        return ChatInfo(
            chat_id=chat_id,
            user_id=user_id,
            title=title,
            created_at=created_at,
        )

    def get_user_chats(self, user_id: str) -> list[ChatInfo]:
        """
        Получает все чаты пользователя.

        Args:
            user_id: ID пользователя

        Returns:
            Список ChatInfo, отсортированный по дате создания (новые первые)
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT chat_id, user_id, title, created_at
                FROM user_chats
                WHERE user_id = ?
                ORDER BY created_at DESC
            """,
                (user_id,),
            )
            rows = cursor.fetchall()
        finally:
            conn.close()

        return [
            ChatInfo(
                chat_id=row['chat_id'],
                user_id=row['user_id'],
                title=row['title'],
                created_at=row['created_at'],
            )
            for row in rows
        ]

    def update_chat_title(self, user_id: str, chat_id: str, new_title: str) -> bool:
        """
        Обновляет название чата.

        Returns:
            True если чат был обновлён
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE user_chats
                SET title = ?
                WHERE user_id = ? AND chat_id = ?
            """,
                (new_title, user_id, chat_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def delete_chat(self, user_id: str, chat_id: str) -> bool:
        """
        Удаляет чат пользователя.

        Returns:
            True если чат был удалён
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM user_chats
                WHERE user_id = ? AND chat_id = ?
            """,
                (user_id, chat_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def delete_all_user_chats(self, user_id: str) -> int:
        """
        Удаляет все чаты пользователя.

        Returns:
            Количество удалённых чатов
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM user_chats
                WHERE user_id = ?
            """,
                (user_id,),
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    def chat_exists(self, user_id: str, chat_id: str) -> bool:
        """
        Проверяет существование чата
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 1 FROM user_chats
                WHERE user_id = ? AND chat_id = ?
            """,
                (user_id, chat_id),
            )
            return cursor.fetchone() is not None
        finally:
            conn.close()


# singleton instance
_storage_instance: UserDataStorage | None = None


def get_user_storage() -> UserDataStorage:
    """
    Возвращает singleton экземпляр хранилища
    """
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = UserDataStorage()
    return _storage_instance

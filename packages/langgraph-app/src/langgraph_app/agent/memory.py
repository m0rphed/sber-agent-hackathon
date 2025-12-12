"""
Управление памятью диалога для городского помощника.

Поддерживает:
- Хранение истории сообщений по session_id
- Ограничение размера истории
- Очистка старых сессий
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from langgraph_app.config import AgentConfig, get_agent_config


@dataclass
class ConversationSession:
    """
    Сессия диалога
    """

    session_id: str
    messages: list[BaseMessage] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)

    def add_human_message(self, content: str) -> None:
        """
        Добавить сообщение пользователя
        """
        self.messages.append(HumanMessage(content=content))
        self.last_activity = datetime.now()

    def add_ai_message(self, content: str) -> None:
        """
        Добавить сообщение ассистента
        """
        self.messages.append(AIMessage(content=content))
        self.last_activity = datetime.now()

    def get_history(self, max_messages: int | None = None) -> list[BaseMessage]:
        """
        Получить историю сообщений

        Args:
            max_messages: Максимальное количество сообщений (None = все)

        Returns:
            Список сообщений
        """
        if max_messages is None:
            return self.messages.copy()
        return self.messages[-max_messages:]

    def clear(self) -> None:
        """
        Очистить историю
        """
        self.messages.clear()
        self.last_activity = datetime.now()


class ConversationMemory:
    """
    Менеджер памяти диалогов

    Хранит историю сообщений для нескольких сессий
    """

    def __init__(
        self,
        max_messages_per_session: int | None = None,
        session_ttl_hours: int = 24,
        config: AgentConfig | None = None,
    ):
        """
        Args:
            max_messages_per_session: Максимум сообщений на сессию (None = из конфига)
            session_ttl_hours: Время жизни сессии в часах
            config: Конфигурация агента (None = глобальный)
        """
        self._config = config or get_agent_config()
        self._sessions: dict[str, ConversationSession] = {}

        if max_messages_per_session is not None:
            self.max_messages = max_messages_per_session
        else:
            self.max_messages = self._config.memory.max_messages_per_session

        self.session_ttl = timedelta(hours=session_ttl_hours)

    def get_or_create_session(self, session_id: str) -> ConversationSession:
        """
        Получить или создать сессию
        """
        if session_id not in self._sessions:
            self._sessions[session_id] = ConversationSession(session_id=session_id)
        return self._sessions[session_id]

    def add_exchange(
        self,
        session_id: str,
        user_message: str,
        ai_response: str,
    ) -> None:
        """
        Добавить обмен сообщениями (вопрос + ответ)

        Args:
            session_id: ID сессии
            user_message: Сообщение пользователя
            ai_response: Ответ ассистента
        """
        session = self.get_or_create_session(session_id)
        session.add_human_message(user_message)
        session.add_ai_message(ai_response)

        # обрезаем историю если превышен лимит
        if len(session.messages) > self.max_messages:
            # оставляем последние N сообщений
            session.messages = session.messages[-self.max_messages :]

    def get_history(
        self,
        session_id: str,
        max_messages: int | None = None,
    ) -> list[BaseMessage]:
        """
        Получить историю диалога

        Args:
            session_id: ID сессии
            max_messages: Лимит сообщений (None = настройка по умолчанию)

        Returns:
            Список сообщений LangChain
        """
        if session_id not in self._sessions:
            return []

        limit = max_messages or self.max_messages
        return self._sessions[session_id].get_history(limit)

    def clear_session(self, session_id: str) -> None:
        """
        Очистить сессию
        """
        if session_id in self._sessions:
            self._sessions[session_id].clear()

    def delete_session(self, session_id: str) -> None:
        """
        Удалить сессию полностью
        """
        self._sessions.pop(session_id, None)

    def cleanup_expired(self) -> int:
        """
        Удалить просроченные сессии

        Returns:
            Количество удалённых сессий
        """
        now = datetime.now()
        expired = [
            sid
            for sid, session in self._sessions.items()
            if now - session.last_activity > self.session_ttl
        ]
        for sid in expired:
            del self._sessions[sid]
        return len(expired)

    def get_session_info(self, session_id: str) -> dict | None:
        """
        Получить информацию о сессии
        """
        if session_id not in self._sessions:
            return None

        session = self._sessions[session_id]
        return {
            'session_id': session_id,
            'message_count': len(session.messages),
            'created_at': session.created_at.isoformat(),
            'last_activity': session.last_activity.isoformat(),
        }

    @property
    def active_sessions_count(self) -> int:
        """
        Количество активных сессий.
        """
        return len(self._sessions)


# глобальный экземпляр памяти (singleton)
_memory_instance: ConversationMemory | None = None


def get_memory() -> ConversationMemory:
    """
    Получить глобальный экземпляр памяти
    """
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = ConversationMemory()
    return _memory_instance

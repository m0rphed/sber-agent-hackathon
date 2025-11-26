from pathlib import Path
import sqlite3

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.sqlite import SqliteSaver
import pytest

from app.agent.memory import ConversationMemory, ConversationSession, get_memory


class TestConversationSession:
    """
    Тесты для сессии диалога
    """

    def test_create_session(self):
        """
        Тест создания сессии
        """
        session = ConversationSession(session_id='test')

        assert session.session_id == 'test'
        assert len(session.messages) == 0
        assert session.created_at is not None

    def test_add_human_message(self):
        """
        Тест добавления сообщения пользователя
        """
        session = ConversationSession(session_id='test')
        session.add_human_message('Привет!')

        assert len(session.messages) == 1
        assert session.messages[0].content == 'Привет!'
        assert session.messages[0].type == 'human'

    def test_add_ai_message(self):
        """
        Тест добавления сообщения ассистента
        """
        session = ConversationSession(session_id='test')
        session.add_ai_message('Здравствуйте!')

        assert len(session.messages) == 1
        assert session.messages[0].content == 'Здравствуйте!'
        assert session.messages[0].type == 'ai'

    def test_get_history(self):
        """
        Тест получения истории
        """
        session = ConversationSession(session_id='test')
        session.add_human_message('Вопрос 1')
        session.add_ai_message('Ответ 1')
        session.add_human_message('Вопрос 2')
        session.add_ai_message('Ответ 2')

        history = session.get_history()
        assert len(history) == 4

        # С лимитом
        history_limited = session.get_history(max_messages=2)
        assert len(history_limited) == 2
        assert history_limited[0].content == 'Вопрос 2'

    def test_clear_session(self):
        """
        Тест очистки сессии
        """
        session = ConversationSession(session_id='test')
        session.add_human_message('Сообщение')
        session.clear()

        assert len(session.messages) == 0


class TestConversationMemory:
    """
    Тесты для менеджера памяти
    """

    def test_create_memory(self):
        """
        Тест создания менеджера памяти
        """
        memory = ConversationMemory()

        assert memory.max_messages == 20
        assert memory.active_sessions_count == 0

    def test_get_or_create_session(self):
        """
        Тест получения/создания сессии
        """
        memory = ConversationMemory()

        session1 = memory.get_or_create_session('user1')
        session2 = memory.get_or_create_session('user1')

        assert session1 is session2
        assert memory.active_sessions_count == 1

    def test_add_exchange(self):
        """
        Тест добавления обмена сообщениями
        """
        memory = ConversationMemory()
        memory.add_exchange('user1', 'Привет!', 'Здравствуйте!')

        history = memory.get_history('user1')
        assert len(history) == 2
        assert history[0].content == 'Привет!'
        assert history[1].content == 'Здравствуйте!'

    def test_multiple_sessions(self):
        """
        Тест нескольких сессий
        """
        memory = ConversationMemory()

        memory.add_exchange('user1', 'Вопрос 1', 'Ответ 1')
        memory.add_exchange('user2', 'Вопрос 2', 'Ответ 2')

        assert memory.active_sessions_count == 2

        history1 = memory.get_history('user1')
        history2 = memory.get_history('user2')

        assert history1[0].content == 'Вопрос 1'
        assert history2[0].content == 'Вопрос 2'

    def test_max_messages_limit(self):
        """
        Тест ограничения количества сообщений
        """
        memory = ConversationMemory(max_messages_per_session=4)

        # добавляем 3 обмена (6 сообщений)
        memory.add_exchange('user1', 'Q1', 'A1')
        memory.add_exchange('user1', 'Q2', 'A2')
        memory.add_exchange('user1', 'Q3', 'A3')

        history = memory.get_history('user1')
        # должно остаться только 4 последних
        assert len(history) == 4
        assert history[0].content == 'Q2'

    def test_clear_session(self):
        """
        Тест очистки сессии
        """
        memory = ConversationMemory()
        memory.add_exchange('user1', 'Q', 'A')
        memory.clear_session('user1')

        history = memory.get_history('user1')
        assert len(history) == 0
        # сессия всё ещё существует
        assert memory.active_sessions_count == 1

    def test_delete_session(self):
        """
        Тест удаления сессии
        """
        memory = ConversationMemory()
        memory.add_exchange('user1', 'Q', 'A')
        memory.delete_session('user1')

        assert memory.active_sessions_count == 0
        assert memory.get_history('user1') == []

    def test_get_session_info(self):
        """
        Тест получения информации о сессии
        """
        memory = ConversationMemory()
        memory.add_exchange('user1', 'Q', 'A')

        info = memory.get_session_info('user1')

        assert info is not None
        assert info['session_id'] == 'user1'
        assert info['message_count'] == 2

    def test_nonexistent_session_info(self):
        """
        Тест информации о несуществующей сессии
        """
        memory = ConversationMemory()
        info = memory.get_session_info('nonexistent')

        assert info is None


class TestGlobalMemory:
    """
    Тесты для глобального экземпляра памяти
    """

    def test_get_memory_singleton(self):
        """
        Тест, что get_memory возвращает singleton
        """
        memory1 = get_memory()
        memory2 = get_memory()

        assert memory1 is memory2


class TestSqliteCheckpointerPersistence:
    """
    Тесты для персистентности памяти через SQLite checkpointer (LangGraph)
    """

    # флаг для сохранения БД в data/test_data для отладки
    # True, чтобы сохранить БД и посмотреть её вручную
    KEEP_TEST_DB = False

    @pytest.fixture
    def temp_db_path(self, tmp_path: Path, request: pytest.FixtureRequest) -> Path:
        """
        Временный путь к БД для тестов

        Если KEEP_TEST_DB=True, БД сохраняется в data/test_data/<имя_теста>.db
        """
        if self.KEEP_TEST_DB:
            # сохраняем в data/test_data для отладки
            test_data_dir = Path(__file__).parent.parent / 'data' / 'test_data'
            test_data_dir.mkdir(parents=True, exist_ok=True)
            db_path = test_data_dir / f'{request.node.name}.db'
            # удаляем старую БД если есть
            if db_path.exists():
                db_path.unlink()
            return db_path
        else:
            # используем временную директорию pytest
            return tmp_path / 'test_checkpoints.db'

    def test_checkpointer_creates_database(self, temp_db_path: Path):
        """
        Тест: checkpointer создаёт файл базы данных
        """
        # создаём checkpointer
        conn = sqlite3.connect(str(temp_db_path), check_same_thread=False)
        checkpointer = SqliteSaver(conn)

        # вызываем setup для создания таблиц
        checkpointer.setup()

        # закрываем соединение
        conn.close()

        # проверяем, что файл БД создан
        assert temp_db_path.exists()
        assert temp_db_path.stat().st_size > 0

    def test_checkpointer_saves_and_retrieves_state(self, temp_db_path: Path):
        """
        Тест: checkpointer сохраняет и восстанавливает состояние
        """
        thread_id = 'test_thread_001'
        config = {'configurable': {'thread_id': thread_id, 'checkpoint_ns': ''}}

        # создаём checkpointer и сохраняем checkpoint
        conn = sqlite3.connect(str(temp_db_path), check_same_thread=False)
        checkpointer = SqliteSaver(conn)
        checkpointer.setup()

        # создаём тестовые сообщения
        messages = [
            HumanMessage(content='Привет!'),
            AIMessage(content='Здравствуйте! Чем могу помочь?'),
        ]

        # сохраняем checkpoint
        checkpoint = {
            'v': 1,
            'ts': '2025-01-01T00:00:00Z',
            'id': 'checkpoint_1',
            'channel_values': {'messages': messages},
            'channel_versions': {},
            'versions_seen': {},
            'pending_sends': [],
        }
        checkpointer.put(config, checkpoint, {}, {})

        # получаем checkpoint обратно
        retrieved = checkpointer.get(config)

        conn.close()

        # проверяем, что данные сохранились
        assert retrieved is not None
        assert 'channel_values' in retrieved
        assert 'messages' in retrieved['channel_values']
        assert len(retrieved['channel_values']['messages']) == 2

    def test_checkpointer_persists_between_connections(self, temp_db_path: Path):
        """
        Тест: данные сохраняются между подключениями к БД
        """
        thread_id = 'persistent_thread'
        _config = {'configurable': {'thread_id': thread_id, 'checkpoint_ns': ''}}

        # первое подключение: сохраняем данные
        conn1 = sqlite3.connect(str(temp_db_path), check_same_thread=False)
        checkpointer1 = SqliteSaver(conn1)
        checkpointer1.setup()

        messages = [
            HumanMessage(content='Меня зовут Алексей'),
            AIMessage(content='Приятно познакомиться, Алексей!'),
        ]

        _checkpoint = {
            'v': 1,
            'ts': '2025-01-01T00:00:00Z',
            'id': 'ckpt_1',
            'channel_values': {'messages': messages},
            'channel_versions': {},
            'versions_seen': {},
            'pending_sends': [],
        }
        checkpointer1.put(_config, _checkpoint, {}, {})
        conn1.close()

        # второе подключение: читаем данные
        conn2 = sqlite3.connect(str(temp_db_path), check_same_thread=False)
        checkpointer2 = SqliteSaver(conn2)

        retrieved = checkpointer2.get(_config)
        conn2.close()

        # проверяем персистентность
        assert retrieved is not None
        msgs = retrieved['channel_values']['messages']
        assert len(msgs) == 2
        assert msgs[0].content == 'Меня зовут Алексей'
        assert msgs[1].content == 'Приятно познакомиться, Алексей!'

    def test_checkpointer_isolates_threads(self, temp_db_path: Path):
        """
        Тест: разные thread_id изолированы друг от друга
        """
        conn = sqlite3.connect(str(temp_db_path), check_same_thread=False)
        checkpointer = SqliteSaver(conn)
        checkpointer.setup()

        # сохраняем данные для двух разных потоков
        config_user1 = {'configurable': {'thread_id': 'user_alice', 'checkpoint_ns': ''}}
        config_user2 = {'configurable': {'thread_id': 'user_bob', 'checkpoint_ns': ''}}

        checkpoint_alice = {
            'v': 1,
            'ts': '2025-01-01T00:00:00Z',
            'id': 'ckpt_alice',
            'channel_values': {
                'messages': [HumanMessage(content='Я Алиса')],
            },
            'channel_versions': {},
            'versions_seen': {},
            'pending_sends': [],
        }

        checkpoint_bob = {
            'v': 1,
            'ts': '2025-01-01T00:00:01Z',
            'id': 'ckpt_bob',
            'channel_values': {
                'messages': [HumanMessage(content='Я Боб')],
            },
            'channel_versions': {},
            'versions_seen': {},
            'pending_sends': [],
        }

        checkpointer.put(config_user1, checkpoint_alice, {}, {})
        checkpointer.put(config_user2, checkpoint_bob, {}, {})

        # получаем данные для каждого пользователя
        retrieved_alice = checkpointer.get(config_user1)
        retrieved_bob = checkpointer.get(config_user2)

        conn.close()

        # проверяем изоляцию
        assert retrieved_alice is not None
        assert retrieved_bob is not None

        alice_msgs = retrieved_alice['channel_values']['messages']
        bob_msgs = retrieved_bob['channel_values']['messages']

        assert len(alice_msgs) == 1
        assert len(bob_msgs) == 1
        assert alice_msgs[0].content == 'Я Алиса'
        assert bob_msgs[0].content == 'Я Боб'

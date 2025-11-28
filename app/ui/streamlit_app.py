"""
Streamlit UI для агента городского помощника
"""

from pathlib import Path
import sys
import uuid

from langgraph.graph.state import CompiledStateGraph
import streamlit as st
import streamlit_authenticator as stauth
import yaml

# добавляем корень проекта в путь для импортов
PROJECT_ROOT = Path(__file__).parent.parent.parent
# print(f'Добавление в sys.path: {Path(__file__).parent.parent}')
sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.city_agent import create_city_agent, safe_chat  # noqa: E402
from app.agent.persistent_memory import (  # noqa: E402
    clear_chat_history,
    get_chat_history,
    messages_to_ui_format,
)
from app.storage.user_data import get_user_storage  # noqa: E402

# конфигурация страницы

st.set_page_config(
    page_title='Городской помощник СПб',
    page_icon='🏛️',
    layout='centered',
    initial_sidebar_state='expanded',
)


# загрузка CSS стилей


def load_css():
    """
    Загружает кастомные CSS стили
    """
    css_path = Path(__file__).parent / 'styles.css'
    if css_path.exists():
        with open(css_path, encoding='utf-8') as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)


load_css()


# простая аутентификация (опционально)

# путь к конфигу аутентификации
AUTH_CONFIG_PATH = Path(__file__).parent / 'auth_config.yaml'


def load_auth_config() -> dict:
    """
    Загружает конфиг аутентификации
    """
    if AUTH_CONFIG_PATH.exists():
        with open(AUTH_CONFIG_PATH, encoding='utf-8') as f:
            return yaml.safe_load(f)
    return {}


def save_auth_config(config: dict) -> None:
    """
    Сохраняет конфиг аутентификации (после регистрации)
    """
    with open(AUTH_CONFIG_PATH, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)


def simple_auth() -> bool:
    """
    Аутентификация через streamlit-authenticator

    Returns:
        True если пользователь авторизован
    """
    # проверяем, включена ли аутентификация через secrets
    auth_enabled = False
    try:
        auth_enabled = st.secrets.get('auth_enabled', False)
    except Exception:
        # secrets.toml не существует - это нормально
        pass

    if not auth_enabled:
        # аутентификация отключена - пускаем всех
        if 'user_id' not in st.session_state:
            _random_id = uuid.uuid4().hex[:8]
            st.session_state.user_id = f'anon_{_random_id}'
            st.session_state.username = 'Гость'
        return True

    # загружаем конфиг аутентификации
    auth_config = load_auth_config()

    if not auth_config:
        st.warning('Файл конфигурации auth_config.yaml не найден')
        return True

    # создаём authenticator
    authenticator = stauth.Authenticate(
        credentials=auth_config['credentials'],
        cookie_name=auth_config['cookie']['name'],
        cookie_key=auth_config['cookie']['key'],
        cookie_expiry_days=auth_config['cookie']['expiry_days'],
    )

    # сохраняем authenticator для logout
    st.session_state.authenticator = authenticator

    # проверяем статус до показа формы
    if st.session_state.get('authentication_status'):
        # успешная авторизация - не показываем форму
        st.session_state.user_id = st.session_state.get('username', 'unknown')
        st.session_state.username = st.session_state.get('name', 'Пользователь')
        return True

    # показываем header для страницы входа
    st.markdown(
        """
        <div class="app-header">
            <h1>🏛️ Городской помощник</h1>
            <p>Войдите или зарегистрируйтесь</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # вкладки: Вход / Регистрация
    tab_login, tab_register = st.tabs(['🔐 Вход', '📝 Регистрация'])

    with tab_login:
        # виджет логина
        authenticator.login(location='main')

        if st.session_state.get('authentication_status') is False:
            st.error('Неверное имя пользователя или пароль')
        elif st.session_state.get('authentication_status') is None:
            st.info('💡 Для демо: логин `demo`, пароль `demo123`')

    with tab_register:
        try:
            (
                email_of_registered_user,
                username_of_registered_user,
                name_of_registered_user,
            ) = authenticator.register_user(
                pre_authorized=auth_config.get('pre-authorized', {}).get('emails'),
                fields={
                    'Form name': 'Регистрация',
                    'Email': 'Email',
                    'Username': 'Имя пользователя',
                    'Password': 'Пароль',
                    'Repeat password': 'Повторите пароль',
                    'Password hint': 'Подсказка для пароля',
                    'Captcha': 'Captcha',
                    'Register': 'Зарегистрироваться',
                },
            )
            if email_of_registered_user:
                st.success(f'Пользователь {username_of_registered_user} успешно зарегистрирован!')
                # сохраняем обновлённый конфиг
                save_auth_config(auth_config)
                st.info('Теперь вы можете войти во вкладке "Вход"')
        except Exception as e:
            st.error(f'Ошибка регистрации: {e}')

    return False


# инициализация состояния


def init_session_state() -> None:
    """
    Инициализирует session_state
    """
    if 'messages' not in st.session_state:
        st.session_state.messages = []

    if 'agent' not in st.session_state:
        st.session_state.agent = None

    # флаг что чаты загружены из БД
    if 'chats_loaded' not in st.session_state:
        st.session_state.chats_loaded = False

    # список чатов пользователя: [{id, title, created_at}, ...]
    if 'user_chats' not in st.session_state:
        st.session_state.user_chats = []

    # текущий активный чат
    if 'current_chat_id' not in st.session_state:
        st.session_state.current_chat_id = None

    # загружаем чаты из SQLite при первом входе
    user_id = st.session_state.get('user_id', 'anon')
    if not st.session_state.chats_loaded and user_id != 'anon':
        _load_user_chats_from_db(user_id)
        st.session_state.chats_loaded = True

    # создаём первый чат если нет чатов
    if not st.session_state.user_chats:
        _create_new_chat()

    # session_id для агента = user_id + chat_id
    chat_id = st.session_state.get('current_chat_id', 'default')
    st.session_state.session_id = f'{user_id}_{chat_id}'

    # инициализируем агента сразу если ещё не создан
    if st.session_state.agent is None:
        try:
            # используем persistence=True для сохранения истории в SQLite
            st.session_state.agent = create_city_agent(with_persistence=True)
        except Exception as e:
            st.error(f'Ошибка инициализации агента: {e}')

    # загружаем историю сообщений из персистентного хранилища
    if not st.session_state.messages and st.session_state.session_id:
        _load_messages_from_persistent_storage()


def _load_user_chats_from_db(user_id: str) -> None:
    """
    Загружает чаты пользователя из SQLite
    """
    storage = get_user_storage()
    chats = storage.get_user_chats(user_id)

    st.session_state.user_chats = [chat.to_dict() for chat in chats]

    # устанавливаем текущий чат (первый в списке, если есть)
    if st.session_state.user_chats:
        st.session_state.current_chat_id = st.session_state.user_chats[0]['id']


def _load_messages_from_persistent_storage() -> None:
    """
    Загружает сообщения из персистентного хранилища (SqliteSaver)
    """
    thread_id = st.session_state.get('session_id')
    if not thread_id:
        return

    # получаем историю из SqliteSaver
    messages = get_chat_history(thread_id)
    # конвертируем в формат UI
    st.session_state.messages = messages_to_ui_format(messages)


def _create_new_chat() -> str:
    """
    Создаёт новый чат и возвращает его ID
    """
    user_id = st.session_state.get('user_id', 'anon')
    chat_id = uuid.uuid4().hex[:8]
    chat_num = len(st.session_state.user_chats) + 1
    title = f'Чат {chat_num}'

    # сохраняем в SQLite (для зарегистрированных пользователей)
    if user_id != 'anon' and not user_id.startswith('anon_'):
        storage = get_user_storage()
        chat_info = storage.create_chat(user_id, chat_id, title)
        st.session_state.user_chats.insert(0, chat_info.to_dict())  # новые сверху
    else:
        from datetime import datetime

        st.session_state.user_chats.insert(
            0,
            {
                'id': chat_id,
                'title': title,
                'created_at': datetime.now().isoformat(),
            },
        )

    st.session_state.current_chat_id = chat_id
    st.session_state.messages = []

    return chat_id


def _delete_chat(chat_id: str) -> None:
    """
    Удаляет чат
    """
    user_id = st.session_state.get('user_id', 'anon')

    # удаляем из SQLite (user_data.db)
    if user_id != 'anon' and not user_id.startswith('anon_'):
        storage = get_user_storage()
        storage.delete_chat(user_id, chat_id)

    # удаляем из session_state
    st.session_state.user_chats = [c for c in st.session_state.user_chats if c['id'] != chat_id]

    # очищаем историю из персистентного хранилища (memory.db)
    thread_id = f'{user_id}_{chat_id}'
    clear_chat_history(thread_id)

    # если удалили текущий чат - переключаемся
    if st.session_state.current_chat_id == chat_id:
        if st.session_state.user_chats:
            _switch_chat(st.session_state.user_chats[0]['id'])
        else:
            _create_new_chat()


def _switch_chat(chat_id: str) -> None:
    """
    Переключает на указанный чат
    """
    # переключаемся
    st.session_state.current_chat_id = chat_id

    # обновляем session_id (thread_id для агента)
    user_id = st.session_state.get('user_id', 'anon')
    st.session_state.session_id = f'{user_id}_{chat_id}'

    # загружаем сообщения из персистентного хранилища (SqliteSaver)
    _load_messages_from_persistent_storage()


def get_agent() -> CompiledStateGraph | None:
    """
    Возвращает или создаёт экземпляр агента
    """
    if st.session_state.agent is None:
        with st.spinner('🔄 Инициализация агента...'):
            try:
                # используем persistence=True для сохранения истории в SQLite
                st.session_state.agent = create_city_agent(with_persistence=True)
            except Exception as e:
                st.error(f'Ошибка инициализации агента: {e}')
                return None
    return st.session_state.agent


# компоненты UI


def render_header():
    """
    Отображает заголовок приложения
    """
    st.markdown(
        """
        <div class="app-header">
            <h1>🏛️ Городской помощник</h1>
            <p>AI-ассистент для жителей Санкт-Петербурга</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar():
    """
    Отображает боковую панель
    """
    with st.sidebar:
        st.markdown('### ⚙️ Настройки')

        # информация о пользователе
        username = st.session_state.get('username', 'Гость')
        st.markdown(f'👤 **{username}**')

        # кнопка выхода (только для авторизованных)
        if st.session_state.get('authentication_status'):
            authenticator = st.session_state.get('authenticator')
            if authenticator:
                authenticator.logout('🚪 Выйти', location='main', key='sidebar_logout')

        st.divider()

        # управление чатами
        st.markdown('### 💬 Чаты')

        # кнопка нового чата
        if st.button('➕ Новый чат', use_container_width=True):
            _create_new_chat()
            st.rerun()

        # список чатов пользователя с кнопками удаления
        for chat in st.session_state.user_chats:
            chat_id = chat['id']
            is_current = chat_id == st.session_state.current_chat_id

            # показываем чат как кнопку + кнопка удаления в одной строке
            btn_label = f'{"▶ " if is_current else ""}{chat["title"]}'

            # используем container для группировки
            chat_container = st.container()
            with chat_container:
                cols = st.columns([4, 1])
                with cols[0]:
                    if st.button(btn_label, key=f'chat_{chat_id}', use_container_width=True):
                        if not is_current:
                            _switch_chat(chat_id)
                            st.rerun()
                with cols[1]:
                    # кнопка удаления (не для единственного чата)
                    if len(st.session_state.user_chats) > 1:
                        if st.button('✕', key=f'del_{chat_id}', help='Удалить чат'):
                            _delete_chat(chat_id)
                            st.rerun()

        st.divider()

        # кнопка очистки текущего чата
        if st.button('🧹 Очистить текущий чат', use_container_width=True):
            st.session_state.messages = []
            # очищаем историю из персистентного хранилища
            clear_chat_history(st.session_state.session_id)
            st.rerun()

        st.divider()

        # информация о возможностях
        st.markdown('### 📋 Возможности')
        st.markdown(
            """
        - 🏢 Поиск ближайших МФЦ
        - 👴 Услуги для пенсионеров
        - 🏥 Информация о поликлиниках
        - 🎭 Культурные мероприятия
        - 📚 Справочная информация
        """
        )

        st.divider()

        # статус системы
        st.markdown('### 📊 Статус')
        agent_status = '🟢 Активен' if st.session_state.agent else '🟡 Не инициализирован'
        st.markdown(f'Агент: {agent_status}')
        st.markdown(f'Чатов: {len(st.session_state.user_chats)}')


def render_example_questions():
    """
    Отображает примеры вопросов
    """
    examples = [
        'Где ближайший МФЦ к Невскому проспекту?',
        'Какие льготы есть для пенсионеров?',
        'Как получить справку о регистрации?',
        'Какие документы нужны для загранпаспорта?',
    ]

    st.markdown('#### 💡 Примеры вопросов:')
    cols = st.columns(2)

    for i, example in enumerate(examples):
        with cols[i % 2]:
            if st.button(example, key=f'example_{i}', use_container_width=True):
                return example

    return None


def render_chat_messages():
    """
    Отображает историю сообщений
    """
    for message in st.session_state.messages:
        role = message['role']
        content = message['content']

        with st.chat_message(role):
            st.markdown(content)


def process_user_input(user_input: str) -> str:
    """
    Обрабатывает ввод пользователя и возвращает ответ

    Args:
        user_input: Сообщение пользователя

    Returns:
        Ответ агента
    """
    agent = get_agent()

    if agent is None:
        return '❌ Агент не инициализирован. Проверьте настройки.'

    try:
        response = safe_chat(
            agent=agent,
            user_message=user_input,
            session_id=st.session_state.session_id,
            use_persistence=True,  # используем SqliteSaver для персистентной памяти
        )
        return response
    except Exception as e:
        return f'❌ Ошибка при обработке запроса: {e}'


# основное приложение


def main():
    """
    Основная функция приложения
    """
    # аутентификация (если включена)
    if not simple_auth():
        return

    # инициализация состояния
    init_session_state()

    # отрисовка UI
    render_header()
    render_sidebar()

    # показать примеры вопросов (только если чат пустой)
    example_clicked = None
    if not st.session_state.messages:
        example_clicked = render_example_questions()
        st.divider()

    # показать историю сообщений
    render_chat_messages()

    # поле ввода
    user_input = st.chat_input('Задайте вопрос о городских услугах...')

    # обработка ввода (из поля или из примера)
    input_to_process = user_input or example_clicked

    if input_to_process:
        # добавляем сообщение пользователя
        st.session_state.messages.append(
            {
                'role': 'user',
                'content': input_to_process,
            }
        )

        # показываем сообщение пользователя
        with st.chat_message('user'):
            st.markdown(input_to_process)

        # получаем и показываем ответ
        with st.chat_message('assistant'):
            with st.spinner('🤔 Думаю...'):
                response = process_user_input(input_to_process)
            st.markdown(response)

        # сохраняем ответ
        st.session_state.messages.append(
            {
                'role': 'assistant',
                'content': response,
            }
        )

        st.rerun()


if __name__ == '__main__':
    main()

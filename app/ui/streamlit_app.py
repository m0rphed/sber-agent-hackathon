"""
Streamlit UI для агента городского помощника.

Использует LangGraph Server API через agent_sdk.
"""

import os
from pathlib import Path
import sys
import uuid

import pendulum
import streamlit as st
import streamlit_authenticator as stauth
import yaml

# добавляем корень проекта в путь для импортов
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Импортируем SDK функции
from agent_sdk.langgraph_functions_ui import (  # noqa: E402
    chat_sync,
    check_server_available,
    clear_thread_history,
    get_available_graphs,
    get_thread_history,
    stream_chat_with_status,
)
from app.storage.user_data import get_user_storage  # noqa: E402

# Проверяем доступность LangGraph Server
USE_LANGGRAPH_SERVER = os.getenv('USE_LANGGRAPH_SERVER', 'false').lower() == 'true'

# Проверяем реальную доступность сервера при старте
if USE_LANGGRAPH_SERVER:
    try:
        LANGGRAPH_SERVER_AVAILABLE = check_server_available()
    except Exception:
        LANGGRAPH_SERVER_AVAILABLE = False
else:
    LANGGRAPH_SERVER_AVAILABLE = False

# fallback на прямой вызов если сервер недоступен
if not LANGGRAPH_SERVER_AVAILABLE:
    from app.agent.persistent_memory import (  # noqa: E402
        clear_chat_history,
        get_chat_history,
        messages_to_ui_format,
    )
    from app.agent.supervisor import get_supervisor_graph, invoke_supervisor  # noqa: E402

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
            st.session_state.display_name = 'Гость'
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
        # ВАЖНО: используем 'username' от authenticator как user_id (это логин)
        # и сохраняем 'name' в отдельную переменную для отображения
        st.session_state.user_id = st.session_state.get('username', 'unknown')
        st.session_state.display_name = st.session_state.get('name', 'Пользователь')
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

    # загружаем чаты из SQLite при первом входе (только для зарегистрированных)
    user_id = st.session_state.get('user_id', 'anon')
    if not st.session_state.chats_loaded and user_id != 'anon' and not user_id.startswith('anon_'):
        _load_user_chats_from_db(user_id)
        st.session_state.chats_loaded = True

    # создаём первый чат если нет чатов
    if not st.session_state.user_chats:
        _create_new_chat()

    # session_id для агента = user_id + chat_id
    chat_id = st.session_state.get('current_chat_id', 'default')
    st.session_state.session_id = f'{user_id}_{chat_id}'

    # инициализируем агент только для fallback режима
    if not LANGGRAPH_SERVER_AVAILABLE and st.session_state.agent is None:
        try:
            st.session_state.agent = get_supervisor_graph(with_persistence=True)
        except Exception as e:
            st.error(f'Ошибка инициализации агента: {e}')

    # загружаем историю сообщений
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
    Загружает сообщения из хранилища.

    Использует LangGraph Server API если доступен, иначе локальный SqliteSaver.
    """
    thread_id = st.session_state.get('session_id')
    if not thread_id:
        return

    if LANGGRAPH_SERVER_AVAILABLE:
        # Загружаем через LangGraph Server API
        st.session_state.messages = get_thread_history(thread_id)
    else:
        # Fallback: локальный SqliteSaver
        messages = get_chat_history(thread_id)
        st.session_state.messages = messages_to_ui_format(messages)


def _create_new_chat(skip_history_load: bool = True) -> str:
    """
    Создаёт новый чат и возвращает его ID.

    Args:
        skip_history_load: Пропустить загрузку истории (для нового чата не нужна)
    """
    user_id = st.session_state.get('user_id', 'anon')
    chat_id = uuid.uuid4().hex[:8]

    # формируем название с датой и временем: "(20 декабря 2025) Чат 15:42"
    now = pendulum.now('Europe/Moscow')
    # pendulum поддерживает русскую локаль
    date_str = now.format('D MMMM YYYY', locale='ru')
    time_str = now.format('HH:mm')
    title = f'({date_str}) Чат {time_str}'

    # сохраняем в SQLite (только для зарегистрированных пользователей)
    if user_id != 'anon' and not user_id.startswith('anon_'):
        storage = get_user_storage()
        try:
            chat_info = storage.create_chat(user_id, chat_id, title)
            st.session_state.user_chats.insert(0, chat_info.to_dict())  # новые сверху
        except Exception:
            pass  # fallback ниже
    else:
        # для анонимных - только в session_state (не сохраняется при обновлении)
        st.session_state.user_chats.insert(
            0,
            {
                'id': chat_id,
                'title': title,
                'created_at': now.to_iso8601_string(),
            },
        )

    st.session_state.current_chat_id = chat_id
    # новый чат — история пустая, не нужно загружать
    st.session_state.messages = []

    # обновляем session_id
    st.session_state.session_id = f'{user_id}_{chat_id}'

    return chat_id


def _delete_chat(chat_id: str) -> None:
    """
    Удаляет чат
    """
    user_id = st.session_state.get('user_id', 'anon')

    # удаляем из SQLite (user_data.db) только для зарегистрированных
    if user_id != 'anon' and not user_id.startswith('anon_'):
        storage = get_user_storage()
        try:
            storage.delete_chat(user_id, chat_id)
        except Exception:
            pass  # игнорируем если чат не найден в БД

    # удаляем из session_state
    st.session_state.user_chats = [c for c in st.session_state.user_chats if c['id'] != chat_id]

    # очищаем историю
    thread_id = f'{user_id}_{chat_id}'
    if LANGGRAPH_SERVER_AVAILABLE:
        clear_thread_history(thread_id)
    else:
        clear_chat_history(thread_id)

    # если удалили текущий чат - переключаемся
    if st.session_state.current_chat_id == chat_id:
        if st.session_state.user_chats:
            _switch_chat(st.session_state.user_chats[0]['id'])
        else:
            _create_new_chat(skip_history_load=True)


def _switch_chat(chat_id: str) -> None:
    """
    Переключает на указанный чат
    """
    # переключаемся
    st.session_state.current_chat_id = chat_id

    # обновляем session_id (thread_id для агента)
    user_id = st.session_state.get('user_id', 'anon')
    st.session_state.session_id = f'{user_id}_{chat_id}'

    # загружаем сообщения
    _load_messages_from_persistent_storage()


def get_agent():
    """
    Возвращает агент для fallback режима.

    Используется только когда LangGraph Server недоступен.
    """
    if not LANGGRAPH_SERVER_AVAILABLE:
        if st.session_state.agent is None:
            with st.spinner('🔄 Инициализация агента...'):
                try:
                    st.session_state.agent = get_supervisor_graph(with_persistence=True)
                except Exception as e:
                    st.error(f'Ошибка инициализации агента: {e}')
                    return None
        return st.session_state.agent
    return None  # В режиме LangGraph Server агент не нужен


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
        display_name = st.session_state.get('display_name', st.session_state.get('name', 'Гость'))
        st.markdown(f'👤 **{display_name}**')

        # кнопка выхода (только для авторизованных)
        if st.session_state.get('authentication_status'):
            authenticator = st.session_state.get('authenticator')
            if authenticator:
                authenticator.logout('🚪 Выйти', location='main', key='sidebar_logout')

        st.divider()

        # управление чатами
        st.markdown('### 💬 Чаты')

        # кнопка нового чата
        if st.button('➕ Новый чат', use_container_width=True, key='new_chat_btn'):
            _create_new_chat(skip_history_load=True)
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
        if st.button('🧹 Очистить текущий чат', use_container_width=True, key='clear_chat_btn'):
            st.session_state.messages = []
            # очищаем историю
            if LANGGRAPH_SERVER_AVAILABLE:
                clear_thread_history(st.session_state.session_id)
            else:
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
        if LANGGRAPH_SERVER_AVAILABLE:
            st.markdown('Сервер: 🟢 LangGraph API')
            st.markdown('Режим: 🚀 Streaming')
        else:
            agent_status = '🟢 Активен' if st.session_state.agent else '🟡 Ожидание'
            st.markdown(f'Агент: {agent_status}')
            st.markdown('Режим: 📦 Локальный')
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
    Обрабатывает ввод пользователя через LangGraph Server или локальный агент.

    Args:
        user_input: Сообщение пользователя

    Returns:
        Ответ агента
    """
    if LANGGRAPH_SERVER_AVAILABLE:
        # Используем LangGraph Server API (синхронный вызов без streaming)
        try:
            return chat_sync(
                user_chat_id=st.session_state.session_id,
                message=user_input,
                agent_graph_id='supervisor',
            )
        except Exception as e:
            return f'❌ Ошибка LangGraph Server: {e}'
    else:
        # fallback: локальный вызов
        agent = get_agent()
        if agent is None:
            return '❌ Агент не инициализирован. Проверьте настройки.'

        try:
            response, metadata = invoke_supervisor(
                query=user_input,
                session_id=st.session_state.session_id,
                with_persistence=True,
            )
            return response
        except Exception as e:
            return f'❌ Ошибка при обработке запроса: {e}'


def process_user_input_streaming(user_input: str, message_placeholder) -> str:
    """
    Streaming версия обработки ввода через LangGraph Server.

    Показывает ответ по мере генерации токенов.

    Args:
        user_input: Сообщение пользователя
        message_placeholder: st.empty() placeholder для обновления

    Returns:
        Полный ответ агента
    """
    if not LANGGRAPH_SERVER_AVAILABLE:
        # fallback на обычный вызов
        return process_user_input(user_input)

    try:
        full_response = ''
        error_occurred = False

        for event in stream_chat_with_status(
            user_chat_id=st.session_state.session_id,
            message=user_input,
            agent_graph_id='supervisor',
        ):
            event_type = event.get('type', '')
            content = event.get('content', '')

            if event_type == 'status':
                # показываем статус
                message_placeholder.markdown(f'*{content}*')

            elif event_type == 'token':
                # добавляем токен к ответу
                full_response += content
                # показываем с курсором
                message_placeholder.markdown(full_response + '▌')

            elif event_type == 'error':
                error_occurred = True
                full_response = f'❌ Ошибка: {content}'
                message_placeholder.markdown(full_response)
                break

            elif event_type == 'complete':
                # финальный ответ готов
                message_placeholder.markdown(full_response)

        if not error_occurred and not full_response:
            full_response = '❌ Пустой ответ от сервера'
            message_placeholder.markdown(full_response)

        return full_response

    except Exception as e:
        error_msg = f'❌ Ошибка streaming: {e}'
        message_placeholder.markdown(error_msg)
        return error_msg


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
            if LANGGRAPH_SERVER_AVAILABLE:
                # Streaming режим через LangGraph Server API
                message_placeholder = st.empty()
                response = process_user_input_streaming(input_to_process, message_placeholder)
            else:
                # Локальный режим — ждём полный ответ
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

        # не делаем rerun — сообщения уже отображены,
        # rerun вызывает мерцание всего UI


if __name__ == '__main__':
    main()

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
print(f'Добавление в sys.path: {Path(__file__).parent.parent}')
sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.city_agent import create_city_agent, safe_chat  # noqa: E402

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
    auth_config_path = Path(__file__).parent / 'auth_config.yaml'

    if not auth_config_path.exists():
        st.warning('Файл конфигурации auth_config.yaml не найден')
        return True

    with open(auth_config_path, encoding='utf-8') as f:
        auth_config = yaml.safe_load(f)

    # создаём authenticator
    authenticator = stauth.Authenticate(
        credentials=auth_config['credentials'],
        cookie_name=auth_config['cookie']['name'],
        cookie_key=auth_config['cookie']['key'],
        cookie_expiry_days=auth_config['cookie']['expiry_days'],
    )

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
            <p>Войдите для доступа к сервису</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # виджет логина
    authenticator.login(location='main')

    if st.session_state.get('authentication_status') is False:
        st.error('Неверное имя пользователя или пароль')
    else:
        st.info('💡 Для демо: логин `demo`, пароль `demo123`')

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

    if 'session_id' not in st.session_state:
        st.session_state.session_id = f'session_{uuid.uuid4().hex[:12]}'

    # инициализируем агента сразу если ещё не создан
    if st.session_state.agent is None:
        try:
            st.session_state.agent = create_city_agent(with_persistence=False)
        except Exception as e:
            st.error(f'Ошибка инициализации агента: {e}')


def get_agent() -> CompiledStateGraph | None:
    """
    Возвращает или создаёт экземпляр агента
    """
    if st.session_state.agent is None:
        with st.spinner('🔄 Инициализация агента...'):
            try:
                st.session_state.agent = create_city_agent(with_persistence=False)
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
        st.markdown(f'🔑 Сессия: `{st.session_state.session_id[:8]}...`')

        st.divider()

        # кнопка очистки чата
        if st.button('🗑️ Очистить чат', use_container_width=True):
            st.session_state.messages = []
            st.session_state.session_id = f'session_{uuid.uuid4().hex[:12]}'
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

        st.markdown('Фильтр токсичности: 🟢 Активен')


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
            use_persistence=False,
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

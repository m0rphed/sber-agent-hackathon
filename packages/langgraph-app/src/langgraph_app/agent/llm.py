"""
Настройка LLM (GigaChat) через LangChain.

Использует централизованную конфигурацию из app.config.
"""

from langchain_gigachat import GigaChat

from langgraph_app.config import (
    GIGACHAT_CREDENTIALS,
    GIGACHAT_SCOPE,
    GIGACHAT_VERIFY_SSL_CERTS,
    AgentConfig,
    get_agent_config,
)


def get_llm_for_intent_routing() -> GigaChat:
    """
    Лёгкая и дешёвая модель для роутинга намерений.
    Те же креды GigaChat, но максимально детерминированные настройки.
    """
    return GigaChat(
        credentials=GIGACHAT_CREDENTIALS,
        scope=GIGACHAT_SCOPE,
        verify_ssl_certs=GIGACHAT_VERIFY_SSL_CERTS,
        # важные параметры именно для роутинга:
        temperature=0.0,
        max_tokens=256,
        # top_p=0.2,
        #
        # frequency_penalty=0.0,
        # presence_penalty=0.0,
    )


def get_llm(
    temperature: float | None = None,
    max_tokens: int | None = None,
    timeout: float | None = None,
    config: AgentConfig | None = None,
) -> GigaChat:
    """
    Создаёт экземпляр GigaChat LLM.

    Args:
        temperature: Температура генерации (None = из конфига)
        max_tokens: Максимальное количество токенов (None = из конфига)
        timeout: Таймаут в секундах (None = из конфига)
        config: Конфигурация агента (None = глобальный)

    Returns:
        Настроенный экземпляр GigaChat
    """
    cfg = config or get_agent_config()

    effective_temp = temperature if temperature is not None else cfg.llm.temperature_conversation
    effective_max_tokens = max_tokens if max_tokens is not None else cfg.llm.max_tokens_default
    effective_timeout = timeout if timeout is not None else float(cfg.timeout.llm_seconds)

    return GigaChat(
        credentials=GIGACHAT_CREDENTIALS,
        scope=GIGACHAT_SCOPE,
        verify_ssl_certs=GIGACHAT_VERIFY_SSL_CERTS,
        model=cfg.llm.model,
        temperature=effective_temp,
        max_tokens=effective_max_tokens,
        timeout=effective_timeout,
    )


def get_llm_for_classification(config: AgentConfig | None = None) -> GigaChat:
    """
    LLM для классификации (детерминированный, низкая temperature).
    """
    cfg = config or get_agent_config()
    return get_llm(
        temperature=cfg.llm.temperature_classification,
        max_tokens=cfg.llm.max_tokens_classification,
        config=cfg,
    )


def get_llm_for_tools(config: AgentConfig | None = None) -> GigaChat:
    """
    LLM для работы с инструментами.
    """
    cfg = config or get_agent_config()
    return get_llm(
        temperature=cfg.llm.temperature_tools,
        max_tokens=cfg.llm.max_tokens_default,
        config=cfg,
    )


def get_llm_for_conversation(config: AgentConfig | None = None) -> GigaChat:
    """
    LLM для разговора.
    """
    cfg = config or get_agent_config()
    return get_llm(
        temperature=cfg.llm.temperature_conversation,
        max_tokens=cfg.llm.max_tokens_conversation,
        config=cfg,
    )


if __name__ == '__main__':
    llm = get_llm()
    response = llm.invoke('Привет! Расскажи кратко о Санкт-Петербурге.')
    print(response.content)

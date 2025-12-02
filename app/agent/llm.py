"""
Настройка LLM (GigaChat) через LangChain
"""

from langchain_gigachat import GigaChat

from app.agent.resilience import DEFAULT_LLM_TIMEOUT
from app.config import (
    GIGACHAT_CREDENTIALS,
    GIGACHAT_SCOPE,
    GIGACHAT_VERIFY_SSL_CERTS,
)


def get_llm(
    temperature: float = 0.7,
    max_tokens: int = 1024,
    timeout: float | None = None,
) -> GigaChat:
    """
    Создаёт экземпляр GigaChat LLM.

    Args:
        temperature: Температура генерации (0.0 - 1.0)
        max_tokens: Максимальное количество токенов в ответе
        timeout: Таймаут в секундах (по умолчанию DEFAULT_LLM_TIMEOUT)

    Returns:
        Настроенный экземпляр GigaChat
    """
    if timeout is None:
        timeout = DEFAULT_LLM_TIMEOUT

    return GigaChat(
        credentials=GIGACHAT_CREDENTIALS,
        scope=GIGACHAT_SCOPE,
        verify_ssl_certs=GIGACHAT_VERIFY_SSL_CERTS,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )


if __name__ == "__main__":
    llm = get_llm()
    response = llm.invoke("Привет! Расскажи кратко о Санкт-Петербурге.")
    print(response.content)

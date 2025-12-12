"""
Утилиты для агента.
"""

from typing import Any


def langchain_cast_sqlite_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """
    Преобразует конфигурацию для SqliteSaver.
    
    Это shim для совместимости — функция была удалена, но импортируется
    в persistent_memory.py. Возвращает конфиг как есть или пустой dict.
    
    Args:
        config: Исходная конфигурация
        
    Returns:
        Обработанная конфигурация
    """
    if config is None:
        return {}
    return dict(config)

"""
Централизованное управление промптами для городского агента.

Все промпты хранятся в виде файлов .txt для простых промптов,
или .jinja2 для промптов с подстановкой переменных.

Usage:
    from prompts import load_prompt, render_prompt

    # Загрузка простого промпта
    system_prompt = load_prompt("city_agent_prompt.txt")

    # Загрузка и рендеринг промпта с переменными
    prompt = render_prompt("entity_extraction.jinja2", intent="search_mfc", query="...")
"""

from functools import lru_cache
from pathlib import Path

# путь к директории с промптами
PROMPTS_DIR = Path(__file__).parent


@lru_cache(maxsize=32)
def load_prompt(filename: str) -> str:
    """
    Загружает промпт из файла.

    Args:
        filename: Имя файла с промптом (например, "city_agent_prompt.txt")

    Returns:
        Текст промпта

    Raises:
        FileNotFoundError: Если файл с промптом не найден
    """
    filepath = PROMPTS_DIR / filename
    if not filepath.exists():
        raise FileNotFoundError(f'Prompt file not found: {filepath}')
    return filepath.read_text(encoding='utf-8')


def render_prompt(filename: str, **kwargs) -> str:
    """
    Загружает и рендерит Jinja2 шаблон промпта.

    Args:
        filename: Имя файла шаблона (например, "entity_extraction.jinja2")
        **kwargs: Переменные для подстановки в шаблон
    Returns:
        Отрендеренный текст промпта
    """
    try:
        from jinja2 import Template
    except ImportError:
        # Fallback: simple string formatting
        template_text = load_prompt(filename)
        return template_text.format(**kwargs)

    template_text = load_prompt(filename)
    template = Template(template_text)
    return template.render(**kwargs)


def clear_cache() -> None:
    """
    Очищает кэш промптов (полезно для тестирования или hot reload)
    """
    load_prompt.cache_clear()


# Экспорт часто используемых промптов как констант для обратной совместимости
# Они загружаются лениво при первом обращении


class _PromptLoader:
    """
    Ленивый загрузчик промптов для избежания I/O во время импортов
    """

    _cache: dict[str, str] = {}

    def __getattr__(self, name: str) -> str:
        if name.startswith('_'):
            raise AttributeError(name)

        # сопоставление имен атрибутов с файлами
        filename_map = {
            'CITY_AGENT_PROMPT':        'city_agent_prompt.txt',
            'TOOL_AGENT_SYSTEM_PROMPT': 'tool_agent_system.txt',
            'INTENT_CLASSIFIER_PROMPT': 'intent_classifier.txt',
            'INTENT_ONLY_PROMPT':       'intent_only.txt',
            'ENTITY_EXTRACTION_PROMPT': 'entity_extraction.jinja2',
            'CONVERSATION_PROMPT':      'conversation.txt',
            'QUERY_REWRITE_PROMPT':     'rag/query_rewrite.txt',
            'DOCUMENT_GRADE_PROMPT':    'rag/document_grade.txt',
            'HYBRID_INTENT_PROMPT':     'hybrid_intent_classifier.txt',
        }

        if name not in filename_map:
            raise AttributeError(f'Unknown prompt: {name}')

        if name not in self._cache:
            self._cache[name] = load_prompt(filename_map[name])

        return self._cache[name]


# Singleton экземпляр для lazy loading-га
prompts = _PromptLoader()

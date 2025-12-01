"""
- конфигурация RAG модуля

Настройки для:
- Парсеров
- Индексации
- Векторного хранилища
"""

from dataclasses import dataclass, field
from pathlib import Path

from app.config import DATA_DIR


@dataclass
class ParserConfig:
    """
    Настройки парсера
    """

    delay: float = 0.5  # секунд между запросами
    timeout: int = 30  # таймаут запроса
    max_depth: int = 3  # максимальная глубина рекурсии
    max_pages: int = 1000  # максимум страниц за один запуск


@dataclass
class ChunkingConfig:
    """
    Настройки разбиения на чанки (кусочки текста)
    """

    chunk_size: int = 800       # размер чанка в символах
    chunk_overlap: int = 200    # перекрытие между чанками
    min_chunk_size: int = 100   # минимальный размер чанка (в символах)


@dataclass
class IndexConfig:
    """
    Настройки индексации
    """

    # пути к данным
    chroma_persist_dir: Path = field(default_factory=lambda: DATA_DIR / 'chroma_db')
    parsed_docs_dir: Path = field(default_factory=lambda: DATA_DIR / 'parsed_docs')
    index_metadata_path: Path = field(default_factory=lambda: DATA_DIR / 'index_metadata.json')

    # настройки коллекции
    collection_name: str = 'city_knowledge'

    # настройки поиска
    search_k: int = 5  # количество результатов
    search_score_threshold: float = 0.5  # порог релевантности


@dataclass
class RAGConfig:
    """
    Общая конфигурация RAG
    """

    parser: ParserConfig = field(default_factory=ParserConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    index: IndexConfig = field(default_factory=IndexConfig)

    # embeddings
    embedding_model: str = 'GigaChat'  # или путь к локальной модели

    def __post_init__(self):
        """
        Создаёт необходимые директории
        """
        self.index.chroma_persist_dir.mkdir(parents=True, exist_ok=True)
        self.index.parsed_docs_dir.mkdir(parents=True, exist_ok=True)


# глобальная конфигурация RAG (singleton)
_config: RAGConfig | None = None


def get_rag_config() -> RAGConfig:
    """
    Возвращает глобальную конфигурацию RAG
    """
    global _config
    if _config is None:
        _config = RAGConfig()
    return _config

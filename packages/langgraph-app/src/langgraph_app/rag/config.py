"""
Конфигурация RAG модуля.

Настройки для:
- Парсеров (delay, timeout, max_depth)
- Чанкинга (chunk_size, overlap, min_size)
- Индексации (paths, collection_name)
- Поиска (k, min_relevant, threshold)
- Эмбеддингов (model, weights)

Использование:
    from langgraph_app.rag.config import get_rag_config

    config = get_rag_config()
    print(config.chunking.chunk_size)  # 800
    print(config.search.k)  # 5
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path

from langgraph_app.config import DATA_DIR

# =============================================================================
# Parser Config
# =============================================================================


@dataclass
class ParserConfig:
    """Настройки парсера."""

    delay: float = 0.5
    """Секунд между запросами."""

    timeout: int = 30
    """Таймаут запроса."""

    max_depth: int = 3
    """Максимальная глубина рекурсии."""

    max_pages: int = 1000
    """Максимум страниц за один запуск."""


# =============================================================================
# Chunking Config
# =============================================================================


@dataclass
class ChunkingConfig:
    """
    Настройки разбиения на чанки.
    """

    chunk_size: int = 800
    """
    Размер чанка в символах.
    """

    chunk_overlap: int = 200
    """
    Перекрытие между чанками.
    """

    min_chunk_size: int = 100
    """Минимальный размер чанка."""


# =============================================================================
# Index Config
# =============================================================================


@dataclass
class IndexConfig:
    """Настройки индексации."""

    chroma_persist_dir: Path = field(default_factory=lambda: DATA_DIR / 'chroma_db')
    """Путь к ChromaDB."""

    parsed_docs_dir: Path = field(default_factory=lambda: DATA_DIR / 'parsed_docs')
    """Путь к распарсенным документам."""

    index_metadata_path: Path = field(default_factory=lambda: DATA_DIR / 'index_metadata.json')
    """Путь к метаданным индекса."""

    collection_name: str = 'city_knowledge'
    """Название коллекции ChromaDB."""


# =============================================================================
# Search Config
# =============================================================================


@dataclass
class SearchConfig:
    """Настройки поиска."""

    k: int = 5
    """Количество результатов поиска."""

    min_relevant: int = 3
    """Минимальное количество релевантных документов."""

    relevance_threshold: float = 0.5
    """Порог релевантности (0.0-1.0)."""

    overfetch_multiplier: int = 3
    """Множитель для предварительной выборки перед фильтрацией."""

    content_preview_limit: int = 300
    """Лимит символов для превью контента."""


# =============================================================================
# Embedding Config
# =============================================================================

# TODO: either generalize config or directly state that we use GigaChat
@dataclass
class EmbeddingConfig:
    """Настройки эмбеддингов."""

    model: str = 'Embeddings' # возможно у других эмбеддингов - другие параметры => TODO: определить имя эмбеддинг-модели по умолчанию
    """Название модели эмбеддингов."""

    verify_ssl: bool = False
    """
    Проверять SSL сертификаты
    """


# =============================================================================
# Retriever Config
# =============================================================================


@dataclass
class RetrieverConfig:
    """Настройки ретривера."""

    vector_weight: float = 0.5
    """Вес векторного поиска в гибридном ретривере."""

    bm25_weight: float = 0.5
    """Вес BM25 поиска в гибридном ретривере."""


# =============================================================================
# Main RAG Config
# =============================================================================


@dataclass
class RAGConfig:
    """
    Полная конфигурация RAG pipeline.

    Объединяет все настройки для RAG:
    - parser: настройки парсера
    - chunking: настройки чанкинга
    - index: настройки индексации
    - search: настройки поиска
    - embedding: настройки эмбеддингов
    - retriever: настройки ретривера

    Использование:
        config = RAGConfig()  # дефолтные значения
        config = RAGConfig(search=SearchConfig(k=10))  # кастомный k

        # или через get_rag_config() для singleton
        config = get_rag_config()
    """

    parser: ParserConfig = field(default_factory=ParserConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    index: IndexConfig = field(default_factory=IndexConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    # TODO: either generalize config or directly state that we use GigaChat
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    retriever: RetrieverConfig = field(default_factory=RetrieverConfig)

    # legacy field for backward compatibility
    embedding_model: str = 'GigaChat'

    def __post_init__(self):
        """Создаёт необходимые директории."""
        self.index.chroma_persist_dir.mkdir(parents=True, exist_ok=True)
        self.index.parsed_docs_dir.mkdir(parents=True, exist_ok=True)


# =============================================================================
# Global Config (Singleton)
# =============================================================================

_config: RAGConfig | None = None


def get_rag_config() -> RAGConfig:
    """
    Возвращает глобальную конфигурацию RAG.

    При первом вызове читает значения из переменных окружения.
    """
    global _config

    if _config is None:
        # Читаем из env, если заданы
        chunk_size = int(os.getenv('RAG_CHUNK_SIZE', '800'))
        chunk_overlap = int(os.getenv('RAG_CHUNK_OVERLAP', '200'))
        search_k = int(os.getenv('RAG_SEARCH_K', '5'))
        min_relevant = int(os.getenv('RAG_MIN_RELEVANT', '3'))
        relevance_threshold = float(os.getenv('RAG_RELEVANCE_THRESHOLD', '0.5'))
        content_preview = int(os.getenv('RAG_CONTENT_PREVIEW', '300'))

        _config = RAGConfig(
            chunking=ChunkingConfig(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            ),
            search=SearchConfig(
                k=search_k,
                min_relevant=min_relevant,
                relevance_threshold=relevance_threshold,
                content_preview_limit=content_preview,
            ),
        )

    return _config


def set_rag_config(config: RAGConfig) -> None:
    """Установить кастомный RAGConfig (для тестов и DI)."""
    global _config
    _config = config


def reset_rag_config() -> None:
    """Сбросить конфиг (для тестов)."""
    global _config
    _config = None

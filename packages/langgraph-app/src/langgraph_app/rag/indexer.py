"""
Модуль индексации документов для RAG.

Обеспечивает:
- Разбиение документов на чанки
- Векторную индексацию с GigaChat embeddings
- BM25 индексацию для гибридного поиска
- Сохранение и загрузку индекса
"""

from datetime import datetime
import json
import os
from pathlib import Path
import pickle
from typing import Any

from langchain_chroma import Chroma
from langchain_classic.retrievers import EnsembleRetriever
from langchain_classic.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_gigachat import GigaChatEmbeddings

from langgraph_app.config import ensure_dotenv
from langgraph_app.logging_config import get_logger
from langgraph_app.rag.config import RAGConfig, get_rag_config
from langgraph_app.rag.models import ParsedDocument

logger = get_logger(__name__)


class DocumentChunker:
    """
    Разбивает документы на чанки для индексации.

    Использует RecursiveCharacterTextSplitter для умного разбиения
    с учётом структуры текста (параграфы, предложения).
    """

    def __init__(self, config: RAGConfig | None = None):
        self.config = config or get_rag_config()
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.config.chunking.chunk_size,
            chunk_overlap=self.config.chunking.chunk_overlap,
            length_function=len,
            separators=['\n\n', '\n', '. ', ', ', ' ', ''],
        )

    def chunk_document(self, doc: ParsedDocument) -> list[Document]:
        """
        Разбивает один документ на чанки.

        Args:
            doc: Распарсенный документ

        Returns:
            Список LangChain Document с метаданными чанков
        """
        # пропускаем слишком короткие документы
        if len(doc.content) < self.config.chunking.min_chunk_size:
            logger.debug(
                'skipping_short_document',
                doc_id=doc.doc_id,
                content_length=len(doc.content),
                min_required=self.config.chunking.min_chunk_size,
            )
            return []

        # создаём базовый LangChain документ
        base_doc = doc.to_langchain_doc()

        # разбиваем на чанки
        chunks = self.splitter.split_documents([base_doc])

        # добавляем метаданные чанков
        for i, chunk in enumerate(chunks):
            chunk.metadata['chunk_index'] = i
            chunk.metadata['total_chunks'] = len(chunks)
            chunk.metadata['chunk_id'] = f'{doc.doc_id}_chunk_{i}'

        return chunks

    def chunk_documents(self, docs: list[ParsedDocument]) -> list[Document]:
        """
        Разбивает список документов на чанки.

        Args:
            docs: Список распарсенных документов

        Returns:
            Список всех чанков с метаданными
        """
        all_chunks = []
        for doc in docs:
            chunks = self.chunk_document(doc)
            all_chunks.extend(chunks)

        logger.info(
            'chunking_complete',
            documents_count=len(docs),
            chunks_count=len(all_chunks),
        )
        return all_chunks


class HybridIndexer:
    """
    Гибридный индексатор с векторным и BM25 поиском.

    Использует:
    - ChromaDB с GigaChat embeddings для семантического поиска
    - BM25Retriever для ключевого поиска
    - EnsembleRetriever для объединения результатов
    """

    # TODO: передавать >= 2 конфига (ChunkingConfig, IndexConfig) для гибкости
    def __init__(self, config: RAGConfig | None = None):
        self.config = config or get_rag_config()
        self.chunker = DocumentChunker(self.config)

        # инициализируем embeddings
        self._embeddings: GigaChatEmbeddings | None = None

        # ChromaDB
        self._vectorstore: Chroma | None = None

        # BM25
        self._bm25_retriever: BM25Retriever | None = None
        self._bm25_docs: list[Document] = []

        # Ensemble
        # TODO: позволить настраивать EnsembleRetriever через конфиг
        # TODO: попробовать другие варианты объединения результатов
        self._ensemble_retriever: EnsembleRetriever | None = None

        # метаданные индекса
        self._metadata: dict[str, Any] = {
            'created_at': None,
            'updated_at': None,
            'document_count': 0,
            'chunk_count': 0,
        }

    # TODO: рассмотреть возможность заменить embeddings на HF
    @property
    def embeddings(self) -> GigaChatEmbeddings:
        """
        Ленивая инициализация embeddings.

        Читает credentials и scope из переменных окружения:
        - GIGACHAT_CREDENTIALS: ключ авторизации
        - GIGACHAT_SCOPE: область доступа (GIGACHAT_API_PERS, GIGACHAT_API_CORP, etc.)
        - EMBEDDINGS_MODEL: модель эмбеддингов (по умолчанию Embeddings)
        """
        if self._embeddings is None:
            ensure_dotenv()

            credentials = os.getenv('GIGACHAT_CREDENTIALS')
            scope = os.getenv('GIGACHAT_SCOPE', 'GIGACHAT_API_PERS')
            model = os.getenv('EMBEDDINGS_MODEL', 'Embeddings')

            if not credentials:
                raise ValueError(
                    'GIGACHAT_CREDENTIALS not set. '
                    'Please set it in .env file or environment variables.'
                )

            logger.info(
                'embeddings_init',
                model=model,
                scope=scope,
                credentials_length=len(credentials),
            )

            self._embeddings = GigaChatEmbeddings(
                credentials=credentials,
                scope=scope,
                model=model,
                verify_ssl_certs=False,
            )
        return self._embeddings

    @property
    def vectorstore(self) -> Chroma:
        """
        Ленивая инициализация ChromaDB
        """
        if self._vectorstore is None:
            persist_dir = str(self.config.index.chroma_persist_dir)
            collection_name = self.config.index.collection_name

            # проверяем, существует ли уже БД
            if self.config.index.chroma_persist_dir.exists():
                logger.info('chromadb_load', path=persist_dir)
            else:
                logger.info('chromadb_create', path=persist_dir)

            self._vectorstore = Chroma(
                collection_name=collection_name,
                embedding_function=self.embeddings,
                persist_directory=persist_dir,
            )
        return self._vectorstore

    def index_documents(self, docs: list[ParsedDocument], force_reindex: bool = False) -> int:
        """
        Индексирует документы.

        Args:
            docs: Список документов для индексации
            force_reindex: Если True, пересоздаёт индекс с нуля

        Returns:
            Количество проиндексированных чанков
        """
        logger.info(
            'indexing_start',
            documents_count=len(docs),
            force_reindex=force_reindex,
        )

        # создаём чанки
        # TODO: какие размеры чанков лучше (?)
        chunks = self.chunker.chunk_documents(docs)
        if not chunks:
            logger.warning('No chunks created from documents')
            return 0

        # очищаем старый индекс если нужно
        if force_reindex:
            self._clear_index()

        # =================================================================
        # ВАЖНО: Сначала сохраняем BM25 (не требует API), потом vector
        # Это позволяет использовать BM25 даже если embeddings API недоступен
        # =================================================================

        # 1. Сохраняем документы для BM25 (локально, без API)
        self._bm25_docs = chunks
        self._save_bm25_docs()
        logger.info('bm25_indexed', chunks_count=len(chunks))

        # 2. Создаём BM25 retriever
        self._bm25_retriever = BM25Retriever.from_documents(chunks)
        self._bm25_retriever.k = self.config.search.k

        # 3. Индексируем в ChromaDB (требует GigaChat API для embeddings)
        vector_indexed = False
        try:
            logger.info('chromadb_indexing', chunks_count=len(chunks))
            self.vectorstore.add_documents(chunks)
            vector_indexed = True
            logger.info('chromadb_indexed', chunks_count=len(chunks))
        except Exception as e:
            logger.error(
                'chromadb_indexing_failed',
                error=str(e),
                message='Vector indexing failed, but BM25 is available',
            )

        # обновляем метаданные
        now = datetime.now().isoformat()
        self._metadata.update(
            {
                'created_at': self._metadata['created_at'] or now,
                'updated_at': now,
                'document_count': len(docs),
                'chunk_count': len(chunks),
                'vector_indexed': vector_indexed,
            }
        )
        self._save_metadata()

        # сбрасываем ensemble retriever
        self._ensemble_retriever = None

        logger.info(
            'indexing_complete',
            chunks_indexed=len(chunks),
            documents_count=len(docs),
        )
        return len(chunks)

    def ensure_indexed(self) -> bool:
        """
        Проверяет наличие индекса и автоматически индексирует если нужно.

        Логика:
        1. Пытается загрузить bm25_docs.pkl
        2. Если не найден — загружает all_documents.json и индексирует
        3. Если all_documents.json тоже нет — возвращает False

        Returns:
            True если индекс готов, False если документы не найдены
        """
        # пытаемся загрузить существующий BM25 индекс
        if not self._bm25_docs:
            self._load_bm25_docs()

        if self._bm25_docs:
            logger.info(
                'index_already_exists',
                bm25_docs_count=len(self._bm25_docs),
            )
            return True

        # BM25 индекс не найден — нужно проиндексировать
        logger.warning(
            'bm25_index_missing',
            message='BM25 index not found, attempting to rebuild from documents',
        )

        # ищем all_documents.json
        docs_path = self.config.index.parsed_docs_dir / 'all_documents.json'
        if not docs_path.exists():
            logger.error(
                'documents_not_found',
                path=str(docs_path),
                message='Cannot rebuild index: all_documents.json not found. Run pipeline first.',
            )
            return False

        # загружаем и индексируем
        try:
            docs = load_parsed_documents(docs_path)
            if not docs:
                logger.error('no_documents_to_index', message='all_documents.json is empty')
                return False

            logger.info(
                'auto_indexing_start',
                documents_count=len(docs),
                message='Automatically indexing documents...',
            )

            chunk_count = self.index_documents(docs, force_reindex=True)

            logger.info(
                'auto_indexing_complete',
                chunks_indexed=chunk_count,
                documents_count=len(docs),
            )
            return True

        except Exception as e:
            logger.error(
                'auto_indexing_failed',
                error=str(e),
                message='Failed to automatically index documents',
            )
            return False

    def reindex_vector(self) -> bool:
        """
        Переиндексирует только vector store (ChromaDB).

        Используй когда BM25 уже есть, но vector индекс нужно пересоздать
        (например, после восстановления доступа к embeddings API).

        Returns:
            True если успешно, False если ошибка
        """
        if not self._bm25_docs:
            self._load_bm25_docs()

        if not self._bm25_docs:
            logger.error('reindex_vector_no_docs', message='No BM25 docs to reindex')
            return False

        try:
            # очищаем старый vector store
            if self._vectorstore is not None:
                self._vectorstore.delete_collection()
                self._vectorstore = None

            # индексируем
            logger.info('vector_reindex_start', chunks_count=len(self._bm25_docs))
            self.vectorstore.add_documents(self._bm25_docs)

            # обновляем метаданные
            self._metadata['vector_indexed'] = True
            self._metadata['updated_at'] = datetime.now().isoformat()
            self._save_metadata()

            # сбрасываем ensemble чтобы пересоздался
            self._ensemble_retriever = None

            logger.info('vector_reindex_complete', chunks_count=len(self._bm25_docs))
            return True

        except Exception as e:
            logger.error('vector_reindex_failed', error=str(e))
            return False

    def get_retriever(
        self,
        weights: tuple[float, float] = (0.5, 0.5),
        fallback_to_bm25: bool = True,
    ) -> EnsembleRetriever | BM25Retriever:
        """
        Возвращает гибридный retriever (или BM25-only как fallback).

        При отсутствии индекса автоматически пытается проиндексировать документы.
        Если vector индекс недоступен, возвращает только BM25 retriever.

        Args:
            weights: Веса для (vector, bm25) retrievers
            fallback_to_bm25: Если True, возвращает BM25 при ошибке vector

        Returns:
            EnsembleRetriever или BM25Retriever (fallback)

        Raises:
            ValueError: Если индекс отсутствует и не удалось его создать
        """
        if self._ensemble_retriever is not None:
            return self._ensemble_retriever

        # проверяем/создаём индекс автоматически
        if not self._bm25_docs:
            if not self.ensure_indexed():
                raise ValueError(
                    'No documents indexed and auto-indexing failed. '
                    'Run `python -m app.rag.pipeline` to parse documents first, '
                    'then `python -m app.rag.indexer` to index them.'
                )

        # создаём BM25 retriever (всегда работает локально)
        if self._bm25_retriever is None:
            self._bm25_retriever = BM25Retriever.from_documents(self._bm25_docs)
            self._bm25_retriever.k = self.config.search.k

        # проверяем метаданные — был ли успешно создан vector индекс?
        metadata = self.load_metadata()
        vector_available = metadata.get('vector_indexed', False)

        if not vector_available:
            logger.info(
                'using_bm25_only',
                message='Vector index not available, using BM25 only',
            )
            return self._bm25_retriever

        # пытаемся создать vector retriever
        try:
            vector_retriever = self.vectorstore.as_retriever(
                search_kwargs={'k': self.config.search.k}
            )

            # создаём ensemble
            self._ensemble_retriever = EnsembleRetriever(
                retrievers=[vector_retriever, self._bm25_retriever],
                weights=list(weights),
            )

            logger.info(
                'ensemble_retriever_created',
                vector_weight=weights[0],
                bm25_weight=weights[1],
            )
            return self._ensemble_retriever

        except Exception as e:
            if fallback_to_bm25:
                logger.warning(
                    'vector_retriever_failed_fallback_bm25',
                    error=str(e),
                    message='Using BM25-only retriever as fallback',
                )
                return self._bm25_retriever
            else:
                raise

    def search(self, query: str, k: int | None = None) -> list[Document]:
        """
        Выполняет гибридный поиск с fallback на BM25.

        Args:
            query: Поисковый запрос
            k: Количество результатов (по умолчанию из конфига)

        Returns:
            Список релевантных документов
        """
        retriever = self.get_retriever()

        try:
            # пытаемся использовать retriever (ensemble или bm25)
            results = retriever.invoke(query)
        except Exception as e:
            # если ensemble упал (например, embeddings API недоступен) — fallback на BM25
            logger.warning(
                'search_fallback_bm25',
                error=str(e)[:100],
                message='Ensemble search failed, falling back to BM25',
            )

            # убеждаемся что BM25 retriever создан
            if self._bm25_retriever is None:
                if not self._bm25_docs:
                    self._load_bm25_docs()
                if self._bm25_docs:
                    self._bm25_retriever = BM25Retriever.from_documents(self._bm25_docs)
                    self._bm25_retriever.k = self.config.search.k

            if self._bm25_retriever is None:
                raise ValueError('No retriever available for search') from e

            results = self._bm25_retriever.invoke(query)

        if k is not None:
            results = results[:k]

        return results

    def _clear_index(self) -> None:
        """
        Очищает индекс
        """
        logger.info('index_clearing')

        # удаляем ChromaDB
        if self._vectorstore is not None:
            self._vectorstore.delete_collection()
            self._vectorstore = None

        # очищаем BM25
        self._bm25_docs = []
        self._bm25_retriever = None
        self._ensemble_retriever = None

        # удаляем файлы
        bm25_path = self.config.index.chroma_persist_dir / 'bm25_docs.pkl'
        if bm25_path.exists():
            bm25_path.unlink()

    def _save_bm25_docs(self) -> None:
        """
        Сохраняет документы для BM25
        """
        bm25_path = self.config.index.chroma_persist_dir / 'bm25_docs.pkl'
        with open(bm25_path, 'wb') as f:
            pickle.dump(self._bm25_docs, f)
        logger.debug(f'Saved {len(self._bm25_docs)} BM25 documents to {bm25_path}')

    def _load_bm25_docs(self) -> None:
        """
        Загружает документы для BM25
        """
        bm25_path = self.config.index.chroma_persist_dir / 'bm25_docs.pkl'
        if bm25_path.exists():
            with open(bm25_path, 'rb') as f:
                self._bm25_docs = pickle.load(f)
            logger.debug(f'Loaded {len(self._bm25_docs)} BM25 documents from {bm25_path}')

    def _save_metadata(self) -> None:
        """
        Сохраняет метаданные индекса
        """
        with open(self.config.index.index_metadata_path, 'w', encoding='utf-8') as f:
            json.dump(self._metadata, f, ensure_ascii=False, indent=2)

    def load_metadata(self) -> dict[str, Any]:
        """
        Загружает метаданные индекса
        """
        if self.config.index.index_metadata_path.exists():
            with open(self.config.index.index_metadata_path, encoding='utf-8') as f:
                self._metadata = json.load(f)
        return self._metadata


def load_parsed_documents(path: Path | None = None) -> list[ParsedDocument]:
    """
    Загружает распарсенные документы из JSON.

    Args:
        path: Путь к файлу (по умолчанию из конфига)

    Returns:
        Список ParsedDocument
    """
    config = get_rag_config()
    path = path or config.index.parsed_docs_dir / 'all_documents.json'

    if not path.exists():
        raise FileNotFoundError(f'Documents file not found: {path}')

    with open(path, encoding='utf-8') as f:
        data = json.load(f)

    docs = [ParsedDocument.from_dict(d) for d in data]
    logger.info(f'Loaded {len(docs)} documents from {path}')
    return docs


# CLI для тестирования
if __name__ == '__main__':
    import argparse
    import os

    # Включаем DEBUG для CLI
    os.environ['LOG_LEVEL'] = 'DEBUG'
    from langgraph_app.logging_config import configure_logging

    configure_logging()

    parser = argparse.ArgumentParser(description='Index parsed documents')
    parser.add_argument('--reindex', action='store_true', help='Force reindex')
    parser.add_argument('--test-query', type=str, help='Test search query')
    args = parser.parse_args()

    # загружаем документы
    docs = load_parsed_documents()
    print(f'\nLoaded {len(docs)} documents')

    # создаём индексатор
    indexer = HybridIndexer()

    # индексируем
    chunk_count = indexer.index_documents(docs, force_reindex=args.reindex)
    print(f'Indexed {chunk_count} chunks')

    # тестовый поиск
    if args.test_query:
        print(f'\nSearching: "{args.test_query}"')
        results = indexer.search(args.test_query, k=3)
        for i, doc in enumerate(results, 1):
            print(f'\n--- Result {i} ---')
            print(f'Title: {doc.metadata.get("title", "N/A")}')
            print(f'URL: {doc.metadata.get("url", "N/A")}')
            print(f'Content: {doc.page_content[:300]}...')

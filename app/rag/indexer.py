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
import logging
from pathlib import Path
import pickle
from typing import Any

from langchain_chroma import Chroma
from langchain_classic.retrievers import EnsembleRetriever
from langchain_classic.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_gigachat import GigaChatEmbeddings

from app.rag.config import RAGConfig, get_rag_config
from app.rag.models import ParsedDocument

logger = logging.getLogger(__name__)


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
            logger.debug(f'Skipping short document: {doc.doc_id} ({len(doc.content)} chars)')
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

        logger.info(f'Created {len(all_chunks)} chunks from {len(docs)} documents')
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
        Ленивая инициализация embeddings
        """
        if self._embeddings is None:
            logger.info('Initializing GigaChat embeddings...')
            self._embeddings = GigaChatEmbeddings(
                model='Embeddings',         # модель для embeddings
                verify_ssl_certs=False,     # для обхода проблем с сертификатами
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
                logger.info(f'Loading existing ChromaDB from {persist_dir}')
            else:
                logger.info(f'Creating new ChromaDB at {persist_dir}')

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
        logger.info(f'Starting indexing of {len(docs)} documents...')

        # создаём чанки
        # TODO: какие размеры чанков лучше (?)
        chunks = self.chunker.chunk_documents(docs)
        if not chunks:
            logger.warning('No chunks created from documents')
            return 0

        # очищаем старый индекс если нужно
        if force_reindex:
            self._clear_index()

        # индексируем в ChromaDB
        logger.info(f'Adding {len(chunks)} chunks to ChromaDB...')
        self.vectorstore.add_documents(chunks)

        # сохраняем документы для BM25
        self._bm25_docs = chunks
        self._save_bm25_docs()

        # создаём BM25 retriever
        self._bm25_retriever = BM25Retriever.from_documents(chunks)
        self._bm25_retriever.k = self.config.index.search_k

        # обновляем метаданные
        now = datetime.now().isoformat()
        self._metadata.update(
            {
                'created_at': self._metadata['created_at'] or now,
                'updated_at': now,
                'document_count': len(docs),
                'chunk_count': len(chunks),
            }
        )
        self._save_metadata()

        # сбрасываем ensemble retriever
        self._ensemble_retriever = None

        logger.info(f'Indexing complete: {len(chunks)} chunks indexed')
        return len(chunks)

    def get_retriever(self, weights: tuple[float, float] = (0.5, 0.5)) -> EnsembleRetriever:
        """
        Возвращает гибридный retriever.

        Args:
            weights: Веса для (vector, bm25) retrievers

        Returns:
            EnsembleRetriever для поиска
        """
        if self._ensemble_retriever is not None:
            return self._ensemble_retriever

        # загружаем BM25 документы если нужно
        if not self._bm25_docs:
            self._load_bm25_docs()

        if not self._bm25_docs:
            raise ValueError('No documents indexed. Run index_documents() first.')

        # создаём retrievers
        vector_retriever = self.vectorstore.as_retriever(
            search_kwargs={'k': self.config.index.search_k}
        )

        if self._bm25_retriever is None:
            self._bm25_retriever = BM25Retriever.from_documents(self._bm25_docs)
            self._bm25_retriever.k = self.config.index.search_k

        # создаём ensemble
        self._ensemble_retriever = EnsembleRetriever(
            retrievers=[vector_retriever, self._bm25_retriever],
            weights=list(weights),
        )

        logger.info(
            f'Created ensemble retriever with weights: vector={weights[0]}, bm25={weights[1]}'
        )
        return self._ensemble_retriever

    def search(self, query: str, k: int | None = None) -> list[Document]:
        """
        Выполняет гибридный поиск.

        Args:
            query: Поисковый запрос
            k: Количество результатов (по умолчанию из конфига)

        Returns:
            Список релевантных документов
        """
        retriever = self.get_retriever()

        # - EnsembleRetriever не поддерживает k напрямую
        # - используем значение из конфига
        results = retriever.invoke(query)

        if k is not None:
            results = results[:k]

        return results

    def _clear_index(self) -> None:
        """
        Очищает индекс
        """
        logger.info('Clearing existing index...')

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

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
    )

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

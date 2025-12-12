"""
Модуль улучшения RAG-запросов.

Содержит:
- QueryRewriter: переформулирование запросов для лучшего поиска
- DocumentGrader: оценка релевантности документов (batch версия)
"""

import re

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_gigachat import GigaChat

from langgraph_app.config import get_agent_config
from langgraph_app.logging_config import get_logger
from langgraph_app.rag.config import RAGConfig, get_rag_config
from prompts import load_prompt

logger = get_logger(__name__)


# Query Rewriter - загружаем prompt из файла
_query_rewrite_system = load_prompt("rag/query_rewrite.txt")

QUERY_REWRITE_PROMPT = ChatPromptTemplate.from_messages(
    [
        ('system', _query_rewrite_system),
        ('human', 'Исходный запрос: {query}\n\nПереформулированный запрос:'),
    ]
)


class QueryRewriter:
    """
    Переформулирует запросы пользователя для улучшения качества поиска.

    Использует LLM для генерации более информативного запроса,
    который лучше подходит для векторного и ключевого поиска.
    """

    def __init__(self, llm: GigaChat | None = None):
        if llm is None:
            agent_config = get_agent_config()
            llm = GigaChat(
                model=agent_config.llm.model,
                temperature=agent_config.llm.temperature_tools,
                verify_ssl_certs=False,
            )
        self.chain = QUERY_REWRITE_PROMPT | llm | StrOutputParser()

    def rewrite(self, query: str) -> str:
        """
        Переформулирует запрос.

        Args:
            query: Исходный запрос пользователя

        Returns:
            Улучшенный запрос для поиска
        """
        try:
            rewritten = self.chain.invoke({'query': query})
            rewritten = rewritten.strip().strip('"').strip("'")

            logger.info(
                "query_rewritten",
                original=query,
                rewritten=rewritten,
                chars_added=len(rewritten) - len(query),
            )
            return rewritten

        except Exception as e:
            logger.warning(
                "query_rewrite_failed",
                query=query,
                error=str(e),
            )
            return query


# Document Grader (Batch version — один вызов LLM вместо N)
# Загружаем prompt из файла
_document_grade_system = load_prompt("rag/document_grade.txt")

DOCUMENT_BATCH_GRADE_PROMPT = ChatPromptTemplate.from_messages(
    [
        ('system', _document_grade_system),
        (
            'human',
            """Вопрос пользователя: {query}

Документы для оценки:
{documents_text}

Номера релевантных документов:""",
        ),
    ]
)


class DocumentGrader:
    """
    Оценивает релевантность документов запросу.

    Использует BATCH grading — один вызов LLM для всех документов,
    что снижает latency с ~10 секунд до ~1 секунды.
    """

    def __init__(self, llm: GigaChat | None = None, config: RAGConfig | None = None):
        self._config = config or get_rag_config()

        if llm is None:
            agent_config = get_agent_config()
            llm = GigaChat(
                model=agent_config.llm.model,
                temperature=agent_config.llm.temperature_classification,  # детерминированный
                verify_ssl_certs=False,
            )
        self.chain = DOCUMENT_BATCH_GRADE_PROMPT | llm | StrOutputParser()

    # TODO: write tests
    def _deduplicate_by_source(self, documents: list[Document]) -> list[Document]:
        """
        Дедупликация фрагментов/кусочков (чанков) по исходному документу.

        Если несколько чанков из одного документа (url), оставляем первый.
        Это важно для grading — не нужно оценивать 5 чанков одной страницы.

        Args:
            documents: Список документов с возможными дубликатами

        Returns:
            Список уникальных документов (по url)
        """
        seen_urls: set[str] = set()
        unique_docs: list[Document] = []

        for doc in documents:
            url = doc.metadata.get('url', '')
            if url and url in seen_urls:
                continue
            seen_urls.add(url)
            unique_docs.append(doc)

        if len(unique_docs) < len(documents):
            logger.info(
                "chunks_deduplicated",
                original_count=len(documents),
                unique_count=len(unique_docs),
            )

        return unique_docs

    def _format_documents_for_batch(self, documents: list[Document]) -> str:
        """
        Форматирует документы для batch grading промпта
        """
        preview_limit = self._config.search.content_preview_limit
        parts = []
        for i, doc in enumerate(documents, 1):
            # берём первые N символов для краткости
            text = doc.page_content[:preview_limit].replace('\n', ' ')
            title = doc.metadata.get('title', 'Без названия')
            parts.append(f'[{i}] {title}\n{text}...')
        return '\n\n'.join(parts)

    def _parse_batch_result(self, result: str, doc_count: int) -> list[int]:
        """
        Парсит ответ LLM с номерами релевантных документов.

        Args:
            result: Ответ LLM (например, "1, 3, 4" или "нет")
            doc_count: Общее количество документов

        Returns:
            Список индексов релевантных документов (0-based)
        """
        result_lower = result.lower().strip()

        # если LLM сказал "нет" или "none"
        if result_lower in ('нет', 'none', 'no', '-', ''):
            return []

        # парсим номера
        relevant_indices = []

        numbers = re.findall(r'\d+', result)

        for num_str in numbers:
            num = int(num_str)
            # конвертируем 1-based → 0-based, проверяем границы
            if 1 <= num <= doc_count:
                relevant_indices.append(num - 1)

        return relevant_indices

    def grade_batch(
        self,
        query: str,
        documents: list[Document],
    ) -> list[int]:
        """
        Оценивает все документы ОДНИМ вызовом LLM.

        Args:
            query: Запрос пользователя
            documents: Список документов для оценки

        Returns:
            Список индексов релевантных документов (0-based)
        """
        if not documents:
            return []

        try:
            docs_text = self._format_documents_for_batch(documents)

            result = self.chain.invoke(
                {
                    'query': query,
                    'documents_text': docs_text,
                }
            )

            relevant_indices = self._parse_batch_result(result, len(documents))

            logger.info(
                "batch_grading_complete",
                total_docs=len(documents),
                relevant_count=len(relevant_indices),
                relevant_indices=relevant_indices,
            )
            logger.debug(
                "batch_grading_llm_response",
                raw_response=result,
            )

            return relevant_indices

        except Exception as e:
            logger.warning(
                "batch_grading_failed",
                error=str(e),
                fallback="returning_all_as_relevant",
            )
            return list(range(len(documents)))

    def filter_relevant(
        self,
        query: str,
        documents: list[Document],
        min_relevant: int | None = None,
        deduplicate: bool = True,
    ) -> list[Document]:
        """
        Фильтрует список документов, оставляя только релевантные.

        Использует batch grading для эффективности.

        Args:
            query: Запрос пользователя
            documents: Список документов для фильтрации
            min_relevant: Минимум документов для возврата (None = из конфига)
            deduplicate: Дедуплицировать чанки по url перед grading

        Returns:
            Отфильтрованный список документов
        """
        if not documents:
            return []

        effective_min_relevant = min_relevant if min_relevant is not None else self._config.search.min_relevant

        # Step 1: Дедупликация (уменьшает количество документов для grading)
        docs_to_grade = documents
        if deduplicate:
            docs_to_grade = self._deduplicate_by_source(documents)

        # Step 2: Batch grading — ОДИН вызов LLM
        relevant_indices = self.grade_batch(query, docs_to_grade)

        # Step 3: Собираем релевантные документы
        relevant = [docs_to_grade[i] for i in relevant_indices]

        for doc in relevant:
            logger.debug(
                "document_graded_relevant",
                title=doc.metadata.get("title", "N/A"),
                url=doc.metadata.get("url", ""),
            )

        # если слишком мало релевантных, возвращаем топ оригинальных
        if len(relevant) < effective_min_relevant:
            logger.warning(
                "insufficient_relevant_docs",
                found=len(relevant),
                min_required=effective_min_relevant,
                fallback="returning_top_original",
            )
            return docs_to_grade[:effective_min_relevant]

        logger.info(
            "documents_filtered",
            input_count=len(docs_to_grade),
            output_count=len(relevant),
        )
        return relevant


# Enhanced RAG Search

class EnhancedRAGSearch:
    """
    Улучшенный RAG-поиск с query rewriting и document grading.

    Пайплайн:
    1. Query Rewriting — улучшаем запрос
    2. Hybrid Search — ищем документы
    3. Document Grading — фильтруем нерелевантные
    4. Return — возвращаем качественные результаты
    """

    def __init__(
        self,
        use_query_rewriting: bool = True,
        use_document_grading: bool = True,
        llm: GigaChat | None = None,
        config: RAGConfig | None = None,
    ):
        self.use_query_rewriting = use_query_rewriting
        self.use_document_grading = use_document_grading
        self._config = config or get_rag_config()

        # общий LLM для всех компонентов
        if llm is None:
            agent_config = get_agent_config()
            llm = GigaChat(
                model=agent_config.llm.model,
                temperature=agent_config.llm.temperature_tools,
                verify_ssl_certs=False,
            )

        self.query_rewriter = QueryRewriter(llm) if use_query_rewriting else None
        self.document_grader = DocumentGrader(llm, config=self._config) if use_document_grading else None

        # ленивая загрузка retriever через singleton
        self._retriever = None

    @property
    def retriever(self):
        """
        Ленивая инициализация retriever (singleton).

        Использует кэшированный HybridRetriever вместо создания
        нового HybridIndexer при каждом запросе.
        """
        if self._retriever is None:
            from langgraph_app.rag.retriever import get_retriever

            self._retriever = get_retriever()
        return self._retriever

    # Backward compatibility alias
    @property
    def indexer(self):
        """Deprecated: use retriever instead."""
        return self.retriever.indexer

    def search(
        self,
        query: str,
        k: int | None = None,
        min_relevant: int | None = None,
    ) -> tuple[list[Document], dict]:
        """
        Выполняет улучшенный поиск.

        Args:
            query: Запрос пользователя
            k: Количество документов для поиска (None = из конфига)
            min_relevant: Минимум релевантных документов (None = из конфига)

        Returns:
            Кортеж (документы, метаданные поиска)
        """
        effective_k = k if k is not None else self._config.search.k
        effective_min_relevant = min_relevant if min_relevant is not None else self._config.search.min_relevant

        metadata = {
            'original_query': query,
            'rewritten_query': None,
            'retrieved_count': 0,
            'filtered_count': 0,
        }

        # Step 1: Query Rewriting
        search_query = query
        if self.query_rewriter:
            search_query = self.query_rewriter.rewrite(query)
            metadata['rewritten_query'] = search_query

        # Step 2: Hybrid Search
        # запрашиваем больше документов, чтобы после фильтрации осталось достаточно
        fetch_k = effective_k * self._config.search.overfetch_multiplier if self.document_grader else effective_k
        documents = self.retriever.search(search_query, k=fetch_k)
        metadata['retrieved_count'] = len(documents)

        # Step 3: Document Grading
        if self.document_grader and documents:
            documents = self.document_grader.filter_relevant(
                query,  # используем оригинальный запрос для оценки
                documents,
                min_relevant=effective_min_relevant,
            )

        metadata['filtered_count'] = len(documents)

        # ограничиваем до k
        documents = documents[:effective_k]

        return documents, metadata

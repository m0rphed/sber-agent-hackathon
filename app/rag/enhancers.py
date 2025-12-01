"""
Модуль улучшения RAG-запросов.

Содержит:
- QueryRewriter: переформулирование запросов для лучшего поиска
- DocumentGrader: оценка релевантности документов
"""

import logging
from typing import Literal

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_gigachat import GigaChat

logger = logging.getLogger(__name__)


# ============================================================================
# Query Rewriter
# ============================================================================

QUERY_REWRITE_PROMPT = ChatPromptTemplate.from_messages([
    ('system', '''Ты — помощник для улучшения поисковых запросов.

Твоя задача: переформулировать запрос пользователя так, чтобы он лучше подходил
для поиска в базе знаний государственных услуг Санкт-Петербурга.

Правила:
1. Сохрани смысл исходного запроса
2. Добавь конкретику (документы, сроки, требования)
3. Используй официальную терминологию госуслуг
4. Запрос должен быть на русском языке
5. Верни ТОЛЬКО переформулированный запрос, без пояснений'''),
    ('human', 'Исходный запрос: {query}\n\nПереформулированный запрос:'),
])


class QueryRewriter:
    """
    Переформулирует запросы пользователя для улучшения качества поиска.
    
    Использует LLM для генерации более информативного запроса,
    который лучше подходит для векторного и ключевого поиска.
    """
    
    def __init__(self, llm: GigaChat | None = None):
        if llm is None:
            llm = GigaChat(
                model='GigaChat',
                temperature=0.3,
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
            
            logger.info(f'Query rewritten: "{query}" → "{rewritten}"')
            return rewritten
            
        except Exception as e:
            logger.warning(f'Query rewrite failed: {e}, using original query')
            return query


# ============================================================================
# Document Grader
# ============================================================================

DOCUMENT_GRADE_PROMPT = ChatPromptTemplate.from_messages([
    ('system', '''Ты — эксперт по оценке релевантности документов для поиска госуслуг.

Твоя задача: определить, может ли документ быть полезен для ответа на вопрос пользователя.

ВАЖНО: Будь снисходительным! Если документ хотя бы частично связан с темой вопроса — это "yes".

Примеры:
- Вопрос про загранпаспорт, документ про паспорт РФ → yes (связанная тема)
- Вопрос про пенсию, документ про выплаты → yes (связанная тема)
- Вопрос про загранпаспорт, документ про регистрацию автомобиля → no (не связано)

Отвечай ТОЛЬКО одним словом: "yes" или "no".'''),
    ('human', '''Вопрос: {query}

Документ:
---
{document}
---

Релевантен?'''),
])


class DocumentGrader:
    """
    Оценивает релевантность документов запросу.
    
    Фильтрует нерелевантные документы перед формированием ответа,
    что улучшает качество и уменьшает галлюцинации.
    """
    
    def __init__(self, llm: GigaChat | None = None):
        if llm is None:
            llm = GigaChat(
                model='GigaChat',
                temperature=0.0,  # детерминированный ответ
                verify_ssl_certs=False,
            )
        self.chain = DOCUMENT_GRADE_PROMPT | llm | StrOutputParser()
    
    def grade(self, query: str, document: Document) -> Literal['yes', 'no']:
        """
        Оценивает один документ.
        
        Args:
            query: Запрос пользователя
            document: Документ для оценки
            
        Returns:
            "yes" если релевантен, "no" если нет
        """
        try:
            # берём первые 1000 символов для оценки
            doc_text = document.page_content[:1000]
            
            result = self.chain.invoke({
                'query': query,
                'document': doc_text,
            })
            
            # проверяем и русский и английский варианты
            result_lower = result.lower().strip()
            if 'yes' in result_lower or 'да' in result_lower:
                return 'yes'
            return 'no'
            
        except Exception as e:
            logger.warning(f'Document grading failed: {e}, assuming relevant')
            return 'yes'
    
    def filter_relevant(
        self, 
        query: str, 
        documents: list[Document],
        min_relevant: int = 1,
    ) -> list[Document]:
        """
        Фильтрует список документов, оставляя только релевантные.
        
        Args:
            query: Запрос пользователя
            documents: Список документов для фильтрации
            min_relevant: Минимум документов для возврата (даже если не релевантны)
            
        Returns:
            Отфильтрованный список документов
        """
        relevant = []
        
        for doc in documents:
            grade = self.grade(query, doc)
            if grade == 'yes':
                relevant.append(doc)
                logger.debug(f'Document graded as relevant: {doc.metadata.get("title", "N/A")}')
            else:
                logger.debug(f'Document graded as NOT relevant: {doc.metadata.get("title", "N/A")}')
        
        # если слишком мало релевантных, возвращаем топ оригинальных
        if len(relevant) < min_relevant:
            logger.warning(
                f'Only {len(relevant)} relevant docs found, '
                f'returning top {min_relevant} from original'
            )
            return documents[:min_relevant]
        
        logger.info(f'Filtered {len(documents)} → {len(relevant)} relevant documents')
        return relevant


# ============================================================================
# Enhanced RAG Search
# ============================================================================

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
    ):
        self.use_query_rewriting = use_query_rewriting
        self.use_document_grading = use_document_grading
        
        # общий LLM для всех компонентов
        if llm is None:
            llm = GigaChat(
                model='GigaChat',
                temperature=0.3,
                verify_ssl_certs=False,
            )
        
        self.query_rewriter = QueryRewriter(llm) if use_query_rewriting else None
        self.document_grader = DocumentGrader(llm) if use_document_grading else None
        
        # ленивая загрузка индексатора
        self._indexer = None
    
    @property
    def indexer(self):
        """Ленивая инициализация индексатора"""
        if self._indexer is None:
            from app.rag.indexer import HybridIndexer
            self._indexer = HybridIndexer()
            self._indexer._load_bm25_docs()
        return self._indexer
    
    def search(
        self, 
        query: str, 
        k: int = 5,
        min_relevant: int = 2,
    ) -> tuple[list[Document], dict]:
        """
        Выполняет улучшенный поиск.
        
        Args:
            query: Запрос пользователя
            k: Количество документов для поиска
            min_relevant: Минимум релевантных документов
            
        Returns:
            Кортеж (документы, метаданные поиска)
        """
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
        fetch_k = k * 2 if self.document_grader else k
        documents = self.indexer.search(search_query, k=fetch_k)
        metadata['retrieved_count'] = len(documents)
        
        # Step 3: Document Grading
        if self.document_grader and documents:
            documents = self.document_grader.filter_relevant(
                query,  # используем оригинальный запрос для оценки
                documents,
                min_relevant=min_relevant,
            )
        
        metadata['filtered_count'] = len(documents)
        
        # ограничиваем до k
        documents = documents[:k]
        
        return documents, metadata

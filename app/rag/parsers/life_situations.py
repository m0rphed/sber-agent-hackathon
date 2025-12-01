"""
Парсер жизненных ситуаций МФЦ Санкт-Петербурга;

-> Источник: https://gu.spb.ru/mfc/life_situations

Структура сайта:
- Главная страница со списком категорий (жизненных ситуаций)
- Каждая категория содержит подкатегории и услуги
- Услуги могут иметь вложенные страницы с деталями

Стратегия парсинга:
1. Получаем список всех категорий с главной страницы
2. Для каждой категории парсим подкатегории и услуги
3. Рекурсивно обходим вложенные страницы
4. Сохраняем иерархию через parent_id
"""

import logging
import re
from typing import Any

from bs4 import BeautifulSoup, Tag
from bs4.element import AttributeValueList

from app.rag.models import ParsedDocument, ParserResult, SourceType
from app.rag.parsers.base import BaseParser

logger = logging.getLogger(__name__)


class LifeSituationsParser(BaseParser):
    """
    Парсер жизненных ситуаций МФЦ Санкт-Петербурга.

    Особенности:
    - Рекурсивный обход иерархии категорий
    - Извлечение FAQ (популярные вопросы)
    - Сохранение связей parent-child
    - Поддержка инкрементального обновления
    """

    # URL для парсинга
    MAIN_URL = 'https://gu.spb.ru/mfc/life_situations/'
    CATEGORY_URL_PATTERN = re.compile(r'/mfc/life_situations/(\d+)/')

    def __init__(
        self,
        delay: float = 0.5,
        timeout: int = 30,
        max_depth: int = 3,
    ):
        """
        Args:
            delay: Задержка между запросами
            timeout: Таймаут запроса
            max_depth: Максимальная глубина рекурсии
        """
        super().__init__(
            base_url='https://gu.spb.ru',
            source_type=SourceType.LIFE_SITUATIONS,
            delay=delay,
            timeout=timeout,
        )
        self.max_depth = max_depth
        self._visited_urls: set[str] = set()

    def parse(self, **kwargs: Any) -> ParserResult:
        """
        Парсит все жизненные ситуации.

        Args:
            incremental: Если True, парсит только изменённые документы

        Returns:
            ParserResult с документами и статистикой
        """
        incremental = kwargs.get('incremental', False)
        result = ParserResult()
        result.stats['start_time'] = __import__('datetime').datetime.now().isoformat()

        logger.info(f'Starting life_situations parsing (incremental={incremental})')

        # 1. получаем список категорий с главной страницы
        categories = self._get_categories()
        result.stats['categories_found'] = len(categories)
        logger.info(f'Found {len(categories)} categories')

        # 2. парсим каждую категорию
        for category_url, category_title in categories:
            try:
                category_result = self._parse_category(
                    url=category_url,
                    title=category_title,
                    depth=0,
                )
                result = result.merge(category_result)

            except Exception as e:
                logger.error(f'Error parsing category {category_url}: {e}')
                result.add_error(category_url, str(e))

        result.stats['end_time'] = __import__('datetime').datetime.now().isoformat()
        result.stats['total_documents'] = result.success_count
        result.stats['total_errors'] = result.error_count

        logger.info(
            f'Parsing complete: {result.success_count} documents, {result.error_count} errors'
        )

        return result

    def _get_categories(self) -> list[tuple[str, str]]:
        """
        Получает список категорий с главной страницы.

        Returns:
            Список кортежей (url, title)
        """
        soup = self.fetch_page(self.MAIN_URL)
        if not soup:
            return []

        categories = []

        # ищем ссылки на категории
        # - структура: <a href="/mfc/life_situations/190057/">Рождение ребёнка</a>
        for link in soup.find_all('a', href=self.CATEGORY_URL_PATTERN):
            href = link.get('href', '')
            title = self.clean_text(link.get_text())

            if href and title:
                full_url = self.get_absolute_url(href)  # type: ignore[arg-type]
                if full_url not in self._visited_urls:
                    categories.append((full_url, title))

        return categories

    def _parse_category(
        self,
        url: str,
        title: str,
        depth: int,
        parent_id: str | None = None,
    ) -> ParserResult:
        """
        Парсит категорию и её подкатегории.

        Args:
            url: URL категории
            title: Заголовок категории
            depth: Текущая глубина рекурсии
            parent_id: ID родительской категории

        Returns:
            ParserResult с документами категории
        """
        result = ParserResult()

        if url in self._visited_urls:
            return result

        if depth > self.max_depth:
            logger.debug(f'Max depth reached for {url}')
            return result

        self._visited_urls.add(url)

        # парсим страницу категории
        doc = self.parse_page(url)
        if doc:
            doc.parent_id = parent_id
            doc.category = title
            result.add_document(doc)

            # ищем подкатегории
            soup = self.fetch_page(url)
            if soup:
                subcategories = self._extract_subcategories(soup)
                for sub_url, sub_title in subcategories:
                    if sub_url not in self._visited_urls:
                        sub_result = self._parse_category(
                            url=sub_url,
                            title=sub_title,
                            depth=depth + 1,
                            parent_id=doc.doc_id,
                        )
                        result = result.merge(sub_result)

                # Извлекаем FAQ если есть
                faq_docs = self._extract_faq(soup, doc.doc_id, title)
                for faq_doc in faq_docs:
                    result.add_document(faq_doc)

        else:
            result.add_error(url, 'Failed to parse page')

        return result

    def parse_page(self, url: str) -> ParsedDocument | None:
        """
        Парсит отдельную страницу жизненной ситуации.

        Args:
            url: URL страницы

        Returns:
            ParsedDocument или None
        """
        soup = self.fetch_page(url)
        if not soup:
            return None

        # извлекаем заголовок
        title = self._extract_title(soup)
        if not title:
            logger.warning(f'No title found for {url}')
            return None

        # извлекаем основной контент
        content = self._extract_content(soup)
        if not content:
            logger.warning(f'No content found for {url}')
            # Всё равно создаём документ с заголовком
            content = title

        # создаём документ
        doc_id = self.extract_id_from_url(url)

        return ParsedDocument(
            doc_id=f'life_situation_{doc_id}',
            title=title,
            content=content,
            url=url,
            source_type=self.source_type,
            metadata={
                'has_subcategories': self._has_subcategories(soup),
            },
        )

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """
        Извлекает заголовок страницы
        """
        # пробуем разные селекторы
        selectors = [
            'h1',
            'h2',
            '.page-title',
            '.content-title',
        ]

        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                title = self.clean_text(element.get_text())
                if title and len(title) > 3:
                    return title

        return ''

    def _extract_content(self, soup: BeautifulSoup) -> str:
        """
        Извлекает основной контент страницы
        """
        content_parts = []

        # ищем основной контентный блок - article содержит вводный текст
        article = soup.select_one('article')
        if not article:
            article = soup.select_one('main')
        if not article:
            article = soup.find('body')

        if not article:
            return ''

        # удаляем ненужные элементы внутри контента
        for selector in [
            'nav',
            'footer',
            'header',
            'script',
            'style',
            'noscript',
            '.social-links',
            '.breadcrumbs',
            '.header',
            '.footer',
            '.header-popup',
            '.header-bar',
            '[class*="social"]',
        ]:
            for element in article.select(selector):
                element.decompose()

        # извлекаем вводный текст из article
        intro_text = self._extract_intro_text(article)
        if intro_text:
            content_parts.append(intro_text)

        # извлекаем drop-down секции (комплексы услуг)
        # (TODO: можно улучшить извлечение ссылок на услуги внутри секций)
        # ВАЖНО: droppanel секции находятся вне article, на уровне body
        droppanel_content = self._extract_droppanel_sections(soup)
        if droppanel_content:
            content_parts.append(droppanel_content)

        return '\n\n'.join(content_parts)

    def _extract_intro_text(self, container: Tag) -> str:
        """
        Извлекает вводный текст до droppanel секций
        """
        intro_parts = []

        # ищем параграфы на верхнем уровне (не внутри droppanel)
        for element in container.find_all(['p'], recursive=False):
            text = self.clean_text(element.get_text())
            if text and len(text) > 15:
                if not self._is_garbage_text(text):
                    intro_parts.append(text)

        # также проверяем div-ы верхнего уровня с текстом
        for div in container.find_all('div', recursive=False):
            # пропускаем droppanel секции
            classes: AttributeValueList = div.get('class', [])  # type: ignore
            if any('droppanel' in c or 'accordion' in c for c in classes):
                continue

            # ищем параграфы внутри
            for p in div.find_all('p'):
                text = self.clean_text(p.get_text())
                if text and len(text) > 15:
                    if not self._is_garbage_text(text):
                        intro_parts.append(text)

        return '\n'.join(intro_parts)

    def _extract_droppanel_sections(self, container: Tag) -> str:
        """
        Извлекает контент из drop-down секций (droppanel/accordion).

        Структура на сайте:
        - section.droppanel.accordion - контейнер секции
        - button.droppanel__head - заголовок секции (Базовый комплекс услуг)
        - div.droppanel__body - содержимое с ссылками на услуги
        """
        sections_content = []

        # ищем все droppanel секции
        droppanels = container.select('section.droppanel, section.accordion')

        for panel in droppanels:
            section_parts = []

            # извлекаем заголовок секции
            header = panel.select_one(
                '.droppanel__head-title, .droppanel__head, button.accordion__button'
            )
            if header:
                header_text = self.clean_text(header.get_text())
                if header_text and len(header_text) > 3:
                    section_parts.append(f'\n## {header_text}')

            # извлекаем содержимое секции
            body = panel.select_one('.droppanel__body, .accordion__drop')
            if body:
                # извлекаем ссылки на услуги
                service_links = self._extract_service_links_from_body(body)
                if service_links:
                    section_parts.append('Услуги:')
                    for service_title, service_url in service_links:
                        section_parts.append(f'- {service_title} ({service_url})')

                # извлекаем дополнительный текст
                for p in body.find_all('p'):
                    text = self.clean_text(p.get_text())
                    if text and len(text) > 15 and not self._is_garbage_text(text):
                        section_parts.append(text)

            if section_parts:
                sections_content.append('\n'.join(section_parts))

        return '\n\n'.join(sections_content)

    def _extract_service_links_from_body(self, body: Tag) -> list[tuple[str, str]]:
        """
        Извлекает ссылки на услуги из тела droppanel.

        Returns:
            Список кортежей (название_услуги, url)
        """
        services = []

        # паттерн для ссылок на услуги: /123456/ или /service/123456/
        service_pattern = re.compile(r'^/(\d+)/?$|^/service/(\d+)/?$')

        for link in body.find_all('a', href=True):
            href = link.get('href', '')

            # проверяем что это ссылка на услугу
            if service_pattern.match(href): # type: ignore[arg-type]
                title = self.clean_text(link.get_text())
                if title and len(title) > 3:
                    full_url = self.get_absolute_url(href)  # type: ignore[arg-type]
                    services.append((title, full_url))

        return services

    def _is_garbage_text(self, text: str) -> bool:
        """
        Проверяет, является ли текст мусорным
        """
        skip_patterns = [
            'Загрузите наше приложение',
            'Скачайте приложение',
            'в социальных сетях',
            'Политика конфиденциальности',
            'Cookie',
            'Ctrl+Enter',
            'Подписаться',
            'Поделиться',
        ]
        return any(pattern.lower() in text.lower() for pattern in skip_patterns)

    def _extract_subcategories(self, soup: BeautifulSoup) -> list[tuple[str, str]]:
        """
        Извлекает ссылки на подкатегории
        """
        subcategories = []

        for link in soup.find_all('a', href=self.CATEGORY_URL_PATTERN):
            href = link.get('href', '')
            title = self.clean_text(link.get_text())

            if href and title:
                full_url = self.get_absolute_url(href)  # type: ignore[arg-type]
                # проверяем что это не текущая страница
                if full_url not in self._visited_urls:
                    subcategories.append((full_url, title))

        return subcategories

    def _extract_faq(
        self,
        soup: BeautifulSoup,
        parent_id: str,
        category: str,
    ) -> list[ParsedDocument]:
        """
        Извлекает FAQ (Популярные вопросы) со страницы.

        Returns:
            Список документов FAQ
        """
        faq_docs: list[Any] = []

        # ищем секцию FAQ
        faq_section = soup.find(
            lambda tag: tag.name in ['section', 'div']
            # TODO: [П|п]опулярные вопросы - мы не знаем точный регистр (?)
            and 'опулярные вопросы' in (tag.get_text() or '') #.lower()
        )

        if not faq_section:
            return faq_docs

        # ищем вопросы-ответы
        faq_items = faq_section.find_all(
            ['details', 'div'], class_=re.compile(r'faq|question|accordion')
        )

        for i, item in enumerate(faq_items):
            question = ''
            answer = ''

            # извлекаем вопрос
            q_element = item.find(['summary', 'h4', 'h5', '.question'])
            if q_element:
                question = self.clean_text(q_element.get_text())

            # извлекаем ответ
            a_element = item.find(['p', 'div'], class_=re.compile(r'answer|content'))
            if a_element:
                answer = self.clean_text(a_element.get_text())
            elif question:
                # берём весь текст кроме вопроса
                full_text = self.clean_text(item.get_text())
                answer = full_text.replace(question, '').strip()

            if question and answer:
                faq_doc = ParsedDocument(
                    doc_id=f'{parent_id}_faq_{i}',
                    title=question,
                    content=f'Вопрос: {question}\n\nОтвет: {answer}',
                    url='',  # faq не имеет отдельного url
                    source_type=self.source_type,
                    category=category,
                    parent_id=parent_id,
                    metadata={'is_faq': True},
                )
                faq_docs.append(faq_doc)

        return faq_docs

    def _has_subcategories(self, soup: BeautifulSoup) -> bool:
        """
        Проверяет, есть ли на странице подкатегории
        """
        links = soup.find_all('a', href=self.CATEGORY_URL_PATTERN)
        return len(links) > 1   # больше 1, т.к. может быть ссылка на себя


# CLI для тестирования
if __name__ == '__main__':
    # import json

    logging.basicConfig(level=logging.INFO)

    parser = LifeSituationsParser(delay=1.0)

    # -> тестируем на одной категории
    print('Testing single page parsing...')
    doc = parser.parse_page('https://gu.spb.ru/mfc/life_situations/190057/')
    if doc:
        print(f'Title: {doc.title}')
        print(f'Content length: {len(doc.content)} chars')
        print(f'First 500 chars: {doc.content[:500]}...')
    else:
        print('Failed to parse page')

    # -> полный парсинг (осторожно!)
    # result = parser.parse()
    # print(f'Parsed {result.success_count} documents')

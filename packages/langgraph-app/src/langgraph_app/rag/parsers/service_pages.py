"""
Парсер страниц услуг (service pages) МФЦ Санкт-Петербурга;

-> Источник: https://gu.spb.ru/{service_id}/

Структура страницы услуги:
- Заголовок h1 с названием услуги
- Табы (под-вкладки/столбцы/колонки) с контентом:
    - Описание услуги (Service_description)
    - Кто подаёт заявление (Who_applying)
    - Срок (srok)
    - Результат (Result)
    - МФЦ (mfc)
- Каждый таб - это article.tabs-item с соответствующим id

Стратегия парсинга:
1. Извлекаем заголовок услуги
2. Извлекаем контент из всех табов
3. Объединяем в структурированный документ
"""

import re
from typing import Any

from bs4 import BeautifulSoup, Tag

from langgraph_app.logging_config import get_logger
from langgraph_app.rag.models import ParsedDocument, ParserResult, SourceType
from langgraph_app.rag.parsers.base import BaseParser

logger = get_logger(__name__)


class ServicePageParser(BaseParser):
    """
    Парсер страниц услуг gu.spb.ru.

    Особенности:
    - Извлечение контента из всех табов
    - Структурированный вывод с секциями
    - Поддержка инкрементального обновления
    """

    # паттерн URL страницы услуги: /123456/ или /service/123456/
    SERVICE_URL_PATTERN = re.compile(r'^https://gu\.spb\.ru/(\d+)/?$')

    # маппинг ID "табов" на человекочитаемые названия
    TAB_NAMES = {
        'tab_item-Service_description': 'Описание услуги',
        'tab_item-Who_applying': 'Кто подаёт заявление',
        'tab_item-srok': 'Срок оказания услуги',
        'tab_item-Result': 'Результат',
        'tab_item-mfc': 'Получение услуги в МФЦ',
    }

    def __init__(
        self,
        delay: float = 0.5,
        timeout: int = 30,
    ):
        """
        Args:
            delay: Задержка между запросами
            timeout: Таймаут запроса
        """
        super().__init__(
            base_url='https://gu.spb.ru',
            source_type=SourceType.SERVICE_PAGES,
            delay=delay,
            timeout=timeout,
        )
        self._visited_urls: set[str] = set()

    def parse(self, urls: list[str] | None = None, **kwargs: Any) -> ParserResult:
        """
        Парсит список страниц услуг.

        Args:
            urls: Список URL страниц услуг для парсинга

        Returns:
            ParserResult с документами и статистикой
        """
        result = ParserResult()

        if not urls:
            logger.warning('No URLs provided for service page parsing')
            return result

        result.stats['start_time'] = __import__('datetime').datetime.now().isoformat()
        result.stats['total_urls'] = len(urls)

        logger.info(f'Starting service page parsing for {len(urls)} URLs')

        for i, url in enumerate(urls, 1):
            try:
                logger.info(f'[{i}/{len(urls)}] Parsing: {url}')
                doc = self.parse_page(url)
                if doc:
                    result.add_document(doc)
                else:
                    result.add_error(url, 'Failed to parse page')
            except Exception as e:
                logger.error(f'Error parsing {url}: {e}')
                result.add_error(url, str(e))

        result.stats['end_time'] = __import__('datetime').datetime.now().isoformat()
        result.stats['total_documents'] = result.success_count
        result.stats['total_errors'] = result.error_count

        logger.info(
            f'Parsing complete: {result.success_count} documents, {result.error_count} errors'
        )

        return result

    def parse_page(self, url: str) -> ParsedDocument | None:
        """
        Парсит отдельную страницу услуги.

        Args:
            url: URL страницы услуги

        Returns:
            ParsedDocument или None
        """
        if url in self._visited_urls:
            return None

        self._visited_urls.add(url)

        soup = self.fetch_page(url)
        if not soup:
            return None

        # извлекаем заголовок
        title = self._extract_title(soup)
        if not title:
            logger.warning(f'No title found for {url}')
            return None

        # извлекаем контент из всех табов
        content = self._extract_all_tabs_content(soup)
        if not content:
            logger.warning(f'No content found for {url}')
            content = title

        # извлекаем ID услуги из URL
        service_id = self.extract_id_from_url(url)

        # извлекаем дополнительные метаданные
        metadata = self._extract_metadata(soup)

        return ParsedDocument(
            doc_id=f'service_{service_id}',
            title=title,
            content=content,
            url=url,
            source_type=self.source_type,
            metadata=metadata,
        )

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """
        Извлекает заголовок услуги
        """
        h1 = soup.select_one('h1.title-regular, h1')
        if h1:
            return self.clean_text(h1.get_text())
        return ''

    def _extract_all_tabs_content(self, soup: BeautifulSoup) -> str:
        """
        Извлекает контент из всех табов страницы услуги.

        Returns:
            Объединённый контент со всех табов
        """
        content_parts = []

        # находим все tab panels
        tab_panels = soup.select('article.tabs-item')

        for panel in tab_panels:
            panel_id = panel.get('id', '')
            section_name = self.TAB_NAMES.get(panel_id, panel_id)  # type: ignore[arg-type]

            # извлекаем контент таба
            tab_content = self._extract_tab_content(panel)

            if tab_content:
                content_parts.append(f'\n## {section_name}\n')
                content_parts.append(tab_content)

        # извлекаем секцию "Популярные вопросы" (FAQ)
        faq_content = self._extract_faq_section(soup)
        if faq_content:
            content_parts.append(faq_content)

        return '\n'.join(content_parts)

    def _extract_faq_section(self, soup: BeautifulSoup) -> str:
        """
        Извлекает секцию "Популярные вопросы" со страницы услуги.

        Структура:
        - section#popularQuestions - контейнер
        - article.droppanel - каждый вопрос-ответ
        - .droppanel__head-title - текст вопроса
        - .droppanel__body .text-container - ответ

        Returns:
            Форматированный текст FAQ
        """
        faq_section = soup.select_one('section#popularQuestions')
        if not faq_section:
            return ''

        faq_parts = ['\n## Популярные вопросы\n']

        # находим все вопросы (droppanel внутри секции FAQ)
        questions = faq_section.select('article.droppanel')

        for q in questions:
            # извлекаем вопрос
            question_elem = q.select_one('.droppanel__head-title')
            if not question_elem:
                continue
            question_text = self.clean_text(question_elem.get_text())
            if not question_text:
                continue

            # извлекаем ответ
            answer_elem = q.select_one('.droppanel__body .text-container')
            if not answer_elem:
                continue

            answer_text = self._extract_answer_text(answer_elem)
            if not answer_text:
                continue

            # форматируем Q&A
            faq_parts.append(f'**Вопрос:** {question_text}')
            faq_parts.append(f'**Ответ:** {answer_text}')
            faq_parts.append('')  # пустая строка между вопросами

        if len(faq_parts) <= 1:  # только заголовок
            return ''

        return '\n'.join(faq_parts)

    def _extract_answer_text(self, container: Tag) -> str:
        """
        Извлекает текст ответа из контейнера.

        Args:
            container: Tag элемент .text-container с ответом

        Returns:
            Очищенный текст ответа
        """
        parts = []

        # Извлекаем параграфы
        for p in container.find_all('p'):
            text = self.clean_text(p.get_text())
            if text and len(text) > 3:
                parts.append(text)

        # Извлекаем списки
        for li in container.find_all('li'):
            text = self.clean_text(li.get_text())
            if text and len(text) > 3:
                parts.append(f'• {text}')

        return ' '.join(parts)

    def _extract_tab_content(self, panel: Tag) -> str:
        """
        Извлекает текстовый контент из одного таба.

        Args:
            panel: Tag элемент article.tabs-item

        Returns:
            Очищенный текст таба
        """
        # клонируем чтобы не модифицировать оригинал
        panel_copy = BeautifulSoup(str(panel), 'html.parser')

        # удаляем ненужные элементы
        for selector in ['script', 'style', 'nav', '.breadcrumbs']:
            for elem in panel_copy.select(selector):
                elem.decompose()

        content_parts = []

        # извлекаем заголовки
        for header in panel_copy.find_all(['h2', 'h3', 'h4']):
            text = self.clean_text(header.get_text())
            if text and len(text) > 2:
                content_parts.append(f'\n### {text}')

        # извлекаем параграфы
        for p in panel_copy.find_all('p'):
            text = self.clean_text(p.get_text())
            if text and len(text) > 10 and not self._is_garbage_text(text):
                content_parts.append(text)

        # извлекаем списки
        for li in panel_copy.find_all('li'):
            # пропускаем если это часть навигации
            if li.find_parent(['nav', 'header']):
                continue
            text = self.clean_text(li.get_text())
            if text and len(text) > 5 and not self._is_garbage_text(text):
                content_parts.append(f'• {text}')

        # извлекаем таблицы (часто содержат важную информацию)
        for table in panel_copy.find_all('table'):
            table_text = self._extract_table_text(table)
            if table_text:
                content_parts.append(table_text)

        return '\n'.join(content_parts)

    def _extract_table_text(self, table: Tag) -> str:
        """
        Извлекает текст из таблицы в читаемом формате
        """
        rows = []
        for tr in table.find_all('tr'):
            cells = []
            for td in tr.find_all(['td', 'th']):
                text = self.clean_text(td.get_text())
                if text:
                    cells.append(text)
            if cells:
                rows.append(' | '.join(cells))
        return '\n'.join(rows)

    def _extract_metadata(self, soup: BeautifulSoup) -> dict[str, Any]:
        """
        Извлекает дополнительные метаданные со страницы
        """
        metadata: dict[str, Any] = {}

        # извлекаем дату обновления
        time_elem = soup.select_one('time[datetime]')
        if time_elem:
            metadata['updated_at'] = time_elem.get('datetime', '')

        # извлекаем ссылку на организацию
        org_link = soup.select_one('a[href*="/organization/"]')
        if org_link:
            metadata['organization'] = self.clean_text(org_link.get_text())
            metadata['organization_url'] = self.get_absolute_url(org_link.get('href', ''))  # type: ignore[arg-type]

        # проверяем наличие кнопки "Получить услугу"
        get_service_btn = soup.select_one('a[href*="gosuslugi"], button:contains("Получить")')
        metadata['has_online_service'] = get_service_btn is not None

        return metadata

    def _is_garbage_text(self, text: str) -> bool:
        """Проверяет, является ли текст мусорным."""
        skip_patterns = [
            'Загрузите приложение',
            'Скачайте приложение',
            'Политика конфиденциальности',
            'Cookie',
            'Ctrl+Enter',
            'Подписаться',
            'Поделиться',
            'Свернуть',
            'Развернуть',
            'Показать ещё',
        ]
        return any(pattern.lower() in text.lower() for pattern in skip_patterns)

    @classmethod
    def is_service_url(cls, url: str) -> bool:
        """
        Проверяет, является ли URL страницей услуги
        """
        return bool(cls.SERVICE_URL_PATTERN.match(url))


# CLI для тестирования
if __name__ == '__main__':
    # import json
    import sys

    # Логгинг уже настроен через app.logging_config

    # Тестовые URL
    test_urls = [
        'https://gu.spb.ru/188353/',
        'https://gu.spb.ru/673843/',
    ]

    if len(sys.argv) > 1:
        test_urls = sys.argv[1:]

    parser = ServicePageParser()
    result = parser.parse(urls=test_urls)

    print('\n--- Results ---')
    print(f'Success: {result.success_count}')
    print(f'Errors: {result.error_count}')

    for doc in result.documents:
        print(f'\n--- {doc.title} ---')
        print(f'ID: {doc.doc_id}')
        print(f'URL: {doc.url}')
        print(f'Content length: {len(doc.content)} chars')
        print(f'Preview: {doc.content[:500]}...')

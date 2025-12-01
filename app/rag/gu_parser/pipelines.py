# Define your item pipelines here
from datetime import datetime
import json
from pathlib import Path

from itemadapter import ItemAdapter


class GuParserPipeline:
    """Pipeline для обработки данных из базы знаний"""

    def open_spider(self, spider):
        self.items_count = 0

    def close_spider(self, spider):
        pass

    def process_item(self, item, spider):
        # Добавляем timestamp
        item['scraped_at'] = datetime.now().isoformat()

        # Очистка и валидация данных
        if item.get('title'):
            item['title'] = item['title'].strip()

        if item.get('content'):
            item['content'] = item['content'].strip()

        self.items_count += 1

        return item


class MarkdownExportPipeline:
    """Пайплайн для сохранения каждой записи в отдельный .md-файл."""

    def __init__(self, output_dir: str = 'knowledge_base_md'):
        self.output_dir = Path(output_dir)

    @classmethod
    def from_crawler(cls, crawler):
        """
        Создание экземпляра пайплайна из настроек Scrapy.
        Можно переопределить каталог через KNOWLEDGE_BASE_MD_DIR.
        """
        output_dir = crawler.settings.get('KNOWLEDGE_BASE_MD_DIR', 'knowledge_base_md')
        return cls(output_dir=output_dir)

    def open_spider(self, spider):
        """Создаёт папку для markdown-файлов при старте паука."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def process_item(self, item, spider):
        """
        На каждый item создаёт отдельный .md-файл с:
        - шапкой (URL, Doc ID, Category, Content Length, Has Subcategories)
        - блоком Extracted Content
        - блоком Raw Metadata с JSON'ом item'а.
        """
        adapter = ItemAdapter(item)
        data = adapter.asdict()

        title = (data.get('title') or 'Без названия').strip()
        url = data.get('url') or ''
        category = data.get('category') or 'N/A'
        content = (data.get('content') or '').strip()

        # doc_id: если есть в item — используем; иначе генерим.
        raw_doc_id = data.get('doc_id')
        doc_id_for_header = raw_doc_id or self._make_doc_id(url, title)

        # имя файла по doc_id
        filename = f'{doc_id_for_header}.md'
        safe_filename = self._slugify(filename)
        file_path = self.output_dir / safe_filename

        # has_subcategories из metadata
        meta = data.get('metadata') or {}
        has_subcategories = False
        if isinstance(meta, dict):
            has_subcategories = bool(meta.get('has_subcategories', False))

        content_length = len(content)

        # JSON для блока Raw Metadata — берём весь item как есть,
        # чтобы он совпадал с тем, что уходит в knowledge_base.json.
        raw_metadata_json = json.dumps(data, ensure_ascii=False, indent=2)

        # Собираем markdown
        md_parts = []

        md_parts.append(f'# {title}\n')
        md_parts.append(f'**URL:** {url}')
        md_parts.append(f'**Doc ID:** {doc_id_for_header}')
        md_parts.append(f'**Category:** {category}')
        md_parts.append(f'**Content Length:** {content_length} chars')
        md_parts.append(f'**Has Subcategories:** {"True" if has_subcategories else "False"}\n')
        md_parts.append('---\n')

        md_parts.append('## Extracted Content\n')
        if content:
            md_parts.append(content)
            md_parts.append('')
        else:
            md_parts.append('_Контент отсутствует_')
            md_parts.append('')

        md_parts.append('---\n')
        md_parts.append('## Raw Metadata\n')
        md_parts.append('```json')
        md_parts.append(raw_metadata_json)
        md_parts.append('```')

        md_text = '\n'.join(md_parts)

        file_path.write_text(md_text, encoding='utf-8')

        # Обязательно возвращаем item, чтобы остальные пайплайны и FEEDS отработали.
        return item

    def _make_doc_id(self, url: str, title: str) -> str:
        """Простейший генератор doc_id, если его не проставил основной пайплайн."""
        if url:
            parts = [p for p in url.rstrip('/').split('/') if p]
            last = parts[-1]
            if last.isdigit():
                return f'knowledge_base_{last}'
            return last
        # fallback: режем заголовок
        safe_title = title[:50].strip().replace(' ', '_')
        return f'knowledge_base_{safe_title or "item"}'

    def _slugify(self, value: str) -> str:
        """Примитивный slug для имени файла (без спец-символов типа /)."""
        return value.replace(' ', '_').replace('/', '_').replace('\\', '_')

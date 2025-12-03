"""
Скрипт для инспекции результатов парсинга.

Сохраняет результаты в data/parsed_docs/ для визуальной проверки.

Запуск:
    python -m app.rag.inspect_parsed --pages 5    # парсить 5 страниц
    python -m app.rag.inspect_parsed --all        # парсить все
    python -m app.rag.inspect_parsed --url URL    # парсить одну страницу
"""

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from app.logging_config import get_logger
from app.rag.config import get_rag_config
from app.rag.parsers import LifeSituationsParser

logger = get_logger(__name__)


def dump_single_page(url: str, output_dir: Path) -> None:
    """
    Парсит и сохраняет одну страницу
    """
    parser = LifeSituationsParser(delay=0.5)
    doc = parser.parse_page(url)

    if not doc:
        logger.error(f'Failed to parse: {url}')
        return

    # сохраняем в markdown для удобного просмотра
    filename = f'{doc.doc_id}.md'
    filepath = output_dir / filename

    content = f"""# {doc.title}

**URL:** {doc.url}
**Doc ID:** {doc.doc_id}
**Source:** {doc.source_type.value}
**Content Hash:** {doc.content_hash}
**Parsed At:** {doc.parsed_at.isoformat()}

---

## Extracted Content

{doc.content}

---

## Metadata

```json
{json.dumps(doc.metadata, ensure_ascii=False, indent=2)}
```
"""

    filepath.write_text(content, encoding='utf-8')
    logger.info(f'Saved: {filepath} ({len(doc.content)} chars)')


def dump_categories(max_pages: int | None, output_dir: Path) -> None:
    """
    Парсит категории и их подстраницы
    """
    parser = LifeSituationsParser(delay=0.5, max_depth=2)

    # получаем список категорий
    categories = parser._get_categories()
    logger.info(f'Found {len(categories)} categories')

    # создаём индексный файл
    index_content = f"""# Жизненные ситуации МФЦ — Результаты парсинга

**Дата:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Категорий найдено:** {len(categories)}
**Лимит страниц:** {max_pages or 'все'}

## Категории

| # | Название | URL | Статус |
|---|----------|-----|--------|
"""

    parsed_count = 0
    results_summary: list[dict[str, Any]] = []

    for i, (url, title) in enumerate(categories):
        if max_pages and parsed_count >= max_pages:
            index_content += f'| {i+1} | {title} | [link]({url}) | ⏭️ skipped |\n'
            continue

        logger.info(f'[{i+1}/{len(categories)}] Parsing: {title}')

        try:
            doc = parser.parse_page(url)

            if doc:
                # сохраняем в markdown
                filename = f'{doc.doc_id}.md'
                filepath = output_dir / filename

                md_content = f"""# {doc.title}

**URL:** {doc.url}
**Doc ID:** {doc.doc_id}
**Category:** {doc.category or 'N/A'}
**Content Length:** {len(doc.content)} chars
**Has Subcategories:** {doc.metadata.get('has_subcategories', False)}

---

## Extracted Content

{doc.content}

---

## Raw Metadata

```json
{json.dumps(doc.to_dict(), ensure_ascii=False, indent=2, default=str)}
```
"""
                filepath.write_text(md_content, encoding='utf-8')

                index_content += f'| {i+1} | [{title}]({filename}) | [source]({url}) | ✅ {len(doc.content)} chars |\n'
                parsed_count += 1

                results_summary.append({
                    'title': title,
                    'doc_id': doc.doc_id,
                    'content_length': len(doc.content),
                    'url': url,
                })
            else:
                index_content += f'| {i+1} | {title} | [link]({url}) | ❌ failed |\n'

        except Exception as e:
            logger.error(f'Error parsing {title}: {e}')
            index_content += f'| {i+1} | {title} | [link]({url}) | ❌ {str(e)[:30]} |\n'

    # добавляем статистику
    index_content += f"""

## Статистика

- **Успешный парсинг:** {parsed_count}
- **Всего категорий:** {len(categories)}
- **Общий объём контента:** {sum(r['content_length'] for r in results_summary)} chars

## Файлы

"""
    for r in results_summary:
        index_content += f"- `{r['doc_id']}.md` — {r['title']} ({r['content_length']} chars)\n"

    # сохраняем индекс
    index_path = output_dir / 'INDEX.md'
    index_path.write_text(index_content, encoding='utf-8')
    logger.info(f'Index saved: {index_path}')

    # также сохраняем JSON для программного анализа
    json_path = output_dir / 'summary.json'
    json_path.write_text(
        json.dumps(results_summary, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    logger.info(f'Summary JSON: {json_path}')


def main():
    parser = argparse.ArgumentParser(description='Inspect parsed content')

    parser.add_argument(
        '--url',
        type=str,
        help='Parse single URL',
    )
    parser.add_argument(
        '--pages',
        type=int,
        default=5,
        help='Max pages to parse (default: 5)',
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Parse all pages (no limit)',
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=None,
        help='Output directory',
    )

    args = parser.parse_args()

    # определяем output директорию
    config = get_rag_config()
    output_dir = args.output or (config.index.parsed_docs_dir / 'inspection')
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f'Output directory: {output_dir}')

    if args.url:
        dump_single_page(args.url, output_dir)
    else:
        max_pages = None if args.all else args.pages
        dump_categories(max_pages, output_dir)

    logger.info(f'Done! Check {output_dir}')


if __name__ == '__main__':
    main()

import scrapy
from gu_parser.items import KnowledgeBaseItem


class KnowledgeBaseSpider(scrapy.Spider):
    """Spider для парсинга базы знаний GU SPB"""

    name = 'knowledge_base'
    allowed_domains = ['gu.spb.ru']
    start_urls = ['https://gu.spb.ru/knowledge-base/']

    custom_settings = {
        'ITEM_PIPELINES': {
            'gu_parser.pipelines.GuParserPipeline': 300,
            'gu_parser.pipelines.MarkdownExportPipeline': 400,
        },
        'FEEDS': {
            'knowledge_base.json': {
                'format': 'json',
                'encoding': 'utf-8',
                'indent': 2,
                'ensure_ascii': False,
            },
        },
        'KNOWLEDGE_BASE_MD_DIR': 'knowledge_base_md',
    }

    def __init__(self, *args, **kwargs):
        super(KnowledgeBaseSpider, self).__init__(*args, **kwargs)
        self.pages_parsed = 0

    def parse(self, response):
        """Парсинг главной страницы базы знаний"""
        article_cards = response.css('div.element-card div.caseinfo')

        for card in article_cards:
            article_link = card.css('div.line-base a.ambient__link-ctrl::attr(href)').get()
            title = card.css('div.line-base a.ambient__link-ctrl::text').get()
            image = card.css('img.img-content::attr(src)').get()

            if article_link:
                full_url = response.urljoin(article_link)
                yield scrapy.Request(
                    full_url,
                    callback=self.parse_article,
                    meta={'card_title': title.strip() if title else None, 'card_image': image},
                )

        # Парсинг пагинации
        pagination_links = response.css('a.pagination__list-button::attr(href)').getall()

        if not pagination_links:
            next_page = response.css('a.pagination__next::attr(href)').get()
            if next_page:
                pagination_links = [next_page]

        if not pagination_links:
            pagination_links = response.xpath(
                '//div[contains(@class, "pagination")]//a/@href'
            ).getall()

        for link in pagination_links:
            if link:
                yield response.follow(link, callback=self.parse)

    def parse_article(self, response):
        """Парсинг отдельной статьи"""
        self.pages_parsed += 1

        item = KnowledgeBaseItem()

        # URL статьи
        item['url'] = response.url

        # Заголовок статьи из meta (из карточки) или из самой страницы
        card_title = response.meta.get('card_title')
        page_title = response.css('h1::text').get()
        if not page_title:
            page_title = response.xpath('//h1/text()').get()

        item['title'] = (page_title or card_title or '').strip()

        # Изображение из карточки
        item['image'] = response.meta.get('card_image')

        # ===== ВЕРХНИЙ БЛОК С ЗАГОЛОВКОМ И ВВОДНЫМ ТЕКСТОМ =====
        header_sel = response.css('section.line-leading.box .text-container')
        header_texts = []
        header_paragraph_nodes = []

        if header_sel:
            header_title = header_sel.css('h1::text').get(default='').strip()
            header_par_texts = header_sel.css('p::text').getall()
            header_paragraphs = [p.strip() for p in header_par_texts if p.strip()]
            header_html = header_sel.get()

            # отдельное поле с тем самым блоком
            item['header_block'] = {
                'title': header_title or None,
                'text': ' '.join(header_paragraphs) if header_paragraphs else None,
                'paragraphs': header_paragraphs,
                'html': header_html,
            }

            header_texts = header_sel.css('::text').getall()
            header_paragraph_nodes = header_sel.css('p').getall()

        # ===== ИЗВЛЕЧЕНИЕ КОНТЕНТА =====
        content_blocks = []

        # 1) Основной контент в main/article
        main_content = response.css('main ::text, article ::text').getall()

        # 2) Если main/article пустые — fallback в text-container
        if not main_content:
            main_content = response.css('div.text-container ::text').getall()

        # 3) Совсем общий fallback по body
        if not main_content:
            main_content = response.css('body ::text').getall()

        # ВАЖНО: сначала добавляем текст из верхнего блока, затем основной
        for text in header_texts + main_content:
            cleaned = text.strip()
            if cleaned and len(cleaned) > 1:
                content_blocks.append(cleaned)

        item['content'] = ' '.join(content_blocks)

        # Параграфы (добавляем параграфы из header-блока + из main/article)
        paragraphs = response.css('main p').getall()
        if not paragraphs:
            paragraphs = response.css('article p').getall()
        if not paragraphs:
            paragraphs = response.css('div.text-container p').getall()

        # Включаем параграфы верхнего блока (если они есть)
        paragraphs = header_paragraph_nodes + paragraphs

        # Заголовки H2–H6
        headers = []
        for level in range(2, 7):
            h_tags = response.css(f'main h{level}::text, article h{level}::text').getall()
            if not h_tags:
                # вдруг заголовки лежат не в main/article
                h_tags = response.css(f'div.text-container h{level}::text').getall()
            headers.extend([f'H{level}: {h.strip()}' for h in h_tags if h.strip()])

        # Списки
        list_items = response.css(
            'main ul li::text, main ol li::text, '
            'article ul li::text, article ol li::text, '
            'div.text-container ul li::text, div.text-container ol li::text'
        ).getall()
        lists = [li.strip() for li in list_items if li.strip()]

        # Ссылки
        links = []
        article_links = response.css('main a, article a, div.text-container a')
        for link in article_links:
            link_text = link.css('::text').get()
            link_href = link.css('::attr(href)').get()
            if link_text and link_href:
                links.append({'text': link_text.strip(), 'url': response.urljoin(link_href)})

        # Раскрывающиеся блоки (accordion / droppanel)
        accordion_sections = []
        droppanels = response.css('div.droppanel, div.accordion')

        for panel in droppanels:
            section_title = panel.css(
                'h2::text, button.droppanel__head span.droppanel__head-title::text'
            ).get()

            if not section_title:
                section_title = panel.css('button ::text').get()

            section_body = panel.css('div.droppanel__body, div.accordion__drop')

            if section_body:
                body_texts = section_body.css('::text').getall()
                body_content = ' '.join([t.strip() for t in body_texts if t.strip()])

                body_paragraphs = section_body.css('p').getall()
                body_list_items = section_body.css('ul li, ol li').getall()

                body_links = []
                for link in section_body.css('a'):
                    link_text = link.css('::text').get()
                    link_href = link.css('::attr(href)').get()
                    if link_text and link_href:
                        body_links.append(
                            {'text': link_text.strip(), 'url': response.urljoin(link_href)}
                        )

                accordion_sections.append(
                    {
                        'title': section_title.strip() if section_title else None,
                        'content': body_content,
                        'paragraphs': body_paragraphs,
                        'list_items': body_list_items,
                        'links': body_links,
                    }
                )

        # Категория / хлебные крошки
        category = response.css('.breadcrumb ::text').getall()
        if not category:
            category = response.xpath(
                '//nav[contains(@class, "breadcrumb")]//text()'
            ).getall()

        category_clean = ' > '.join([c.strip() for c in category if c.strip()])
        item['category'] = category_clean if category_clean else None

        # Метаданные
        item['metadata'] = {
            'headers': headers,
            'lists': lists,
            'links': links,
            'accordion_sections': accordion_sections,
            'paragraphs_count': len(paragraphs),
            'response_status': response.status,
        }

        yield item


    def closed(self, reason):
        """Вызывается при закрытии spider"""
        pass

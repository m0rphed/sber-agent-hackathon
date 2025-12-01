import scrapy
from gu_parser.items import KnowledgeBaseItem


class KnowledgeBaseSpider(scrapy.Spider):
    """Spider для парсинга базы знаний GU SPB"""
    
    name = "knowledge_base"
    allowed_domains = ["gu.spb.ru"]
    start_urls = ["https://gu.spb.ru/knowledge-base/"]
    
    custom_settings = {
        'ITEM_PIPELINES': {
            'gu_parser.pipelines.GuParserPipeline': 300,
        },
        'FEEDS': {
            'knowledge_base.json': {
                'format': 'json',
                'encoding': 'utf-8',
                'indent': 2,
                'ensure_ascii': False,
            },
        },
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
                    meta={
                        'card_title': title.strip() if title else None,
                        'card_image': image
                    }
                )
        
        # Парсинг пагинации
        pagination_links = response.css('a.pagination__list-button::attr(href)').getall()
        
        if not pagination_links:
            next_page = response.css('a.pagination__next::attr(href)').get()
            if next_page:
                pagination_links = [next_page]
        
        if not pagination_links:
            pagination_links = response.xpath('//div[contains(@class, "pagination")]//a/@href').getall()
        
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
        
        # Приоритет: заголовок со страницы, если нет - из карточки
        item['title'] = (page_title or card_title or '').strip()
        
        # Изображение из карточки
        item['image'] = response.meta.get('card_image')
        
        # Извлечение всего контента статьи
        # Основной контент находится в main или в специальных блоках
        content_blocks = []
        
        # Собираем весь текстовый контент из основного блока
        # Используем разные селекторы для полноты
        main_content = response.css('main ::text, article ::text').getall()
        
        # Фильтруем и очищаем текст
        for text in main_content:
            cleaned = text.strip()
            if cleaned and len(cleaned) > 1:
                content_blocks.append(cleaned)
        
        item['content'] = ' '.join(content_blocks)
        
        # Извлекаем все параграфы для структурированного контента
        paragraphs = response.css('main p').getall()
        if not paragraphs:
            paragraphs = response.css('article p').getall()
        
        # Извлекаем все заголовки H2-H6 для структуры
        headers = []
        for level in range(2, 7):
            h_tags = response.css(f'main h{level}::text, article h{level}::text').getall()
            headers.extend([f"H{level}: {h.strip()}" for h in h_tags if h.strip()])
        
        # Извлекаем списки (ul, ol)
        lists = []
        list_items = response.css('main ul li::text, main ol li::text, article ul li::text, article ol li::text').getall()
        lists = [li.strip() for li in list_items if li.strip()]
        
        # Извлекаем ссылки внутри статьи
        links = []
        article_links = response.css('main a, article a')
        for link in article_links:
            link_text = link.css('::text').get()
            link_href = link.css('::attr(href)').get()
            if link_text and link_href:
                links.append({
                    'text': link_text.strip(),
                    'url': response.urljoin(link_href)
                })
        
        # ===== ПАРСИНГ РАСКРЫВАЮЩИХСЯ БЛОКОВ (ACCORDION/DROPPANEL) =====
        accordion_sections = []
        
        # Находим все блоки droppanel
        droppanels = response.css('div.droppanel, div.accordion')
        
        for panel in droppanels:
            # Извлекаем заголовок из h2.visually-hidden или из button
            section_title = panel.css('h2::text, button.droppanel__head span.droppanel__head-title::text').get()
            
            if not section_title:
                section_title = panel.css('button ::text').get()
            
            # Извлекаем содержимое из div.droppanel__body
            section_body = panel.css('div.droppanel__body, div.accordion__drop')
            
            if section_body:
                # Извлекаем весь текст из body
                body_texts = section_body.css('::text').getall()
                body_content = ' '.join([t.strip() for t in body_texts if t.strip()])
                
                # Извлекаем параграфы
                body_paragraphs = section_body.css('p').getall()
                
                # Извлекаем списки из этого блока
                body_list_items = section_body.css('ul li, ol li').getall()
                
                # Извлекаем ссылки из этого блока
                body_links = []
                for link in section_body.css('a'):
                    link_text = link.css('::text').get()
                    link_href = link.css('::attr(href)').get()
                    if link_text and link_href:
                        body_links.append({
                            'text': link_text.strip(),
                            'url': response.urljoin(link_href)
                        })
                
                accordion_sections.append({
                    'title': section_title.strip() if section_title else None,
                    'content': body_content,
                    'paragraphs': body_paragraphs,
                    'list_items': body_list_items,
                    'links': body_links
                })
        
        # Категория или breadcrumb
        category = response.css('.breadcrumb ::text').getall()
        if not category:
            category = response.xpath('//nav[contains(@class, "breadcrumb")]//text()').getall()
        
        category_clean = ' > '.join([c.strip() for c in category if c.strip()])
        item['category'] = category_clean if category_clean else None
        
        # Дополнительные метаданные
        item['metadata'] = {
            'headers': headers,
            'lists': lists,
            'links': links,
            'accordion_sections': accordion_sections,  # ДОБАВЛЕНО
            'paragraphs_count': len(paragraphs),
            'response_status': response.status,
        }
        
        yield item
    
    def closed(self, reason):
        """Вызывается при закрытии spider"""
        pass

# Define here the models for your scraped items
import scrapy


class KnowledgeBaseItem(scrapy.Item):
    """Item для хранения данных из базы знаний GU SPB"""
    
    # URL страницы
    url = scrapy.Field()
    
    # Заголовок статьи
    title = scrapy.Field()
    
    # Изображение из карточки
    image = scrapy.Field()
    
    # Полное содержимое статьи
    content = scrapy.Field()
    
    # Категория
    category = scrapy.Field()
    
    # Дата парсинга
    scraped_at = scrapy.Field()
    
    # Дополнительные метаданные (заголовки, списки, ссылки)
    metadata = scrapy.Field()

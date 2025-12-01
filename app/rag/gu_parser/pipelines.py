# Define your item pipelines here
from datetime import datetime


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

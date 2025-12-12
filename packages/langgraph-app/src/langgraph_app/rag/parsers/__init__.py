"""
Парсеры источников данных для RAG

Содержит:
- base.py - базовый класс парсера
- life_situations.py - парсер жизненных ситуаций МФЦ
- service_pages.py - парсер страниц услуг
"""

from langgraph_app.rag.parsers.base import BaseParser
from langgraph_app.rag.parsers.life_situations import LifeSituationsParser
from langgraph_app.rag.parsers.service_pages import ServicePageParser

__all__ = ['BaseParser', 'LifeSituationsParser', 'ServicePageParser']

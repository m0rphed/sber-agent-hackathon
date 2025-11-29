"""
LangChain Tools для городского помощника
"""

from app.tools.city_tools import (
    ALL_TOOLS as CITY_TOOLS,
    find_nearest_mfc_tool,
    get_pensioner_categories_tool,
    get_pensioner_services_tool,
)
from app.tools.rag_tools import RAG_TOOLS, search_city_services

# Все инструменты для агента
ALL_TOOLS = CITY_TOOLS + RAG_TOOLS

__all__ = [
    # City tools
    'find_nearest_mfc_tool',
    'get_pensioner_categories_tool',
    'get_pensioner_services_tool',
    # RAG tools
    'search_city_services',
    # Aggregated lists
    'CITY_TOOLS',
    'RAG_TOOLS',
    'ALL_TOOLS',
]

"""
LangChain Tools Tools - инструменты агента для работы с API и базой знаний.
"""

# V3: новые async tools на основе yazzh_final
from langgraph_app.tools.city_tools_v3 import ALL_TOOLS as CITY_TOOLS_V3
from langgraph_app.tools.rag_tools import RAG_TOOLS, search_city_services

# Все инструменты для агента (V3)
ALL_TOOLS = CITY_TOOLS_V3 + RAG_TOOLS

__all__ = [
    # V3 tools
    'CITY_TOOLS_V3',
    'RAG_TOOLS',
    'ALL_TOOLS',
    # RAG tool (часто используется отдельно)
    'search_city_services',
]


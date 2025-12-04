import logging
import os
from typing import Literal

from dotenv import load_dotenv

load_dotenv()

LOG_LEVEL = os.getenv('LOG_LEVEL', 'DEBUG').upper()
logging.basicConfig(level=LOG_LEVEL)

# подключение к LangGraph Server
LANGGRAPH_URL = os.getenv('LANGGRAPH_URL', 'http://localhost:2024')

# доступные графы (работают с messages) => задать одинаковые значения!
GraphType = Literal['supervisor', 'hybrid']  # какие id графов бывают
supported_graphs: set[GraphType] = {'supervisor', 'hybrid'}  # какие id поддерживаются сейчас в боте

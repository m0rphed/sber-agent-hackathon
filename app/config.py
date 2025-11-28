"""
конфигурация приложения
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# базовая директория для данных
DATA_DIR = Path(os.getenv('DATA_DIR', 'data'))

# GigaChat
GIGACHAT_CREDENTIALS        = os.getenv('GIGACHAT_CREDENTIALS', '')
GIGACHAT_SCOPE              = os.getenv('GIGACHAT_SCOPE', '')
GIGACHAT_VERIFY_SSL_CERTS   = os.getenv('GIGACHAT_VERIFY_SSL_CERTS', 'false').lower() == 'true'

# Настройки модели
CHUNK_SIZE = os.getenv('CHUNK_SIZE', '800')
CHUNK_OVERLAP = os.getenv('CHUNK_OVERLAP', '200')
TOP_K = os.getenv('TOP_K', '5')

# API "Я Здесь Живу"
API_GEO     = os.getenv('API_GEO', 'https://yazzh-geo.gate.petersburg.ru')
API_SITE    = os.getenv('API_SITE', 'https://yazzh.gate.petersburg.ru')

# регион по умолчанию (78 = Санкт-Петербург)
REGION_ID = os.getenv('REGION_ID', '78')

# путь к базе данных для памяти агента
MEMORY_DB_PATH = os.getenv('MEMORY_DB_PATH', 'data/memory.db')

SYSTEM_PROMPT_PATH = os.getenv('SYSTEM_PROMPT_PATH', 'prompts/city_agent_prompt.txt')

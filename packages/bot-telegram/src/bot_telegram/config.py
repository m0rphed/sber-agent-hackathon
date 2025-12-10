import logging
import os

from dotenv import load_dotenv

load_dotenv()

TOKEN_TG = os.getenv('TOKEN_TG', None)

LOG_LEVEL = os.getenv('LOG_LEVEL', 'DEBUG').upper()
logging.basicConfig(level=LOG_LEVEL)

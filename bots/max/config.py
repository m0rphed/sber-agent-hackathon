import logging
import os

from dotenv import load_dotenv

load_dotenv()

TOKEN_MAX = os.getenv('TOKEN_MAX', None)

LOG_LEVEL = os.getenv('LOG_LEVEL', 'DEBUG').upper()
logging.basicConfig(level=LOG_LEVEL)

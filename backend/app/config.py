import os
from dotenv import load_dotenv
load_dotenv()

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')
ALPHA_VANTAGE_API_KEY = os.getenv('ALPHA_VANTAGE_API_KEY', '')
BAND_AGENT_API_KEY = os.getenv('BAND_AGENT_API_KEY', '')
BAND_CHAT_ID = os.getenv('BAND_CHAT_ID', '')
BAND_BASE_URL = os.getenv('BAND_BASE_URL', 'https://app.band.ai/api/v1/agent')
DB_PATH = os.getenv('DB_PATH', 'marketmind.db')
MAX_POSITION_PCT = float(os.getenv('MAX_POSITION_PCT', '0.20'))
MAX_PORTFOLIO_EXPOSURE_PCT = float(os.getenv('MAX_PORTFOLIO_EXPOSURE_PCT', '0.70'))

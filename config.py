import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN", "")
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
REMINDER_HOUR: int = int(os.getenv("REMINDER_HOUR", "9"))
TIMEZONE: str = os.getenv("TIMEZONE", "Europe/Moscow")
DB_PATH: str = os.getenv("DB_PATH", "plants.db")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN is not set in .env")
if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY is not set in .env")

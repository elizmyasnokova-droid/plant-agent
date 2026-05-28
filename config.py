import os
from dotenv import load_dotenv

# Загружаем .env если он есть (для локальной разработки)
# На Railway переменные берутся напрямую из окружения
load_dotenv()

TELEGRAM_TOKEN: str = os.environ.get("TELEGRAM_TOKEN", "")
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
REMINDER_HOUR: int = int(os.environ.get("REMINDER_HOUR", "9"))
TIMEZONE: str = os.environ.get("TIMEZONE", "Europe/Moscow")
DB_PATH: str = os.environ.get("DB_PATH", "plants.db")

# Отладка — покажет что Railway передаёт
print(f"[config] TELEGRAM_TOKEN set: {bool(TELEGRAM_TOKEN)}")
print(f"[config] ANTHROPIC_API_KEY set: {bool(ANTHROPIC_API_KEY)}")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не найден! Проверь Variables в Railway.")
if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY не найден! Проверь Variables в Railway.")

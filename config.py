import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)


def _required(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise SystemExit(f"❌ Не задана переменная: {key}\nПроверь {env_path}")
    return value.strip()


BOT_TOKEN = _required("BOT_TOKEN")

_admin_raw = os.getenv("ADMIN_ID", "").strip()
ADMIN_ID = int(_admin_raw) if _admin_raw.isdigit() else None

DB_PATH = Path(__file__).parent / "bot.db"

# Интервал проверки таблиц (в секундах). Минимум 60, рекомендуется 300 (5 мин).
CHECK_INTERVAL = 300
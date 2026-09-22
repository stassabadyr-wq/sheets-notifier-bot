"""
Sheets Notifier Bot — точка входа.

⚠️ Это ДЕМО-версия. Полный код доступен в платной версии.

Демо показывает структуру проекта и базовый запуск.
Полная версия включает:
- bot_handlers.py (FSM, обработчики)
- yandex_sheets.py (Yandex Disk API)
- database.py (SQLite)

Купить полную версию: [ссылка на VibeDepot]
"""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s · %(levelname)s · %(name)s · %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


async def main():
    log.info("🚀 Sheets Notifier Bot — ДЕМО-версия")

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    me = await bot.get_me()
    log.info(f"✅ Бот @{me.username} подключён")

    log.warning("⚠️ Это демо. Полный функционал доступен в платной версии.")
    log.warning("   Полная версия: bot_handlers.py, yandex_sheets.py, database.py")

    await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Остановка")
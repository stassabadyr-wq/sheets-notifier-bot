"""
Точка входа: запускает бота и worker проверки таблиц одновременно.
"""
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN, CHECK_INTERVAL
from database import init_db
from bot_handlers import router, check_all_trackings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s · %(levelname)s · %(name)s · %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


async def tracking_worker(bot: Bot):
    """
    Бесконечный цикл проверки таблиц.
    Запускается в фоне, не блокирует бота.
    """
    log.info(f"▶️ Worker запущен (интервал: {CHECK_INTERVAL} сек)")

    # Первая проверка через 30 секунд после старта
    await asyncio.sleep(30)

    while True:
        try:
            await check_all_trackings(bot)
        except Exception as e:
            log.error(f"Ошибка в worker: {e}", exc_info=True)

        await asyncio.sleep(CHECK_INTERVAL)


async def main():
    log.info("=" * 60)
    log.info("🚀 Sheets Notifier Bot запускается...")
    log.info("=" * 60)

    # 1. Инициализация БД
    await init_db()
    log.info("✅ База данных готова")

    # 2. Создание бота и диспетчера
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)

    # 3. Проверка токена
    me = await bot.get_me()
    log.info(f"✅ Бот @{me.username} запущен (ID: {me.id})")
    log.info(f"📖 Имя: {me.first_name}")

    # 4. Запуск worker'а в фоне
    worker_task = asyncio.create_task(tracking_worker(bot), name="tracking_worker")

    # 5. Запуск polling
    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
        )
    finally:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
        await bot.session.close()
        log.info("👋 Бот остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Остановка по сигналу")
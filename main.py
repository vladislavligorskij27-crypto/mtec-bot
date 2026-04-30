import asyncio
import logging
import datetime
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN, MINSK_TZ
from app.services import scraper
from app.services.database import init_db, close_db
from app.handlers.common import router as main_router, send_morning_schedule, scheduled_check_updates
from app.handlers.feedback import router as feedback_router
from app.handlers.admin import router as admin_router
from app.handlers.rooms import router as rooms_router
from app.handlers.journal import router as journal_router  
from app.middlewares.antispam import AntiSpamMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logging.basicConfig(level=logging.INFO)

async def on_startup(bot: Bot):
    logging.info("⏳ Генерация первичного кэша при запуске...")
    now = datetime.datetime.now(MINSK_TZ)

    await scraper.build_global_cache(now.strftime("%d.%m.%Y"))

    if now.hour >= 16:
        await scraper.build_global_cache((now + datetime.timedelta(days=1)).strftime("%d.%m.%Y"))
        
    logging.info("✅ Первичный кэш загружен в память!")

async def main():
    # Прокси выпилен нахрен. Дефолтная инициализация:
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    scheduler = AsyncIOScheduler(timezone="Europe/Minsk")
    
    scheduler.add_job(
        send_morning_schedule, 
        trigger='cron', 
        day_of_week='mon-sat', 
        hour=7, 
        minute=0, 
        args=[bot]
    )
    
    scheduler.add_job(
        scheduled_check_updates,
        trigger='interval',
        minutes=5,
        args=[bot]
    )
    
    scheduler.start()

    dp.message.middleware(AntiSpamMiddleware())
    dp.callback_query.middleware(AntiSpamMiddleware())

    dp.include_router(admin_router)
    dp.include_router(rooms_router)
    dp.include_router(feedback_router)
    dp.include_router(journal_router)
    dp.include_router(main_router)

    await init_db()

    dp.startup.register(on_startup)

    @dp.shutdown()
    async def on_shutdown(*args):
        logging.info("Закрытие соединений с БД...")
        await close_db()
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен!")
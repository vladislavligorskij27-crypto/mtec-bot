import os
import signal
import sys
import time
import asyncio
import logging
import datetime
from aiogram import Router, F, Bot, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from app.services import database, scraper
from config import ADMIN_ID, MINSK_TZ

router = Router()
start_time = time.time()

ADMIN_IDS = [ADMIN_ID]

class AdminState(StatesGroup):
    waiting_for_broadcast_text = State()
    waiting_for_broadcast_target = State()
    waiting_for_broadcast_confirm = State()

@router.message(Command("admin"), F.from_user.id.in_(ADMIN_IDS))
async def admin_main(message: types.Message):
    db = await database.get_db()
    async with db.execute("SELECT COUNT(*) FROM users") as cursor:
        count = await cursor.fetchone()
    
    await message.answer(
        f"👨‍💻 **Панель администратора**\n\n"
        f"👥 Всего пользователей в базе: {count[0]}\n\n"
        f"Доступные команды:\n"
        f"/broadcast — запустить рассылку\n"
        f"/reply <id> <текст> — написать пользователю\n"
        f"/status — подробный статус системы\n"
        f"/reboot — перезагрузить бота\n"
        f"/cancel — отмена любого действия"
    )

@router.message(Command("reboot"), F.from_user.id.in_(ADMIN_IDS))
async def admin_reboot(message: types.Message):
    await message.answer("🔄 **Перезагрузка бота...**\nПосылаю сигнал остановки (SIGINT).")
    await asyncio.sleep(0.5)
    # Корректное завершение процесса для срабатывания хуков aiogram (закрытие БД)
    os.kill(os.getpid(), signal.SIGINT)

@router.callback_query(F.data == "restart_bot")
async def cb_restart(callback: CallbackQuery):
    if callback.from_user.id in ADMIN_IDS:
        await callback.answer("Запускаю процесс перезагрузки...")
        await callback.message.edit_text("♻️ Бот перезагружается...")
        await asyncio.sleep(0.5)
        os.kill(os.getpid(), signal.SIGINT)
    else:
        await callback.answer("У вас нет прав админа!", show_alert=True)

@router.message(Command("reply"), F.from_user.id.in_(ADMIN_IDS))
async def admin_reply(message: types.Message, bot: Bot):
    args = message.text.split(maxsplit=2)
    
    if len(args) < 3:
        return await message.answer(
            "⚠️ Неверный формат команды.\n"
            "Использование: `/reply <ID пользователя> <текст сообщения>`\n"
            "Пример: `/reply 1234567890 Привет!`"
        )
    
    user_id = args[1]
    reply_text = args[2]
    
    if not user_id.isdigit():
        return await message.answer("⚠️ ID пользователя должен состоять только из цифр.")
        
    try:
        await bot.send_message(chat_id=int(user_id), text=f"✉️ **Сообщение от Администратора:**\n\n{reply_text}", parse_mode="Markdown")
        await message.answer(f"✅ Сообщение успешно отправлено пользователю `{user_id}`.")
    except Exception as e:
        await message.answer(f"❌ Ошибка при отправке сообщения:\n{str(e)}")

@router.message(Command("broadcast"), F.from_user.id.in_(ADMIN_IDS))
async def broadcast_start(message: types.Message, state: FSMContext):
    await message.answer("Введите текст для рассылки или /cancel для отмены:", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(AdminState.waiting_for_broadcast_text)

@router.message(AdminState.waiting_for_broadcast_text, F.from_user.id.in_(ADMIN_IDS))
async def broadcast_ask_target(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        return await message.answer("❌ Рассылка отменена.")

    if not message.text and not message.photo:
        return await message.answer("Пожалуйста, отправьте текст (или фото с текстом).")

    # Сохраняем не только текст, но и file_id картинки, если она есть
    await state.update_data(
        broadcast_text=message.text or message.caption,
        broadcast_photo=message.photo[-1].file_id if message.photo else None
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Всем", callback_data="bc_target_all")],
        [InlineKeyboardButton(text="🎓 Только студентам", callback_data="bc_target_student")],
        [InlineKeyboardButton(text="👨‍🏫 Только преподавателям", callback_data="bc_target_teacher")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="bc_cancel")]
    ])

    await message.answer("📝 Сообщение принято. **Кому отправить рассылку?**", reply_markup=kb)
    await state.set_state(AdminState.waiting_for_broadcast_target)

@router.callback_query(AdminState.waiting_for_broadcast_target, F.data.startswith("bc_target_") | (F.data == "bc_cancel"))
async def broadcast_ask_sound(callback: CallbackQuery, state: FSMContext):
    if callback.data == "bc_cancel":
        await state.clear()
        return await callback.message.edit_text("❌ Рассылка отменена.")

    target = callback.data.replace("bc_target_", "")
    await state.update_data(broadcast_target=target)

    target_labels = {
        "all": "👥 Всем",
        "student": "🎓 Студентам",
        "teacher": "👨‍🏫 Преподавателям"
    }

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔊 Со звуком", callback_data="bc_sound")],
        [InlineKeyboardButton(text="🔕 Без звука (Ночью)", callback_data="bc_silent")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="bc_cancel")]
    ])

    await callback.message.edit_text(
        f"Выбрана аудитория: **{target_labels.get(target)}**.\nКак отправить сообщение?", 
        reply_markup=kb
    )
    await state.set_state(AdminState.waiting_for_broadcast_confirm)


async def _run_broadcast_task(bot: Bot, users: list, text: str, photo_id: str, is_silent: bool, admin_id: int, target: str):
    count_success = 0
    count_error = 0
    total = len(users)

    try:
        for idx, user in enumerate(users, 1):
            try:
                if photo_id:
                    await bot.send_photo(
                        chat_id=int(user[0]),
                        photo=photo_id,
                        caption=text,
                        disable_notification=is_silent
                    )
                else:
                    await bot.send_message(
                        chat_id=int(user[0]), 
                        text=text,
                        disable_notification=is_silent
                    )
                count_success += 1
                await asyncio.sleep(0.05) # Чуть ускорили, 20 сообщений в секунду - сейвово для ТГ
            except Exception as e:
                logging.error(f"Ошибка рассылки юзеру {user[0]}: {e}")
                count_error += 1
            
            if idx % 100 == 0: # Отчет каждые 100 юзеров (меньше спама админу)
                try:
                    await bot.send_message(
                        chat_id=admin_id,
                        text=f"⏳ Прогресс рассылки: {idx}/{total}...\n✅ Успешно: {count_success}\n❌ Ошибок: {count_error}"
                    )
                except: pass

        type_str = "🔕 Без звука" if is_silent else "🔊 Со звуком"
        target_labels = {"all": "👥 Всем", "student": "🎓 Студентам", "teacher": "👨‍🏫 Преподавателям"}
        
        await bot.send_message(
            chat_id=admin_id,
            text=(
                f"✅ **Рассылка завершена!**\n\n"
                f"🎯 Аудитория: {target_labels.get(target)}\n"
                f"🔊 Тип: {type_str}\n"
                f"📈 Успешно: {count_success}\n"
                f"📉 Ошибок: {count_error}"
            )
        )
    except Exception as e:
        logging.error(f"КРИТИЧЕСКАЯ ОШИБКА РАССЫЛКИ: {e}")
        try:
            await bot.send_message(chat_id=admin_id, text=f"❌ **Рассылка прервана из-за ошибки!**\nТекст ошибки: `{e}`")
        except: pass


@router.callback_query(AdminState.waiting_for_broadcast_confirm, F.data.in_(["bc_sound", "bc_silent", "bc_cancel"]))
async def broadcast_execute(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if callback.data == "bc_cancel":
        await state.clear()
        return await callback.message.edit_text("❌ Рассылка отменена.")

    data = await state.get_data()
    text = data.get("broadcast_text", "")
    photo_id = data.get("broadcast_photo")
    target = data.get("broadcast_target", "all")
    is_silent = (callback.data == "bc_silent")
    
    db = await database.get_db()

    try:
        if target == "all":
            async with db.execute("SELECT user_id FROM users") as cursor:
                users = await cursor.fetchall()
        else:
            async with db.execute("SELECT user_id FROM users WHERE role = ?", (target,)) as cursor:
                users = await cursor.fetchall()
    except Exception as e:
        await state.clear()
        return await callback.message.answer(
            f"⚠️ **Ошибка базы данных!** Возможно, в вашей таблице `users` нет нужной колонки.\n"
            f"Текст: `{e}`\nРассылка отменена."
        )

    if not users:
        await state.clear()
        return await callback.message.edit_text("❌ В выбранной аудитории нет пользователей.")

    await state.clear()
    
    await callback.message.edit_text(f"🚀 Рассылка запущена для {len(users)} чел. в фоне...\nЯ буду присылать отчеты по ходу дела!")

    asyncio.create_task(
        _run_broadcast_task(bot, users, text, photo_id, is_silent, callback.from_user.id, target)
    )

@router.message(Command("status"), F.from_user.id.in_(ADMIN_IDS))
async def admin_status(message: types.Message):
    uptime = time.time() - start_time
    up_str = time.strftime("%H:%M:%S", time.gmtime(uptime))
    now_minsk = datetime.datetime.now(MINSK_TZ).strftime("%H:%M:%S")
    
    try:
        db = await database.get_db()
        
        # ОДИН запрос вместо пяти (экономит время I/O)
        query = """
            SELECT 
                COUNT(*),
                SUM(CASE WHEN role = 'student' THEN 1 ELSE 0 END),
                SUM(CASE WHEN role = 'teacher' THEN 1 ELSE 0 END),
                SUM(CASE WHEN notifications = 1 THEN 1 ELSE 0 END),
                SUM(CASE WHEN curator_group IS NOT NULL THEN 1 ELSE 0 END)
            FROM users
        """
        async with db.execute(query) as cursor:
            res = await cursor.fetchone()
            
        total_users = res[0] or 0
        students = res[1] or 0
        teachers = res[2] or 0
        notif_on = res[3] or 0
        curators = res[4] or 0

        db_status = "✅ Подключена"
    except Exception as e:
        logging.error(f"Ошибка получения статуса: {e}")
        db_status = "❌ Ошибка БД"
        total_users = students = teachers = curators = notif_on = "?"

    # Кэш в памяти
    img_cache_size = len(scraper.IMAGE_CACHE)
    sched_cache_size = len(scraper.GLOBAL_SCHEDULE_CACHE)

    status_text = (
        f"📊 **Расширенный статус системы**\n\n"
        f"👥 **Пользователи:**\n"
        f"├ Всего в базе: `{total_users}`\n"
        f"├ Студенты: `{students}`\n"
        f"├ Преподаватели: `{teachers}`\n"
        f"├ Кураторы: `{curators}`\n"
        f"└ С уведомлениями: `{notif_on}`\n\n"
        f"💾 **Состояние кэша:**\n"
        f"├ Картинок в памяти: `{img_cache_size}`\n"
        f"└ Расписаний (дни): `{sched_cache_size}`\n\n"
        f"⚙️ **Параметры сервера:**\n"
        f"├ Время Минск: `{now_minsk}`\n"
        f"├ Аптайм бота: `{up_str}`\n"
        f"├ База данных: {db_status}\n"
        f"└ Python: `{sys.version.split()[0]}`"
    )

    await message.answer(status_text, parse_mode="Markdown")
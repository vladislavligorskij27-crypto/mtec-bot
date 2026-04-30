import logging
import re
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from app.keyboards import builders as kb
from config import ADMIN_ID

router = Router()

class FeedbackState(StatesGroup):
    waiting_for_message = State()

# --- ХЕНДЛЕРЫ ДЛЯ ПОЛЬЗОВАТЕЛЯ ---

@router.message(F.text == "📝 Обратная связь")
async def feedback_start(message: types.Message, state: FSMContext):
    await message.answer(
        "Напишите ваше сообщение (ошибку или предложение).\n"
        "Я передам его разработчику! 🫡\n\n"
        "Чтобы отменить, просто напишите /cancel",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await state.set_state(FeedbackState.waiting_for_message)

@router.message(FeedbackState.waiting_for_message, F.text == "/cancel")
async def feedback_cancel(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Отправка сообщения отменена.", reply_markup=kb.main_menu())

@router.message(FeedbackState.waiting_for_message)
async def feedback_sent(message: types.Message, state: FSMContext, bot: Bot):
    await bot.send_message(
        ADMIN_ID,
        f"📩 **Новое сообщение!**\n\n"
        f"От: {message.from_user.full_name} (@{message.from_user.username})\n"
        f"ID: `{message.from_user.id}`\n\n"
        f"Текст: {message.text}"
    )
    await message.answer("Спасибо! Ваше сообщение успешно доставлено.", reply_markup=kb.main_menu())
    await state.clear()

# --- ХЕНДЛЕР ДЛЯ АДМИНА (ОТВЕТ) ---

@router.message(F.reply_to_message)
async def reply_to_user(message: types.Message, bot: Bot):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        reply_msg = message.reply_to_message
        source_text = reply_msg.text or reply_msg.caption
        
        if not source_text:
            return

        match = re.search(r"ID:\s*`?(\d+)`?", source_text)
        
        if match:
            user_id = int(match.group(1))
            await bot.send_message(
                chat_id=user_id,
                text=f"✉️ **Ответ от разработчика:**\n\n{message.text}",
                parse_mode="Markdown"
            )
            await message.answer(f"✅ Ответ успешно отправлен пользователю `{user_id}`!")
        else:
            await message.answer("❌ Ошибка: Не удалось найти ID пользователя.")
            
    except Exception as e:
        logging.error(f"Ошибка в reply_to_user: {e}")
        await message.answer(f"❌ Ошибка при отправке: {e}")
import os
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import FSInputFile, CallbackQuery

from app.services import database
from app.services.journal_service import fetch_and_process_journal
from app.keyboards import builders as kb

router = Router()

class JournalStates(StatesGroup):
    waiting_for_login = State()
    waiting_for_password = State()

# --- ОТМЕНА ДЕЙСТВИЯ ---
@router.message(F.text == "/cancel", JournalStates.waiting_for_login)
@router.message(F.text == "/cancel", JournalStates.waiting_for_password)
async def cancel_journal_auth(message: types.Message, state: FSMContext):
    await state.clear()
    user = await database.get_user(message.from_user.id)
    await message.answer("❌ Авторизация отменена.", reply_markup=kb.main_menu(user['role'], bool(user['curator_group'])))


# --- ГЛАВНАЯ КНОПКА ЖУРНАЛА ---
@router.message(F.text == "📖 Электронный журнал")
@router.message(Command("journal"))
async def open_journal(message: types.Message, state: FSMContext):
    user = await database.get_user(message.from_user.id)
    if not user: return
    
    # Если данные уже есть - пытаемся получить журнал
    if user['journal_login'] and user['journal_password']:
        await send_journal_document(message, user['journal_login'], user['journal_password'], message.from_user.id)
        # Отправляем инлайн клавиатуру для управления данными
        await message.answer(
            "⚙️ **Управление журналом**\nВы можете изменить или удалить сохраненные данные авторизации.",
            reply_markup=kb.journal_settings_kb(),
            parse_mode="Markdown"
        )
    else:
        # Если данных нет - просим ввести логин
        await message.answer(
            "🔒 **Авторизация в Электронном журнале**\n\n"
            "Пожалуйста, введите ваше **ФИО** (как на сайте mtec.by).\n\n"
            "👉 *Для отмены напишите /cancel*",
            reply_markup=types.ReplyKeyboardRemove(),
            parse_mode="Markdown"
        )
        await state.set_state(JournalStates.waiting_for_login)

# --- ПРОЦЕСС ВВОДА ДАННЫХ ---
@router.message(JournalStates.waiting_for_login)
async def process_journal_login(message: types.Message, state: FSMContext):
    await state.update_data(login=message.text.strip())
    
    await message.answer(
        "🔑 Теперь введите **Пароль**:\n\n"
        "👉 *Для отмены напишите /cancel*",
        parse_mode="Markdown"
    )
    await state.set_state(JournalStates.waiting_for_password)

@router.message(JournalStates.waiting_for_password)
async def process_journal_password(message: types.Message, state: FSMContext):
    password = message.text.strip()
    data = await state.get_data()
    login = data.get("login")
    user_id = message.from_user.id
    
    wait_msg = await message.answer("⏳ Проверяю данные и загружаю журнал...")
    
    # Пробуем авторизоваться сразу
    success, result = await fetch_and_process_journal(login, password, user_id)
    
    user = await database.get_user(user_id)
    
    if success:
        # Сохраняем данные в БД только если авторизация успешна
        await database.save_journal_auth(user_id, login, password)
        await wait_msg.delete()
        
        await message.answer(
            "✅ **Успешно!** Ваши данные сохранены.", 
            reply_markup=kb.main_menu(user['role'], bool(user['curator_group'])),
            parse_mode="Markdown"
        )
        
        # Отправляем файл
        doc = FSInputFile(result)
        await message.answer_document(doc, caption="📖 Ваш электронный журнал")
        
        # Удаляем временный файл
        if os.path.exists(result):
            os.remove(result)
            
    else:
        await wait_msg.edit_text(
            f"❌ **Ошибка авторизации:**\n{result}\n\nПопробуйте нажать кнопку журнала еще раз.",
            parse_mode="Markdown"
        )
        await message.answer("Возврат в меню.", reply_markup=kb.main_menu(user['role'], bool(user['curator_group'])))

    await state.clear()


# --- ФУНКЦИЯ ОТПРАВКИ ЖУРНАЛА ПО УЖЕ СОХРАНЕННЫМ ДАННЫМ ---
async def send_journal_document(message: types.Message, login, password, user_id):
    wait_msg = await message.answer("⏳ Соединяюсь с сервером и загружаю журнал...")
    
    success, result = await fetch_and_process_journal(login, password, user_id)
    
    if success:
        await wait_msg.delete()
        doc = FSInputFile(result)
        await message.answer_document(doc, caption="📖 Ваш электронный журнал")
        
        if os.path.exists(result):
            os.remove(result)
    else:
        await wait_msg.edit_text(f"❌ **Ошибка при получении журнала:**\n{result}", parse_mode="Markdown")


# --- УПРАВЛЕНИЕ ДАННЫМИ (INLINE КНОПКИ) ---
@router.callback_query(F.data == "journal_change")
async def change_journal_data(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer(
        "🔄 **Смена данных журнала**\n\nВведите ваше новое **ФИО**:\n\n👉 *Для отмены напишите /cancel*",
        reply_markup=types.ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )
    await state.set_state(JournalStates.waiting_for_login)

@router.callback_query(F.data == "journal_delete")
async def delete_journal_data(callback: CallbackQuery):
    await database.delete_journal_auth(callback.from_user.id)
    await callback.answer("✅ Данные от журнала удалены из базы!", show_alert=True)
    await callback.message.edit_text("🗑 Данные удалены.")
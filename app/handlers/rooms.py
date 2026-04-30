import os
import logging
from aiogram import Router, F, types
from app.services import scraper
from app.keyboards import builders as kb
from config import ROOMS_FILE

router = Router()

def load_rooms_mapping():
    """Загружает словарь {чистое_имя: красивое_имя} для сопоставления"""
    if not os.path.exists(ROOMS_FILE):
        logging.error(f"Файл кабинетов не найден: {ROOMS_FILE}")
        return {}
    
    mapping = {}
    try:
        with open(ROOMS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                raw_name = line.strip()
                if not raw_name: continue
                clean_name = scraper.clean_room(raw_name)
                mapping[clean_name] = raw_name
        return mapping
    except Exception as e:
        logging.error(f"Ошибка загрузки комнат: {e}")
        return {}

ALL_ROOMS_MAP = load_rooms_mapping()

def format_free_rooms(rooms_list):
    if not rooms_list:
        return "❌ Все занято"
    
    categories = {
        "1️⃣ этаж": [],
        "2️⃣ этаж": [],
        "3️⃣ этаж": [],
        "4️⃣ этаж": [],
        "🏠 Общага": [],
        "🎭 Залы/Прочее": []
    }
    
    for r in rooms_list:
        r_low = r.lower()
        if "общ" in r_low:
            categories["🏠 Общага"].append(r)
        elif any(word in r_low for word in ["зал", "библиотека", "отдыха", "чит"]):
            categories["🎭 Залы/Прочее"].append(r)
        elif r.startswith("1"): categories["1️⃣ этаж"].append(r)
        elif r.startswith("2"): categories["2️⃣ этаж"].append(r)
        elif r.startswith("3"): categories["3️⃣ этаж"].append(r)
        elif r.startswith("4"): categories["4️⃣ этаж"].append(r)
        else: categories["🎭 Залы/Прочее"].append(r)

    output = []
    for cat, items in categories.items():
        if items:
            sorted_items = sorted(items)
            output.append(f"*{cat}:* {', '.join(sorted_items)}")
    
    return "\n   ".join(output)

@router.message(F.text == "🔍 Свободные кабинеты")
async def rooms_start(message: types.Message):
    await message.answer(
        "Выберите день для поиска свободных аудиторий:",
        reply_markup=kb.rooms_date_keyboard()
    )

@router.callback_query(F.data.startswith("rooms_date_"))
async def rooms_finish(callback: types.CallbackQuery):
    # Отвечаем серверу Telegram СРАЗУ, чтобы избежать ошибки timeout (query is too old)
    await callback.answer()
    
    date_str = callback.data.replace("rooms_date_", "")
    await callback.message.edit_text(f"⏳ Сверяю расписание на {date_str}...\nЭто займет пару секунд.")
    
    occupied_data = await scraper.get_occupied_rooms(date_str)
    
    header = f"🏛 **СВОБОДНЫЕ КАБИНЕТЫ**\n📅 `{date_str}`\n" + "—"*15 + "\n"
    res_parts = [header]
    
    pair_icons = {"1": "1️⃣", "2": "2️⃣", "3": "3️⃣", "4": "4️⃣", "5": "5️⃣", "6": "6️⃣", "7": "7️⃣", "8": "8️⃣"}
    all_clean_names = set(ALL_ROOMS_MAP.keys())

    for p in range(1, 9):
        p_str = str(p)
        occupied_in_pair = occupied_data.get(p_str, set())
        
        free_cleans = all_clean_names - occupied_in_pair
        free_list = [ALL_ROOMS_MAP[c] for c in free_cleans if c in ALL_ROOMS_MAP]
        
        formatted_rooms = format_free_rooms(free_list)
        res_parts.append(f"{pair_icons.get(p_str, p_str)} **пара:**\n   {formatted_rooms}\n")

    final_text = "\n".join(res_parts)
    if len(final_text) > 4096:
        await callback.message.edit_text(final_text[:4000] + "...")
    else:
        await callback.message.edit_text(final_text, parse_mode="Markdown")
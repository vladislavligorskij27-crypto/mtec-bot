import os
import datetime
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import MENTORS_FILE, MINSK_TZ

def load_list(file_path):
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def start_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="👨‍🎓 Студент", callback_data="role_student")
    builder.button(text="👨‍🏫 Преподаватель", callback_data="role_teacher")
    builder.adjust(1)
    return builder.as_markup()

def group_prefixes_keyboard(groups, mode="std"):
    builder = InlineKeyboardBuilder()
    prefixes = sorted(list(set(g[0] for g in groups if g)))
    for p in prefixes:
        callback = f"pref_{p}" if mode == "std" else f"curpref_{p}"
        builder.button(text=p, callback_data=callback)
    builder.adjust(4)
    return builder.as_markup()

def groups_by_prefix_keyboard(groups, prefix, mode="std"):
    builder = InlineKeyboardBuilder()
    filtered = [g for g in groups if g.startswith(prefix)]
    for g in filtered:
        callback = f"set_std_{g}" if mode == "std" else f"set_cur_{g}"
        builder.button(text=g, callback_data=callback)
    
    back_callback = "role_student" if mode == "std" else "is_curator_yes"
    builder.button(text="⬅️ Назад", callback_data=back_callback)
    builder.adjust(2)
    return builder.as_markup()

def alphabet_keyboard(mentors, mode="reg"):
    builder = InlineKeyboardBuilder()
    letters = sorted(list(set(m[0] for m in mentors if m)))
    for l in letters:
        cb = f"let_{l}" if mode == "reg" else f"srch_let_{l}"
        builder.button(text=l, callback_data=cb)
    builder.adjust(5)
    return builder.as_markup()

def mentors_by_letter_keyboard(mentors, letter, mode="reg"):
    builder = InlineKeyboardBuilder()
    for idx, m in enumerate(mentors):
        if m.startswith(letter):
            cb = f"set_tch_{idx}" if mode == "reg" else f"srch_ment_{idx}"
            builder.button(text=m, callback_data=cb)
    
    back_cb = "role_teacher" if mode == "reg" else "search_mentor_back"
    builder.button(text="⬅️ Назад", callback_data=back_cb)
    builder.adjust(1)
    return builder.as_markup()

def curator_choice_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, я куратор", callback_data="is_curator_yes")
    builder.button(text="❌ Нет", callback_data="is_curator_no")
    builder.adjust(2)
    return builder.as_markup()

def future_days_keyboard(mode="std"):
    builder = InlineKeyboardBuilder()
    now = datetime.datetime.now(MINSK_TZ)
    day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

    added = 0
    for i in range(1, 8): 
        d = now + datetime.timedelta(days=i)
        if d.weekday() == 6: continue 
        
        date_str = d.strftime("%d.%m.%Y")
        name = f"{date_str} ({day_names[d.weekday()]})"
        
        cb_data = f"show_date_{date_str}" if mode == "std" else f"cur_date_{date_str}"
        builder.button(text=name, callback_data=cb_data)
        
        added += 1
        if added >= 5: break 
        
    builder.adjust(2) 
    return builder.as_markup()

def main_menu(role="student", is_curator=False):
    now = datetime.datetime.now(MINSK_TZ)
    weekday = now.weekday() 
    
    if weekday < 5: 
        schedule_row = [KeyboardButton(text="📅 На сегодня"), KeyboardButton(text="⏭️ На завтра")]
    elif weekday == 5: 
        schedule_row = [KeyboardButton(text="📅 На сегодня"), KeyboardButton(text="➡️ На понедельник")]
    else: 
        schedule_row = [KeyboardButton(text="➡️ На понедельник")]

    buttons = [
        schedule_row,
        [KeyboardButton(text="🗓 Другие дни")]
    ]

    if role == "student":
        buttons.append([KeyboardButton(text="🔍 Свободные кабинеты"), KeyboardButton(text="🔍 Где препод?")])
        buttons.append([KeyboardButton(text="📖 Электронный журнал"), KeyboardButton(text="📂 Архив расписания")])
        buttons.append([KeyboardButton(text="🔔 Звонки"), KeyboardButton(text="📝 Обратная связь")])
        buttons.append([KeyboardButton(text="ℹ️ Инфо"), KeyboardButton(text="⚙️ Настройки")])
    else:
        buttons.append([KeyboardButton(text="🔍 Свободные кабинеты"), KeyboardButton(text="📂 Архив расписания")])
        buttons.append([KeyboardButton(text="🔔 Звонки"), KeyboardButton(text="📝 Обратная связь")])
        if is_curator:
            buttons.append([KeyboardButton(text="👨‍🏫 Меню куратора")])
        buttons.append([KeyboardButton(text="ℹ️ Инфо"), KeyboardButton(text="⚙️ Настройки")])

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def journal_settings_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Изменить данные", callback_data="journal_change")
    builder.button(text="🗑 Удалить данные", callback_data="journal_delete")
    builder.adjust(1)
    return builder.as_markup()

def settings_keyboard(notifications_enabled=True):
    builder = InlineKeyboardBuilder()
    notif_text = "🔔 Уведомления: ВКЛ" if notifications_enabled else "🔕 Уведомления: ВЫКЛ"
    builder.button(text=notif_text, callback_data="toggle_notif")
    builder.button(text="🔄 Сбросить профиль", callback_data="reset_setup")
    builder.adjust(1)
    return builder.as_markup()

def group_management_kb(group_name):
    weekday = datetime.datetime.now(MINSK_TZ).weekday()
    
    if weekday < 5:
        sched_row = [KeyboardButton(text=f"📅 {group_name}: Сегодня"), KeyboardButton(text=f"⏭️ {group_name}: Завтра")]
    elif weekday == 5:
        sched_row = [KeyboardButton(text=f"📅 {group_name}: Сегодня"), KeyboardButton(text=f"➡️ {group_name}: Пн")]
    else:
        sched_row = [KeyboardButton(text=f"➡️ {group_name}: Пн")]

    kb = [
        sched_row,
        [KeyboardButton(text=f"🗓 {group_name}: Другие дни")], # Кнопка для куратора
        [KeyboardButton(text=f"📢 Сообщение группе {group_name}")],
        [KeyboardButton(text="⬅️ Назад в меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def rooms_date_keyboard():
    builder = InlineKeyboardBuilder()
    now = datetime.datetime.now(MINSK_TZ)
    
    date_today = now.strftime("%d.%m.%Y")
    date_tomorrow = (now + datetime.timedelta(days=1)).strftime("%d.%m.%Y")
    
    builder.button(text="На сегодня", callback_data=f"rooms_date_{date_today}")
    builder.button(text="На завтра", callback_data=f"rooms_date_{date_tomorrow}")
    
    builder.adjust(2)
    return builder.as_markup()
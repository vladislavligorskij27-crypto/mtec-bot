import io
import re
import time
import logging
import asyncio
import datetime
import hashlib

import aiohttp
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont

from config import FONT_PATH, GROUPS_FILE, MENTORS_FILE, MINSK_TZ, BASE_URL

TIMEOUT = aiohttp.ClientTimeout(total=15)

college_cache = {"date": "", "data": [], "last_update": None}
rooms_data_cache = {}
CACHE_TTL = 600

GLOBAL_SCHEDULE_CACHE = {}  
IMAGE_CACHE = {}            

def get_data_hash(data):
    if not data or data == "error_logic":
        return "no_lessons"
    content_str = ""
    for item in data:
        content_str += f"{item.get('para', '')}{item.get('info', '')}{item.get('room', '')}"
    return hashlib.md5(content_str.encode('utf-8')).hexdigest()

def clean_room(room_str):
    if not room_str: return ""
    s = str(room_str).lower().strip().replace(".", "").replace("  ", " ")
    if any(word in s for word in ["общ", "этаж", "("]):
        if "2" in s or "втор" in s: return "2этаж(общ)"
        if "3" in s or "трет" in s: return "3этаж(общ)"
        if "4" in s or "четв" in s: return "4этаж(общ)"
    synonyms = {
        "спортзал": "спортзал", "спортивныйзал": "спортзал",
        "актовыйзал": "актовыйзал", "актовый": "актовыйзал",
        "библиотека": "библиотека", "библеотека": "библиотека",
        "читзал": "читзал", "читальныйзал": "читзал",
        "комотдыха": "комотдыха", "комнатаотдыха": "комотдыха"
    }
    s_no_spaces = s.replace(" ", "")
    if s_no_spaces in synonyms: return synonyms[s_no_spaces]
    match = re.search(r'(\d+[a-zа-я]?)', s_no_spaces)
    if match: return match.group()
    return s_no_spaces

def get_smart_wrap(text, font, max_pixel_width):
    words = text.split()
    lines = []
    current_line = []
    for word in words:
        test_line = ' '.join(current_line + [word])
        w = font.getlength(test_line) if hasattr(font, 'getlength') else font.getbbox(test_line)[2]
        if w <= max_pixel_width:
            current_line.append(word)
        else:
            if current_line: lines.append(' '.join(current_line))
            current_line = [word]
    if current_line: lines.append(' '.join(current_line))
    return lines

def format_lesson_info(raw_text):
    """
    Разбивает сплошной текст пары на:
    Предмет
    Подгруппа
    Преподаватель
    """
    text = re.sub(r'\s+', ' ', raw_text.strip())

    teacher = ""
    teacher_match = re.search(r'([А-ЯЁ][а-яё\-]+\s+[А-ЯЁ]\.\s*[А-ЯЁ]\.)', text)
    if teacher_match:
        teacher = teacher_match.group(1).strip()
        text = text.replace(teacher_match.group(0), "").strip()

    subgroup = ""
    subgroup_match = re.search(r'(\d+(?:-?[а-яяё]+)?\s*подгруппа)', text, re.IGNORECASE)
    if subgroup_match:
        subgroup = subgroup_match.group(1).strip()
        text = text.replace(subgroup_match.group(0), "").strip()

    subject = text.strip()
    subject = re.sub(r'\s+', ' ', subject).strip()

    lines = []
    if subject: lines.append(subject)
    if subgroup: lines.append(subgroup.capitalize())
    if teacher: lines.append(teacher)

    return "\n".join(lines)

async def get_full_college_schedule(date_str):
    global college_cache
    now = datetime.datetime.now(MINSK_TZ)
    
    if college_cache["date"] == date_str and college_cache["last_update"]:
        if (now - college_cache["last_update"]).total_seconds() < 900:
            return college_cache["data"]

    try:
        with open(GROUPS_FILE, 'r', encoding='utf-8') as f:
            groups = [line.strip() for line in f if line.strip()]
    except Exception as e:
        logging.error(f"Ошибка чтения файла групп: {e}")
        return []

    new_data = [] 
    
    async def fetch_group(session, group):
        payload = {"action": "sendSchedule", "date": date_str, "value": group, "rtype": "stds"}
        try:
            async with session.post(BASE_URL, data=payload, allow_redirects=True) as response:
                if response.status != 200: return None, group
                return await response.text(), group
        except Exception: 
            return None, group

    headers = {"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest", "Referer": "https://mtec.by/"}

    async with aiohttp.ClientSession(timeout=TIMEOUT, headers=headers) as session:
        semaphore = asyncio.Semaphore(10)
        async def sem_fetch(group):
            async with semaphore:
                return await fetch_group(session, group)

        tasks = [sem_fetch(group) for group in groups]
        responses = await asyncio.gather(*tasks)

        for html, group_name in responses:
            if not html or "table" not in html or "не имеет занятий" in html: continue
            try:
                soup = BeautifulSoup(html, 'lxml')
                for row in soup.find_all('tr')[1:]:
                    cols = row.find_all('td')
                    if len(cols) < 3: continue 
                    para_text = cols[0].get_text(strip=True).replace("пара", "").strip()
                    para_match = re.search(r'(\d+)', para_text)
                    if not para_match: continue
                    
                    info_raw = cols[1].get_text(" ", strip=True)
                    info_formatted = format_lesson_info(info_raw)
                    
                    new_data.append(((para_match.group(), group_name), {
                        "info": info_formatted,
                        "room": cols[2].get_text(strip=True)
                    }))
            except Exception as e:
                logging.error(f"Ошибка парсинга группы {group_name}: {e}")
                continue

    college_cache = {"date": date_str, "data": new_data, "last_update": now}
    return new_data

async def build_global_cache(date_str):
    full_schedule = await get_full_college_schedule(date_str)
    cache_data = {"students": {}, "teachers": {}}
    
    try:
        with open(MENTORS_FILE, 'r', encoding='utf-8') as f:
            mentors = [line.strip() for line in f if line.strip()]
    except Exception as e:
        mentors = []

    for (para, group), details in full_schedule:
        if group not in cache_data["students"]: cache_data["students"][group] = []
        cache_data["students"][group].append({"para": para, "info": details["info"], "room": details["room"]})

    for teacher in mentors:
        t_last_name = teacher.split()[0].lower()
        para_to_data = {}
        
        for (para, group), details in full_schedule:
            if t_last_name in details['info'].lower():
                # Убираем ФИО преподавателя из его собственного расписания
                lines = details['info'].split('\n')
                clean_lines = [line for line in lines if t_last_name not in line.lower()]
                clean_info = "\n".join(clean_lines)

                cache_key = f"{para}_{clean_info}"
                
                if cache_key not in para_to_data:
                    para_to_data[cache_key] = {"para": para, "groups": set(), "info": clean_info, "room": details['room']}
                para_to_data[cache_key]["groups"].add(group)
        
        t_sched = []
        for cache_key, pdata in para_to_data.items():
            info_text = pdata["info"]
            if pdata["groups"]:
                info_text += f"\nГруппы: {', '.join(sorted(pdata['groups']))}"
            t_sched.append({"para": pdata["para"], "info": info_text, "room": pdata["room"]})
        
        if t_sched:
            t_sched.sort(key=lambda x: int(re.search(r'\d+', str(x['para'])).group()) if re.search(r'\d+', str(x['para'])) else 0)
            cache_data["teachers"][teacher] = t_sched

    for group in cache_data["students"]:
        cache_data["students"][group].sort(key=lambda x: int(re.search(r'\d+', str(x['para'])).group()) if re.search(r'\d+', str(x['para'])) else 0)

    GLOBAL_SCHEDULE_CACHE[date_str] = cache_data
    return cache_data

async def get_schedule(target_name, role="student", date_str=None):
    if not date_str:
        date_str = datetime.datetime.now(MINSK_TZ).strftime("%d.%m.%Y")
    
    if date_str in GLOBAL_SCHEDULE_CACHE:
        r_key = "students" if role == "student" else "teachers"
        return GLOBAL_SCHEDULE_CACHE[date_str][r_key].get(target_name, None)

    payload = {"action": "sendSchedule", "date": date_str, "value": target_name, "rtype": "stds" if role == "student" else "teachers"}
    headers = {"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest", "Referer": "https://mtec.by/"}
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT, headers=headers) as session:
            async with session.post(BASE_URL, data=payload, allow_redirects=True) as response:
                if response.status != 200: return "error_logic"
                html = await response.text()
                if not html or "не имеет занятий" in html or html.strip() == '0': return None
                
                soup = BeautifulSoup(html, 'lxml')
                table = soup.find('table')
                if not table: return "error_logic"

                schedule_data = []
                for row in table.find_all('tr')[1:]:
                    cols = row.find_all('td')
                    if len(cols) < 3 or "не имеет занятий" in row.text: continue
                    
                    info_raw = cols[1].get_text(" ", strip=True)
                    
                    schedule_data.append({
                        "para": cols[0].get_text(strip=True).replace("пара", "").strip(),
                        "info": format_lesson_info(info_raw),
                        "room": cols[2].get_text(strip=True)
                    })
                return schedule_data
    except Exception as e:
        return "error_logic"

async def get_user_specific_hash(user_target, role, date_str):
    data = await get_schedule(user_target, role, date_str)
    if data == "error_logic": return None
    return get_data_hash(data)

async def get_occupied_rooms(date_str):
    now_ts = time.time()
    if date_str in rooms_data_cache and now_ts < rooms_data_cache[date_str]['expires']:
        return rooms_data_cache[date_str]['data']

    occupied = {}
    
    if date_str in GLOBAL_SCHEDULE_CACHE:
        for group, schedule in GLOBAL_SCHEDULE_CACHE[date_str]["students"].items():
            for details in schedule:
                room = clean_room(details.get('room'))
                if room: occupied.setdefault(str(details.get('para')), set()).add(room)
    else:
        full_schedule = await get_full_college_schedule(date_str)
        for (para, group), details in full_schedule:
            room = clean_room(details.get('room'))
            if room: occupied.setdefault(str(para), set()).add(room)
            
    rooms_data_cache[date_str] = {'data': occupied, 'expires': now_ts + CACHE_TTL}
    return occupied

def create_schedule_png(data, target, date_str, role="student"):
    if not isinstance(data, list): data = []

    WIDTH = 1000
    COLOR_BG_HEADER = (0, 0, 0)
    COLOR_BG_TABLE = (255, 255, 255)
    COLOR_GRID = (0, 0, 0)
    COLOR_TEXT_BLACK = (0, 0, 0)
    COLOR_TEXT_WHITE = (255, 255, 255)
    COLOR_TEXT_MUTED = (150, 150, 150)
    COLOR_BLUE_LINE = (0, 122, 255)
    COLOR_TIME_BG = (245, 245, 245)
    COLOR_LIVE = (255, 69, 58)

    COL1_W = 220
    COL3_W = 160
    COL2_W = WIDTH - COL1_W - COL3_W # 620

    try:
        dt = datetime.datetime.strptime(date_str.strip(), "%d.%m.%Y")
        day_names = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
        day_name = day_names[dt.weekday()]
        is_saturday = dt.weekday() == 5
    except Exception: 
        day_name = "Расписание"
        is_saturday = False

    if is_saturday:
        time_logic = {
            "1": ("08:00", "09:40"), "2": ("09:50", "11:30"),
            "3": ("11:40", "13:20"), "4": ("13:30", "15:10"),
            "5": ("15:20", "17:00"), "6": ("17:10", "18:50"), "7": ("19:00", "20:40")
        }
        c_map = {
            "1": "08:00 – 08:45\n08:55 – 09:40", "2": "09:50 – 10:35\n10:45 – 11:30",
            "3": "11:40 – 12:25\n12:35 – 13:20", "4": "13:30 – 14:15\n14:25 – 15:10",
            "5": "15:20 – 16:05\n16:15 – 17:00", "6": "17:10 – 17:55\n18:05 – 18:50",
            "7": "19:00 – 19:45\n19:55 – 20:40"
        }
    else:
        time_logic = {
            "1": ("08:00", "09:40"), "2": ("09:50", "11:30"),
            "3": ("12:00", "13:40"), "4": ("13:50", "15:25"),
            "5": ("15:32", "17:15"), "6": ("17:25", "19:05"),
            "7": ("19:15", "20:50")
        }
        c_map = {
            "1": "08:00 – 08:45\n08:55 – 09:40", "2": "09:50 – 10:35\n10:45 – 11:30",
            "3": "12:00 – 12:45\n12:55 – 13:40", "4": "13:50 – 14:35\n14:40 – 15:25",
            "5": "15:32 – 16:20\n16:30 – 17:15", "6": "17:25 – 18:10\n18:20 – 19:05", 
            "7": "19:15 – 20:00\n20:05 – 20:50"
        }

    now = datetime.datetime.now(MINSK_TZ)
    is_today = date_str == now.strftime("%d.%m.%Y")
    current_time_str = now.strftime("%H:%M")

    header_font_size = 64
    if len(target) > 22: header_font_size = 42
    elif len(target) > 15: header_font_size = 50

    try:
        f_h_main = ImageFont.truetype(FONT_PATH, header_font_size)
        f_h_sub = ImageFont.truetype(FONT_PATH, 28)
        f_th = ImageFont.truetype(FONT_PATH, 22)
        f_b_bold = ImageFont.truetype(FONT_PATH, 28) 
        f_b = ImageFont.truetype(FONT_PATH, 28)
        f_t = ImageFont.truetype(FONT_PATH, 20)
        f_n = ImageFont.truetype(FONT_PATH, 26)
        f_live = ImageFont.truetype(FONT_PATH, 16)
    except Exception:
        f_h_main = f_h_sub = f_th = f_b_bold = f_b = f_t = f_n = f_live = ImageFont.load_default()

    rows = []
    header_h = 200
    table_header_h = 60
    
    if not data:
        rows.append({'is_empty': True, 'h': 250, 'msg': "ПАР НЕТ"})
    else:
        grouped_data = {}
        for item in data:
            para_num = str(item['para'])
            if para_num not in grouped_data:
                grouped_data[para_num] = []
            grouped_data[para_num].append(item)

        for para_num, items in grouped_data.items():
            sub_rows = []
            is_current = False 
            if is_today and para_num in time_logic:
                start, end = time_logic[para_num]
                if start <= current_time_str <= end: is_current = True

            total_h = 0
            for item in items:
                lines = item['info'].split('\n')
                proc = []
                for i, line in enumerate(lines):
                    is_bold = (i == 0) 
                    wrapped = get_smart_wrap(line, (f_b_bold if is_bold else f_b), COL2_W - 40)
                    for wl in wrapped: proc.append((wl, is_bold))
                
                room_str = str(item['room'])
                r_lines = get_smart_wrap(room_str, f_b_bold, COL3_W - 20)

                text_h = len(proc) * 38
                room_h = len(r_lines) * 34
                h = max(100, text_h + 40, room_h + 40)
                sub_rows.append({
                    'lines': proc, 'r_lines': r_lines, 'h': h
                })
                total_h += h
            
            min_left_h = 160
            if total_h < min_left_h:
                extra = min_left_h - total_h
                for sr in sub_rows:
                    sr['h'] += extra / len(sub_rows)
                total_h = min_left_h

            rows.append({
                'n': para_num, 't': c_map.get(para_num, ""), 
                'sub_rows': sub_rows, 'h': total_h, 'is_current': is_current
            })

    total_h = header_h + table_header_h + sum(r['h'] for r in rows) + 4
    img = Image.new('RGB', (WIDTH, int(total_h)), COLOR_BG_TABLE)
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, WIDTH, header_h + table_header_h], fill=COLOR_BG_HEADER)
    draw.text((WIDTH/2, 80), target.upper(), font=f_h_main, fill=COLOR_TEXT_WHITE, anchor="mm")
    draw.text((WIDTH/2, 140), f"{day_name} | {date_str}", font=f_h_sub, fill=COLOR_TEXT_MUTED, anchor="mm")

    th_y = 200
    draw.text((COL1_W / 2, th_y + 30), "№ / ВРЕМЯ", font=f_th, fill=COLOR_TEXT_WHITE, anchor="mm")
    draw.text((COL1_W + COL2_W / 2, th_y + 30), "НАИМЕНОВАНИЕ ДИСЦИПЛИНЫ", font=f_th, fill=COLOR_TEXT_WHITE, anchor="mm")
    draw.text((WIDTH - COL3_W / 2, th_y + 30), "АУД", font=f_th, fill=COLOR_TEXT_WHITE, anchor="mm")

    curr_y = 260
    draw.line([0, curr_y, WIDTH, curr_y], fill=COLOR_BLUE_LINE, width=6)
    curr_y += 3

    for r in rows:
        if r.get('is_empty'):
            draw.text((WIDTH/2, curr_y + r['h']/2), r['msg'], font=f_h_main, fill=COLOR_TEXT_BLACK, anchor="mm")
            draw.line([0, curr_y + r['h'], WIDTH, curr_y + r['h']], fill=COLOR_GRID, width=2)
            curr_y += r['h']
            continue

        mid_y = curr_y + r['h'] / 2

        if r.get('is_current'):
            draw.rectangle([0, curr_y, WIDTH, curr_y + r['h']], fill=(255, 242, 242))
            draw.rectangle([0, curr_y, 6, curr_y + r['h']], fill=COLOR_LIVE)

        draw.line([COL1_W, curr_y, COL1_W, curr_y + r['h']], fill=COLOR_GRID, width=2)
        draw.line([COL1_W + COL2_W, curr_y, COL1_W + COL2_W, curr_y + r['h']], fill=COLOR_GRID, width=2)

        # ====================================================================
        # ВЛАД, ВНИМАНИЕ! ИСПРАВЛЕНИЯ КООРДИНАТ НАХОДЯТСЯ ЗДЕСЬ (строки 335-343)
        # ====================================================================
        if r.get('is_current'):
            badge_w, badge_h = 80, 24
            # 1. Поднимаем плашку "СЕЙЧАС" выше (сдвиг -60 пикселей вместо -45)
            badge_y = mid_y - 60
            badge_rect = [COL1_W/2 - badge_w/2, badge_y, COL1_W/2 + badge_w/2, badge_y + badge_h]
            draw.rounded_rectangle(badge_rect, radius=6, fill=COLOR_LIVE)
            draw.text((COL1_W/2, badge_y + badge_h/2 - 1), "СЕЙЧАС", font=f_live, fill=COLOR_TEXT_WHITE, anchor="mm")
            
            # 2. Опускаем текст "3 ПАРА" и Время (n_y это ПАРА, t_y это ВРЕМЯ)
            n_y, t_y = mid_y - 20, mid_y + 15
        else:
            n_y, t_y = mid_y - 25, mid_y + 10
        # ====================================================================

        draw.text((COL1_W/2, n_y), f"{r['n']} ПАРА", font=f_n, fill=COLOR_TEXT_BLACK, anchor="mm")
        
        time_box_w, time_box_h = 170, 56
        time_box_rect = [COL1_W/2 - time_box_w/2, t_y, COL1_W/2 + time_box_w/2, t_y + time_box_h]
        if r.get('is_current'):
            draw.rounded_rectangle(time_box_rect, radius=12, fill=(255, 220, 220))
            draw.text((COL1_W/2, t_y + time_box_h/2), r['t'], font=f_t, fill=COLOR_LIVE, anchor="mm", align="center")
        else:
            draw.rounded_rectangle(time_box_rect, radius=12, fill=COLOR_TIME_BG)
            draw.text((COL1_W/2, t_y + time_box_h/2), r['t'], font=f_t, fill=COLOR_TEXT_MUTED, anchor="mm", align="center")

        sub_y = curr_y
        for i, sr in enumerate(r['sub_rows']):
            sub_mid_y = sub_y + sr['h'] / 2
            
            line_h = 38
            content_h = len(sr['lines']) * line_h
            text_y = sub_mid_y - content_h / 2 + line_h / 2
            
            center_x_col2 = COL1_W + COL2_W / 2
            for text_line, is_bold in sr['lines']:
                f_current = f_b_bold if is_bold else f_b
                draw.text((center_x_col2, text_y), text_line, font=f_current, fill=COLOR_TEXT_BLACK, anchor="mm")
                text_y += line_h

            r_line_h = 34
            r_content_h = len(sr['r_lines']) * r_line_h
            r_text_y = sub_mid_y - r_content_h / 2 + r_line_h / 2
            
            center_x_col3 = WIDTH - COL3_W / 2
            for r_line in sr['r_lines']:
                draw.text((center_x_col3, r_text_y), r_line, font=f_b_bold, fill=COLOR_TEXT_BLACK, anchor="mm")
                r_text_y += r_line_h

            sub_y += sr['h']
            
            if i < len(r['sub_rows']) - 1:
                draw.line([COL1_W, sub_y, WIDTH, sub_y], fill=(220, 220, 220), width=2)

        draw.line([0, curr_y + r['h'], WIDTH, curr_y + r['h']], fill=COLOR_GRID, width=2)
        curr_y += r['h']

    draw.rectangle([0, 263, WIDTH, total_h], outline=COLOR_GRID, width=4)

    out = io.BytesIO()
    img.save(out, format='PNG')
    out.seek(0)
    return out
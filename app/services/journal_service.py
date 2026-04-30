import os
import aiohttp
import logging
import asyncio
from bs4 import BeautifulSoup
from config import WORKSPACE, PATH_CSS, EJOURNAL_HEADERS

# АКТУАЛЬНЫЕ АДРЕСА для office.mtec.by
# Мы используем корень сайта, так как форма входа находится там
NEW_BASE_URL = "https://office.mtec.by/"

async def fetch_and_process_journal(login, password, user_id):
    """
    Авторизуется на сервере office.mtec.by, скачивает журнал, 
    очищает его и применяет стили.
    """
    output_file = os.path.join(WORKSPACE, f"{user_id}_journal.html")
    
    # Данные формы (имена полей обычно стандартные: login, password)
    login_data = {
        "login": login,
        "password": password,
        "submit": "Войти"
    }

    # Настраиваем таймауты
    timeout = aiohttp.ClientTimeout(total=25)

    async with aiohttp.ClientSession(headers=EJOURNAL_HEADERS, timeout=timeout) as session:
        try:
            # 1. ШАГ: Инициализация (заходим на главную, получаем куки)
            async with session.get(NEW_BASE_URL, allow_redirects=True) as init_resp:
                if init_resp.status != 200:
                    logging.error(f"Ошибка доступа к {NEW_BASE_URL}: {init_resp.status}")
                    return False, f"Сервер журнала недоступен (Код {init_resp.status})."
                
                # Читаем текст, чтобы убедиться, что мы на странице входа
                init_html = await init_resp.text()
                if 'name="login"' not in init_html:
                    logging.warning("Форма логина не найдена на главной странице.")
            
            # 2. ШАГ: Авторизация (POST запрос)
            # Отправляем данные на тот же URL, так как обычно обработчик там же или в index.php
            async with session.post(NEW_BASE_URL, data=login_data, allow_redirects=True) as login_resp:
                if login_resp.status != 200:
                    logging.error(f"Ошибка POST запроса: {login_resp.status}")
                    return False, f"Ошибка при попытке входа (Код {login_resp.status})."
                
                login_html = await login_resp.text()
                
                # Проверка на ошибку авторизации
                if "Неверный логин или пароль" in login_html:
                    return False, "❌ Неверный ФИО или пароль."

            # 3. ШАГ: Получение страницы с оценками
            # После логина нас должно либо оставить на той же странице (но с данными), 
            # либо перекинуть на index.php. Пробуем получить содержимое.
            async with session.get(NEW_BASE_URL, allow_redirects=True) as profile_resp:
                html_content = await profile_resp.text()

                # Если все еще видим форму логина - авторизация не прошла
                if 'name="login"' in html_content or 'Вход в кабинет' in html_content:
                    return False, "❌ Ошибка авторизации. Проверьте ФИО в настройках."

                # 4. ШАГ: Обработка HTML (Очистка)
                soup = BeautifulSoup(html_content, "html.parser")
                
                # Список элементов для удаления (адаптировано под новый сайт)
                elements_to_remove = [
                    ("nav", {}),
                    ("footer", {}),
                    ("header", {}),
                    ("a", {"href": "logout.php"}),
                    ("div", {"class": "navbar"}),
                    ("div", {"class": "alert"}), # Убираем уведомления
                    ("button", {}),
                    ("input", {})
                ]

                for tag, attrs in elements_to_remove:
                    for el in soup.find_all(tag, attrs):
                        el.decompose()

                # 5. ШАГ: Стилизация
                css_content = ""
                css_file_path = os.path.join(PATH_CSS, "style.css")
                
                if os.path.exists(css_file_path):
                    try:
                        with open(css_file_path, "r", encoding="utf-8") as f:
                            css_content = f.read()
                    except: pass

                if not css_content:
                    css_content = """
                    body { font-family: 'Inter', -apple-system, sans-serif; background: #f0f2f5; padding: 20px; color: #1c1e21; }
                    .container, div[class*="container"] { max-width: 1100px; margin: 0 auto; background: #fff; padding: 25px; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); }
                    table { width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 14px; }
                    th, td { padding: 12px; border: 1px solid #e4e6eb; text-align: center; }
                    th { background: #007bff; color: #fff; font-weight: 600; text-transform: uppercase; }
                    tr:nth-child(even) { background: #f9fafb; }
                    tr:hover { background: #f0f2f5; }
                    h2, h3 { color: #007bff; margin: 20px 0 10px; border-bottom: 2px solid #007bff; padding-bottom: 8px; }
                    @media (max-width: 600px) { 
                        body { padding: 10px; }
                        table { font-size: 11px; }
                        th, td { padding: 6px 2px; }
                    }
                    """

                if not soup.head:
                    soup.insert(0, soup.new_tag("head"))
                
                style_tag = soup.new_tag("style")
                style_tag.string = css_content
                soup.head.append(style_tag)
                
                meta_vp = soup.new_tag("meta", attrs={"name": "viewport", "content": "width=device-width, initial-scale=1"})
                soup.head.append(meta_vp)

                # 6. ШАГ: Сохранение результата
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(str(soup.prettify()))

                return True, output_file

        except Exception as e:
            logging.error(f"Ошибка при работе с office.mtec.by: {e}")
            return False, f"Ошибка связи с сервером журнала: {str(e)}"
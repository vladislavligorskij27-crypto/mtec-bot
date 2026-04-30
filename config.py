import os
import pytz
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 7889314108))

MINSK_TZ = pytz.timezone("Europe/Minsk")
BASE_URL = "https://mtec.by/wp-admin/admin-ajax.php"

GROUPS_FILE = os.path.join(BASE_DIR, "data", "txt", "all_groups.txt")
MENTORS_FILE = os.path.join(BASE_DIR, "data", "txt", "all_mentors.txt")
ROOMS_FILE = os.path.join(BASE_DIR, "data", "txt", "rooms.txt") 
DATABASE_NAME = os.path.join(BASE_DIR, "mtec_bot.db")
ARCHIVE_DIR = os.path.join(BASE_DIR, "data", "archive")

FONT_PATH = os.path.join(BASE_DIR, "data", "assets", "Arial.ttf")
LOGO_PATH = os.path.join(BASE_DIR, "data", "assets", "logo.png")
CALLS_1 = os.path.join(BASE_DIR, "data", "assets", "CALLS_1.jpg")
CALLS_2 = os.path.join(BASE_DIR, "data", "assets", "CALLS_2.jpg")

if not BOT_TOKEN:
    exit("Ошибка: BOT_TOKEN не найден в файле .env")

WORKSPACE = os.path.join(BASE_DIR, "data", "temp_journals")
PATH_CSS = os.path.join(BASE_DIR, "data", "assets", "css")

os.makedirs(WORKSPACE, exist_ok=True)
os.makedirs(ARCHIVE_DIR, exist_ok=True)

EJOURNAL_LOGIN_URL = "https://mtec.by/reit/login.php"
EJOURNAL_PROFILE_URL = "https://mtec.by/reit/index.php"
EJOURNAL_PROFILE_PERIOD_URL = "https://mtec.by/reit/index.php?period="
EJOURNAL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
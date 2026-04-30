import aiosqlite
from config import DATABASE_NAME

_db = None

async def get_db():
    global _db
    if _db is None:
        _db = await aiosqlite.connect(DATABASE_NAME)
        _db.row_factory = aiosqlite.Row
    return _db

async def close_db():
    global _db
    if _db is not None:
        await _db.close()
        _db = None

async def init_db():
    db = await get_db()
    await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            role TEXT,
            target TEXT,
            last_hash TEXT,
            notifications INTEGER DEFAULT 1,
            curator_group TEXT DEFAULT NULL,
            pending_hash TEXT DEFAULT NULL,
            journal_login TEXT DEFAULT NULL,
            journal_password TEXT DEFAULT NULL,
            last_message_id INTEGER DEFAULT NULL
        )
    """)
    
    await db.execute("CREATE INDEX IF NOT EXISTS idx_users_notifications ON users(notifications)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_users_target ON users(target)")
    
    # Автоматическое обновление базы данных (добавляем колонки, если их нет)
    cursor = await db.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in await cursor.fetchall()]
    
    if "curator_group" not in columns:
        await db.execute("ALTER TABLE users ADD COLUMN curator_group TEXT DEFAULT NULL")
    if "pending_hash" not in columns:
        await db.execute("ALTER TABLE users ADD COLUMN pending_hash TEXT DEFAULT NULL")
    if "journal_login" not in columns:
        await db.execute("ALTER TABLE users ADD COLUMN journal_login TEXT DEFAULT NULL")
    if "journal_password" not in columns:
        await db.execute("ALTER TABLE users ADD COLUMN journal_password TEXT DEFAULT NULL")
    # === НОВОЕ ПОЛЕ ===
    if "last_message_id" not in columns:
        await db.execute("ALTER TABLE users ADD COLUMN last_message_id INTEGER DEFAULT NULL")
        
    await db.commit()

async def get_user(user_id):
    db = await get_db()
    async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
        return await cursor.fetchone()

async def save_user(user_id, role, target):
    db = await get_db()
    await db.execute(
        """
        INSERT INTO users (user_id, role, target) 
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET 
            role = excluded.role, 
            target = excluded.target
        """,
        (user_id, role, target)
    )
    await db.commit()

async def toggle_notifications(user_id):
    db = await get_db()
    user = await get_user(user_id)
    if not user: return 1
    
    new_state = 0 if user['notifications'] == 1 else 1
    await db.execute("UPDATE users SET notifications = ? WHERE user_id = ?", (new_state, user_id))
    await db.commit()
    return new_state

async def set_curator(user_id, group_name):
    db = await get_db()
    await db.execute("UPDATE users SET curator_group = ? WHERE user_id = ?", (group_name, user_id))
    await db.commit()

async def update_pending_hash(user_id, pending_hash):
    db = await get_db()
    await db.execute("UPDATE users SET pending_hash = ? WHERE user_id = ?", (pending_hash, user_id))
    await db.commit()

async def update_last_hash(user_id, last_hash):
    db = await get_db()
    await db.execute(
        "UPDATE users SET last_hash = ?, pending_hash = NULL WHERE user_id = ?", 
        (last_hash, user_id)
    )
    await db.commit()

async def save_journal_auth(user_id, login, password):
    db = await get_db()
    await db.execute(
        "UPDATE users SET journal_login = ?, journal_password = ? WHERE user_id = ?",
        (login, password, user_id)
    )
    await db.commit()

async def delete_journal_auth(user_id):
    db = await get_db()
    await db.execute(
        "UPDATE users SET journal_login = NULL, journal_password = NULL WHERE user_id = ?",
        (user_id,)
    )
    await db.commit()

# === НОВЫЕ ФУНКЦИИ ДЛЯ ЗАПОМИНАНИЯ СООБЩЕНИЙ ===
async def update_last_message_id(user_id, message_id):
    db = await get_db()
    await db.execute("UPDATE users SET last_message_id = ? WHERE user_id = ?", (message_id, user_id))
    await db.commit()

async def get_last_message_id(user_id):
    db = await get_db()
    async with db.execute("SELECT last_message_id FROM users WHERE user_id = ?", (user_id,)) as cursor:
        res = await cursor.fetchone()
        return res[0] if res else None
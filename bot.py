import os
import re
import sqlite3
import asyncio

from aiohttp import web, ClientTimeout
from aiogram import Bot, Dispatcher, executor, types


API_TOKEN = os.getenv("BOT_TOKEN")
if not API_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

DB_PATH = "users.db"


# =========================
# BOT (увеличенный timeout)
# =========================
timeout = ClientTimeout(total=60)

bot = Bot(
    token=API_TOKEN,
    timeout=60
)

dp = Dispatcher(bot)


# =========================
# DB
# =========================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def normalize_username(u: str) -> str:
    """Храним username без @, в lower, чистим мусор вокруг."""
    if not u:
        return ""
    s = str(u).strip().lower()
    if s.startswith("@"):
        s = s[1:]
    return s


def save_user(username: str, user_id: int):
    uname = normalize_username(username)
    if not uname:
        return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO users (username, user_id) VALUES (?, ?)",
        (uname, user_id)
    )
    conn.commit()
    conn.close()


def get_user_id(username: str):
    uname = normalize_username(username)
    if not uname:
        return None
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id FROM users WHERE username = ?",
        (uname,)
    )
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


# =========================
# SAFE SEND (retry)
# =========================
async def safe_send(user_id: int, text: str):
    for attempt in range(3):
        try:
            await bot.send_message(user_id, text, disable_web_page_preview=True)
            return
        except asyncio.TimeoutError:
            await asyncio.sleep(2)
        except Exception as e:
            print("Send error:", e)
            return


# =========================
# /start
# =========================
@dp.message_handler(commands=["start"])
async def start_handler(message: types.Message):
    if not message.from_user.username:
        await message.answer(
            "У тебя нет username в Telegram.\n"
            "Без него уведомления не работают."
        )
        return

    save_user(message.from_user.username, message.from_user.id)

    await message.answer(
        "Готово ✅\n"
        "Теперь буду присылать уведомления об упоминаниях."
    )


# =========================
# MENTION EXTRACTOR
# =========================
MENTION_RE = re.compile(r'@([a-zA-Z0-9_]{5,32})')

def extract_mentions_from_message(message: types.Message) -> set[str]:
    """
    Возвращает set “targets” для уведомлений:
    - username без @ (например: 'user_name')
    - или 'ID:123456' для text_mention (кликабельное упоминание без @)
    """
    found = set()

    def handle_entities(text: str, entities):
        if not text or not entities:
            return
        for ent in entities:
            # обычное @username
            if ent.type == "mention":
                raw = text[ent.offset: ent.offset + ent.length]  # "@user_name"
                uname = normalize_username(raw)
                if uname:
                    found.add(uname)
            # кликабельное упоминание без @ (TEXT_MENTION)
            elif ent.type == "text_mention":
                if ent.user and ent.user.id:
                    found.add(f"ID:{ent.user.id}")

    text = message.text or ""
    caption = message.caption or ""

    handle_entities(text, message.entities)
    handle_entities(caption, message.caption_entities)

    # fallback: обычный regex (если entities отсутствуют)
    for m in MENTION_RE.findall(text):
        found.add(normalize_username(m))
    for m in MENTION_RE.findall(caption):
        found.add(normalize_username(m))

    return found


# =========================
# CHANNEL POSTS
# =========================
@dp.channel_post_handler(content_types=types.ContentTypes.ANY)
async def channel_post_handler(message: types.Message):
    text = message.text or message.caption
    if not text:
        return

    targets = extract_mentions_from_message(message)
    if not targets:
        return

    if not message.chat.username:
        return

    post_link = f"https://t.me/{message.chat.username}/{message.message_id}"

    for t in targets:
        # TEXT_MENTION — отправляем сразу по user_id
        if t.startswith("ID:"):
            try:
                user_id = int(t.split(":", 1)[1])
            except Exception:
                continue

            await safe_send(user_id, f"Вас упомянули в Джурыми!\n{post_link}")
            continue

        # обычный @username — ищем в базе
        user_id = get_user_id(t)
        if not user_id:
            continue

        await safe_send(user_id, f"Вас упомянули в Джурыми!\n{post_link}")


@dp.edited_channel_post_handler(content_types=types.ContentTypes.ANY)
async def edited_channel_post_handler(message: types.Message):
    return


# =========================
# HEALTH ENDPOINT (anti-sleep)
# =========================
async def health(request):
    return web.Response(text="OK")


async def start_health_server():
    app = web.Application()
    app.router.add_get("/", health)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    print(f"Health server started on port {port}")


async def on_startup(dp):
    await start_health_server()


# =========================
# START
# =========================
if __name__ == "__main__":
    init_db()
    executor.start_polling(
        dp,
        skip_updates=True,
        on_startup=on_startup
    )

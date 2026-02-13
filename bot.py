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


def save_user(username: str, user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO users (username, user_id) VALUES (?, ?)",
        (username.lower(), user_id)
    )
    conn.commit()
    conn.close()


def get_user_id(username: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id FROM users WHERE username = ?",
        (username.lower(),)
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
            await bot.send_message(user_id, text)
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
# CHANNEL POSTS
# =========================
@dp.channel_post_handler()
async def channel_post_handler(message: types.Message):
    text = message.text or message.caption
    if not text:
        return

    mentions = re.findall(r'@([a-zA-Z0-9_]{3,})', text)
    if not mentions:
        return

    if not message.chat.username:
        return

    post_link = f"https://t.me/{message.chat.username}/{message.message_id}"

    for mention in mentions:
        user_id = get_user_id(mention)
        if not user_id:
            continue

        await safe_send(
            user_id,
            f"Вас упомянули!\n{post_link}"
        )


@dp.edited_channel_post_handler()
async def edited_channel_post_handler(message: types.Message):
    await channel_post_handler(message)


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

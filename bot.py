import os
import re
import sqlite3
from aiogram import Bot, Dispatcher, executor, types

API_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

DB_PATH = "users.db"


# ---------- DB ----------
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


# ---------- /start ----------
@dp.message_handler(commands=["start"])
async def start_handler(message: types.Message):
    if not message.from_user.username:
        await message.answer(
            "У тебя нет username в Telegram.\n"
            "Без него я не смогу присылать уведомления."
        )
        return

    save_user(message.from_user.username, message.from_user.id)

    await message.answer(
        "Готово ✅\n"
        "Я буду присылать уведомления, если тебя упомянут в канале."
    )


# ---------- channel posts ----------
@dp.channel_post_handler(content_types=types.ContentTypes.ANY)
async def channel_post_handler(message: types.Message):
    text = message.text or message.caption
    if not text:
        return

    mentions = re.findall(r'@([a-zA-Z0-9_]{3,})', text)
    if not mentions:
        return

    post_link = f"https://t.me/{message.chat.username}/{message.message_id}"

    for mention in mentions:
        user_id = get_user_id(mention)
        if not user_id:
            continue

        try:
            await bot.send_message(
                user_id,
                f"Вас упомянули в Джурыми!\n{post_link}"
            )
        except Exception as e:
            print(e)

@dp.edited_channel_post_handler(content_types=types.ContentTypes.ANY)
async def edited_channel_post_handler(message: types.Message):
    await channel_post_handler(message)

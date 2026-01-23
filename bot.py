import os
import re
import json
from aiogram import Bot, Dispatcher, executor, types

API_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

USERS_FILE = "users.json"


# ---------- helpers ----------
def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_users(data):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------- /start ----------
@dp.message_handler(commands=["start"])
async def start_handler(message: types.Message):
    if not message.from_user.username:
        await message.answer(
            "У тебя нет username в Telegram.\n"
            "Без него я не смогу присылать уведомления."
        )
        return

    users = load_users()
    username = message.from_user.username.lower()

    users[username] = message.from_user.id
    save_users(users)

    await message.answer(
        "Готово ✅\n"
        "Я буду присылать уведомления, если тебя упомянут в канале."
    )


# ---------- channel posts ----------
@dp.channel_post_handler()
async def channel_post_handler(message: types.Message):
    if not message.text:
        return

    # ищем ВСЕ @username
    mentions = re.findall(r'@([a-zA-Z0-9_]{3,})', message.text)
    if not mentions:
        return

    users = load_users()

    if not message.chat.username:
        return

    post_link = f"https://t.me/{message.chat.username}/{message.message_id}"

    for mention in mentions:
        username = mention.lower()
        user_id = users.get(username)

        if not user_id:
            continue

        try:
            await bot.send_message(
                user_id,
                f"Вас упомянули в Джурыми!\n{post_link}"
            )
        except Exception:
            # пользователь недоступен — не мешаем остальным
            continue


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)

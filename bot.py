from aiogram import Bot, Dispatcher, executor, types
import os

TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

users = {}

@dp.channel_post_handler()
async def channel_post(message: types.Message):
    if not message.text:
        return

    text = message.text.lower()

    channel_username = message.chat.username
    post_id = message.message_id
    post_link = f"https://t.me/{channel_username}/{post_id}"

    for username, user_id in users.items():
        if f"@{username}" in text:
            await bot.send_message(
                user_id,
                f"Вас упомянули в посте в Джурыми! \n{post_link}"
            )


from aiogram import Bot, Dispatcher, executor, types
import os

TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

users = {}

@dp.message_handler(commands=['start'])
async def start(msg: types.Message):
    if not msg.from_user.username:
        await msg.answer("Нужен username в Telegram.")
        return
    users[msg.from_user.username.lower()] = msg.from_user.id
    await msg.answer("Я буду уведомлять тебя при упоминании.")

@dp.channel_post_handler()
async def channel_post(message: types.Message):
    if not message.text:
        return
    text = message.text.lower()
    for username, user_id in users.items():
        if f"@{username}" in text:
            await bot.send_message(
                user_id,
                f"Тебя упомянули:\n\n{message.text}"
            )

if __name__ == "__main__":
    executor.start_polling(dp)

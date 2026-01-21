import logging
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

API_TOKEN = 8397596709:AAE2MM-UeGeQyCvX00KF2tioS9Iy4inVX7k

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# Храним пользователей, которые нажали /start
users = set()


@dp.message_handler(commands=["start"])
async def start_handler(message: types.Message):
    users.add(message.from_user.id)
    await message.answer("✅ Бот активирован. Я сообщу, если вас упомянут в канале.")


@dp.channel_post_handler()
async def channel_post_handler(message: types.Message):
    if not message.entities:
        return

    channel_username = message.chat.username
    if not channel_username:
        return  # канал должен быть публичным

    post_link = f"https://t.me/{channel_username}/{message.message_id}"

    for entity in message.entities:
        if entity.type == "mention":
            username = message.text[entity.offset : entity.offset + entity.length]

            for user_id in users:
                try:
                    await bot.send_message(
                        user_id,
                        f"❤️ Вас упомянули в Джурыми!\n{post_link}"
                    )
                except:
                    pass


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)

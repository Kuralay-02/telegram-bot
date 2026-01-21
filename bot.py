import os
import re
from aiogram import Bot, Dispatcher, executor, types

API_TOKEN = 8397596709:AAE2MM-UeGeQyCvX00KF2tioS9Iy4inVX7k

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# Храним пользователей, которые нажали /start
users = set()


@dp.message_handler(commands=["start"])
async def start_handler(message: types.Message):
    users.add(message.from_user.id)
    await message.answer("Готово. Я буду присылать уведомления, если вас упомянут в канале.")


@dp.channel_post_handler()
async def channel_post_handler(message: types.Message):
    if not message.text:
        return

    text = message.text

    # Ищем @username
    mentions = re.findall(r'@(\w+)', text)

    if not mentions:
        return

    for user_id in users:
        try:
            chat = await bot.get_chat(user_id)
            username = chat.username

            if username and username in mentions:
                # ссылка на пост
                if message.chat.username:
                    post_link = f"https://t.me/{message.chat.username}/{message.message_id}"
                else:
                    continue

                await bot.send_message(
                    user_id,
                    f"Вас упомянули в Джурыми!\n{post_link}"
                )
        except Exception as e:
            print(e)


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)

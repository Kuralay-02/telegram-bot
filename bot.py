from bot_io import (
    LazyResource,
    configure_client,
    run_sheets,
    telegram_call,
)
import os
import asyncio
import json
import gspread

from aiohttp import web, ClientTimeout
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


API_TOKEN = os.getenv("BOT_TOKEN")
if not API_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")


# =========================
# BOT
# =========================
timeout = ClientTimeout(total=60)

bot = Bot(
    token=API_TOKEN,
    timeout=60
)

dp = Dispatcher(bot)


# =========================
# GOOGLE SHEETS
# =========================
creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
gc = configure_client(gspread.service_account_from_dict(creds_dict))

spreadsheet = LazyResource(
    lambda: gc.open_by_url(
        "https://docs.google.com/spreadsheets/d/1fqMGsQqXP9a7RNg-_7unYsqQeufg1If3oGPIFfqa-_o/edit?usp=sharing"
    )
)
sheet = LazyResource(lambda: spreadsheet.worksheet("Users"))


# =========================
# CACHE ДЛЯ ПОВТОРА
# =========================
FAILED_CACHE = {}


# =========================
# UTILS
# =========================
def normalize_username(u: str) -> str:
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
    values = sheet.get_all_records()
    own_row = None
    for index, row in enumerate(values, start=2):
        if str(row.get("user_id", "")) == str(user_id):
            own_row = index
        elif normalize_username(row.get("username", "")) == uname:
            sheet.update_cell(index, 1, "")
    if own_row is not None:
        sheet.update(range_name=f"A{own_row}:B{own_row}", values=[[uname, user_id]])
    else:
        sheet.append_row([uname, user_id])


def get_user_id(username: str):
    uname = normalize_username(username)
    if not uname:
        return None

    data = sheet.get_all_records()

    for row in data:
        if row["username"] == uname:
            return int(row["user_id"])

    return None


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

    await run_sheets(save_user, message.from_user.username, message.from_user.id)

    await message.answer(
        "Готово ✅\n"
        "Теперь буду присылать уведомления об упоминаниях."
    )


# =========================
# MENTION EXTRACTOR (ФИКС)
# =========================
def extract_mentions_from_message(message: types.Message) -> set[str]:
    found = set()

    def handle_entities(text: str, entities):
        if not text or not entities:
            return

        for ent in entities:
            if ent.type == "mention":
                raw = ent.get_text(text)  # 🔥 ключевой фикс
                uname = normalize_username(raw)
                if uname:
                    found.add(uname)

            elif ent.type == "text_mention":
                if ent.user and ent.user.id:
                    found.add(f"ID:{ent.user.id}")

    text = message.text or ""
    caption = message.caption or ""

    handle_entities(text, message.entities)
    handle_entities(caption, message.caption_entities)

    return found


# =========================
# ОТПРАВКА + ОТЧЁТ
# =========================
def get_user_map():
    return {
        normalize_username(row.get("username", "")): int(row["user_id"])
        for row in sheet.get_all_records()
        if normalize_username(row.get("username", ""))
        and str(row.get("user_id", "")).isdigit()
    }


async def send_batch_notifications(targets, post_link):
    admin_id = int(os.getenv("ADMIN_ID", "0"))

    users = await run_sheets(get_user_map)
    success = []
    failed = []

    for t in targets:
        if t.startswith("ID:"):
            try:
                user_id = int(t.split(":", 1)[1])
                username = f"id:{user_id}"
            except:
                continue
        else:
            user_id = users.get(normalize_username(t))
            username = t

            if not user_id:
                failed.append((username, None, "нет в базе"))
                continue

        try:
            if not t.startswith("ID:"):
                current = await telegram_call(bot.get_chat, user_id)
                if normalize_username(current.username) != normalize_username(t):
                    failed.append((username, None, "юзернейм изменился, нужен /start"))
                    continue
            await telegram_call(
                bot.send_message,
                user_id,
                f"Вас упомянули в Джурыми!\n{post_link}",
                disable_web_page_preview=True,
            )
            success.append(username)

        except Exception as e:
            error_text = str(e)

            if "bot was blocked" in error_text:
                error_text = "заблокировал бота"
            elif "chat not found" in error_text:
                error_text = "не нажал /start"
            elif "user is deactivated" in error_text:
                error_text = "аккаунт удалён"

            failed.append((username, user_id, error_text))

        await asyncio.sleep(0.05)

    FAILED_CACHE[post_link] = [(u, uid) for u, uid, _ in failed]

    report = f"📊 Отчёт по посту\n\n"
    report += f"✅ Успешно: {len(success)}\n"
    report += f"❌ Ошибки: {len(failed)}\n\n"

    if success:
        report += "📨 Получили:\n"
        report += "\n".join(success[:30]) + "\n\n"

    if failed:
        report += "⚠️ Не получили:\n"
        report += "\n".join([f"{u} — {e}" for u, _, e in failed[:30]])

    report += f"\n\n🔗 {post_link}"

    keyboard = InlineKeyboardMarkup()
    if FAILED_CACHE.get(post_link):
        keyboard.add(
            InlineKeyboardButton(
                "🔁 Повторить отправку",
                callback_data=f"retry|{post_link}"
            )
        )

    await telegram_call(bot.send_message, admin_id, report, reply_markup=keyboard)


# =========================
# КНОПКА ПОВТОРА
# =========================
@dp.callback_query_handler(lambda c: c.data.startswith("retry|"))
async def retry_failed(callback: types.CallbackQuery):
    post_link = callback.data.split("|", 1)[1]

    retry_list = FAILED_CACHE.get(post_link, [])

    if not retry_list:
        await callback.answer("Нет пользователей для повтора")
        return

    success = 0
    remaining = []
    users = await run_sheets(get_user_map)

    for username, user_id in retry_list:
        if not username.startswith("id:"):
            user_id = users.get(normalize_username(username))

        if not user_id:
            user_id = await run_sheets(get_user_id, username)

        if not user_id:
            remaining.append((username, None))
            continue

        try:
            if not username.startswith("id:"):
                current = await telegram_call(bot.get_chat, user_id)
                if normalize_username(current.username) != normalize_username(username):
                    remaining.append((username, None))
                    continue
            await telegram_call(
                bot.send_message,
                user_id,
                f"Вас упомянули в Джурыми!\n{post_link}",
                disable_web_page_preview=True,
            )
            success += 1
        except Exception:
            remaining.append((username, user_id))

        await asyncio.sleep(0.05)

    FAILED_CACHE[post_link] = remaining
    await callback.answer()
    await callback.message.answer(
        f"🔁 Повторная отправка завершена\n\nУспешно: {success}"
    )


# =========================
# CHANNEL POSTS
# =========================
@dp.channel_post_handler(content_types=types.ContentTypes.ANY)
async def channel_post_handler(message: types.Message):
    text = message.text or message.caption
    if not text:
        return

    targets = extract_mentions_from_message(message)

    EXCLUDE = {
        "jureumishopmentionbot",
        "shopmentionbot",
        "jureumiqa_bot",
        "jureumitrackerbot",
        "jureumisheetsbot",
        "teplocsjureumi_bot",
        "teplodvjureumi_bot",
        "jureumidv_bot",
        "consolidationjureumi_bot",
        "jureumishop"
    }

    targets = {t for t in targets if t not in EXCLUDE}

    if not targets:
        return

    if not message.chat.username:
        return

    post_link = f"https://t.me/{message.chat.username}/{message.message_id}"

    await send_batch_notifications(targets, post_link)


@dp.edited_channel_post_handler(content_types=types.ContentTypes.ANY)
async def edited_channel_post_handler(message: types.Message):
    return


# =========================
# HEALTH
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
@dp.errors_handler()
async def handle_bot_error(update, exception):
    import logging

    logging.error(
        "Ошибка обработки сообщения",
        exc_info=(type(exception), exception, exception.__traceback__),
    )
    message = update.message or (
        update.callback_query.message if update.callback_query else None
    )
    if message and message.chat.type == "private":
        try:
            await message.answer(
                "Не удалось выполнить действие из-за технической ошибки. Попробуйте ещё раз через минуту."
            )
        except Exception:
            logging.exception("Не удалось отправить сообщение об ошибке")
    return True


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=False, on_startup=on_startup)

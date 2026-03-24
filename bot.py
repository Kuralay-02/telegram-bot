import os
import re
import asyncio
import json
import gspread

from aiohttp import web, ClientTimeout
from aiogram import Bot, Dispatcher, executor, types


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
gc = gspread.service_account_from_dict(creds_dict)

spreadsheet = gc.open_by_url("https://docs.google.com/spreadsheets/d/1fqMGsQqXP9a7RNg-_7unYsqQeufg1If3oGPIFfqa-_o/edit?usp=sharing")
sheet = spreadsheet.worksheet("Users")


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

    data = sheet.get_all_records()

    for row in data:
        if row["username"] == uname:
            return

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
# SAFE SEND (ЛОГИРОВАНИЕ)
# =========================
async def safe_send(user_id: int, text: str, username: str = ""):
    try:
        await bot.send_message(user_id, text, disable_web_page_preview=True)
        print(f"✅ Отправлено: {username} ({user_id})")

    except Exception as e:
        print(f"❌ НЕ отправлено: {username} ({user_id}) | ошибка: {e}")


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
    found = set()

    def handle_entities(text: str, entities):
        if not text or not entities:
            return
        for ent in entities:
            if ent.type == "mention":
                raw = text[ent.offset: ent.offset + ent.length]
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
        if t.startswith("ID:"):
            try:
                user_id = int(t.split(":", 1)[1])
            except Exception:
                continue

            await safe_send(
                user_id,
                f"Вас упомянули в Джурыми!\n{post_link}",
                t
            )
            continue

        user_id = get_user_id(t)
        if not user_id:
            print(f"⚠️ Нет в базе: {t}")
            continue

        await safe_send(
            user_id,
            f"Вас упомянули в Джурыми!\n{post_link}",
            t
        )


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
if __name__ == "__main__":
    executor.start_polling(
        dp,
        skip_updates=True,
        on_startup=on_startup
    )

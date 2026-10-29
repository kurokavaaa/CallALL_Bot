"""CallALL — бот-зазывала для Telegram-чатов. Без рекламы."""

import asyncio
import html
import logging
import os
import random
import time
from pathlib import Path

import aiosqlite
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("callall")


# ---------- настройки окружения ----------

def load_env(path: Path) -> None:
    """Простой загрузчик .env, чтобы не тянуть лишние зависимости."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env(Path(__file__).with_name(".env"))
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DB_PATH = os.environ.get("DB_PATH", str(Path(__file__).with_name("callall.db")))


# ---------- команды и алиасы ----------

# команда -> русский алиас (пишется без слэша)
ALIASES = {
    "all": "каллалл",
    "call": "калл",
    "callone": "каллван",
    "stop": "стоп",
    "unreg": "анрег",
    "reg": "рег",
    "unregs": "анрегс",
    "me": "ми",
    "bigme": "бигми",
    "changeme": "чанджми",
}
ALIAS_TO_CMD = {alias: cmd for cmd, alias in ALIASES.items()}
COMMANDS = {"start", "help", "settings", "language", *ALIASES}

MENU = {
    "ru": [
        ("help", "справка"),
        ("all", "(каллалл) позвать всех"),
        ("call", "(калл) позвать актив"),
        ("callone", "(каллван) позвать всех по одному"),
        ("stop", "(стоп) остановить созыв"),
        ("unreg", "(анрег) выйти из призыва"),
        ("reg", "(рег) вернуться в призыв"),
        ("unregs", "(анрегс) список анрегнутых"),
        ("settings", "настройки чата"),
        ("language", "язык чата"),
        ("me", "(ми) позывной"),
        ("bigme", "(бигми) полноразмерный позывной"),
        ("changeme", "(чанджми) изменить позывной"),
    ],
    "en": [
        ("help", "help"),
        ("all", "call everyone"),
        ("call", "call active members"),
        ("callone", "call everyone one by one"),
        ("stop", "stop the call"),
        ("unreg", "opt out of calls"),
        ("reg", "opt back in"),
        ("unregs", "list of opted-out members"),
        ("settings", "chat settings"),
        ("language", "chat language"),
        ("me", "your callsign"),
        ("bigme", "full-size callsign"),
        ("changeme", "change callsign"),
    ],
}

EMOJIS = (
    "🐶 🐱 🐭 🐹 🐰 🦊 🐻 🐼 🐨 🐯 🦁 🐮 🐷 🐸 🐵 🐔 🐧 🐦 🐤 🦆 🦅 🦉 🦇 🐺 🐗 🐴 🦄 🐝 🐛 🦋 "
    "🐌 🐞 🐜 🦂 🐢 🐍 🦎 🦖 🦕 🐙 🦑 🦐 🦞 🦀 🐡 🐠 🐟 🐬 🐳 🐋 🦈 🐊 🐅 🐆 🦓 🦍 🐘 🦛 🦏 🐪 "
    "🦒 🦘 🐃 🐂 🐄 🐎 🐖 🐏 🐑 🦙 🐐 🦌 🐕 🐩 🐈 🐓 🦃 🦚 🦜 🦢 🦩 🕊 🐇 🦝 🦨 🦡 🦦 🦥 🐁 🐿 "
    "🦔 🐉 🌵 🌲 🌴 🍀 🍁 🍄 🌻 🌹 🌷 🌸 🌼 🌙 ⭐ 🔥 🌈 ❄ 🍏 🍎 🍐 🍊 🍋 🍌 🍉 🍇 🍓 🍒 🍑 🥭 "
    "🍍 🥥 🥝 🍅 🍆 🥑 🥦 🌶 🌽 🥕 🥐 🥨 🧀 🥚 🥞 🍔 🍟 🍕 🌭 🌮 🍣 🍩 🍪 🎂 🍫 🍬 🍭 ☕ 🧃 🎈"
).split()

ACTIVE_DAYS_OPTIONS = [1, 3, 7, 14, 30]
BATCH_OPTIONS = [1, 3, 5, 10, 20]


# ---------- тексты ----------

T = {
    "ru": {
        "help": (
            "📢 <b>CallALL</b> — зазывала без рекламы.\n\n"
            "/all (каллалл) — позвать всех\n"
            "/call (калл) — позвать актив (кто писал за последние {days} дн.)\n"
            "/callone (каллван) — позвать всех по одному сообщению на человека\n"
            "/stop (стоп) — остановить созыв\n"
            "/unreg (анрег) — выйти из призыва\n"
            "/reg (рег) — вернуться в призыв\n"
            "/unregs (анрегс) — список анрегнутых\n"
            "/me (ми) — твой позывной\n"
            "/bigme (бигми) — позывной крупно\n"
            "/changeme (чанджми) — сменить позывной, например <code>чанджми 🦄</code>\n"
            "/settings — настройки чата\n"
            "/language — язык чата\n\n"
            "К команде созыва можно дописать текст: <code>каллалл пара через 5 минут</code>\n\n"
            "ℹ️ Telegram не даёт ботам список участников, поэтому бот запоминает "
            "тех, кто пишет в чат. Попросите всех написать хоть что-нибудь."
        ),
        "private": (
            "Привет! Я <b>CallALL</b> — зову всех в групповом чате, без рекламы.\n\n"
            "Добавь меня в группу и сделай админом (или отключи privacy mode у бота), "
            "чтобы я видел сообщения и запоминал участников. Потом пиши /help в группе."
        ),
        "hello": (
            "Привет! Я <b>CallALL</b> 📢\n"
            "Я запоминаю участников, когда они пишут в чат — напишите что-нибудь, "
            "чтобы попасть в призыв. Справка: /help"
        ),
        "head_all": "📢 {name} зовёт всех!",
        "head_call": "📢 {name} зовёт актив!",
        "head_text": "📢 {name}: {text}",
        "nobody": (
            "Звать некого 🤷\nЯ запоминаю участников, когда они пишут в чат. "
            "Пусть каждый напишет хоть что-нибудь."
        ),
        "busy": "Уже идёт созыв. Остановить: /stop",
        "stopped": "⏹ Созыв остановлен.",
        "nothing": "Сейчас ничего не идёт.",
        "unreg": "Ок, {name}, тебя больше не будут звать. Вернуться: /reg",
        "already_unreg": "{name}, ты и так не в призыве. Вернуться: /reg",
        "reg": "{name}, ты снова в призыве! 📢",
        "already_reg": "{name}, ты и так в призыве.",
        "unregs_empty": "Анрегнутых нет — все в призыве 💪",
        "unregs": "🚫 Не зовутся ({n}):\n{list}",
        "admins_only": "Звать могут только админы этого чата.",
        "not_admin": "Это могут делать только админы.",
        "me": "{name}, твой позывной: {emoji}",
        "changed": "Готово, твой новый позывной: {emoji}",
        "bad_emoji": "Позывной — это 1–2 эмодзи или короткое слово (до 8 символов).",
        "taken": "Позывной {emoji} уже занят в этом чате, выбери другой.",
        "settings": "⚙️ <b>Настройки чата</b>",
        "s_days": "Актив: писали за {v} дн.",
        "s_batch": "Упоминаний в сообщении: {v}",
        "s_who": "Звать могут: {v}",
        "s_all": "все",
        "s_admins": "админы",
        "close": "✖ Закрыть",
        "language": "🌐 Выбери язык чата:",
        "lang_set": "Язык: русский 🇷🇺",
    },
    "en": {
        "help": (
            "📢 <b>CallALL</b> — an ad-free caller bot.\n\n"
            "/all — call everyone\n"
            "/call — call active members (wrote in the last {days} days)\n"
            "/callone — call everyone, one message per person\n"
            "/stop — stop the call\n"
            "/unreg — opt out of calls\n"
            "/reg — opt back in\n"
            "/unregs — list of opted-out members\n"
            "/me — your callsign\n"
            "/bigme — full-size callsign\n"
            "/changeme — change callsign, e.g. <code>/changeme 🦄</code>\n"
            "/settings — chat settings\n"
            "/language — chat language\n\n"
            "Add text after a call command: <code>/all class in 5 minutes</code>\n\n"
            "ℹ️ Telegram doesn't give bots the member list, so I remember everyone "
            "who writes in the chat. Ask everyone to send something."
        ),
        "private": (
            "Hi! I'm <b>CallALL</b> — I call everyone in group chats, no ads.\n\n"
            "Add me to a group and make me admin (or disable the bot's privacy mode) "
            "so I can see messages and remember members. Then type /help in the group."
        ),
        "hello": (
            "Hi! I'm <b>CallALL</b> 📢\n"
            "I remember members when they write in the chat — send something to get "
            "on the list. Help: /help"
        ),
        "head_all": "📢 {name} is calling everyone!",
        "head_call": "📢 {name} is calling active members!",
        "head_text": "📢 {name}: {text}",
        "nobody": (
            "Nobody to call 🤷\nI remember members when they write in the chat. "
            "Ask everyone to send something."
        ),
        "busy": "A call is already running. Stop it: /stop",
        "stopped": "⏹ Call stopped.",
        "nothing": "Nothing is running.",
        "unreg": "OK, {name}, you won't be called anymore. Come back: /reg",
        "already_unreg": "{name}, you're already opted out. Come back: /reg",
        "reg": "{name}, you're back on the list! 📢",
        "already_reg": "{name}, you're already on the list.",
        "unregs_empty": "Nobody opted out 💪",
        "unregs": "🚫 Not called ({n}):\n{list}",
        "admins_only": "Only admins of this chat can call.",
        "not_admin": "Only admins can do this.",
        "me": "{name}, your callsign: {emoji}",
        "changed": "Done, your new callsign: {emoji}",
        "bad_emoji": "A callsign is 1–2 emoji or a short word (up to 8 characters).",
        "taken": "Callsign {emoji} is already taken in this chat, pick another one.",
        "settings": "⚙️ <b>Chat settings</b>",
        "s_days": "Active: wrote in {v} days",
        "s_batch": "Mentions per message: {v}",
        "s_who": "Who can call: {v}",
        "s_all": "everyone",
        "s_admins": "admins",
        "close": "✖ Close",
        "language": "🌐 Choose chat language:",
        "lang_set": "Language: English 🇬🇧",
    },
}


def tr(lang: str, key: str, **kw) -> str:
    return T.get(lang, T["ru"])[key].format(**kw)


# ---------- база данных ----------

SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    chat_id     INTEGER PRIMARY KEY,
    lang        TEXT    NOT NULL DEFAULT 'ru',
    active_days INTEGER NOT NULL DEFAULT 7,
    batch       INTEGER NOT NULL DEFAULT 5,
    admins_only INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS users (
    chat_id   INTEGER NOT NULL,
    user_id   INTEGER NOT NULL,
    name      TEXT    NOT NULL,
    emoji     TEXT    NOT NULL,
    last_seen INTEGER NOT NULL DEFAULT 0,
    unreg     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (chat_id, user_id)
);
"""


class DB:
    conn: aiosqlite.Connection

    async def open(self, path: str) -> None:
        self.conn = await aiosqlite.connect(path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()

    async def chat(self, chat_id: int) -> dict:
        await self.conn.execute("INSERT OR IGNORE INTO chats(chat_id) VALUES (?)", (chat_id,))
        await self.conn.commit()
        cur = await self.conn.execute("SELECT * FROM chats WHERE chat_id=?", (chat_id,))
        return dict(await cur.fetchone())

    async def set_chat(self, chat_id: int, field: str, value) -> None:
        assert field in {"lang", "active_days", "batch", "admins_only"}
        await self.conn.execute(f"UPDATE chats SET {field}=? WHERE chat_id=?", (value, chat_id))
        await self.conn.commit()

    async def user(self, chat_id: int, user_id: int) -> dict | None:
        cur = await self.conn.execute(
            "SELECT * FROM users WHERE chat_id=? AND user_id=?", (chat_id, user_id)
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def free_emoji(self, chat_id: int) -> str:
        cur = await self.conn.execute("SELECT emoji FROM users WHERE chat_id=?", (chat_id,))
        used = {r["emoji"] for r in await cur.fetchall()}
        free = [e for e in EMOJIS if e not in used]
        return random.choice(free or EMOJIS)

    async def touch(self, chat_id: int, user_id: int, name: str, seen: bool = True) -> None:
        """Запомнить участника (или обновить имя и время активности)."""
        now = int(time.time()) if seen else 0
        cur = await self.conn.execute(
            "UPDATE users SET name=?, last_seen=MAX(last_seen, ?) WHERE chat_id=? AND user_id=?",
            (name, now, chat_id, user_id),
        )
        if cur.rowcount == 0:
            emoji = await self.free_emoji(chat_id)
            await self.conn.execute(
                "INSERT INTO users(chat_id, user_id, name, emoji, last_seen) VALUES (?,?,?,?,?)",
                (chat_id, user_id, name, emoji, now),
            )
        await self.conn.commit()

    async def remove(self, chat_id: int, user_id: int) -> None:
        await self.conn.execute("DELETE FROM users WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        await self.conn.commit()

    async def set_user(self, chat_id: int, user_id: int, field: str, value) -> None:
        assert field in {"emoji", "unreg"}
        await self.conn.execute(
            f"UPDATE users SET {field}=? WHERE chat_id=? AND user_id=?", (value, chat_id, user_id)
        )
        await self.conn.commit()

    async def emoji_taken(self, chat_id: int, user_id: int, emoji: str) -> bool:
        cur = await self.conn.execute(
            "SELECT 1 FROM users WHERE chat_id=? AND emoji=? AND user_id<>?", (chat_id, emoji, user_id)
        )
        return await cur.fetchone() is not None

    async def targets(self, chat_id: int, exclude: int, since: int = 0) -> list[dict]:
        cur = await self.conn.execute(
            "SELECT * FROM users WHERE chat_id=? AND unreg=0 AND user_id<>? AND last_seen>=? "
            "ORDER BY last_seen DESC",
            (chat_id, exclude, since),
        )
        return [dict(r) for r in await cur.fetchall()]

    async def unregs(self, chat_id: int) -> list[dict]:
        cur = await self.conn.execute(
            "SELECT * FROM users WHERE chat_id=? AND unreg=1 ORDER BY name", (chat_id,)
        )
        return [dict(r) for r in await cur.fetchall()]

    async def migrate(self, old_id: int, new_id: int) -> None:
        """Группа стала супергруппой — у чата сменился id."""
        await self.conn.execute("UPDATE OR IGNORE chats SET chat_id=? WHERE chat_id=?", (new_id, old_id))
        await self.conn.execute("UPDATE OR IGNORE users SET chat_id=? WHERE chat_id=?", (new_id, old_id))
        await self.conn.commit()


db = DB()
router = Router()
running: dict[int, asyncio.Task] = {}  # chat_id -> идущий созыв


# ---------- помощники ----------

def mention(user_id: int, text: str) -> str:
    return f'<a href="tg://user?id={user_id}">{html.escape(text)}</a>'


def parse_command(text: str | None, bot_username: str) -> tuple[str, str] | None:
    """'/all@CallALLbot текст' или 'каллалл текст' -> ('all', 'текст')."""
    if not text:
        return None
    parts = text.strip().split(maxsplit=1)
    if not parts:
        return None
    head, args = parts[0], (parts[1] if len(parts) > 1 else "")
    if head.startswith("/"):
        name, _, target = head[1:].partition("@")
        if target and target.lower() != bot_username.lower():
            return None
        name = name.lower()
        return (name, args) if name in COMMANDS else None
    name = ALIAS_TO_CMD.get(head.lower())
    return (name, args) if name else None


async def is_admin(bot: Bot, message_or_chat_id, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(message_or_chat_id, user_id)
    except TelegramBadRequest:
        return False
    return member.status in ("creator", "administrator")


async def sender_is_admin(message: Message) -> bool:
    # анонимный админ пишет от имени самого чата
    if message.sender_chat and message.sender_chat.id == message.chat.id:
        return True
    return await is_admin(message.bot, message.chat.id, message.from_user.id)


async def send(bot: Bot, chat_id: int, text: str) -> None:
    """Отправить сообщение, переждав флуд-лимиты Telegram."""
    for _ in range(5):
        try:
            await bot.send_message(chat_id, text, disable_web_page_preview=True)
            return
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)


async def register_admins(bot: Bot, chat_id: int) -> None:
    try:
        admins = await bot.get_chat_administrators(chat_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        return
    for a in admins:
        if not a.user.is_bot:
            await db.touch(chat_id, a.user.id, a.user.full_name, seen=False)


# ---------- созыв ----------

async def run_call(bot: Bot, chat_id: int, header: str, people: list[dict], batch: int, delay: float):
    try:
        await send(bot, chat_id, header)
        for i in range(0, len(people), batch):
            await asyncio.sleep(delay)
            chunk = people[i : i + batch]
            await send(bot, chat_id, " ".join(mention(p["user_id"], p["emoji"]) for p in chunk))
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("call failed in %s", chat_id)
    finally:
        running.pop(chat_id, None)


async def start_call(message: Message, chat: dict, kind: str, args: str) -> None:
    lang, chat_id = chat["lang"], message.chat.id
    if chat["admins_only"] and not await sender_is_admin(message):
        await message.reply(tr(lang, "admins_only"))
        return
    if chat_id in running:
        await message.reply(tr(lang, "busy"))
        return

    caller_id = message.from_user.id if message.from_user else 0
    since = int(time.time()) - chat["active_days"] * 86400 if kind == "call" else 0
    people = await db.targets(chat_id, exclude=caller_id, since=since)
    if not people:
        await message.reply(tr(lang, "nobody"))
        return

    if message.sender_chat:
        name = html.escape(message.sender_chat.title or "Admin")
    else:
        name = mention(caller_id, message.from_user.full_name)
    if args:
        header = tr(lang, "head_text", name=name, text=html.escape(args))
    else:
        header = tr(lang, "head_call" if kind == "call" else "head_all", name=name)

    if kind == "callone":
        batch, delay = 1, 1.1  # по одному — медленнее, чтобы не упереться в лимиты
    else:
        batch, delay = chat["batch"], 0.4
    running[chat_id] = asyncio.create_task(run_call(message.bot, chat_id, header, people, batch, delay))


# ---------- клавиатуры ----------

def settings_kb(chat: dict) -> InlineKeyboardMarkup:
    lang = chat["lang"]
    who = tr(lang, "s_admins" if chat["admins_only"] else "s_all")
    rows = [
        [InlineKeyboardButton(text=tr(lang, "s_days", v=chat["active_days"]), callback_data="set:days")],
        [InlineKeyboardButton(text=tr(lang, "s_batch", v=chat["batch"]), callback_data="set:batch")],
        [InlineKeyboardButton(text=tr(lang, "s_who", v=who), callback_data="set:who")],
        [InlineKeyboardButton(text=tr(lang, "close"), callback_data="set:close")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def lang_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
            InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en"),
        ]]
    )


def next_option(options: list[int], current: int) -> int:
    later = [o for o in options if o > current]
    return later[0] if later else options[0]


# ---------- обработчики ----------

@router.message(F.chat.type == "private")
async def private(message: Message) -> None:
    await message.answer(tr("ru", "private") + "\n\n" + tr("en", "private"))


@router.message(F.migrate_to_chat_id)
async def migrated(message: Message) -> None:
    await db.migrate(message.chat.id, message.migrate_to_chat_id)


@router.message(F.new_chat_members)
async def joined(message: Message) -> None:
    chat = await db.chat(message.chat.id)
    for u in message.new_chat_members:
        if u.id == message.bot.id:
            await register_admins(message.bot, message.chat.id)
            await message.answer(tr(chat["lang"], "hello"))
        elif not u.is_bot:
            await db.touch(message.chat.id, u.id, u.full_name)


@router.message(F.left_chat_member)
async def left(message: Message) -> None:
    await db.remove(message.chat.id, message.left_chat_member.id)


@router.message()
async def group_message(message: Message, bot_username: str) -> None:
    chat_id = message.chat.id
    user = message.from_user
    if user and not user.is_bot:
        await db.touch(chat_id, user.id, user.full_name)

    parsed = parse_command(message.text or message.caption, bot_username)
    if not parsed:
        return
    cmd, args = parsed
    via_alias = not (message.text or message.caption or "").startswith("/")
    chat = await db.chat(chat_id)
    lang = chat["lang"]

    if cmd in ("all", "call", "callone"):
        await start_call(message, chat, cmd, args)
        return

    if cmd in ("help", "start"):
        await message.reply(tr(lang, "help", days=chat["active_days"]))
        return

    if cmd == "stop":
        task = running.get(chat_id)
        if task:
            task.cancel()
            running.pop(chat_id, None)
            await message.reply(tr(lang, "stopped"))
        elif not via_alias:  # на случайное «стоп» в переписке молчим
            await message.reply(tr(lang, "nothing"))
        return

    if cmd == "unregs":
        people = await db.unregs(chat_id)
        if not people:
            await message.reply(tr(lang, "unregs_empty"))
        else:
            lines = "\n".join(f"{p['emoji']} {html.escape(p['name'])}" for p in people)
            await message.reply(tr(lang, "unregs", n=len(people), list=lines))
        return

    if cmd == "settings":
        if not await sender_is_admin(message):
            await message.reply(tr(lang, "not_admin"))
            return
        await message.answer(tr(lang, "settings"), reply_markup=settings_kb(chat))
        return

    if cmd == "language":
        if not await sender_is_admin(message):
            await message.reply(tr(lang, "not_admin"))
            return
        await message.answer(tr(lang, "language"), reply_markup=lang_kb())
        return

    # дальше — личные команды, нужен живой пользователь
    if not user or user.is_bot or message.sender_chat:
        return
    me = await db.user(chat_id, user.id)
    name = html.escape(user.first_name)

    if cmd == "unreg":
        if me["unreg"]:
            await message.reply(tr(lang, "already_unreg", name=name))
        else:
            await db.set_user(chat_id, user.id, "unreg", 1)
            await message.reply(tr(lang, "unreg", name=name))
    elif cmd == "reg":
        if not me["unreg"]:
            await message.reply(tr(lang, "already_reg", name=name))
        else:
            await db.set_user(chat_id, user.id, "unreg", 0)
            await message.reply(tr(lang, "reg", name=name))
    elif cmd == "me":
        await message.reply(tr(lang, "me", name=name, emoji=html.escape(me["emoji"])))
    elif cmd == "bigme":
        await message.answer(html.escape(me["emoji"]))  # одиночный эмодзи Telegram рисует крупно
    elif cmd == "changeme":
        new = args.strip() or await db.free_emoji(chat_id)
        if len(new) > 8 or " " in new:
            await message.reply(tr(lang, "bad_emoji"))
        elif await db.emoji_taken(chat_id, user.id, new):
            await message.reply(tr(lang, "taken", emoji=html.escape(new)))
        else:
            await db.set_user(chat_id, user.id, "emoji", new)
            await message.reply(tr(lang, "changed", emoji=html.escape(new)))


@router.callback_query(F.data.startswith("set:") | F.data.startswith("lang:"))
async def on_button(query: CallbackQuery) -> None:
    chat_id = query.message.chat.id
    chat = await db.chat(chat_id)
    if not await is_admin(query.bot, chat_id, query.from_user.id):
        await query.answer(tr(chat["lang"], "not_admin"), show_alert=True)
        return

    kind, _, value = query.data.partition(":")
    if kind == "lang":
        await db.set_chat(chat_id, "lang", value)
        await query.message.edit_text(tr(value, "lang_set"))
        await query.answer()
        return

    if value == "close":
        await query.message.delete()
        await query.answer()
        return
    if value == "days":
        await db.set_chat(chat_id, "active_days", next_option(ACTIVE_DAYS_OPTIONS, chat["active_days"]))
    elif value == "batch":
        await db.set_chat(chat_id, "batch", next_option(BATCH_OPTIONS, chat["batch"]))
    elif value == "who":
        await db.set_chat(chat_id, "admins_only", 0 if chat["admins_only"] else 1)

    chat = await db.chat(chat_id)
    try:
        await query.message.edit_reply_markup(reply_markup=settings_kb(chat))
    except TelegramBadRequest:
        pass
    await query.answer()


# ---------- запуск ----------

async def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("Не задан BOT_TOKEN. Создай файл .env рядом с bot.py (см. .env.example).")

    await db.open(DB_PATH)
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    me = await bot.get_me()

    scope = BotCommandScopeAllGroupChats()
    for lang, items in MENU.items():
        commands = [BotCommand(command=c, description=d) for c, d in items]
        await bot.set_my_commands(commands, scope=scope, language_code=None if lang == "ru" else lang)

    dp = Dispatcher()
    dp.include_router(router)
    log.info("CallALL запущен как @%s", me.username)
    await dp.start_polling(bot, bot_username=me.username)


if __name__ == "__main__":
    asyncio.run(main())

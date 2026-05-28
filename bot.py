"""
🌿 Plant Agent Bot
Telegram бот-агент для ухода за растениями на базе Claude.
"""
import asyncio
import base64
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, Message

import database as db
from agent import chat
from config import TELEGRAM_TOKEN
from scheduler import setup_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

async def agent_reply(message: Message, user_text: str, image_b64: str = None):
    """Run the agent and reply. Saves conversation to DB."""
    await bot.send_chat_action(message.chat.id, "typing")

    history = await db.get_chat_history(message.from_user.id)
    response = await chat(
        user_id=message.from_user.id,
        message=user_text,
        history=history,
        image_base64=image_b64,
    )

    await db.save_message(message.from_user.id, "user", user_text)
    await db.save_message(message.from_user.id, "assistant", response)
    await message.answer(response, parse_mode="Markdown")


# ─────────────────────────────────────────────
# Handlers
# ─────────────────────────────────────────────

@dp.message(CommandStart())
async def cmd_start(message: Message):
    await db.ensure_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
    )
    name = message.from_user.first_name or "друг"
    await message.answer(
        f"🌿 Привет, {name}! Я твой персональный ботаник.\n\n"
        "Умею:\n"
        "📸 *Определять растения* по фото и находить проблемы\n"
        "💧 *Напоминать о поливе* — никогда не забудешь\n"
        "🔍 *Давать советы по уходу* — научно обоснованные\n"
        "🌡️ *Диагностировать болезни* и вредителей\n"
        "📋 *Вести коллекцию* твоих растений\n\n"
        "Просто напиши мне или пришли фото растения!\n\n"
        "Команды: /plants · /schedule · /help",
        parse_mode="Markdown",
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "🌿 *Как пользоваться ботом*\n\n"
        "📸 *Пришли фото* — определю растение, найду проблемы\n\n"
        "💬 *Примеры вопросов:*\n"
        "• «Добавь мою монстеру, поливаю раз в неделю»\n"
        "• «Почему желтеют листья у фикуса?»\n"
        "• «Полил орхидею»\n"
        "• «Какие растения нужно полить сегодня?»\n"
        "• «Как ухаживать за суккулентами зимой?»\n\n"
        "📋 *Команды:*\n"
        "/plants — список твоих растений\n"
        "/schedule — расписание полива\n"
        "/help — эта справка",
        parse_mode="Markdown",
    )


@dp.message(Command("plants"))
async def cmd_plants(message: Message):
    await db.ensure_user(message.from_user.id)
    plants = await db.get_plants(message.from_user.id)

    if not plants:
        await message.answer(
            "🌱 У тебя пока нет растений в коллекции.\n\n"
            "Напиши, например:\n"
            "«Добавь монстеру, стоит у окна, поливаю раз в 7 дней»"
        )
        return

    lines = ["🌿 *Твои растения:*\n"]
    for i, p in enumerate(plants, 1):
        name = p.get("nickname") or p["name"]
        location = f" · {p['location']}" if p.get("location") else ""
        interval = p.get("watering_interval_days", 7)

        last = p.get("last_watered")
        if last:
            from datetime import datetime
            try:
                last = datetime.fromisoformat(last).strftime("%d.%m.%Y")
            except ValueError:
                last = "неизвестно"
        else:
            last = "никогда"

        lines.append(
            f"*{i}. {name}*{location}\n"
            f"   💧 Последний полив: {last}\n"
            f"   🔄 Интервал: каждые {interval} дн.\n"
        )

    await message.answer("\n".join(lines), parse_mode="Markdown")


@dp.message(Command("schedule"))
async def cmd_schedule(message: Message):
    await db.ensure_user(message.from_user.id)
    await agent_reply(
        message,
        "Покажи расписание полива для всех моих растений. "
        "Что просрочено, что нужно полить сегодня и что скоро?",
    )


@dp.message(F.photo)
async def handle_photo(message: Message):
    await db.ensure_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
    )
    await bot.send_chat_action(message.chat.id, "typing")

    # Download highest-resolution photo
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_bytes = await bot.download_file(file.file_path)
    image_b64 = base64.standard_b64encode(file_bytes.read()).decode("utf-8")

    caption = message.caption or ""
    user_text = caption if caption else "Что это за растение? Есть ли признаки болезней или проблем?"

    await agent_reply(message, user_text, image_b64=image_b64)


@dp.message(F.text)
async def handle_text(message: Message):
    await db.ensure_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
    )
    await agent_reply(message, message.text)


# ─────────────────────────────────────────────
# Startup
# ─────────────────────────────────────────────

async def set_bot_commands():
    await bot.set_my_commands([
        BotCommand(command="start", description="Начать"),
        BotCommand(command="plants", description="🌿 Мои растения"),
        BotCommand(command="schedule", description="💧 Расписание полива"),
        BotCommand(command="help", description="Помощь"),
    ])


async def main():
    await db.init_db()
    await set_bot_commands()
    setup_scheduler(bot)

    logger.info("🌿 Plant Agent Bot started!")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())

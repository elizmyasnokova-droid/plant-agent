"""
🌿 Plant Agent Bot v2.0
"""
import asyncio
import base64
import logging
import os
import tempfile
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BotCommand, CallbackQuery, InlineKeyboardButton,
    InlineKeyboardMarkup, Message
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

import database as db
from agent import chat
from config import TELEGRAM_TOKEN
from scheduler import setup_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# ─────────────────────────────────────────────
# FSM — пошаговое добавление растения
# ─────────────────────────────────────────────

class AddPlant(StatesGroup):
    name = State()
    nickname = State()
    location = State()
    interval = State()


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

async def agent_reply(message: Message, user_text: str, image_b64: str = None):
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


def plant_keyboard(plant_id: int) -> InlineKeyboardMarkup:
    """Кнопки под карточкой растения."""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="💧 Полил", callback_data=f"water_{plant_id}"))
    builder.add(InlineKeyboardButton(text="📔 Журнал", callback_data=f"journal_{plant_id}"))
    builder.add(InlineKeyboardButton(text="✏️ Изменить", callback_data=f"edit_{plant_id}"))
    builder.adjust(3)
    return builder.as_markup()


# ─────────────────────────────────────────────
# Команды
# ─────────────────────────────────────────────

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await db.ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    name = message.from_user.first_name or "друг"
    await message.answer(
        f"🌿 Привет, {name}! Я твой персональный ботаник.\n\n"
        "📸 *Фото* — определю растение, найду проблемы, сохраню в коллекцию\n"
        "💧 *Напоминания* — скажу когда поливать\n"
        "🔍 *Советы* — научно обоснованный уход\n"
        "🌡️ *Диагностика* — болезни и вредители\n"
        "📔 *Журнал* — история ухода за каждым растением\n\n"
        "Команды: /plants · /add · /schedule · /help",
        parse_mode="Markdown",
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "🌿 *Как пользоваться ботом*\n\n"
        "📸 *Пришли фото* — определю вид, найду проблемы\n\n"
        "💬 *Примеры:*\n"
        "• «Добавь мою монстеру, поливаю раз в 7 дней»\n"
        "• «Полил орхидею»\n"
        "• «Удобрил фикус»\n"
        "• «Почему желтеют листья?»\n\n"
        "📋 *Команды:*\n"
        "/plants — список с фото и кнопками\n"
        "/add — добавить растение пошагово\n"
        "/schedule — расписание полива\n"
        "/help — эта справка",
        parse_mode="Markdown",
    )


@dp.message(Command("plants"))
async def cmd_plants(message: Message, state: FSMContext):
    await state.clear()
    await db.ensure_user(message.from_user.id)
    plants = await db.get_plants(message.from_user.id)

    if not plants:
        await message.answer(
            "🌱 У тебя пока нет растений.\n\n"
            "Используй /add чтобы добавить, или просто напиши мне!"
        )
        return

    await message.answer(f"🌿 *Твои растения* — {len(plants)} шт.:", parse_mode="Markdown")

    for i, p in enumerate(plants, 1):
        name = p.get("nickname") or p["name"]
        location = f"📍 {p['location']}\n" if p.get("location") else ""
        interval = p.get("watering_interval_days", 7)
        last = p.get("last_watered")
        if last:
            try:
                last = datetime.fromisoformat(last).strftime("%d.%m.%Y")
            except ValueError:
                last = "неизвестно"
        else:
            last = "никогда"

        caption = (
            f"*{i}. {name}*\n"
            f"{location}"
            f"💧 Полив: {last}\n"
            f"🔄 Каждые {interval} дн."
        )

        kb = plant_keyboard(p["id"])

        if p.get("photo_file_id"):
            try:
                await bot.send_photo(message.chat.id, photo=p["photo_file_id"],
                                     caption=caption, parse_mode="Markdown", reply_markup=kb)
                continue
            except Exception as e:
                logger.warning(f"Photo send error: {e}")

        await message.answer(caption, parse_mode="Markdown", reply_markup=kb)


@dp.message(Command("schedule"))
async def cmd_schedule(message: Message, state: FSMContext):
    await state.clear()
    await db.ensure_user(message.from_user.id)
    await agent_reply(message,
        "Покажи расписание полива. Что просрочено, что нужно полить сегодня и что скоро?")


# ─────────────────────────────────────────────
# FSM /add — пошаговое добавление
# ─────────────────────────────────────────────

@dp.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext):
    await state.set_state(AddPlant.name)
    await message.answer(
        "🌱 *Добавляем новое растение!*\n\n"
        "Шаг 1/4 — Как называется растение?\n"
        "_(например: Монстера, Фикус, Орхидея)_",
        parse_mode="Markdown",
    )


@dp.message(AddPlant.name)
async def add_plant_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(AddPlant.nickname)
    await message.answer(
        f"✅ *{message.text}* — отлично!\n\n"
        "Шаг 2/4 — Дашь ему имя/прозвище?\n"
        "_(например: Мася, Зелёный друг, или напиши «нет»)_",
        parse_mode="Markdown",
    )


@dp.message(AddPlant.nickname)
async def add_plant_nickname(message: Message, state: FSMContext):
    nickname = None if message.text.lower() in ("нет", "no", "-") else message.text
    await state.update_data(nickname=nickname)
    await state.set_state(AddPlant.location)
    await message.answer(
        "Шаг 3/4 — Где стоит растение?\n"
        "_(например: подоконник, рабочий стол, балкон, или «нет»)_",
        parse_mode="Markdown",
    )


@dp.message(AddPlant.location)
async def add_plant_location(message: Message, state: FSMContext):
    location = None if message.text.lower() in ("нет", "no", "-") else message.text
    await state.update_data(location=location)
    await state.set_state(AddPlant.interval)
    await message.answer(
        "Шаг 4/4 — Как часто поливать? (в днях)\n"
        "_(например: 7 — раз в неделю, 3 — каждые 3 дня)_",
        parse_mode="Markdown",
    )


@dp.message(AddPlant.interval)
async def add_plant_interval(message: Message, state: FSMContext):
    try:
        interval = int(message.text.strip())
    except ValueError:
        await message.answer("⚠️ Введи число дней, например: 7")
        return

    data = await state.get_data()
    await state.clear()

    plant_id = await db.add_plant(
        user_id=message.from_user.id,
        name=data["name"],
        nickname=data.get("nickname"),
        location=data.get("location"),
        watering_interval_days=interval,
    )

    name = data.get("nickname") or data["name"]
    loc = f" ({data['location']})" if data.get("location") else ""
    await message.answer(
        f"✅ *{name}*{loc} добавлен в коллекцию!\n\n"
        f"💧 Напомню о поливе через {interval} дней.\n\n"
        f"Пришли фото растения чтобы сохранить его в карточку 📸",
        parse_mode="Markdown",
        reply_markup=plant_keyboard(plant_id),
    )


# ─────────────────────────────────────────────
# Callback — кнопки под карточкой
# ─────────────────────────────────────────────

@dp.callback_query(F.data.startswith("water_"))
async def cb_water(callback: CallbackQuery):
    plant_id = int(callback.data.split("_")[1])
    plant = await db.get_plant(plant_id)
    if not plant:
        await callback.answer("Растение не найдено", show_alert=True)
        return

    await db.water_plant(plant_id)
    name = plant.get("nickname") or plant["name"]
    interval = plant.get("watering_interval_days", 7)

    await callback.answer(f"💧 {name} полит!")
    await callback.message.answer(
        f"💧 *{name}* полит!\n"
        f"Следующий полив через {interval} дней 🗓",
        parse_mode="Markdown",
    )


@dp.callback_query(F.data.startswith("journal_"))
async def cb_journal(callback: CallbackQuery):
    plant_id = int(callback.data.split("_")[1])
    plant = await db.get_plant(plant_id)
    if not plant:
        await callback.answer("Растение не найдено", show_alert=True)
        return

    history = await db.get_care_history(plant_id, limit=10)
    name = plant.get("nickname") or plant["name"]

    await callback.answer()

    if not history:
        await callback.message.answer(
            f"📔 Журнал *{name}*\n\nЗаписей пока нет.\n"
            "Напиши мне «удобрил {name}» или «пересадил {name}» — запишу!",
            parse_mode="Markdown",
        )
        return

    ICONS = {"полив": "💧", "удобрение": "🌱", "пересадка": "🪴",
              "обрезка": "✂️", "лечение": "💊", "заметка": "📝"}

    lines = [f"📔 *Журнал {name}:*\n"]
    for entry in history:
        try:
            dt = datetime.fromisoformat(entry["created_at"]).strftime("%d.%m.%Y")
        except Exception:
            dt = entry["created_at"][:10]
        icon = ICONS.get(entry["action_type"], "•")
        note = f" — {entry['notes']}" if entry.get("notes") else ""
        lines.append(f"{icon} {dt} {entry['action_type']}{note}")

    await callback.message.answer("\n".join(lines), parse_mode="Markdown")


@dp.callback_query(F.data.startswith("edit_"))
async def cb_edit(callback: CallbackQuery):
    plant_id = int(callback.data.split("_")[1])
    plant = await db.get_plant(plant_id)
    if not plant:
        await callback.answer("Растение не найдено", show_alert=True)
        return

    name = plant.get("nickname") or plant["name"]
    await callback.answer()
    await callback.message.answer(
        f"✏️ Что изменить у *{name}*?\n\n"
        "Напиши мне, например:\n"
        f"• «Измени интервал полива {name} на 5 дней»\n"
        f"• «Переименуй {name} в Васю»\n"
        f"• «{name} переехал на балкон»",
        parse_mode="Markdown",
    )


# ─────────────────────────────────────────────
# Фото
# ─────────────────────────────────────────────

@dp.message(F.photo)
async def handle_photo(message: Message, state: FSMContext):
    await state.clear()
    await db.ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    await bot.send_chat_action(message.chat.id, "typing")

    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_bytes = await bot.download_file(file.file_path)
    image_b64 = base64.standard_b64encode(file_bytes.read()).decode("utf-8")

    caption = message.caption or ""
    user_text = (
        f"[photo_file_id: {photo.file_id}]\n{caption}"
        if caption else
        f"[photo_file_id: {photo.file_id}]\nЧто это за растение? Есть ли признаки болезней?"
    )

    await agent_reply(message, user_text, image_b64=image_b64)


# ─────────────────────────────────────────────
# Голосовые сообщения
# ─────────────────────────────────────────────

@dp.message(F.voice)
async def handle_voice(message: Message, state: FSMContext):
    await state.clear()
    await db.ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)

    try:
        import speech_recognition as sr
        from pydub import AudioSegment

        await bot.send_chat_action(message.chat.id, "typing")

        # Скачиваем OGG файл
        file = await bot.get_file(message.voice.file_id)
        file_bytes = await bot.download_file(file.file_path)

        with tempfile.TemporaryDirectory() as tmpdir:
            ogg_path = os.path.join(tmpdir, "voice.ogg")
            wav_path = os.path.join(tmpdir, "voice.wav")

            with open(ogg_path, "wb") as f:
                f.write(file_bytes.read())

            # Конвертируем OGG → WAV
            audio = AudioSegment.from_ogg(ogg_path)
            audio.export(wav_path, format="wav")

            # Распознаём речь
            recognizer = sr.Recognizer()
            with sr.AudioFile(wav_path) as source:
                audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language="ru-RU")

        await message.answer(f"🎙️ _Распознал: «{text}»_", parse_mode="Markdown")
        await agent_reply(message, text)

    except Exception as e:
        logger.warning(f"Voice recognition failed: {e}")
        await message.answer(
            "🎙️ Не смог распознать голосовое сообщение.\n"
            "Напиши текстом — отвечу быстро! 💬"
        )


# ─────────────────────────────────────────────
# Текст
# ─────────────────────────────────────────────

@dp.message(F.text)
async def handle_text(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        return  # FSM обрабатывает сам

    await db.ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    await agent_reply(message, message.text)


# ─────────────────────────────────────────────
# Startup
# ─────────────────────────────────────────────

async def set_bot_commands():
    await bot.set_my_commands([
        BotCommand(command="start", description="Начать"),
        BotCommand(command="plants", description="🌿 Мои растения"),
        BotCommand(command="add", description="➕ Добавить растение"),
        BotCommand(command="schedule", description="💧 Расписание полива"),
        BotCommand(command="help", description="Помощь"),
    ])


async def main():
    await db.init_db()
    await set_bot_commands()
    setup_scheduler(bot)
    logger.info("🌿 Plant Agent Bot v2.0 started!")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())

"""
🌿 Plant Agent Bot v2.1
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
    InlineKeyboardMarkup, KeyboardButton, Message,
    ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

import database as db
from agent import chat
from config import TELEGRAM_TOKEN
from scheduler import setup_scheduler
from weather import get_weather

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# ─── FSM ───

class AddPlant(StatesGroup):
    name = State()
    nickname = State()
    location = State()
    interval = State()


# ─── Helpers ───

async def agent_reply(message: Message, user_text: str, image_b64: str = None):
    await bot.send_chat_action(message.chat.id, "typing")
    history = await db.get_chat_history(message.from_user.id, limit=50)
    user_name = message.from_user.first_name or message.from_user.username or "друг"
    response = await chat(
        user_id=message.from_user.id,
        message=user_text,
        history=history,
        image_base64=image_b64,
        user_name=user_name,
    )
    await db.save_message(message.from_user.id, "user", user_text)
    await db.save_message(message.from_user.id, "assistant", response)
    await message.answer(response, parse_mode="Markdown")


def plant_keyboard(plant_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="💧 Полил", callback_data=f"water_{plant_id}"))
    builder.add(InlineKeyboardButton(text="📔 Журнал", callback_data=f"journal_{plant_id}"))
    builder.add(InlineKeyboardButton(text="✏️ Изменить", callback_data=f"edit_{plant_id}"))
    builder.adjust(3)
    return builder.as_markup()


# ─── Команды ───

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await db.ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    name = message.from_user.first_name or "друг"
    await message.answer(
        f"🌿 Привет, {name}! Я твой персональный ботаник.\n\n"
        "📸 *Фото* — определю растение, найду проблемы\n"
        "💧 *Напоминания* — утром и вечером если не полил\n"
        "🌤️ *Погода* — советы с учётом температуры\n"
        "📊 *Статистика* — твой прогресс в уходе\n"
        "📔 *Журнал* — история каждого растения\n\n"
        "Команды: /plants · /add · /schedule · /stats · /weather · /help",
        parse_mode="Markdown",
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "🌿 *Команды бота*\n\n"
        "/plants — список растений с фото и кнопками\n"
        "/add — добавить растение пошагово\n"
        "/schedule — расписание полива\n"
        "/stats — твоя статистика\n"
        "/weather — погода и советы по поливу\n"
        "/help — эта справка\n\n"
        "💬 *Просто пиши:*\n"
        "• «Полил орхидею»\n"
        "• «Удобрил фикус»\n"
        "• «Почему желтеют листья?»\n\n"
        "📸 Пришли фото — определю вид и найду проблемы",
        parse_mode="Markdown",
    )


@dp.message(Command("plants"))
async def cmd_plants(message: Message, state: FSMContext):
    await state.clear()
    await db.ensure_user(message.from_user.id)
    plants = await db.get_plants(message.from_user.id)

    if not plants:
        await message.answer(
            "🌱 У тебя пока нет растений.\n\nИспользуй /add или просто напиши мне!"
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

        caption = f"*{i}. {name}*\n{location}💧 Полив: {last}\n🔄 Каждые {interval} дн."
        kb = plant_keyboard(p["id"])

        if p.get("photo_file_id"):
            try:
                await bot.send_photo(message.chat.id, photo=p["photo_file_id"],
                                     caption=caption, parse_mode="Markdown", reply_markup=kb)
                continue
            except Exception as e:
                logger.warning(f"Photo error: {e}")
        await message.answer(caption, parse_mode="Markdown", reply_markup=kb)


@dp.message(Command("schedule"))
async def cmd_schedule(message: Message, state: FSMContext):
    await state.clear()
    await db.ensure_user(message.from_user.id)
    await agent_reply(message, "Покажи расписание полива. Что просрочено, сегодня и скоро?")


@dp.message(Command("weather"))
async def cmd_weather(message: Message):
    await db.ensure_user(message.from_user.id)
    loc = await db.get_user_location(message.from_user.id)

    if loc:
        weather = await get_weather(loc[0], loc[1])
    else:
        weather = await get_weather()

    temp = weather.get("temperature")
    summary = weather.get("summary", "данные недоступны")
    advice = weather.get("watering_advice", "")

    location_note = "" if loc else "\n\n💡 _Отправь свою геолокацию для точной погоды:\nскрепка 📎 → Геолокация_"

    await message.answer(
        f"🌤️ *Погода сейчас*\n\n"
        f"🌡️ {summary}\n\n"
        f"{advice}{location_note}",
        parse_mode="Markdown",
    )


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    await db.ensure_user(message.from_user.id)
    stats = await db.get_user_stats(message.from_user.id)

    total = stats["total_plants"]
    watered_today = stats["watered_today"]
    streak = stats["watering_streak"]
    tenure = stats["tenure_days"]
    total_actions = stats["total_actions"]

    # Эмодзи для стрика
    if streak >= 30:
        streak_icon = "🏆"
    elif streak >= 14:
        streak_icon = "🔥"
    elif streak >= 7:
        streak_icon = "⭐"
    elif streak >= 3:
        streak_icon = "✨"
    else:
        streak_icon = "🌱"

    # Стаж
    if tenure >= 365:
        tenure_str = f"{tenure // 365} г. {(tenure % 365) // 30} мес."
    elif tenure >= 30:
        tenure_str = f"{tenure // 30} мес."
    elif tenure > 0:
        tenure_str = f"{tenure} дн."
    else:
        tenure_str = "сегодня начали!"

    await message.answer(
        f"📊 *Твоя статистика*\n\n"
        f"🌿 Растений в коллекции: *{total}*\n"
        f"💧 Полито сегодня: *{watered_today}/{total}*\n"
        f"{streak_icon} Стрик полива: *{streak} дн.*\n"
        f"📋 Всего действий ухода: *{total_actions}*\n"
        f"⏱ Ты с нами: *{tenure_str}*",
        parse_mode="Markdown",
    )


# ─── FSM /add ───

@dp.message(Command("history"))
async def cmd_history(message: Message):
    await db.ensure_user(message.from_user.id)
    plants = await db.get_plants(message.from_user.id)

    if not plants:
        await message.answer("🌱 У тебя пока нет растений. Добавь через /add!")
        return

    if len(plants) == 1:
        await send_health_chart(message, plants[0])
        return

    lines = ["📈 *История здоровья — выбери растение:*\n"]
    for i, p in enumerate(plants, 1):
        name = p.get("nickname") or p["name"]
        latest = await db.get_latest_health(p["id"])
        if latest:
            score = latest["score"]
            stars = "⭐" * score + "☆" * (5 - score)
            lines.append(f"{i}. {name} — {stars}")
        else:
            lines.append(f"{i}. {name} — нет записей")

    lines.append("\nНапиши номер растения")
    await message.answer("\n".join(lines), parse_mode="Markdown")


async def send_health_chart(message: Message, plant: dict):
    import io
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    history = await db.get_health_history(plant["id"], days=90)
    name = plant.get("nickname") or plant["name"]

    if not history:
        text = "📈 У *" + name + "* пока нет записей о здоровье.\n\nFlora автоматически записывает состояние когда ты присылаешь фото!"
        await message.answer(text, parse_mode="Markdown")
        return

    dates, scores = [], []
    for entry in history:
        try:
            dates.append(datetime.fromisoformat(entry["created_at"]))
            scores.append(entry["score"])
        except Exception:
            continue

    if not dates:
        await message.answer("Нет данных для графика.")
        return

    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#16213e")

    ax.plot(dates, scores, color="#4ade80", linewidth=2.5, zorder=3)
    ax.fill_between(dates, scores, 1, alpha=0.2, color="#4ade80")

    colors = {1: "#ef4444", 2: "#f97316", 3: "#eab308", 4: "#84cc16", 5: "#22c55e"}
    for d, s in zip(dates, scores):
        ax.scatter(d, s, color=colors.get(s, "#4ade80"), s=80, zorder=5)

    labels_map = {1: "Критично", 2: "Плохо", 3: "Средне", 4: "Хорошо", 5: "Отлично"}
    for i in range(1, 6):
        ax.axhline(y=i, color="#ffffff", alpha=0.05, linewidth=0.5)

    ax.set_yticks(range(1, 6))
    ax.set_yticklabels([str(i) + " — " + labels_map[i] for i in range(1, 6)], color="#9ca3af", fontsize=9)
    ax.set_ylim(0.5, 5.5)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
    plt.setp(ax.get_xticklabels(), color="#9ca3af", fontsize=9)
    for spine in ax.spines.values():
        spine.set_edgecolor("#374151")

    title = "📈 История здоровья — " + name
    ax.set_title(title, color="#f9fafb", fontsize=14, pad=15, fontweight="bold")
    ax.set_xlabel("Дата", color="#9ca3af", fontsize=10)
    ax.tick_params(colors="#9ca3af")
    fig.tight_layout(pad=2)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    buf.seek(0)
    plt.close(fig)

    score = history[-1]["score"]
    stars = "⭐" * score + "☆" * (5 - score)
    trend = ""
    if len(scores) >= 2:
        diff = scores[-1] - scores[-2]
        trend = " 📈" if diff > 0 else (" 📉" if diff < 0 else " ➡️")

    caption = "📈 *" + name + "* — история за 90 дней\n\nСостояние: " + stars + trend + "\nЗаписей: " + str(len(history))

    from aiogram.types import BufferedInputFile
    await bot.send_photo(
        message.chat.id,
        photo=BufferedInputFile(buf.read(), filename="health.png"),
        caption=caption,
        parse_mode="Markdown"
    )


@dp.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext):
    await state.set_state(AddPlant.name)
    await message.answer(
        "🌱 *Добавляем растение!*\n\n"
        "Шаг 1/4 — Как называется?\n_(Монстера, Фикус, Орхидея...)_",
        parse_mode="Markdown",
    )


@dp.message(AddPlant.name)
async def add_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(AddPlant.nickname)
    await message.answer(
        f"✅ *{message.text}*\n\nШаг 2/4 — Дашь прозвище?\n_(или напиши «нет»)_",
        parse_mode="Markdown",
    )


@dp.message(AddPlant.nickname)
async def add_nickname(message: Message, state: FSMContext):
    nickname = None if message.text.lower() in ("нет", "no", "-") else message.text
    await state.update_data(nickname=nickname)
    await state.set_state(AddPlant.location)
    await message.answer("Шаг 3/4 — Где стоит?\n_(подоконник, балкон, стол... или «нет»)_", parse_mode="Markdown")


@dp.message(AddPlant.location)
async def add_location(message: Message, state: FSMContext):
    location = None if message.text.lower() in ("нет", "no", "-") else message.text
    await state.update_data(location=location)
    await state.set_state(AddPlant.interval)
    await message.answer("Шаг 4/4 — Как часто поливать? (в днях)\n_(например: 7)_", parse_mode="Markdown")


@dp.message(AddPlant.interval)
async def add_interval(message: Message, state: FSMContext):
    try:
        interval = int(message.text.strip())
    except ValueError:
        await message.answer("⚠️ Введи число, например: 7")
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
        f"✅ *{name}*{loc} добавлен!\n\n"
        f"💧 Напомню через {interval} дней.\n"
        f"📸 Пришли фото — сохраню в карточку!",
        parse_mode="Markdown",
        reply_markup=plant_keyboard(plant_id),
    )


# ─── Callbacks ───

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
        f"💧 *{name}* полит!\nСледующий полив через {interval} дней 🗓",
        parse_mode="Markdown",
    )


@dp.callback_query(F.data.startswith("journal_"))
async def cb_journal(callback: CallbackQuery):
    plant_id = int(callback.data.split("_")[1])
    plant = await db.get_plant(plant_id)
    if not plant:
        await callback.answer("Растение не найдено", show_alert=True)
        return
    history = await db.get_care_history(plant_id)
    name = plant.get("nickname") or plant["name"]
    await callback.answer()
    if not history:
        await callback.message.answer(
            f"📔 Журнал *{name}*\n\nЗаписей пока нет.\n"
            "Напиши «удобрил» или «пересадил» — запишу!", parse_mode="Markdown"
        )
        return
    ICONS = {"полив": "💧", "удобрение": "🌱", "пересадка": "🪴", "обрезка": "✂️", "лечение": "💊", "заметка": "📝"}
    lines = [f"📔 *Журнал {name}:*\n"]
    for e in history:
        try:
            dt = datetime.fromisoformat(e["created_at"]).strftime("%d.%m.%Y")
        except Exception:
            dt = e["created_at"][:10]
        icon = ICONS.get(e["action_type"], "•")
        note = f" — {e['notes']}" if e.get("notes") else ""
        lines.append(f"{icon} {dt} {e['action_type']}{note}")
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
        f"• «Измени интервал полива {name} на 5 дней»\n"
        f"• «Переименуй {name} в Васю»\n"
        f"• «{name} переехал на балкон»",
        parse_mode="Markdown",
    )


# ─── Геолокация ───

@dp.message(F.location)
async def handle_location(message: Message):
    await db.ensure_user(message.from_user.id)
    lat = message.location.latitude
    lon = message.location.longitude
    await db.save_user_location(message.from_user.id, lat, lon)

    weather = await get_weather(lat, lon)
    await message.answer(
        f"📍 Локация сохранена!\n\n"
        f"🌤️ *Погода у тебя:* {weather.get('summary', 'недоступно')}\n\n"
        f"{weather.get('watering_advice', '')}\n\n"
        f"Теперь советы по поливу будут учитывать твою погоду 🌿",
        parse_mode="Markdown",
    )


# ─── Фото ───

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

    if caption:
        # Пользователь написал что-то — добавляем запрос полного анализа
        user_text = (
            f"[photo_file_id: {photo.file_id}]\n{caption}\n\n"
            "Определи растение и дай полный анализ по уходу."
        )
    else:
        # Просто фото — полный анализ
        user_text = (
            f"[photo_file_id: {photo.file_id}]\n"
            "Определи это растение и дай полный анализ: полив, освещение, температура, "
            "влажность, удобрения, пересадка, частые болезни. "
            "Если видишь проблемы на фото — диагностируй их."
        )
    await agent_reply(message, user_text, image_b64=image_b64)


# ─── Голос ───

@dp.message(F.voice)
async def handle_voice(message: Message, state: FSMContext):
    await state.clear()
    await db.ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    try:
        import speech_recognition as sr
        from pydub import AudioSegment

        await bot.send_chat_action(message.chat.id, "typing")
        file = await bot.get_file(message.voice.file_id)
        file_bytes = await bot.download_file(file.file_path)

        with tempfile.TemporaryDirectory() as tmpdir:
            ogg_path = os.path.join(tmpdir, "voice.ogg")
            wav_path = os.path.join(tmpdir, "voice.wav")
            with open(ogg_path, "wb") as f:
                f.write(file_bytes.read())
            AudioSegment.from_ogg(ogg_path).export(wav_path, format="wav")
            recognizer = sr.Recognizer()
            with sr.AudioFile(wav_path) as source:
                audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language="ru-RU")

        await message.answer(f"🎙️ _«{text}»_", parse_mode="Markdown")
        await agent_reply(message, text)
    except Exception as e:
        logger.warning(f"Voice failed: {e}")
        await message.answer("🎙️ Не смог распознать. Напиши текстом! 💬")


# ─── Текст ───

@dp.message(F.text)
async def handle_text(message: Message, state: FSMContext):
    if await state.get_state() is not None:
        return
    await db.ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    await agent_reply(message, message.text)


# ─── Startup ───

async def set_bot_commands():
    await bot.set_my_commands([
        BotCommand(command="start", description="Начать"),
        BotCommand(command="plants", description="🌿 Мои растения"),
        BotCommand(command="add", description="➕ Добавить растение"),
        BotCommand(command="schedule", description="💧 Расписание полива"),
        BotCommand(command="weather", description="🌤️ Погода и советы"),
        BotCommand(command="stats", description="📊 Моя статистика"),
        BotCommand(command="help", description="Помощь"),
    ])


async def main():
    await db.init_db()
    await set_bot_commands()
    setup_scheduler(bot)
    logger.info("🌿 Plant Agent Bot v2.1 started!")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())

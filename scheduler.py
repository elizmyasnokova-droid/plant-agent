"""
APScheduler — утренние и вечерние напоминания о поливе.
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import database as db
from config import REMINDER_HOUR, TIMEZONE

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone=TIMEZONE)


async def send_morning_reminders(bot):
    """Утром — напоминание всем у кого просрочен полив."""
    user_ids = await db.get_users_with_overdue_plants()
    logger.info(f"Morning reminders: {len(user_ids)} users")

    for user_id in user_ids:
        schedule = await db.get_watering_schedule(user_id)
        overdue = schedule["overdue"]
        today = schedule["today"]
        if not overdue and not today:
            continue

        lines = ["🌅 *Доброе утро! Пора позаботиться о растениях.*\n"]
        if overdue:
            lines.append("⚠️ *Просрочено:*")
            for p in overdue:
                name = p.get("nickname") or p["name"]
                info = p.get("days_overdue", p.get("status", ""))
                suffix = f" (+{info} дн.)" if isinstance(info, int) else f" ({info})"
                lines.append(f"  🌿 {name}{suffix}")

        if today:
            lines.append("\n💧 *Полить сегодня:*")
            for p in today:
                lines.append(f"  🌿 {p.get('nickname') or p['name']}")

        lines.append("\nНапиши «полил [растение]» или нажми кнопку 💧 в /plants")

        try:
            await bot.send_message(user_id, "\n".join(lines), parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Morning reminder failed for {user_id}: {e}")


async def send_evening_reminders(bot):
    """Вечером — повторное напоминание только тем кто НЕ полил с утра."""
    unwatered = await db.get_unwatered_overdue_users()
    logger.info(f"Evening reminders: {len(unwatered)} users")

    for user_id, plants in unwatered.items():
        names = ", ".join(p.get("nickname") or p["name"] for p in plants[:3])
        more = f" и ещё {len(plants)-3}" if len(plants) > 3 else ""

        try:
            await bot.send_message(
                user_id,
                f"🌙 *Вечернее напоминание*\n\n"
                f"Сегодня ещё не политы: *{names}{more}*\n\n"
                f"Успей до конца дня! 💧",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.warning(f"Evening reminder failed for {user_id}: {e}")


async def send_weekly_tips(bot):
    """Каждое воскресенье — персональные советы по уходу для каждого растения."""
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic()

    user_ids = await db.get_users_with_overdue_plants.__wrapped__() if hasattr(db.get_users_with_overdue_plants, '__wrapped__') else None

    # Берём всех пользователей у которых есть растения
    import aiosqlite
    from config import DB_PATH
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute("SELECT DISTINCT user_id FROM plants") as cursor:
            all_users = [r[0] for r in await cursor.fetchall()]

    logger.info(f"Weekly tips: {len(all_users)} users")

    for user_id in all_users:
        plants = await db.get_plants(user_id)
        if not plants:
            continue

        names = ", ".join(p.get("nickname") or p["name"] for p in plants[:5])
        try:
            response = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Ты — бот Flora, помощник по растениям. "
                        f"У пользователя есть растения: {names}. "
                        f"Напиши короткий дружелюбный совет на эту неделю — "
                        f"что важно сделать с учётом текущего сезона (конец мая). "
                        f"Конкретно, 3-4 пункта, с эмодзи. Начни с '🌿 Совет недели от Flora:'"
                    )
                }]
            )
            tip = response.content[0].text
            await bot.send_message(user_id, tip, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Weekly tip failed for {user_id}: {e}")


async def send_fertilizing_reminders(bot):
    """Напоминание об удобрениях — каждый вторник."""
    user_plants = await db.get_users_with_overdue_fertilizing()
    logger.info(f"Fertilizing reminders: {len(user_plants)} users")

    for user_id, plants in user_plants.items():
        lines = ["🌱 *Пора удобрить растения!*\n"]
        for p in plants:
            name = p.get("nickname") or p["name"]
            fertilizer = p.get("fertilizer_name")
            fert_str = f" — используй *{fertilizer}*" if fertilizer else ""
            last_raw = p.get("last_fertilized")
            if last_raw:
                from datetime import datetime as dt
                try:
                    days_ago = (dt.now() - dt.fromisoformat(last_raw)).days
                    lines.append(f"  🌿 {name}{fert_str} (последний раз {days_ago} дн. назад)")
                except Exception:
                    lines.append(f"  🌿 {name}{fert_str}")
            else:
                lines.append(f"  🌿 {name}{fert_str} (ещё не удобрялось)")

        lines.append("\nНапиши «удобрила [растение]» после того как сделаешь ✅")

        try:
            await bot.send_message(user_id, "\n".join(lines), parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Fertilizing reminder failed for {user_id}: {e}")


def setup_scheduler(bot):
    # Утреннее напоминание
    scheduler.add_job(
        send_morning_reminders,
        CronTrigger(hour=REMINDER_HOUR, minute=0),
        args=[bot],
        id="morning_reminders",
        replace_existing=True,
    )
    # Вечернее напоминание в 19:00
    scheduler.add_job(
        send_evening_reminders,
        CronTrigger(hour=19, minute=0),
        args=[bot],
        id="evening_reminders",
        replace_existing=True,
    )
    # Напоминания об удобрениях — каждый вторник в 10:00
    scheduler.add_job(
        send_fertilizing_reminders,
        CronTrigger(day_of_week="tue", hour=10, minute=0),
        args=[bot],
        id="fertilizing_reminders",
        replace_existing=True,
    )
    # Еженедельные советы — каждое воскресенье в 10:00
    scheduler.add_job(
        send_weekly_tips,
        CronTrigger(day_of_week="sun", hour=10, minute=0),
        args=[bot],
        id="weekly_tips",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(f"Scheduler: утро {REMINDER_HOUR}:00, вечер 19:00, удобрения вт 10:00, советы вс 10:00 ({TIMEZONE})")
    return scheduler

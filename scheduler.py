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
    scheduler.start()
    logger.info(f"Scheduler: утро {REMINDER_HOUR}:00, вечер 19:00 ({TIMEZONE})")
    return scheduler

"""
APScheduler — ежедневные напоминания о поливе.
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import database as db
from config import REMINDER_HOUR, TIMEZONE

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone=TIMEZONE)


async def send_watering_reminders(bot):
    """
    Runs daily at REMINDER_HOUR.
    Finds all users with overdue plants and sends them a reminder.
    """
    user_ids = await db.get_users_with_overdue_plants()
    logger.info(f"Watering reminders: {len(user_ids)} users need reminding")

    for user_id in user_ids:
        schedule = await db.get_watering_schedule(user_id)
        overdue = schedule["overdue"]
        today = schedule["today"]

        if not overdue and not today:
            continue

        lines = ["💧 *Напоминание о поливе!*\n"]

        if overdue:
            lines.append("⚠️ *Просрочено:*")
            for p in overdue:
                name = p.get("nickname") or p["name"]
                info = p.get("days_overdue", p.get("status", ""))
                suffix = f" (на {info} д.)" if isinstance(info, int) else f" ({info})"
                lines.append(f"  🌿 {name}{suffix}")

        if today:
            lines.append("\n🌊 *Сегодня нужно полить:*")
            for p in today:
                name = p.get("nickname") or p["name"]
                lines.append(f"  🌿 {name}")

        lines.append("\nНапиши мне «полил [растение]» чтобы отметить полив ✅")

        try:
            await bot.send_message(
                user_id,
                "\n".join(lines),
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.warning(f"Failed to send reminder to {user_id}: {e}")


def setup_scheduler(bot):
    scheduler.add_job(
        send_watering_reminders,
        CronTrigger(hour=REMINDER_HOUR, minute=0),
        args=[bot],
        id="daily_watering_reminders",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(f"Scheduler started — reminders at {REMINDER_HOUR}:00 ({TIMEZONE})")
    return scheduler

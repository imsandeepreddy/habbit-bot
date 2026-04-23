"""
scheduler.py — background reminder engine.

Uses APScheduler to run a job every minute.
The job checks which reminders are due at the current HH:MM
and sends a Telegram message to those users.
"""

import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot

from db import get_all_active_reminders

logger = logging.getLogger(__name__)

_scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")   # ← set your timezone


# ---------------------------------------------------------------------------
# Core job: runs every minute, sends due reminders
# ---------------------------------------------------------------------------
async def _send_due_reminders(bot: Bot):
    now_hhmm = datetime.now().strftime("%H:%M")
    reminders = get_all_active_reminders()

    due = [r for r in reminders if r["remind_at"] == now_hhmm]

    for reminder in due:
        try:
            await bot.send_message(
                chat_id=reminder["chat_id"],
                text=(
                    f"⏰ *Reminder!*\n\n"
                    f"📌 {reminder['goal_text']}\n\n"
                    f"Did you do it today? Reply /done {_get_goal_number(reminder)} to mark it complete."
                ),
                parse_mode="Markdown",
            )
            logger.info(f"Sent reminder to {reminder['chat_id']} for goal: {reminder['goal_text']}")
        except Exception as e:
            logger.error(f"Failed to send reminder to {reminder['chat_id']}: {e}")


def _get_goal_number(reminder: dict) -> str:
    """
    Returns a hint number — in MVP this is always 1 since we can't know
    the exact list position without fetching the full list.
    User can always run /mygoals to see the numbered list.
    """
    return "?"


# ---------------------------------------------------------------------------
# Weekly summary job: every Sunday at 20:00
# ---------------------------------------------------------------------------
async def _send_weekly_summary(bot: Bot):
    """
    Placeholder — you can wire this up in the next iteration.
    """
    pass


# ---------------------------------------------------------------------------
# Start the scheduler (called once from main.py on_startup)
# ---------------------------------------------------------------------------
def start_scheduler(bot: Bot):
    _scheduler.add_job(
        _send_due_reminders,
        trigger="cron",
        minute="*",          # every minute
        args=[bot],
        id="reminder_job",
        replace_existing=True,
        misfire_grace_time=30,
    )

    _scheduler.add_job(
        _send_weekly_summary,
        trigger="cron",
        day_of_week="sun",
        hour=20,
        minute=0,
        args=[bot],
        id="weekly_summary",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("APScheduler started — checking reminders every minute")

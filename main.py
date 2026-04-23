import os
import asyncio
import logging
from datetime import date

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from db import (
    save_goal,
    get_active_goals,
    mark_goal_done_today,
    get_todays_completions,
)
from scheduler import start_scheduler

# ---------------------------------------------------------------------------
# Config — replace with your actual values or load from .env
# ---------------------------------------------------------------------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_HOST = "https://habbit-bot.onrender.com"   # e.g. your Railway / Render URL
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = 8080

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bot + Dispatcher
# ---------------------------------------------------------------------------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 Hey! I'm your habit reminder bot.\n\n"
        "Here's what I can do:\n"
        "  /setgoal — add a new goal with a reminder time\n"
        "  /mygoals — see all your active goals\n"
        "  /done    — mark a goal as done for today\n\n"
        "Let's build some habits 🚀"
    )


# ---------------------------------------------------------------------------
# /setgoal
# Expects: /setgoal <HH:MM> <goal text>
# Example: /setgoal 07:00 Read for 30 minutes
# ---------------------------------------------------------------------------
@dp.message(Command("setgoal"))
async def cmd_setgoal(message: Message):
    parts = message.text.strip().split(maxsplit=2)

    if len(parts) < 3:
        await message.answer(
            "Usage: /setgoal <HH:MM> <goal text>\n"
            "Example: /setgoal 07:00 Read for 30 minutes"
        )
        return

    time_str = parts[1]
    goal_text = parts[2]

    # Basic time validation
    try:
        hour, minute = map(int, time_str.split(":"))
        assert 0 <= hour <= 23 and 0 <= minute <= 59
    except Exception:
        await message.answer("⚠️ Time format should be HH:MM, e.g. 07:30")
        return

    chat_id = message.chat.id

    entry_id = await save_goal(
        chat_id=chat_id,
        goal_text=goal_text,
        remind_at=time_str,
    )

    if entry_id:
        await message.answer(
            f"✅ Goal saved!\n\n"
            f"📌 *{goal_text}*\n"
            f"⏰ I'll remind you daily at {time_str}",
            parse_mode="Markdown",
        )
    else:
        await message.answer("❌ Something went wrong saving your goal. Try again.")


# ---------------------------------------------------------------------------
# /mygoals
# ---------------------------------------------------------------------------
@dp.message(Command("mygoals"))
async def cmd_mygoals(message: Message):
    chat_id = message.chat.id
    goals = await get_active_goals(chat_id)

    if not goals:
        await message.answer(
            "You have no active goals yet.\nUse /setgoal to add one!"
        )
        return

    completions = await get_todays_completions(chat_id)
    done_ids = {c["journal_entry_id"] for c in completions}

    lines = ["📋 *Your active goals:*\n"]
    for i, g in enumerate(goals, 1):
        status = "✅" if g["id"] in done_ids else "⬜"
        lines.append(f"{status} *{i}.* {g['text']}  _(remind at {g['remind_at']})_")

    await message.answer("\n".join(lines), parse_mode="Markdown")


# ---------------------------------------------------------------------------
# /done
# Expects: /done <number>  (number from /mygoals list)
# Example: /done 1
# ---------------------------------------------------------------------------
@dp.message(Command("done"))
async def cmd_done(message: Message):
    chat_id = message.chat.id
    parts = message.text.strip().split()

    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer(
            "Usage: /done <number>\n"
            "Run /mygoals first to see your goal numbers."
        )
        return

    index = int(parts[1]) - 1
    goals = await get_active_goals(chat_id)

    if not goals or index < 0 or index >= len(goals):
        await message.answer("⚠️ Invalid goal number. Run /mygoals to check.")
        return

    goal = goals[index]
    success = await mark_goal_done_today(
        chat_id=chat_id,
        journal_entry_id=goal["id"],
        goal_text=goal["text"],
    )

    if success:
        await message.answer(
            f"🎉 Marked as done for today!\n\n"
            f"✅ *{goal['text']}*\n\n"
            f"Keep it up!",
            parse_mode="Markdown",
        )
    else:
        await message.answer("❌ Could not mark as done. Try again.")


# ---------------------------------------------------------------------------
# Startup / shutdown hooks
# ---------------------------------------------------------------------------
async def on_startup(bot: Bot):
    await bot.delete_webhook()
    await bot.set_webhook(WEBHOOK_URL)
    logger.info(f"Webhook set to {WEBHOOK_URL}")
    start_scheduler(bot)
    logger.info("Scheduler started")


async def on_shutdown(bot: Bot):
    await bot.delete_webhook()
    logger.info("Webhook deleted")


# ---------------------------------------------------------------------------
# App entry point
# ---------------------------------------------------------------------------
def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    web.run_app(app, host=WEB_SERVER_HOST, port=WEB_SERVER_PORT)


if __name__ == "__main__":
    main()

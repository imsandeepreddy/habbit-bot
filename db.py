"""
db.py — all Supabase interactions for the habit bot.

journal_entries : existing table  (bot writes goal entries here)
reminders       : new table       (bot owns this entirely)
"""
import os
import logging
from datetime import date, datetime
from uuid import UUID

from supabase import create_client, Client

# ---------------------------------------------------------------------------
# Config — replace with your actual values or load from .env
# ---------------------------------------------------------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")        # use service role for server-side

logger = logging.getLogger(__name__)

# Single shared client
_supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ---------------------------------------------------------------------------
# Save a new goal
# Writes to journal_entries (type='habit') + reminders
# ---------------------------------------------------------------------------
async def save_goal(chat_id: int, goal_text: str, remind_at: str) -> str | None:
    """
    Returns the journal_entry id on success, None on failure.
    remind_at format: "HH:MM"
    """
    try:
        # 1. Write entry to journal_entries
        entry_resp = (
            _supabase.table("journal_entries")
            .insert({
                "entry_date": date.today().isoformat(),
                "text": goal_text,
                "type": "habit",
                "tags": ["goal", "bot"],
            })
            .execute()
        )
        entry = entry_resp.data[0]
        entry_id = entry["id"]

        # 2. Write reminder row
        _supabase.table("reminders").insert({
            "journal_entry_id": entry_id,
            "chat_id": chat_id,
            "remind_at": remind_at,
            "frequency": "daily",
            "is_active": True,
        }).execute()

        return entry_id

    except Exception as e:
        logger.error(f"save_goal error: {e}")
        return None


# ---------------------------------------------------------------------------
# Get all active goals for a chat_id
# Joins reminders → journal_entries
# ---------------------------------------------------------------------------
async def get_active_goals(chat_id: int) -> list[dict]:
    """
    Returns list of dicts with keys: id, text, remind_at
    """
    try:
        resp = (
            _supabase.table("reminders")
            .select("journal_entry_id, remind_at, journal_entries(id, text)")
            .eq("chat_id", chat_id)
            .eq("is_active", True)
            .execute()
        )

        goals = []
        for row in resp.data:
            entry = row.get("journal_entries")
            if entry:
                goals.append({
                    "id": entry["id"],
                    "text": entry["text"],
                    "remind_at": row["remind_at"],
                })
        return goals

    except Exception as e:
        logger.error(f"get_active_goals error: {e}")
        return []


# ---------------------------------------------------------------------------
# Mark a goal as done today
# Writes a new journal_entries row with type='habit' and tag 'done'
# ---------------------------------------------------------------------------
async def mark_goal_done_today(
    chat_id: int, journal_entry_id: str, goal_text: str
) -> bool:
    try:
        _supabase.table("journal_entries").insert({
            "entry_date": date.today().isoformat(),
            "text": f"[Done] {goal_text}",
            "type": "habit",
            "tags": ["done", "bot", str(chat_id)],
        }).execute()

        # Update last_sent_at on the reminder so scheduler knows it was actioned
        _supabase.table("reminders").update({
            "last_sent_at": datetime.utcnow().isoformat(),
        }).eq("journal_entry_id", journal_entry_id).execute()

        return True

    except Exception as e:
        logger.error(f"mark_goal_done_today error: {e}")
        return False


# ---------------------------------------------------------------------------
# Get today's completed goals for a chat_id (for /mygoals tick display)
# ---------------------------------------------------------------------------
async def get_todays_completions(chat_id: int) -> list[dict]:
    try:
        today = date.today().isoformat()
        resp = (
            _supabase.table("journal_entries")
            .select("text, tags")
            .eq("entry_date", today)
            .eq("type", "habit")
            .contains("tags", ["done", str(chat_id)])
            .execute()
        )
        # Return minimal shape that main.py checks for journal_entry_id
        # We store chat_id in tags — so completions are matched by text prefix
        return resp.data or []

    except Exception as e:
        logger.error(f"get_todays_completions error: {e}")
        return []


# ---------------------------------------------------------------------------
# Get all active reminders across all users (used by scheduler)
# ---------------------------------------------------------------------------
def get_all_active_reminders() -> list[dict]:
    """
    Synchronous — called by APScheduler.
    Returns list of dicts: chat_id, remind_at, journal_entry_id, goal_text
    """
    try:
        resp = (
            _supabase.table("reminders")
            .select("chat_id, remind_at, journal_entry_id, journal_entries(text)")
            .eq("is_active", True)
            .execute()
        )

        result = []
        for row in resp.data:
            entry = row.get("journal_entries")
            if entry:
                result.append({
                    "chat_id": row["chat_id"],
                    "remind_at": row["remind_at"],          # "HH:MM"
                    "journal_entry_id": row["journal_entry_id"],
                    "goal_text": entry["text"],
                })
        return result

    except Exception as e:
        logger.error(f"get_all_active_reminders error: {e}")
        return []

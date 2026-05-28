"""
Database layer — SQLite via aiosqlite.
"""
import aiosqlite
from datetime import datetime, timedelta
from typing import Optional

from config import DB_PATH


# ─────────────────────────────────────────────
# Init
# ─────────────────────────────────────────────

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id    INTEGER PRIMARY KEY,
                username   TEXT,
                first_name TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS plants (
                id                     INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id                INTEGER NOT NULL,
                name                   TEXT    NOT NULL,
                nickname               TEXT,
                location               TEXT,
                watering_interval_days INTEGER DEFAULT 7,
                last_watered           TEXT,
                photo_file_id          TEXT,
                notes                  TEXT,
                created_at             TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS care_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                plant_id    INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                action_type TEXT    NOT NULL,
                notes       TEXT,
                created_at  TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (plant_id) REFERENCES plants(id)
            );

            CREATE TABLE IF NOT EXISTS chat_history (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                role       TEXT    NOT NULL,
                content    TEXT    NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );
        """)
        await db.commit()


# ─────────────────────────────────────────────
# Users
# ─────────────────────────────────────────────

async def ensure_user(user_id: int, username: str = None, first_name: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
            (user_id, username, first_name)
        )
        await db.commit()


# ─────────────────────────────────────────────
# Plants
# ─────────────────────────────────────────────

async def get_plants(user_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM plants WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_plant(plant_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM plants WHERE id = ?", (plant_id,)) as cursor:
            row = await cursor.fetchone()
    return dict(row) if row else None


async def add_plant(
    user_id: int,
    name: str,
    nickname: str = None,
    location: str = None,
    watering_interval_days: int = 7,
    notes: str = None,
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO plants (user_id, name, nickname, location, watering_interval_days, notes)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, name, nickname, location, watering_interval_days, notes),
        )
        await db.commit()
        return cursor.lastrowid


async def update_plant(plant_id: int, **fields) -> bool:
    allowed = {"name", "nickname", "location", "watering_interval_days", "notes", "photo_file_id"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [plant_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE plants SET {set_clause} WHERE id = ?", values)
        await db.commit()
    return True


async def delete_plant(plant_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM plants WHERE id = ?", (plant_id,))
        await db.commit()


async def water_plant(plant_id: int, notes: str = None):
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE plants SET last_watered = ? WHERE id = ?", (now, plant_id))
        await db.execute(
            "INSERT INTO care_log (plant_id, user_id, action_type, notes) "
            "SELECT ?, user_id, 'полив', ? FROM plants WHERE id = ?",
            (plant_id, notes, plant_id)
        )
        await db.commit()


async def get_watering_schedule(user_id: int) -> dict:
    plants = await get_plants(user_id)
    now = datetime.now()
    overdue, today_list, upcoming = [], [], []

    for p in plants:
        interval = p.get("watering_interval_days") or 7
        last_raw = p.get("last_watered")

        if not last_raw:
            overdue.append({**p, "status": "никогда не поливалось"})
            continue

        try:
            last = datetime.fromisoformat(last_raw)
        except ValueError:
            overdue.append({**p, "status": "дата полива повреждена"})
            continue

        next_watering = last + timedelta(days=interval)
        diff = (next_watering.date() - now.date()).days

        if diff < 0:
            overdue.append({**p, "days_overdue": abs(diff)})
        elif diff == 0:
            today_list.append(p)
        elif diff <= 3:
            upcoming.append({**p, "days_until": diff})

    return {"overdue": overdue, "today": today_list, "upcoming_3_days": upcoming}


async def get_users_with_overdue_plants() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT DISTINCT user_id FROM plants
               WHERE last_watered IS NULL
               OR datetime(last_watered, '+' || watering_interval_days || ' days') <= datetime('now')"""
        ) as cursor:
            rows = await cursor.fetchall()
    return [r[0] for r in rows]


# ─────────────────────────────────────────────
# Care log
# ─────────────────────────────────────────────

async def log_care_action(plant_id: int, user_id: int, action_type: str, notes: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO care_log (plant_id, user_id, action_type, notes) VALUES (?, ?, ?, ?)",
            (plant_id, user_id, action_type, notes)
        )
        await db.commit()


async def get_care_history(plant_id: int, limit: int = 10) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT action_type, notes, created_at FROM care_log
               WHERE plant_id = ? ORDER BY created_at DESC LIMIT ?""",
            (plant_id, limit)
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────
# Chat history
# ─────────────────────────────────────────────

async def get_chat_history(user_id: int, limit: int = 20) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT role, content FROM chat_history
               WHERE user_id = ? ORDER BY created_at DESC LIMIT ?""",
            (user_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


async def save_message(user_id: int, role: str, content: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO chat_history (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content),
        )
        await db.execute(
            """DELETE FROM chat_history WHERE user_id = ? AND id NOT IN (
               SELECT id FROM chat_history WHERE user_id = ? ORDER BY created_at DESC LIMIT 50
            )""",
            (user_id, user_id),
        )
        await db.commit()

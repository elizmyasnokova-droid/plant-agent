"""
Database layer — SQLite via aiosqlite.
"""
import aiosqlite
from datetime import datetime, timedelta
from typing import Optional

from config import DB_PATH


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id    INTEGER PRIMARY KEY,
                username   TEXT,
                first_name TEXT,
                latitude   REAL,
                longitude  REAL,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS plants (
                id                        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id                   INTEGER NOT NULL,
                name                      TEXT    NOT NULL,
                nickname                  TEXT,
                location                  TEXT,
                watering_interval_days    INTEGER DEFAULT 7,
                last_watered              TEXT,
                fertilizing_interval_days INTEGER DEFAULT 14,
                last_fertilized           TEXT,
                fertilizer_name           TEXT,
                photo_file_id             TEXT,
                notes                     TEXT,
                created_at                TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            -- Добавляем колонки если их нет (миграция для существующих БД)
            CREATE TABLE IF NOT EXISTS _migration_done (id INTEGER PRIMARY KEY);

            CREATE TABLE IF NOT EXISTS care_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                plant_id    INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                action_type TEXT    NOT NULL,
                notes       TEXT,
                created_at  TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (plant_id) REFERENCES plants(id)
            );

            CREATE TABLE IF NOT EXISTS health_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                plant_id   INTEGER NOT NULL,
                user_id    INTEGER NOT NULL,
                score      INTEGER NOT NULL,
                notes      TEXT,
                created_at TEXT DEFAULT (datetime('now')),
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

        # Миграция — добавляем новые колонки в существующую БД
        for col, definition in [
            ("fertilizing_interval_days", "INTEGER DEFAULT 14"),
            ("last_fertilized", "TEXT"),
            ("fertilizer_name", "TEXT"),
        ]:
            try:
                await db.execute(f"ALTER TABLE plants ADD COLUMN {col} {definition}")
                await db.commit()
            except Exception:
                pass  # Колонка уже есть


# ─── Users ───

async def ensure_user(user_id: int, username: str = None, first_name: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
            (user_id, username, first_name)
        )
        await db.commit()


async def save_user_location(user_id: int, latitude: float, longitude: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET latitude=?, longitude=? WHERE user_id=?",
            (latitude, longitude, user_id)
        )
        await db.commit()


async def get_user_location(user_id: int) -> Optional[tuple[float, float]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT latitude, longitude FROM users WHERE user_id=?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
    if row and row["latitude"] is not None:
        return row["latitude"], row["longitude"]
    return None


# ─── Plants ───

async def get_plants(user_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM plants WHERE user_id=? ORDER BY created_at DESC", (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_plant(plant_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM plants WHERE id=?", (plant_id,)) as cursor:
            row = await cursor.fetchone()
    return dict(row) if row else None


async def add_plant(user_id: int, name: str, nickname: str = None,
                    location: str = None, watering_interval_days: int = 7,
                    notes: str = None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO plants (user_id, name, nickname, location, watering_interval_days, notes) VALUES (?,?,?,?,?,?)",
            (user_id, name, nickname, location, watering_interval_days, notes),
        )
        await db.commit()
        return cursor.lastrowid


async def update_plant(plant_id: int, **fields) -> bool:
    allowed = {"name", "nickname", "location", "watering_interval_days", "notes", "photo_file_id"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return False
    set_clause = ", ".join(f"{k}=?" for k in updates)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE plants SET {set_clause} WHERE id=?", [*updates.values(), plant_id])
        await db.commit()
    return True


async def delete_plant(plant_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM plants WHERE id=?", (plant_id,))
        await db.commit()


async def water_plant(plant_id: int, notes: str = None):
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE plants SET last_watered=? WHERE id=?", (now, plant_id))
        await db.execute(
            "INSERT INTO care_log (plant_id, user_id, action_type, notes) "
            "SELECT ?, user_id, 'полив', ? FROM plants WHERE id=?",
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
            overdue.append({**p, "status": "дата повреждена"})
            continue
        diff = ((last + timedelta(days=interval)).date() - now.date()).days
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
               OR datetime(last_watered,'+'||watering_interval_days||' days')<=datetime('now')"""
        ) as cursor:
            rows = await cursor.fetchall()
    return [r[0] for r in rows]


async def get_unwatered_overdue_users() -> dict[int, list[dict]]:
    """Для вечернего напоминания — пользователи у которых ещё не полили сегодня."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT p.*, p.user_id as uid FROM plants p
               WHERE (p.last_watered IS NULL
               OR datetime(p.last_watered,'+'||p.watering_interval_days||' days')<=datetime('now'))
               AND date(p.last_watered) != date('now')"""
        ) as cursor:
            rows = await cursor.fetchall()
    result: dict[int, list] = {}
    for r in rows:
        uid = r["uid"]
        if uid not in result:
            result[uid] = []
        result[uid].append(dict(r))
    return result


# ─── Fertilizing ───

async def fertilize_plant(plant_id: int, fertilizer_name: str = None, notes: str = None):
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        if fertilizer_name:
            await db.execute(
                "UPDATE plants SET last_fertilized=?, fertilizer_name=? WHERE id=?",
                (now, fertilizer_name, plant_id)
            )
        else:
            await db.execute("UPDATE plants SET last_fertilized=? WHERE id=?", (now, plant_id))
        await db.execute(
            "INSERT INTO care_log (plant_id, user_id, action_type, notes) "
            "SELECT ?, user_id, 'удобрение', ? FROM plants WHERE id=?",
            (plant_id, notes or fertilizer_name, plant_id)
        )
        await db.commit()


async def set_fertilizing_schedule(plant_id: int, interval_days: int, fertilizer_name: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        if fertilizer_name:
            await db.execute(
                "UPDATE plants SET fertilizing_interval_days=?, fertilizer_name=? WHERE id=?",
                (interval_days, fertilizer_name, plant_id)
            )
        else:
            await db.execute(
                "UPDATE plants SET fertilizing_interval_days=? WHERE id=?",
                (interval_days, plant_id)
            )
        await db.commit()


async def get_fertilizing_schedule(user_id: int) -> dict:
    plants = await get_plants(user_id)
    now = datetime.now()
    overdue, today_list, upcoming = [], [], []

    for p in plants:
        interval = p.get("fertilizing_interval_days") or 14
        last_raw = p.get("last_fertilized")

        if not last_raw:
            overdue.append({**p, "status": "ещё не удобрялось"})
            continue

        try:
            last = datetime.fromisoformat(last_raw)
        except ValueError:
            continue

        diff = ((last + timedelta(days=interval)).date() - now.date()).days

        if diff < 0:
            overdue.append({**p, "days_overdue": abs(diff)})
        elif diff == 0:
            today_list.append(p)
        elif diff <= 3:
            upcoming.append({**p, "days_until": diff})

    return {"overdue": overdue, "today": today_list, "upcoming_3_days": upcoming}


async def get_users_with_overdue_fertilizing() -> dict[int, list[dict]]:
    """Пользователи у которых пора удобрять растения."""
    plants_list = []
    import aiosqlite as _aio
    async with _aio.connect(DB_PATH) as db:
        db.row_factory = _aio.Row
        async with db.execute(
            """SELECT * FROM plants
               WHERE fertilizing_interval_days IS NOT NULL
               AND (last_fertilized IS NULL
               OR datetime(last_fertilized,'+'||fertilizing_interval_days||' days')<=datetime('now'))"""
        ) as cursor:
            rows = await cursor.fetchall()
        plants_list = [dict(r) for r in rows]

    result: dict[int, list] = {}
    for p in plants_list:
        uid = p["user_id"]
        if uid not in result:
            result[uid] = []
        result[uid].append(p)
    return result


# ─── Care log ───

async def log_care_action(plant_id: int, user_id: int, action_type: str, notes: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO care_log (plant_id, user_id, action_type, notes) VALUES (?,?,?,?)",
            (plant_id, user_id, action_type, notes)
        )
        await db.commit()


async def get_care_history(plant_id: int, limit: int = 10) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT action_type, notes, created_at FROM care_log WHERE plant_id=? ORDER BY created_at DESC LIMIT ?",
            (plant_id, limit)
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(r) for r in rows]


# ─── Statistics ───

async def get_user_stats(user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        # Общее количество растений
        async with db.execute("SELECT COUNT(*) FROM plants WHERE user_id=?", (user_id,)) as c:
            total_plants = (await c.fetchone())[0]

        # Полито сегодня
        async with db.execute(
            "SELECT COUNT(*) FROM plants WHERE user_id=? AND date(last_watered)=date('now')", (user_id,)
        ) as c:
            watered_today = (await c.fetchone())[0]

        # Всего действий по уходу
        async with db.execute(
            "SELECT COUNT(*) FROM care_log WHERE user_id=?", (user_id,)
        ) as c:
            total_actions = (await c.fetchone())[0]

        # Дата первого действия (стаж)
        async with db.execute(
            "SELECT MIN(created_at) FROM care_log WHERE user_id=?", (user_id,)
        ) as c:
            first_action = (await c.fetchone())[0]

        # Стрик полива — считаем последние 30 дней
        async with db.execute(
            """SELECT DISTINCT date(created_at) as day FROM care_log
               WHERE user_id=? AND action_type='полив'
               ORDER BY day DESC LIMIT 30""",
            (user_id,)
        ) as c:
            days = [row[0] for row in await c.fetchall()]

    # Считаем streak
    streak = 0
    today = datetime.now().date()
    for i, day_str in enumerate(days):
        day = datetime.strptime(day_str, "%Y-%m-%d").date()
        expected = today - timedelta(days=i)
        if day == expected:
            streak += 1
        else:
            break

    # Стаж в днях
    tenure_days = 0
    if first_action:
        try:
            first = datetime.fromisoformat(first_action)
            tenure_days = (datetime.now() - first).days
        except Exception:
            pass

    return {
        "total_plants": total_plants,
        "watered_today": watered_today,
        "total_actions": total_actions,
        "watering_streak": streak,
        "tenure_days": tenure_days,
    }


# ─── Health log ───

async def log_health(plant_id: int, user_id: int, score: int, notes: str = None):
    """Записать состояние здоровья растения. score: 1-5."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO health_log (plant_id, user_id, score, notes) VALUES (?,?,?,?)",
            (plant_id, user_id, score, notes)
        )
        await db.commit()


async def get_health_history(plant_id: int, days: int = 90) -> list[dict]:
    """История здоровья за последние N дней."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT score, notes, created_at FROM health_log
               WHERE plant_id=?
               AND created_at >= datetime('now', '-' || ? || ' days')
               ORDER BY created_at ASC""",
            (plant_id, days)
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_latest_health(plant_id: int) -> Optional[dict]:
    """Последняя запись здоровья."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT score, notes, created_at FROM health_log WHERE plant_id=? ORDER BY created_at DESC LIMIT 1",
            (plant_id,)
        ) as cursor:
            row = await cursor.fetchone()
    return dict(row) if row else None


# ─── Chat history ───

async def get_chat_history(user_id: int, limit: int = 50) -> list[dict]:
    """
    Умная выборка истории:
    — последние 50 сообщений (текущий контекст)
    — + важные старые: добавление растений, диагнозы, первое сообщение
    Всё хранится безлимитно, в контекст идёт самое нужное.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Последние N сообщений — основной контекст
        async with db.execute(
            "SELECT id, role, content FROM chat_history WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ) as cursor:
            recent_rows = await cursor.fetchall()

        # Важные старые сообщения (содержат ключевые слова)
        keywords = "добав%,болезн%,диагноз%,пересад%,лечени%,умира%,спас%,фото%,определ%"
        placeholders = ",".join(["?" for _ in keywords.split(",")])
        like_clauses = " OR ".join(["content LIKE ?" for _ in keywords.split(",")])
        like_values = [k for k in keywords.split(",")]

        async with db.execute(
            f"""SELECT id, role, content FROM chat_history
               WHERE user_id=? AND ({like_clauses})
               AND id NOT IN (SELECT id FROM chat_history WHERE user_id=? ORDER BY created_at DESC LIMIT ?)
               ORDER BY created_at ASC LIMIT 20""",
            [user_id] + like_values + [user_id, limit],
        ) as cursor:
            important_rows = await cursor.fetchall()

    # Собираем: важные старые + разделитель + свежие (без дублей)
    recent_ids = {r["id"] for r in recent_rows}
    result = []

    if important_rows:
        for r in important_rows:
            if r["id"] not in recent_ids:
                result.append({"role": r["role"], "content": r["content"]})
        # Разделитель чтобы агент понимал что это старый контекст
        if result:
            result.append({
                "role": "user",
                "content": "[--- выше: важные моменты из прошлых разговоров ---]"
            })
            result.append({"role": "assistant", "content": "Понял, учту весь контекст."})

    for r in reversed(recent_rows):
        result.append({"role": r["role"], "content": r["content"]})

    return result


async def get_chat_stats(user_id: int) -> dict:
    """Статистика переписки."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM chat_history WHERE user_id=?", (user_id,)
        ) as c:
            total = (await c.fetchone())[0]
        async with db.execute(
            "SELECT MIN(created_at), MAX(created_at) FROM chat_history WHERE user_id=?", (user_id,)
        ) as c:
            row = await c.fetchone()
            first, last = (row[0], row[1]) if row else (None, None)
    return {"total_messages": total, "first_message": first, "last_message": last}


async def save_message(user_id: int, role: str, content: str):
    """Сохранить сообщение. Хранение БЕЗЛИМИТНОЕ — ничего не удаляется."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO chat_history (user_id, role, content) VALUES (?,?,?)",
            (user_id, role, content),
        )
        await db.commit()

"""
База данных SQLite для хранения настроек отслеживания Яндекс Таблиц.
"""
import aiosqlite
from datetime import datetime
from config import DB_PATH


async def init_db():
    """Создаёт таблицы при старте бота."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                full_name   TEXT,
                created_at  TEXT
            );

            CREATE TABLE IF NOT EXISTS trackings (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL,
                public_key      TEXT NOT NULL,
                file_path       TEXT NOT NULL,
                sheet_name      TEXT NOT NULL,
                last_row        INTEGER DEFAULT 1,
                is_active       INTEGER DEFAULT 1,
                created_at      TEXT NOT NULL,
                updated_at      TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_trackings_active
                ON trackings(is_active, id);

            CREATE TABLE IF NOT EXISTS sent_rows (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                tracking_id     INTEGER NOT NULL,
                row_number      INTEGER NOT NULL,
                row_data        TEXT,
                sent_at         TEXT NOT NULL,
                UNIQUE(tracking_id, row_number)
            );

            CREATE INDEX IF NOT EXISTS idx_sent_tracking
                ON sent_rows(tracking_id, row_number DESC);
        """)
        await db.commit()


async def save_user(user_id: int, username: str | None, full_name: str):
    """Сохраняет или обновляет пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO users (user_id, username, full_name, created_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 username=excluded.username,
                 full_name=excluded.full_name""",
            (
                user_id, username, full_name,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        await db.commit()


async def add_tracking(
    user_id: int,
    public_key: str,
    file_path: str,
    sheet_name: str,
    last_row: int = 1,
) -> int:
    """Добавляет новое отслеживание. Возвращает ID."""
    now = datetime.now().isoformat(timespec="seconds")
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO trackings
               (user_id, public_key, file_path, sheet_name, last_row, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, public_key, file_path, sheet_name, last_row, now),
        )
        await db.commit()
        return cur.lastrowid


async def get_user_trackings(user_id: int) -> list[dict]:
    """Все отслеживания пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM trackings WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_tracking(tracking_id: int) -> dict | None:
    """Одно отслеживание по ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM trackings WHERE id = ?",
            (tracking_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_all_active_trackings() -> list[dict]:
    """Все активные отслеживания (для worker'а)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM trackings WHERE is_active = 1 ORDER BY id"
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def update_tracking_last_row(tracking_id: int, last_row: int):
    """Обновляет last_row после обработки."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE trackings
               SET last_row = ?, updated_at = ?
               WHERE id = ?""",
            (
                last_row,
                datetime.now().isoformat(timespec="seconds"),
                tracking_id,
            ),
        )
        await db.commit()


async def toggle_tracking(tracking_id: int) -> bool:
    """Переключает is_active. Возвращает новое состояние."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT is_active FROM trackings WHERE id = ?",
            (tracking_id,),
        )
        row = await cur.fetchone()
        if not row:
            return False
        new_state = 0 if row["is_active"] else 1
        await db.execute(
            """UPDATE trackings SET is_active = ?, updated_at = ?
               WHERE id = ?""",
            (
                new_state,
                datetime.now().isoformat(timespec="seconds"),
                tracking_id,
            ),
        )
        await db.commit()
        return bool(new_state)


async def delete_tracking(tracking_id: int) -> bool:
    """Удаляет отслеживание и связанные sent_rows."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM sent_rows WHERE tracking_id = ?",
            (tracking_id,),
        )
        cur = await db.execute(
            "DELETE FROM trackings WHERE id = ?",
            (tracking_id,),
        )
        await db.commit()
        return cur.rowcount > 0


async def is_row_sent(tracking_id: int, row_number: int) -> bool:
    """Проверяет, отправляли ли уже эту строку."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT 1 FROM sent_rows WHERE tracking_id = ? AND row_number = ?",
            (tracking_id, row_number),
        )
        return (await cur.fetchone()) is not None


async def mark_row_sent(tracking_id: int, row_number: int, row_data: str):
    """Отмечает строку как отправленную."""
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                """INSERT INTO sent_rows
                   (tracking_id, row_number, row_data, sent_at)
                   VALUES (?, ?, ?, ?)""",
                (
                    tracking_id, row_number, row_data,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            await db.commit()
        except aiosqlite.IntegrityError:
            pass


async def get_stats() -> dict:
    """Общая статистика для админки."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c:
            users = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM trackings") as c:
            trackings = (await c.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM trackings WHERE is_active = 1"
        ) as c:
            active = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM sent_rows") as c:
            notifications = (await c.fetchone())[0]

    return {
        "users": users,
        "trackings": trackings,
        "active": active,
        "notifications": notifications,
    }
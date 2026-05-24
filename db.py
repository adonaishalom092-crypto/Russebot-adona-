import asyncpg
import logging
import os

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")

_pool = None

async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL)
    return _pool

async def init_db():
    pool = await get_pool()
    async with pool.acquire() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id               SERIAL PRIMARY KEY,
                user_id          BIGINT UNIQUE,
                balance          INTEGER DEFAULT 0,
                referrer_id      BIGINT,
                last_bonus_date  TEXT,
                total_referrals  INTEGER DEFAULT 0,
                total_bonus      INTEGER DEFAULT 0,
                language         TEXT,
                referral_paid    INTEGER DEFAULT 0,
                is_banned        INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS withdrawals (
                id                  SERIAL PRIMARY KEY,
                user_id             BIGINT,
                amount              INTEGER,
                method              TEXT,
                number              TEXT,
                name                TEXT,
                status              TEXT DEFAULT 'pending',
                referrals_snapshot  INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS channels (
                id       SERIAL PRIMARY KEY,
                username TEXT UNIQUE
            );
        """)

        for col_sql in [
            "ALTER TABLE withdrawals ADD COLUMN IF NOT EXISTS referrals_snapshot INTEGER DEFAULT 0",
        ]:
            try:
                await db.execute(col_sql)
            except Exception:
                pass

        # Canal principal par défaut
        await db.execute(
            "INSERT INTO channels (username) VALUES ($1) ON CONFLICT DO NOTHING",
            "@zarabotok_official0"
        )
    logger.info("База данных PostgreSQL инициализирована.")

async def get_user(user_id: int):
    pool = await get_pool()
    async with pool.acquire() as db:
        return await db.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)

async def get_or_create_user(user_id: int, referrer_id=None, language=None):
    pool = await get_pool()
    async with pool.acquire() as db:
        user = await db.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)
        if not user:
            await db.execute(
                "INSERT INTO users (user_id, referrer_id, language) VALUES ($1, $2, $3)",
                user_id, referrer_id, language
            )
            user = await db.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)
        return user

async def get_balance(user_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as db:
        row = await db.fetchrow("SELECT balance FROM users WHERE user_id=$1", user_id)
        return row["balance"] if row else 0

async def is_banned(user_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as db:
        row = await db.fetchrow("SELECT is_banned FROM users WHERE user_id=$1", user_id)
        return bool(row and row["is_banned"])

async def ban_user(user_id: int):
    pool = await get_pool()
    async with pool.acquire() as db:
        await db.execute("UPDATE users SET is_banned=1 WHERE user_id=$1", user_id)

async def unban_user(user_id: int):
    pool = await get_pool()
    async with pool.acquire() as db:
        await db.execute("UPDATE users SET is_banned=0 WHERE user_id=$1", user_id)

async def claim_daily_bonus(user_id: int, today: str) -> bool:
    from config import DAILY_BONUS, REFERRAL_BONUS
    pool = await get_pool()
    async with pool.acquire() as db:
        user = await db.fetchrow(
            "SELECT last_bonus_date, referrer_id, referral_paid FROM users WHERE user_id=$1", user_id
        )
        if not user or user["last_bonus_date"] == today:
            return False
        async with db.transaction():
            await db.execute(
                "UPDATE users SET balance=balance+$1, last_bonus_date=$2, total_bonus=total_bonus+1 WHERE user_id=$3",
                DAILY_BONUS, today, user_id
            )
            if user["referrer_id"] and not user["referral_paid"]:
                await db.execute(
                    "UPDATE users SET balance=balance+$1, total_referrals=total_referrals+1 WHERE user_id=$2",
                    REFERRAL_BONUS, user["referrer_id"]
                )
                await db.execute(
                    "UPDATE users SET referral_paid=1 WHERE user_id=$1", user_id
                )
        return True

async def count_pending_withdrawals(user_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as db:
        row = await db.fetchrow(
            "SELECT COUNT(*) as c FROM withdrawals WHERE user_id=$1 AND status='pending'",
            user_id
        )
        return row["c"] if row else 0

async def get_withdrawal_count(user_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as db:
        row = await db.fetchrow(
            "SELECT COUNT(*) as c FROM withdrawals WHERE user_id=$1 AND status='paid'",
            user_id
        )
        return row["c"] if row else 0

async def get_referrals_at_last_withdrawal(user_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as db:
        row = await db.fetchrow(
            "SELECT referrals_snapshot FROM withdrawals WHERE user_id=$1 AND status='paid' ORDER BY id DESC LIMIT 1",
            user_id
        )
        return row["referrals_snapshot"] if row else 0

async def get_all_withdrawal_snapshots(user_id: int) -> list:
    pool = await get_pool()
    async with pool.acquire() as db:
        rows = await db.fetch(
            "SELECT referrals_snapshot FROM withdrawals WHERE user_id=$1 AND status='paid' ORDER BY id ASC",
            user_id
        )
        return [r["referrals_snapshot"] for r in rows]

async def fix_snapshots_for_old_users() -> int:
    pool = await get_pool()
    async with pool.acquire() as db:
        rows = await db.fetch("""
            SELECT DISTINCT w.user_id
            FROM withdrawals w
            WHERE w.status = 'paid'
            AND w.referrals_snapshot = 0
        """)
        count = 0
        for row in rows:
            uid = row["user_id"]
            user = await db.fetchrow(
                "SELECT total_referrals FROM users WHERE user_id=$1", uid
            )
            if not user:
                continue
            total_referrals = user["total_referrals"]
            await db.execute("""
                UPDATE withdrawals
                SET referrals_snapshot = $1
                WHERE id = (
                    SELECT id FROM withdrawals
                    WHERE user_id = $2
                    AND status = 'paid'
                    ORDER BY id DESC
                    LIMIT 1
                )
            """, total_referrals, uid)
            count += 1
        return count

async def create_withdrawal(user_id: int, amount: int, method: str, number: str, name: str) -> int:
    pool = await get_pool()
    async with pool.acquire() as db:
        user = await db.fetchrow(
            "SELECT total_referrals FROM users WHERE user_id=$1", user_id
        )
        referrals_snapshot = user["total_referrals"] if user else 0
        async with db.transaction():
            await db.execute(
                "UPDATE users SET balance=balance-$1 WHERE user_id=$2", amount, user_id
            )
            row = await db.fetchrow(
                "INSERT INTO withdrawals "
                "(user_id, amount, method, number, name, status, referrals_snapshot) "
                "VALUES ($1,$2,$3,$4,$5,'pending',$6) RETURNING id",
                user_id, amount, method, number, name, referrals_snapshot
            )
            return row["id"]

async def get_withdrawal(wid: int):
    pool = await get_pool()
    async with pool.acquire() as db:
        return await db.fetchrow("SELECT * FROM withdrawals WHERE id=$1", wid)

async def pay_withdrawal(wid: int):
    pool = await get_pool()
    async with pool.acquire() as db:
        await db.execute("UPDATE withdrawals SET status='paid' WHERE id=$1", wid)

async def refuse_withdrawal(wid: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as db:
        row = await db.fetchrow(
            "SELECT user_id, amount, status FROM withdrawals WHERE id=$1", wid
        )
        if not row or row["status"] != "pending":
            return False
        async with db.transaction():
            await db.execute(
                "UPDATE withdrawals SET status='refused' WHERE id=$1", wid
            )
            await db.execute(
                "UPDATE users SET balance=balance+$1 WHERE user_id=$2",
                row["amount"], row["user_id"]
            )
        return True

async def get_user_withdrawals(user_id: int, limit: int = 20):
    pool = await get_pool()
    async with pool.acquire() as db:
        return await db.fetch(
            "SELECT amount, method, status FROM withdrawals "
            "WHERE user_id=$1 ORDER BY id DESC LIMIT $2",
            user_id, limit
        )

async def get_all_user_ids():
    pool = await get_pool()
    async with pool.acquire() as db:
        rows = await db.fetch("SELECT user_id FROM users WHERE is_banned=0")
        return [r["user_id"] for r in rows]

async def get_stats() -> dict:
    pool = await get_pool()
    async with pool.acquire() as db:
        users = (await db.fetchrow("SELECT COUNT(*) as c FROM users"))["c"]
        pending = (await db.fetchrow(
            "SELECT COUNT(*) as c FROM withdrawals WHERE status='pending'"))["c"]
        total_wd = (await db.fetchrow("SELECT COUNT(*) as c FROM withdrawals"))["c"]
        total_balance = (await db.fetchrow(
            "SELECT COALESCE(SUM(balance),0) as s FROM users"))["s"]
    return {
        "users": users,
        "pending": pending,
        "total_withdrawals": total_wd,
        "total_balance": total_balance
    }

async def get_channels():
    pool = await get_pool()
    async with pool.acquire() as db:
        rows = await db.fetch("SELECT username FROM channels")
        return [r["username"] for r in rows]

async def add_channel(username: str) -> bool:
    pool = await get_pool()
    async with pool.acquire() as db:
        try:
            await db.execute("INSERT INTO channels (username) VALUES ($1)", username)
            return True
        except asyncpg.UniqueViolationError:
            return False

async def delete_channel(username: str):
    pool = await get_pool()
    async with pool.acquire() as db:
        await db.execute("DELETE FROM channels WHERE username=$1", username)
      

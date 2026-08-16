"""Database module providing thread-safe, atomic SQLite operations."""
import sqlite3
import time
import uuid
import asyncio
from typing import List, Dict, Any, Optional
from app.matcher import matches_keyword


class Database:
    def __init__(self, db_path: str = "linkplease.db"):
        self.db_path = db_path
        self._lock = asyncio.Lock()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for high concurrency read/write performance
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
        return conn

    async def init_db(self):
        """Initialize database schema with strict unique constraints and indices."""
        async with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    # Rules table
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS rules (
                            rule_id TEXT PRIMARY KEY,
                            keyword TEXT NOT NULL,
                            dm_message TEXT NOT NULL,
                            created_at REAL NOT NULL
                        );
                    """)

                    # Events table for event deduplication
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS events (
                            event_id TEXT PRIMARY KEY,
                            event_type TEXT NOT NULL,
                            comment_id TEXT,
                            post_id TEXT,
                            user_id TEXT,
                            text TEXT,
                            sent_at TEXT,
                            received_at REAL NOT NULL
                        );
                    """)

                    # Deleted comments table
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS deleted_comments (
                            comment_id TEXT PRIMARY KEY,
                            deleted_at REAL NOT NULL
                        );
                    """)

                    # Durable User+Rule uniqueness constraint
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS processed_user_rules (
                            rule_id TEXT NOT NULL,
                            user_id TEXT NOT NULL,
                            first_comment_id TEXT NOT NULL,
                            processed_at REAL NOT NULL,
                            PRIMARY KEY (rule_id, user_id)
                        );
                    """)

                    # Duplicate blocks audit ledger
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS duplicate_blocks (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            rule_id TEXT NOT NULL,
                            user_id TEXT NOT NULL,
                            comment_id TEXT NOT NULL,
                            blocked_at REAL NOT NULL
                        );
                    """)

                    # Jobs queue table
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS jobs (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            job_id TEXT UNIQUE NOT NULL,
                            rule_id TEXT NOT NULL,
                            user_id TEXT NOT NULL,
                            comment_id TEXT NOT NULL,
                            message TEXT NOT NULL,
                            status TEXT NOT NULL, -- queued, accepted, delivered, failed, cancelled_deleted
                            dm_id TEXT,
                            retries INTEGER DEFAULT 0,
                            next_retry_at REAL NOT NULL,
                            last_error TEXT,
                            created_at REAL NOT NULL,
                            updated_at REAL NOT NULL
                        );
                    """)

                    # Indices for fast worker polling and stats
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status_retry ON jobs(status, next_retry_at);")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_dm_id ON jobs(dm_id);")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_comment_id ON jobs(comment_id);")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_received ON events(received_at);")
            finally:
                conn.close()

    async def create_rule(self, keyword: str, dm_message: str) -> Dict[str, Any]:
        """Create a new automation rule."""
        rule_id = f"rule_{uuid.uuid4().hex[:12]}"
        now = time.time()
        async with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    conn.execute(
                        "INSERT INTO rules (rule_id, keyword, dm_message, created_at) VALUES (?, ?, ?, ?)",
                        (rule_id, keyword, dm_message, now)
                    )
                return {
                    "rule_id": rule_id,
                    "keyword": keyword,
                    "dm_message": dm_message
                }
            finally:
                conn.close()

    async def get_all_rules(self) -> List[Dict[str, Any]]:
        """Retrieve all active rules."""
        async with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute("SELECT rule_id, keyword, dm_message, created_at FROM rules")
                return [dict(row) for row in cursor.fetchall()]
            finally:
                conn.close()

    async def process_webhook_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Atomically process incoming webhook payload:
        1. Event deduplication via event_id PRIMARY KEY.
        2. Handle comment.deleted events.
        3. Handle comment.created events with rule matching & (rule_id, user_id) deduplication.
        """
        event_id = event_data.get("event_id")
        event_type = event_data.get("event_type")
        sent_at = event_data.get("sent_at")
        data = event_data.get("data") or {}
        now = time.time()

        if not event_id or not event_type:
            return {"status": "ignored", "reason": "invalid_payload"}

        async with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    # 1. Event Deduplication Check
                    try:
                        comment_id = data.get("comment_id")
                        post_id = data.get("post_id")
                        text = data.get("text")
                        from_user = data.get("from") or {}
                        user_id = from_user.get("user_id") if isinstance(from_user, dict) else None

                        conn.execute(
                            """
                            INSERT INTO events (event_id, event_type, comment_id, post_id, user_id, text, sent_at, received_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (event_id, event_type, comment_id, post_id, user_id, text, sent_at, now)
                        )
                    except sqlite3.IntegrityError:
                        # Event already received and processed -> idempotent ACK
                        return {"status": "duplicate_event", "event_id": event_id}

                    # 2. Handle comment.deleted
                    if event_type == "comment.deleted":
                        if comment_id:
                            conn.execute(
                                "INSERT OR IGNORE INTO deleted_comments (comment_id, deleted_at) VALUES (?, ?)",
                                (comment_id, now)
                            )
                            # Cancel pending queued jobs for this comment if not yet dispatched
                            conn.execute(
                                """
                                UPDATE jobs
                                SET status = 'cancelled_deleted', updated_at = ?
                                WHERE comment_id = ? AND status = 'queued'
                                """,
                                (now, comment_id)
                            )
                        return {"status": "deleted_recorded", "comment_id": comment_id}

                    # 3. Handle comment.created
                    if event_type == "comment.created":
                        if not user_id or not comment_id:
                            return {"status": "ignored", "reason": "missing_identifiers"}

                        # Check if comment was already marked deleted (out-of-order deletion)
                        del_check = conn.execute(
                            "SELECT 1 FROM deleted_comments WHERE comment_id = ?", (comment_id,)
                        ).fetchone()
                        if del_check:
                            return {"status": "already_deleted", "comment_id": comment_id}

                        # Fetch all rules to match text
                        rules_cur = conn.execute("SELECT rule_id, keyword, dm_message FROM rules")
                        rules = rules_cur.fetchall()

                        matched_rules = []
                        for rule in rules:
                            if matches_keyword(rule["keyword"], text):
                                matched_rules.append(rule)

                        if not matched_rules:
                            return {"status": "no_rule_match", "comment_id": comment_id}

                        jobs_created = 0
                        duplicates_blocked = 0

                        for rule in matched_rules:
                            r_id = rule["rule_id"]
                            dm_msg = rule["dm_message"]

                            # Atomic rule + user uniqueness check
                            try:
                                conn.execute(
                                    """
                                    INSERT INTO processed_user_rules (rule_id, user_id, first_comment_id, processed_at)
                                    VALUES (?, ?, ?, ?)
                                    """,
                                    (r_id, user_id, comment_id, now)
                                )
                                # New (rule, user) pair -> create job
                                job_id = f"job_{uuid.uuid4().hex[:16]}"
                                conn.execute(
                                    """
                                    INSERT INTO jobs (job_id, rule_id, user_id, comment_id, message, status, dm_id, retries, next_retry_at, last_error, created_at, updated_at)
                                    VALUES (?, ?, ?, ?, ?, 'queued', NULL, 0, ?, NULL, ?, ?)
                                    """,
                                    (job_id, r_id, user_id, comment_id, dm_msg, now, now, now)
                                )
                                jobs_created += 1
                            except sqlite3.IntegrityError:
                                # Duplicate (rule, user) combination detected!
                                conn.execute(
                                    """
                                    INSERT INTO duplicate_blocks (rule_id, user_id, comment_id, blocked_at)
                                    VALUES (?, ?, ?, ?)
                                    """,
                                    (r_id, user_id, comment_id, now)
                                )
                                duplicates_blocked += 1

                        return {
                            "status": "processed",
                            "jobs_created": jobs_created,
                            "duplicates_blocked": duplicates_blocked
                        }

                    return {"status": "unhandled_event_type"}
            finally:
                conn.close()

    async def get_queued_jobs(self, limit: int = 10, now_ts: Optional[float] = None) -> List[Dict[str, Any]]:
        """Fetch pending/retryable queued jobs."""
        if now_ts is None:
            now_ts = time.time()
        async with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    """
                    SELECT id, job_id, rule_id, user_id, comment_id, message, status, dm_id, retries, next_retry_at, last_error
                    FROM jobs
                    WHERE status = 'queued' AND next_retry_at <= ?
                    ORDER BY created_at ASC
                    LIMIT ?
                    """,
                    (now_ts, limit)
                )
                return [dict(row) for row in cursor.fetchall()]
            finally:
                conn.close()

    async def get_accepted_jobs(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Fetch accepted jobs that need delivery status reconciliation."""
        async with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    """
                    SELECT id, job_id, rule_id, user_id, comment_id, message, status, dm_id, retries, next_retry_at, last_error
                    FROM jobs
                    WHERE status = 'accepted' AND dm_id IS NOT NULL
                    ORDER BY updated_at ASC
                    LIMIT ?
                    """,
                    (limit,)
                )
                return [dict(row) for row in cursor.fetchall()]
            finally:
                conn.close()

    async def is_comment_deleted(self, comment_id: str) -> bool:
        """Check if a comment has been deleted."""
        async with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute("SELECT 1 FROM deleted_comments WHERE comment_id = ?", (comment_id,))
                return cur.fetchone() is not None
            finally:
                conn.close()

    async def update_job(
        self,
        job_id: str,
        status: str,
        dm_id: Optional[str] = None,
        retries: Optional[int] = None,
        next_retry_at: Optional[float] = None,
        last_error: Optional[str] = None
    ):
        """Update job status and retry metadata."""
        now = time.time()
        async with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    fields = ["status = ?", "updated_at = ?"]
                    values = [status, now]

                    if dm_id is not None:
                        fields.append("dm_id = ?")
                        values.append(dm_id)
                    if retries is not None:
                        fields.append("retries = ?")
                        values.append(retries)
                    if next_retry_at is not None:
                        fields.append("next_retry_at = ?")
                        values.append(next_retry_at)
                    if last_error is not None:
                        fields.append("last_error = ?")
                        values.append(last_error)

                    values.append(job_id)
                    query = f"UPDATE jobs SET {', '.join(fields)} WHERE job_id = ?"
                    conn.execute(query, tuple(values))
            finally:
                conn.close()

    async def get_stats(self) -> Dict[str, int]:
        """
        Compute live stats accurately from database state:
        - sent: DMs confirmed delivered by mock API
        - failed: DMs given up after max retries or fatal 400
        - queued: DMs waiting to send, waiting for retry, or accepted and pending reconciliation
        - duplicates_blocked: DMs blocked due to rule+user uniqueness
        """
        async with self._lock:
            conn = self._get_connection()
            try:
                sent_row = conn.execute("SELECT COUNT(*) as cnt FROM jobs WHERE status = 'delivered'").fetchone()
                failed_row = conn.execute("SELECT COUNT(*) as cnt FROM jobs WHERE status = 'failed'").fetchone()
                queued_row = conn.execute("SELECT COUNT(*) as cnt FROM jobs WHERE status IN ('queued', 'accepted')").fetchone()
                dup_row = conn.execute("SELECT COUNT(*) as cnt FROM duplicate_blocks").fetchone()

                return {
                    "sent": sent_row["cnt"] if sent_row else 0,
                    "failed": failed_row["cnt"] if failed_row else 0,
                    "queued": queued_row["cnt"] if queued_row else 0,
                    "duplicates_blocked": dup_row["cnt"] if dup_row else 0
                }
            finally:
                conn.close()

    async def reset(self):
        """Reset database tables for clean testing and simulations."""
        async with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    conn.execute("DELETE FROM jobs;")
                    conn.execute("DELETE FROM duplicate_blocks;")
                    conn.execute("DELETE FROM processed_user_rules;")
                    conn.execute("DELETE FROM deleted_comments;")
                    conn.execute("DELETE FROM events;")
                    conn.execute("DELETE FROM rules;")
            finally:
                conn.close()


# Global database instance
db = Database()

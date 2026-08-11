"""SQLiteAlertCooldownStore — secondary deduplication defense for the
Alert pipeline (TASK-023 Phase G). The PRIMARY defense against repeat
alerts is the advancing snapshot baseline in AlertService (each cycle
compares against the immediately preceding snapshot, so a single price
move is only ever detected once). This store exists only to suppress
*flapping* — the same category of change firing repeatedly in a short
window (e.g. price oscillating across the +3% line).

Mirrors SQLiteSnapshotStore's connection lifecycle exactly: one
connection opened in initialize(), held for the store's lifetime,
plain sqlite3, no ORM.
"""
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from phoenix_core.utils.exceptions import StorageError
from phoenix_core.utils.logger import get_logger

logger = get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS alert_cooldowns (
    symbol TEXT PRIMARY KEY,
    last_change_fingerprint TEXT NOT NULL,
    last_alert_at TEXT NOT NULL
);
"""


def build_fingerprint(change_categories: List[str]) -> str:
    """Build a deterministic fingerprint from change *categories* (e.g.
    "price", "sentiment", "news", "fee") — not their exact values, so the
    same kind of event within the cooldown window is recognized as a
    repeat even if the precise numbers differ slightly."""
    return "|".join(sorted(set(change_categories)))


class SQLiteAlertCooldownStore:
    """Tracks the last alerted fingerprint + timestamp per symbol."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def initialize(self) -> None:
        if self._conn is not None:
            return

        try:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.executescript(_SCHEMA)
            conn.commit()
        except sqlite3.Error as e:
            logger.error(
                "Alert cooldown database initialization failed",
                database_path=self._db_path,
                error_type=type(e).__name__,
            )
            raise StorageError(
                f"Could not open or initialize the alert cooldown SQLite database at '{self._db_path}': {e}"
            ) from e

        self._conn = conn
        logger.info("Alert cooldown database opened", database_path=self._db_path)

    def should_alert(self, symbol: str, change_categories: List[str], cooldown_seconds: float) -> bool:
        """True if an alert for this symbol/fingerprint should be sent now.

        Always True if there is no prior record for `symbol` (never
        suppress a first-ever alert). Always True if the fingerprint
        differs from the last one recorded (a genuinely different kind of
        change is never hidden by an unrelated cooldown). Only False when
        the same fingerprint was alerted within `cooldown_seconds`.
        """
        conn = self._require_conn()
        normalized = symbol.strip().upper()
        fingerprint = build_fingerprint(change_categories)

        row = conn.execute(
            "SELECT last_change_fingerprint, last_alert_at FROM alert_cooldowns WHERE symbol = ?",
            (normalized,),
        ).fetchone()

        if row is None:
            return True

        last_fingerprint, last_alert_at_iso = row
        if fingerprint != last_fingerprint:
            return True

        last_alert_at = datetime.fromisoformat(last_alert_at_iso)
        elapsed = (datetime.now(timezone.utc) - last_alert_at).total_seconds()
        return elapsed >= cooldown_seconds

    def record_alert(self, symbol: str, change_categories: List[str]) -> None:
        """Record that an alert was just sent for `symbol` with this fingerprint."""
        conn = self._require_conn()
        normalized = symbol.strip().upper()
        fingerprint = build_fingerprint(change_categories)
        now_iso = datetime.now(timezone.utc).isoformat()

        conn.execute(
            """
            INSERT INTO alert_cooldowns (symbol, last_change_fingerprint, last_alert_at)
            VALUES (?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                last_change_fingerprint = excluded.last_change_fingerprint,
                last_alert_at = excluded.last_alert_at
            """,
            (normalized, fingerprint, now_iso),
        )
        conn.commit()
        logger.info("Alert cooldown recorded", symbol=normalized, fingerprint=fingerprint)

    def health_check(self) -> Dict[str, Any]:
        try:
            self._require_conn().execute("SELECT 1")
            available = True
        except sqlite3.Error:
            available = False

        return {
            "status": "healthy" if available else "unhealthy",
            "backend": "sqlite",
            "database_available": available,
            "database_path": self._db_path,
        }

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("SQLiteAlertCooldownStore.initialize() must be called before use")
        return self._conn

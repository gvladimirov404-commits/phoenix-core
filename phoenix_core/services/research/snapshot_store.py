"""SQLiteSnapshotStore — stdlib sqlite3-backed storage for the last known
market snapshot per coin symbol (TASK-023 Phase F). Mirrors
phoenix_core.services.watchlist.store.SQLiteWatchlistStore exactly: one
connection opened in initialize() and held for the store's lifetime (so
db_path=":memory:" behaves as a real database for tests), plain sqlite3
(no ORM), all SQL lives here only.

Unlike the watchlist store, this state is global (one row per symbol),
not per-user — market data isn't user-specific. This store only persists
the *last observed* snapshot; it is intentionally silent infrastructure
for now (Phase F) and is not wired into any command yet. Phase G (Alerts)
is expected to be the first caller.
"""
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from phoenix_core.utils.exceptions import StorageError
from phoenix_core.utils.logger import get_logger

logger = get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshot_history (
    symbol TEXT PRIMARY KEY,
    price_usd REAL,
    change_24h_pct REAL,
    fear_greed_value INTEGER,
    fear_greed_classification TEXT,
    top_news_title TEXT,
    fees_fastest_sat_vb REAL,
    captured_at TEXT NOT NULL
);
"""


@dataclass
class SnapshotRecord:
    """The last stored snapshot for one symbol. Any field except `symbol`
    and `captured_at` may be None — a sub-source can be missing on any
    given capture, same as MarketSnapshot itself."""

    symbol: str
    price_usd: Optional[float]
    change_24h_pct: Optional[float]
    fear_greed_value: Optional[int]
    fear_greed_classification: Optional[str]
    top_news_title: Optional[str]
    fees_fastest_sat_vb: Optional[float]
    captured_at: str


class SQLiteSnapshotStore:
    """Raw-SQL sqlite3 store for the last known snapshot per symbol.

    One open connection, held for its lifetime. `save_snapshot` accepts
    any duck-typed object shaped like MarketSnapshot (symbol, market,
    fear_greed, top_news, fees) — it deliberately does not import
    MarketSnapshot itself, mirroring evidence.derive_evidence()'s
    duck-typing so this module has no hard dependency on the intel
    aggregator's internals.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        """Create a store for `db_path` (not yet connected — call initialize())."""
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def initialize(self) -> None:
        """Open the connection (creating the file automatically if needed) and ensure schema exists.

        Raises:
            StorageError: If `db_path` exists but isn't a valid SQLite
                database, or schema creation otherwise fails — callers are
                expected to catch this and degrade (same contract as
                SQLiteWatchlistStore.initialize()).
        """
        if self._conn is not None:
            return  # already initialized — idempotent

        try:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.executescript(_SCHEMA)
            conn.commit()
        except sqlite3.Error as e:
            logger.error(
                "Snapshot database initialization failed",
                database_path=self._db_path,
                error_type=type(e).__name__,
            )
            raise StorageError(
                f"Could not open or initialize the snapshot SQLite database at '{self._db_path}': {e}"
            ) from e

        self._conn = conn
        logger.info("Snapshot database opened", database_path=self._db_path)

    def get_latest(self, symbol: str) -> Optional[SnapshotRecord]:
        """Return the last stored snapshot for `symbol`, or None if never captured."""
        conn = self._require_conn()
        normalized = symbol.strip().upper()
        row = conn.execute(
            "SELECT symbol, price_usd, change_24h_pct, fear_greed_value, "
            "fear_greed_classification, top_news_title, fees_fastest_sat_vb, captured_at "
            "FROM snapshot_history WHERE symbol = ?",
            (normalized,),
        ).fetchone()
        if row is None:
            return None
        return SnapshotRecord(
            symbol=row[0],
            price_usd=row[1],
            change_24h_pct=row[2],
            fear_greed_value=row[3],
            fear_greed_classification=row[4],
            top_news_title=row[5],
            fees_fastest_sat_vb=row[6],
            captured_at=row[7],
        )

    def save_snapshot(self, snapshot: Any) -> None:
        """Insert or update (upsert) the stored snapshot for `snapshot.symbol`.

        Accepts anything shaped like a MarketSnapshot: a `.symbol` string
        plus optional `.market` (.price_usd, .change_24h_pct),
        `.fear_greed` (.value, .classification), `.top_news` (.title),
        and `.fees` (.fastest_sat_vb) — any of which may be None.
        """
        conn = self._require_conn()

        market = snapshot.market
        fear_greed = snapshot.fear_greed
        top_news = snapshot.top_news
        fees = snapshot.fees

        price_usd = market.price_usd if market is not None else None
        change_24h_pct = market.change_24h_pct if market is not None else None
        fear_greed_value = fear_greed.value if fear_greed is not None else None
        fear_greed_classification = fear_greed.classification if fear_greed is not None else None
        top_news_title = top_news.title if top_news is not None else None
        fees_fastest_sat_vb = fees.fastest_sat_vb if fees is not None else None
        captured_at = datetime.now(timezone.utc).isoformat()
        normalized_symbol = snapshot.symbol.strip().upper()

        conn.execute(
            """
            INSERT INTO snapshot_history
                (symbol, price_usd, change_24h_pct, fear_greed_value,
                 fear_greed_classification, top_news_title, fees_fastest_sat_vb, captured_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                price_usd = excluded.price_usd,
                change_24h_pct = excluded.change_24h_pct,
                fear_greed_value = excluded.fear_greed_value,
                fear_greed_classification = excluded.fear_greed_classification,
                top_news_title = excluded.top_news_title,
                fees_fastest_sat_vb = excluded.fees_fastest_sat_vb,
                captured_at = excluded.captured_at
            """,
            (
                normalized_symbol,
                price_usd,
                change_24h_pct,
                fear_greed_value,
                fear_greed_classification,
                top_news_title,
                fees_fastest_sat_vb,
                captured_at,
            ),
        )
        conn.commit()
        logger.info("Snapshot stored", symbol=normalized_symbol)

    def count_tracked_symbols(self) -> int:
        conn = self._require_conn()
        (count,) = conn.execute("SELECT COUNT(*) FROM snapshot_history").fetchone()
        return count

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
            "tracked_symbols": self.count_tracked_symbols() if available else 0,
        }

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __del__(self) -> None:
        """Safety-net finalizer — see SQLiteWatchlistStore.__del__ for the rationale."""
        try:
            self.close()
        except Exception:
            pass

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("SQLiteSnapshotStore.initialize() must be called before use")
        return self._conn

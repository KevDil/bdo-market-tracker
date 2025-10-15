import sqlite3
import threading
from datetime import datetime, timedelta
from config import DB_PATH

# -----------------------
# DB initialisieren
# -----------------------
_base_conn = sqlite3.connect(DB_PATH, check_same_thread=False,
                       detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
_base_cur = _base_conn.cursor()
_base_cur.execute("""
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_name TEXT,
    quantity INTEGER,
    price REAL,          -- total price for the whole quantity
    transaction_type TEXT,
    timestamp DATETIME,
    tx_case TEXT,
    occurrence_index INTEGER DEFAULT 0,
    content_hash TEXT
)
""")
# Migration: ensure 'tx_case' column exists; if legacy 'case' exists, rename it
try:
    _base_cur.execute("PRAGMA table_info(transactions)")
    cols = [r[1] for r in _base_cur.fetchall()]
    if 'tx_case' not in cols:
        if 'case' in cols:
            # try to rename legacy column 'case' -> 'tx_case'
            try:
                _base_cur.execute("ALTER TABLE transactions RENAME COLUMN \"case\" TO tx_case")
            except Exception:
                # if rename not supported, add new column
                _base_cur.execute("ALTER TABLE transactions ADD COLUMN tx_case TEXT")
        else:
            _base_cur.execute("ALTER TABLE transactions ADD COLUMN tx_case TEXT")
    if 'occurrence_index' not in cols:
        try:
            _base_cur.execute("ALTER TABLE transactions ADD COLUMN occurrence_index INTEGER DEFAULT 0")
        except Exception:
            pass
    if 'content_hash' not in cols:
        try:
            _base_cur.execute("ALTER TABLE transactions ADD COLUMN content_hash TEXT")
        except Exception:
            pass
except Exception:
    pass
try:
    _base_cur.execute("DROP INDEX IF EXISTS idx_unique_tx_full")
except Exception:
    pass
_base_cur.execute("""
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_tx_full
ON transactions(item_name, quantity, price, transaction_type, timestamp, occurrence_index, content_hash)
""")

# Performance: Additional indexes for common queries (30-40% faster filtering)
_base_cur.execute("""
CREATE INDEX IF NOT EXISTS idx_item_name 
ON transactions(item_name)
""")

_base_cur.execute("""
CREATE INDEX IF NOT EXISTS idx_timestamp 
ON transactions(timestamp DESC)
""")

_base_cur.execute("""
CREATE INDEX IF NOT EXISTS idx_transaction_type 
ON transactions(transaction_type)
""")

# Composite index for delta detection (faster baseline checks)
_base_cur.execute("""
CREATE INDEX IF NOT EXISTS idx_delta_detection 
ON transactions(item_name, timestamp, transaction_type)
""")

# State table for persistent tracker state (baseline, last processed timestamp, etc.)
_base_cur.execute("""
CREATE TABLE IF NOT EXISTS tracker_state (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

# Store tracker settings in dedicated table
_base_cur.execute(
    """
    CREATE TABLE IF NOT EXISTS tracker_settings (
        key TEXT PRIMARY KEY,
        value TEXT,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """
)

_base_conn.commit()

# Thread-local connections
_local = threading.local()

def get_connection():
    conn = getattr(_local, 'conn', None)
    if conn is None:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False,
                       detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
        setattr(_local, 'conn', conn)
    return conn

def get_cursor():
    return get_connection().cursor()

# keep names for backward compat in simple usages
conn = _base_conn
cur = _base_cur

# Utility: update timestamp to earlier game time when same tx (item,qty,price,type,occurrence) is detected later
def update_tx_timestamp_if_earlier(item_name: str, quantity: int, price: int, ttype: str, new_ts, occurrence_index: int | None = None):
    try:
        conn = get_connection()
        c = conn.cursor()
        query = (
            """
            SELECT id, timestamp FROM transactions
            WHERE item_name = ? AND quantity = ? AND price = ? AND transaction_type = ?
            """
        )
        params = [item_name, int(quantity), int(price), ttype]
        if occurrence_index is not None:
            query += " AND occurrence_index = ?"
            params.append(int(occurrence_index))
        query += " ORDER BY timestamp DESC LIMIT 1"
        c.execute(query, params)
        row = c.fetchone()
        if not row:
            return False
        tx_id, existing_ts = row
        # Only update if the new game timestamp is earlier than the stored one
        try:
            # existing_ts may be string or datetime depending on adapter; normalize to string comparison via ISO
            from datetime import datetime
            if isinstance(existing_ts, str):
                try:
                    existing_dt = datetime.fromisoformat(existing_ts)
                except Exception:
                    existing_dt = None
            else:
                existing_dt = existing_ts
            if hasattr(new_ts, 'strftime'):
                new_dt = new_ts
            else:
                # try best-effort parse
                new_dt = datetime.fromisoformat(str(new_ts))
            if existing_dt and new_dt and new_dt < existing_dt:
                c.execute("UPDATE transactions SET timestamp = ? WHERE id = ?", (new_dt.strftime("%Y-%m-%d %H:%M:%S"), tx_id))
                conn.commit()
                return True
        except Exception:
            return False
    except Exception:
        return False

# Utility functions for persistent state
def save_state(key: str, value: str):
    """Save a key-value pair to persistent state"""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO tracker_state (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """, (key, value))
        conn.commit()
    except Exception as e:
        print(f"Error saving state {key}: {e}")

def load_state(key: str, default=None):
    """Load a value from persistent state"""
    try:
        c = get_cursor()
        c.execute("SELECT value FROM tracker_state WHERE key = ?", (key,))
        row = c.fetchone()
        return row[0] if row else default
    except Exception as e:
        print(f"Error loading state {key}: {e}")
        return default

# Utility: find an existing transaction row by (item_name, quantity, price, transaction_type), optional timestamp/occurrence filter
def find_existing_tx_by_values(item_name: str, quantity: int, price: int, ttype: str, timestamp=None, occurrence_index: int | None = None):
    try:
        c = get_cursor()
        query = (
            """
            SELECT id, timestamp, occurrence_index FROM transactions
            WHERE item_name = ? AND quantity = ? AND price = ? AND transaction_type = ?
            """
        )
        params = [item_name, int(quantity), int(price), ttype]
        if timestamp is not None:
            if hasattr(timestamp, 'strftime'):
                ts_val = timestamp.strftime("%Y-%m-%d %H:%M:%S")
            else:
                ts_val = str(timestamp)
            query += " AND timestamp = ?"
            params.append(ts_val)
        if occurrence_index is not None:
            query += " AND occurrence_index = ?"
            params.append(int(occurrence_index))
        query += " ORDER BY timestamp ASC LIMIT 1"
        c.execute(query, params)
        return c.fetchone()  # (id, timestamp, occurrence_index) or None
    except Exception:
        return None

# Utility: check if a transaction already exists for an item+type around a specific timestamp
def transaction_exists_by_item_timestamp(item_name: str, timestamp, ttype: str, tolerance_seconds: int = 0) -> bool:
    try:
        if timestamp is None:
            return False
        if not isinstance(timestamp, datetime):
            try:
                timestamp = datetime.fromisoformat(str(timestamp))
            except Exception:
                return False
        conn = get_connection()
        c = conn.cursor()
        if tolerance_seconds and tolerance_seconds > 0:
            start_ts = timestamp - timedelta(seconds=tolerance_seconds)
            end_ts = timestamp + timedelta(seconds=tolerance_seconds)
            c.execute(
                """
                SELECT 1 FROM transactions
                WHERE item_name = ? AND transaction_type = ? AND timestamp BETWEEN ? AND ?
                LIMIT 1
                """,
                (item_name, ttype, start_ts.strftime("%Y-%m-%d %H:%M:%S"), end_ts.strftime("%Y-%m-%d %H:%M:%S"))
            )
        else:
            c.execute(
                """
                SELECT 1 FROM transactions
                WHERE item_name = ? AND transaction_type = ? AND timestamp = ?
                LIMIT 1
                """,
                (item_name, ttype, timestamp.strftime("%Y-%m-%d %H:%M:%S"))
            )
        return c.fetchone() is not None
    except Exception:
        return False


def fetch_occurrence_indices(item_name: str, quantity: int, price: int, ttype: str, timestamp) -> list[int]:
    try:
        if not isinstance(timestamp, datetime):
            try:
                timestamp = datetime.fromisoformat(str(timestamp))
            except Exception:
                return []
        c = get_cursor()
        c.execute(
            """
            SELECT occurrence_index FROM transactions
            WHERE item_name = ? AND quantity = ? AND price = ? AND transaction_type = ? AND timestamp = ?
            ORDER BY occurrence_index ASC
            """,
            (item_name, int(quantity), int(price), ttype, timestamp.strftime("%Y-%m-%d %H:%M:%S"))
        )
        rows = c.fetchall()
        return [int(r[0]) for r in rows if r and r[0] is not None]
    except Exception:
        return []


def transaction_exists_exact(item_name: str, quantity: int, price: int, ttype: str, timestamp, occurrence_index: int) -> bool:
    try:
        if hasattr(timestamp, 'strftime'):
            ts_val = timestamp.strftime("%Y-%m-%d %H:%M:%S")
        else:
            ts_val = str(timestamp)
        c = get_cursor()
        c.execute(
            """
            SELECT 1 FROM transactions
            WHERE item_name = ? AND quantity = ? AND price = ? AND transaction_type = ? AND timestamp = ? AND occurrence_index = ?
            LIMIT 1
            """,
            (item_name, int(quantity), int(price), ttype, ts_val, int(occurrence_index))
        )
        return c.fetchone() is not None
    except Exception:
        return False


def transaction_exists_any_side(item_name: str, quantity: int, price: int, timestamp) -> bool:
    """Check whether an entry exists for the same item/qty/price/timestamp regardless of buy/sell classification."""
    try:
        if hasattr(timestamp, 'strftime'):
            ts_val = timestamp.strftime("%Y-%m-%d %H:%M:%S")
        else:
            ts_val = str(timestamp)
        c = get_cursor()
        c.execute(
            """
            SELECT 1 FROM transactions
            WHERE item_name = ? AND quantity = ? AND price = ? AND timestamp = ?
            LIMIT 1
            """,
            (item_name, int(quantity), int(price), ts_val)
        )
        return c.fetchone() is not None
    except Exception:
        return False


def transaction_exists_by_values_near_time(item_name: str, quantity: int, price: int, timestamp, tolerance_minutes: int = 2) -> bool:
    """Check whether a transaction exists with same item/qty/price within a time tolerance.
    
    CRITICAL: Used to prevent duplicates when OCR gives wrong timestamp.
    
    Args:
        tolerance_minutes: Time window in minutes to check for duplicates (default 2 minutes)
    
    Example:
        - Transaction exists at 22:26 with Magical Shard 200x @ 546M
        - New scan at 22:42 with same values but different timestamp (OCR error)
        - If within tolerance (e.g., 2 min): DUPLICATE (skip)
        - If outside tolerance (e.g., 20 min): DIFFERENT TRANSACTION (save)
    
    This allows:
        - Filtering out OCR-induced duplicates (seconds/minutes apart)
        - Saving legitimate repeat purchases (hours/days apart)
    """
    try:
        if not isinstance(timestamp, datetime):
            try:
                timestamp = datetime.fromisoformat(str(timestamp))
            except Exception:
                return False
        
        start_time = timestamp - timedelta(minutes=tolerance_minutes)
        end_time = timestamp + timedelta(minutes=tolerance_minutes)
        
        c = get_cursor()
        c.execute(
            """
            SELECT timestamp FROM transactions
            WHERE item_name = ? AND quantity = ? AND price = ?
              AND timestamp BETWEEN ? AND ?
            LIMIT 1
            """,
            (item_name, int(quantity), int(price), 
             start_time.strftime("%Y-%m-%d %H:%M:%S"), 
             end_time.strftime("%Y-%m-%d %H:%M:%S"))
        )
        return c.fetchone() is not None
    except Exception:
        return False

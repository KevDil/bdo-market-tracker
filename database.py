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

# Item presets table for filter presets (e.g., "Harmony Draught" materials)
_base_cur.execute(
    """
    CREATE TABLE IF NOT EXISTS item_presets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        items TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """
)

# Preorder tracking table (NEW)
_base_cur.execute("""
CREATE TABLE IF NOT EXISTS preorders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_name TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    quantity_filled INTEGER DEFAULT 0,
    price REAL NOT NULL,
    timestamp DATETIME NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    collected_at DATETIME,
    collected_tx_id INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

# Migration: Add quantity_filled column if missing
try:
    _base_cur.execute("PRAGMA table_info(preorders)")
    cols = [r[1] for r in _base_cur.fetchall()]
    if 'quantity_filled' not in cols:
        _base_cur.execute("ALTER TABLE preorders ADD COLUMN quantity_filled INTEGER DEFAULT 0")
except Exception:
    pass

# Indexes for fast preorder lookup
_base_cur.execute("""
CREATE INDEX IF NOT EXISTS idx_preorders_item_status 
ON preorders(item_name, status)
""")

_base_cur.execute("""
CREATE INDEX IF NOT EXISTS idx_preorders_timestamp 
ON preorders(timestamp DESC)
""")

_base_cur.execute("""
CREATE INDEX IF NOT EXISTS idx_preorders_status 
ON preorders(status)
""")

# CRITICAL: Unique constraint to enforce ONE active preorder per item
_base_cur.execute("""
CREATE UNIQUE INDEX IF NOT EXISTS idx_preorders_one_active_per_item
ON preorders(item_name)
WHERE status = 'active'
""")

# Listing tracking table (NEW - analog to preorders for sell-side)
_base_cur.execute("""
CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_name TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    quantity_sold INTEGER DEFAULT 0,
    price REAL NOT NULL,
    timestamp DATETIME NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    collected_at DATETIME,
    collected_tx_id INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

# Migration: Add quantity_sold column if missing
try:
    _base_cur.execute("PRAGMA table_info(listings)")
    cols = [r[1] for r in _base_cur.fetchall()]
    if 'quantity_sold' not in cols:
        _base_cur.execute("ALTER TABLE listings ADD COLUMN quantity_sold INTEGER DEFAULT 0")
except Exception:
    pass

# Indexes for fast listing lookup
_base_cur.execute("""
CREATE INDEX IF NOT EXISTS idx_listings_item_status 
ON listings(item_name, status)
""")

_base_cur.execute("""
CREATE INDEX IF NOT EXISTS idx_listings_timestamp 
ON listings(timestamp DESC)
""")

_base_cur.execute("""
CREATE INDEX IF NOT EXISTS idx_listings_status 
ON listings(status)
""")

# CRITICAL: Unique constraint to enforce ONE active listing per item
_base_cur.execute("""
CREATE UNIQUE INDEX IF NOT EXISTS idx_listings_one_active_per_item
ON listings(item_name)
WHERE status = 'active'
""")

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


# -----------------------
# PERFORMANCE V6: Batch Insert (2025-10-22)
# -----------------------
# Provides 5-11x speedup when inserting multiple transactions from a single scan.
# Uses executemany() instead of individual execute() calls.
# Typical use case: Collecting 5+ items at once from buy/sell overview.
def store_transactions_batch(transactions: list[dict]) -> int:
    """
    Store multiple transactions in a single batch for 5-11x faster writes.
    
    Args:
        transactions: List of transaction dicts with keys:
            - item_name (str)
            - quantity (int)
            - price (float/int)
            - transaction_type (str)
            - timestamp (datetime or str)
            - tx_case (str)
            - occurrence_index (int, default=0)
            - content_hash (str)
    
    Returns:
        Number of rows inserted (may be less than len(transactions) due to duplicates)
    """
    if not transactions:
        return 0
    
    conn = get_connection()
    cur = conn.cursor()
    
    # Prepare rows for executemany
    rows = []
    for tx in transactions:
        # Normalize timestamp to string
        timestamp = tx.get('timestamp')
        if hasattr(timestamp, 'strftime'):
            ts_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
        else:
            ts_str = str(timestamp)
        
        rows.append((
            tx.get('item_name'),
            int(tx.get('quantity', 0)),
            float(tx.get('price', 0.0)),
            tx.get('transaction_type'),
            ts_str,
            tx.get('tx_case'),
            int(tx.get('occurrence_index', 0)),
            tx.get('content_hash')
        ))
    
    # Batch insert with INSERT OR IGNORE (skips duplicates)
    cur.executemany("""
        INSERT OR IGNORE INTO transactions 
        (item_name, quantity, price, transaction_type, timestamp, tx_case, occurrence_index, content_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    
    inserted_count = cur.rowcount
    conn.commit()
    
    return inserted_count


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


def transaction_exists_by_values_near_time(item_name: str, quantity: int, price: int, timestamp, tolerance_minutes: int = 2, ignore_quantity: bool = False) -> bool:
    """Check whether a transaction exists with same item/qty/price within a time tolerance.
    
    Args:
        tolerance_minutes: Time window in minutes to check for duplicates (default 2 minutes)
        ignore_quantity: When True, match only on item + price within the tolerance window. Useful for
            UI-inferred entries where quantity may fluctuate slightly but the price indicates duplication.
    
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
        if ignore_quantity:
            c.execute(
                """
                SELECT timestamp FROM transactions
                WHERE item_name = ? AND price = ?
                  AND timestamp BETWEEN ? AND ?
                LIMIT 1
                """,
                (item_name, int(price),
                 start_time.strftime("%Y-%m-%d %H:%M:%S"),
                 end_time.strftime("%Y-%m-%d %H:%M:%S"))
            )
        else:
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


# -----------------------
# Item Presets Management
# -----------------------

def get_all_presets() -> list[dict[str, any]]:
    """Retrieve all item presets from the database.
    
    Returns:
        List of dicts with keys: id, name, items (list), created_at, updated_at
    """
    try:
        import json
        c = get_cursor()
        c.execute("""
            SELECT id, name, items, created_at, updated_at 
            FROM item_presets 
            ORDER BY name ASC
        """)
        rows = c.fetchall()
        result = []
        for row in rows:
            preset_id, name, items_json, created_at, updated_at = row
            try:
                items_list = json.loads(items_json)
            except Exception:
                items_list = []
            result.append({
                'id': preset_id,
                'name': name,
                'items': items_list,
                'created_at': created_at,
                'updated_at': updated_at
            })
        return result
    except Exception as e:
        print(f"Error loading presets: {e}")
        return []


def get_preset_by_name(name: str) -> dict[str, any] | None:
    """Retrieve a single preset by name.
    
    Args:
        name: The preset name
        
    Returns:
        Dict with keys: id, name, items (list), created_at, updated_at, or None if not found
    """
    try:
        import json
        c = get_cursor()
        c.execute("""
            SELECT id, name, items, created_at, updated_at 
            FROM item_presets 
            WHERE name = ?
        """, (name,))
        row = c.fetchone()
        if not row:
            return None
        preset_id, name, items_json, created_at, updated_at = row
        try:
            items_list = json.loads(items_json)
        except Exception:
            items_list = []
        return {
            'id': preset_id,
            'name': name,
            'items': items_list,
            'created_at': created_at,
            'updated_at': updated_at
        }
    except Exception as e:
        print(f"Error loading preset '{name}': {e}")
        return None


def save_preset(name: str, items: list[str]) -> bool:
    """Create or update an item preset.
    
    Args:
        name: The preset name (unique identifier)
        items: List of item names to include in the preset
        
    Returns:
        True if successful, False otherwise
    """
    try:
        import json
        items_json = json.dumps(items, ensure_ascii=False)
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO item_presets (name, items, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """, (name, items_json))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error saving preset '{name}': {e}")
        return False


def delete_preset(name: str) -> bool:
    """Delete an item preset by name.
    
    Args:
        name: The preset name to delete
        
    Returns:
        True if successful, False otherwise
    """
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("DELETE FROM item_presets WHERE name = ?", (name,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error deleting preset '{name}': {e}")
        return False


def get_transactions_by_preset(preset_name: str, start_date: str, end_date: str) -> list[tuple]:
    """Retrieve transactions filtered by items in a preset.
    
    Args:
        preset_name: Name of the preset to use for filtering
        start_date: Start date (YYYY-MM-DD format)
        end_date: End date (YYYY-MM-DD format)
        
    Returns:
        List of transaction tuples
    """
    try:
        preset = get_preset_by_name(preset_name)
        if not preset or not preset['items']:
            return []
        
        items = preset['items']
        c = get_cursor()
        
        # Build IN clause with placeholders
        placeholders = ','.join('?' * len(items))
        query = f"""
            SELECT * FROM transactions 
            WHERE timestamp BETWEEN ? AND ?
            AND item_name IN ({placeholders})
            ORDER BY timestamp DESC
        """
        
        params = [f"{start_date} 00:00:00", f"{end_date} 23:59:59"] + items
        c.execute(query, params)
        return c.fetchall()
    except Exception as e:
        print(f"Error querying transactions by preset '{preset_name}': {e}")
        return []


def initialize_default_presets():
    """Create default presets if they don't exist yet.
    
    This function is called on database initialization to seed the presets table
    with useful default configurations.
    """
    # Check if "Harmony Draught" preset already exists
    if get_preset_by_name("Harmony Draught") is not None:
        return
    
    # Harmony Draught preset: All items related to crafting and selling Harmony Draught elixirs
    harmony_draught_items = [
        # All Harmony Draught variants
        "Harmony Draught",
        "[Party] Harmony Draught - Human",
        "[Party] Harmony Draught - Demihuman",
        "[Party] Harmony Draught - Kamasylvia",
        "[Party] Harmony Draught - Edania",
        "[Party] Immortal: Harmony Draught - Human",
        
        # All Elixirs (commonly used/traded alongside Harmony Draughts)
        "Brutal Death Elixir",
        "Defense Elixir",
        "Elixir of Advanced Concentration",
        "Elixir of Agile Spells",
        "Elixir of Assassination",
        "Elixir of Brutal Carnage",
        "Elixir of Brutal Perforation",
        "Elixir of Carnage",
        "Elixir of Concentration",
        "Elixir of Death",
        "Elixir of Destruction",
        "Elixir of Detection",
        "Elixir of Draining",
        "Elixir of Edania",
        "Elixir of Endless Frenzy",
        "Elixir of Endurance",
        "Elixir of Flowing Wind",
        "Elixir of Frenzy",
        "Elixir of Intrepid Swiftness",
        "Elixir of Lethal Assassin", 
        "Elixir of Lethal Destruction",
        "Elixir of Life",
        "Elixir of Overwhelming Endurance",
        "Elixir of Perforation",
        "Elixir of Sharp Detection",
        "Elixir of Shock",
        "Elixir of Sky",
        "Elixir of Spells",
        "Elixir of Steel Defense",
        "Elixir of Strong Draining",
        "Elixir of Strong Life",
        "Elixir of Strong Shock",
        "Elixir of Swiftness",
        "Elixir of Remarkable Will",
        "Elixir of Will",
        "Elixir of Wind",
        "Grim Reaper's Elixir",
        "Grim Soul Reaper's Elixir",
        "Helix Elixir",
        "Merciless Sky Elixir",
        "Splendid Helix Elixir",
        "Strong Elixir of Edania",
        
        # Crafting materials (mushrooms, saps, powders, etc.)
        "Arrow Mushroom",
        "Ash Sap",
        "Birch Sap",
        "Black Stone Powder",
        "Bloody Tree Knot",
        "Caphras Tree Sap",
        "Cedar Sap",
        "Clear Liquid Reagent",
        "Cloud Mushroom",
        "Clown's Blood",
        "Dwarf Mushroom",
        "Emperor Mushroom",
        "Fir Sap",
        "Fire Flake Flower",
        "Fortune Teller Mushroom",
        "Fox Blood",
        "Ghost Mushroom",
        "HP Potion (Small)",
        "Ibellab's Essence",
        "Legendary Beast's Blood",
        "Lion Blood",
        "Maple Sap",
        "Monk's Branch",
        "Oil of Corruption",
        "Oil of Fortitude",
        "Oil of Regeneration",
        "Oil of Storms",
        "Oil of Tranquility",
        "Old Tree Bark",
        "Pig Blood",
        "Pine Sap",
        "Powder of Darkness",
        "Powder of Flame",
        "Powder of Time",
        "Pure Powder Reagent",
        "Purified Water",
        "Red Tree Lump",
        "Rhino Blood",
        "Silver Azalea",
        "Sinner's Blood",
        "Sky Mushroom",
        "Snowfield Cedar Sap",
        "Special Amanita Mushroom",
        "Special Ancient Mushroom",
        "Special Bluffer Mushroom",
        "Special Hump Mushroom",
        "Spellbound Catalyst",
        "Spirit's Leaf",
        "Sunrise Herb",
        "Thuja Sap",
        "Tiger Mushroom",
        "Trace of Nature",
        "Truffle Mushroom",
        "Tyrant's Blood",
        "Wild Grass",
        "Wise Man's Blood",
    ]
    
    save_preset("Harmony Draught", harmony_draught_items)
    print("[DB] Initialized default preset: 'Harmony Draught'")


# Initialize default presets on module load
try:
    initialize_default_presets()
except Exception as e:
    print(f"[WARNING] Could not initialize default presets: {e}")


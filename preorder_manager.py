"""
Order Manager Module (Preorders & Listings)
Handles storage, retrieval, and matching of preorder (buy-side) and listing (sell-side) data.

This module implements the complete order lifecycle for BOTH sides:
- BUY-SIDE: Preorders (placed buy orders waiting to be filled)
- SELL-SIDE: Listings (listed items waiting to be sold)

Key Features:
- ONE active preorder/listing per item (enforced by DB unique constraint)
- Auto-collection on order replacement
- Partial fill support (quantity_filled/quantity_sold tracking)
- In-memory caching for performance (< 5ms lookup)
- No expiration (orders remain active indefinitely)
"""

import sqlite3
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
from database import get_cursor, get_connection
from utils import log_debug


class PreorderManager:
    """
    Manages order lifecycle for BOTH buy-side (preorders) and sell-side (listings):
    
    BUY-SIDE (Preorders):
    1. Store preorder when user places order
    2. Retrieve matching preorders for auto-collect detection
    3. Mark preorders as collected after successful transaction
    
    SELL-SIDE (Listings):
    1. Store listing when user lists items for sale
    2. Retrieve matching listings when items are sold
    3. Mark listings as collected after successful transaction
    
    Both sides work analogously with the same API.
    """
    
    def __init__(self, debug: bool = False):
        self.debug = debug
        # In-memory cache of active preorders (refreshed on demand)
        self._active_preorders_cache: Optional[List[Dict]] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl = timedelta(seconds=60)  # Refresh cache every 60s
        
        # In-memory cache of active listings (sell-side analog)
        self._active_listings_cache: Optional[List[Dict]] = None
        self._listings_cache_timestamp: Optional[datetime] = None
    
    # === Storage Operations ===
    
    def store_preorder(
        self,
        item_name: str,
        quantity: int,
        price: float,
        timestamp: datetime
    ) -> int:
        """
        Store a new preorder in the database.
        
        CRITICAL: Only ONE active preorder per item allowed!
        If an active preorder already exists for this item:
        1. Mark old preorder as 'collected' (auto-collected on replacement)
        2. Store new preorder
        
        Args:
            item_name: Corrected item name (after market_json_manager)
            quantity: Quantity of the preorder
            price: Total price paid for the preorder
            timestamp: Game timestamp when order was placed
            
        Returns:
            Preorder ID (database primary key)
        """
        try:
            cur = get_cursor()
            
            # Check for existing active preorder for this item
            cur.execute(
                """
                SELECT id, quantity, quantity_filled, price
                FROM preorders
                WHERE item_name = ? AND status = 'active'
                """,
                (item_name,)
            )
            existing = cur.fetchone()
            
            if existing:
                old_id, old_qty, old_filled, old_price = existing
                # Mark old preorder as collected (auto-collected on replacement)
                # This includes any partial fills
                cur.execute(
                    """
                    UPDATE preorders
                    SET status = 'collected',
                        collected_at = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (timestamp, old_id)
                )
                
                if self.debug:
                    fill_info = f", filled={old_filled}" if old_filled > 0 else ""
                    log_debug(
                        f"[PREORDER] Auto-collected old preorder on replacement: "
                        f"{item_name} x{old_qty}{fill_info} @ {old_price:,.0f} (ID: {old_id})"
                    )
            
            # Store new preorder
            cur.execute(
                """
                INSERT INTO preorders 
                (item_name, quantity, price, timestamp, status)
                VALUES (?, ?, ?, ?, 'active')
                """,
                (item_name, quantity, price, timestamp)
            )
            get_connection().commit()
            preorder_id = cur.lastrowid
            
            # Invalidate cache
            self._active_preorders_cache = None
            
            if self.debug:
                log_debug(
                    f"[PREORDER] Stored: {item_name} x{quantity} @ "
                    f"{price:,.0f} Silver (ID: {preorder_id}, TS: {timestamp})"
                )
            
            return preorder_id
        
        except Exception as e:
            if self.debug:
                log_debug(f"[PREORDER] ERROR storing preorder: {e}")
            return -1

    def record_legacy_preorder(
        self,
        item_name: str,
        quantity: int,
        price: float,
        collected_at: datetime,
        status: str = 'collected',
    ) -> Optional[int]:
        """Persistiert historische Preorders ohne aktive ID."""
        try:
            cur = get_cursor()
            cur.execute(
                """
                INSERT INTO preorders (
                    item_name,
                    quantity,
                    quantity_filled,
                    price,
                    timestamp,
                    status,
                    collected_at,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    item_name,
                    quantity,
                    quantity,
                    price,
                    collected_at,
                    status,
                    collected_at,
                ),
            )
            get_connection().commit()
            legacy_id = cur.lastrowid
            if self.debug:
                log_debug(
                    f"[PREORDER] Recorded legacy preorder: {item_name} x{quantity} @ {price:,.0f} (status={status})"
                )
            return legacy_id
        except Exception as exc:
            if self.debug:
                log_debug(f"[PREORDER] ERROR recording legacy preorder: {exc}")
            return None

    # === Retrieval Operations ===
    
    def find_matching_preorder(
        self,
        item_name: str,
        warehouse_delta: int,
        balance_delta: float,
        timestamp: datetime
    ) -> Optional[Dict]:
        """
        Find a matching active preorder for auto-collect detection.
        
        Matching Logic:
        1. Item name must match (exact, case-insensitive)
        2. Status must be 'active'
        3. Quantity consistent with warehouse_delta surplus
        
        NOTE: No time tolerance needed - preorders never expire!
              Only ONE active preorder per item possible.
        
        Args:
            item_name: Item being purchased (from baseline)
            warehouse_delta: Warehouse increase (may include preorder qty)
            balance_delta: Balance decrease (purchase price only)
            timestamp: Current transaction timestamp (for logging only)
            
        Returns:
            Dict with preorder data, or None if no match found
            Keys: id, item_name, quantity, quantity_filled, price, timestamp
        """
        try:
            # Refresh cache if stale
            self._refresh_cache_if_needed()
            
            if not self._active_preorders_cache:
                return None
            
            # Filter by item name (case-insensitive)
            item_lower = item_name.lower()
            candidates = [
                po for po in self._active_preorders_cache
                if po['item_name'].lower() == item_lower
            ]
            
            if not candidates:
                return None
            
            # With ONE active preorder per item, we should have at most 1 candidate
            if len(candidates) > 1:
                if self.debug:
                    log_debug(
                        f"[PREORDER] WARNING: Multiple active preorders for '{item_name}' "
                        f"(should not happen with unique constraint!)"
                    )
            
            # Take the first (and should be only) candidate
            candidate = candidates[0]
            
            # Check if there's any filled quantity to collect
            quantity_filled = candidate.get('quantity_filled', 0) or 0

            # Berechne erwartete Auto-Collect-Summe für gefüllte Mengen
            expected_autocollect_total = None
            try:
                if candidate['quantity'] > 0 and quantity_filled > 0:
                    unit_price = candidate['price'] / candidate['quantity']
                    expected_autocollect_total = unit_price * quantity_filled
            except Exception:
                expected_autocollect_total = None

            # Validate quantity alignment
            # For partial fills: wir sammeln die gefüllte Menge ein
            if quantity_filled > 0:
                if warehouse_delta >= quantity_filled:
                    if self.debug:
                        log_debug(
                            f"[PREORDER] Match found (partial fill): {candidate['item_name']} "
                            f"x{candidate['quantity']} (filled={quantity_filled}) @ {candidate['price']:,.0f} "
                            f"(ID: {candidate['id']})"
                        )
                    return candidate

                # Sonderfall: warehouse_delta == 0 (Detail-OCR hat Lager nicht gelesen)
                # Prüfe ob balance_delta dem erwarteten Auto-Collect entspricht (mit Toleranz)
                if warehouse_delta == 0 and expected_autocollect_total is not None and balance_delta:
                    spent = abs(balance_delta)
                    tolerance = max(expected_autocollect_total * 0.02, 1000)  # 2% oder mindestens 1k Silver
                    if abs(spent - expected_autocollect_total) <= tolerance:
                        if self.debug:
                            log_debug(
                                f"[PREORDER] Match via balance delta: {candidate['item_name']} "
                                f"filled={quantity_filled}, expected_total={expected_autocollect_total:,.0f}, "
                                f"balance_delta={balance_delta:,.0f}"
                            )
                        return candidate

            # Für komplett ungefüllte Preorders (quantity_filled == 0): Standard-Check
            if quantity_filled == 0 and candidate['quantity'] <= warehouse_delta and candidate['quantity'] > 0:
                if self.debug:
                    log_debug(
                        f"[PREORDER] Match found: {candidate['item_name']} "
                        f"x{candidate['quantity']} @ {candidate['price']:,.0f} "
                        f"(ID: {candidate['id']})"
                    )
                return candidate

            if self.debug:
                log_debug(
                    f"[PREORDER] No quantity match for '{item_name}' "
                    f"(preorder_qty={candidate['quantity']}, filled={quantity_filled}, "
                    f"warehouse_delta={warehouse_delta}, balance_delta={balance_delta})"
                )
            return None
        
        except Exception as e:
            if self.debug:
                log_debug(f"[PREORDER] ERROR finding match: {e}")
            return None
    
    def get_active_preorders(
        self,
        item_name: Optional[str] = None
    ) -> List[Dict]:
        """
        Retrieve all active preorders, optionally filtered by item name.
        
        Args:
            item_name: Optional item name filter
            
        Returns:
            List of preorder dicts
        """
        try:
            # Refresh cache if needed
            self._refresh_cache_if_needed()
            
            if self._active_preorders_cache is None:
                return []
            
            if item_name is None:
                return self._active_preorders_cache.copy()
            
            item_lower = item_name.lower()
            return [
                po for po in self._active_preorders_cache
                if po['item_name'].lower() == item_lower
            ]
        
        except Exception as e:
            if self.debug:
                log_debug(f"[PREORDER] ERROR retrieving active preorders: {e}")
            return []
    
    # === Update Operations ===
    
    def mark_collected(
        self,
        preorder_id: int,
        collected_at: datetime,
        transaction_id: Optional[int] = None
    ) -> bool:
        """
        Mark a preorder as collected after successful transaction storage.
        
        Args:
            preorder_id: ID of the preorder to mark
            collected_at: Timestamp when collection occurred
            transaction_id: Optional foreign key to transactions table
            
        Returns:
            True if update successful, False otherwise
        """
        try:
            cur = get_cursor()
            cur.execute(
                """
                UPDATE preorders
                SET status = 'collected',
                    collected_at = ?,
                    collected_tx_id = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'active'
                """,
                (collected_at, transaction_id, preorder_id)
            )
            get_connection().commit()
            
            if cur.rowcount > 0:
                # Invalidate cache
                self._active_preorders_cache = None
                
                if self.debug:
                    log_debug(
                        f"[PREORDER] Marked collected: ID={preorder_id}, "
                        f"collected_at={collected_at}, tx_id={transaction_id}"
                    )
                return True
            else:
                if self.debug:
                    log_debug(
                        f"[PREORDER] Failed to mark collected: ID={preorder_id} "
                        "(not found or already collected)"
                    )
                return False
        
        except Exception as e:
            if self.debug:
                log_debug(f"[PREORDER] ERROR marking collected: {e}")
            return False
    
    def cancel_preorder(
        self,
        item_name: str,
        quantity: int,
        price: float
    ) -> bool:
        """
        Mark a preorder as cancelled (triggered by "Withdrew order" log entry).
        
        Match by item_name + quantity + price (all must match).
        
        Args:
            item_name: Item name (corrected)
            quantity: Order quantity
            price: Order price (total)
            
        Returns:
            True if preorder found and cancelled, False otherwise
        """
        try:
            cur = get_cursor()
            
            # Find matching active preorder
            cur.execute(
                """
                SELECT id
                FROM preorders
                WHERE item_name = ? 
                  AND quantity = ? 
                  AND price = ?
                  AND status = 'active'
                """,
                (item_name, quantity, price)
            )
            
            row = cur.fetchone()
            if not row:
                if self.debug:
                    log_debug(
                        f"[PREORDER] No active preorder to cancel: "
                        f"{item_name} x{quantity} @ {price:,.0f}"
                    )
                return False
            
            preorder_id = row[0]
            
            # Mark as cancelled
            cur.execute(
                """
                UPDATE preorders
                SET status = 'cancelled',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (preorder_id,)
            )
            get_connection().commit()
            
            # Invalidate cache
            self._active_preorders_cache = None
            
            if self.debug:
                log_debug(
                    f"[PREORDER] Cancelled: {item_name} x{quantity} @ {price:,.0f} "
                    f"(ID: {preorder_id})"
                )
            
            return True
        
        except Exception as e:
            if self.debug:
                log_debug(f"[PREORDER] ERROR cancelling preorder: {e}")
            return False
    
    def update_quantity_filled(
        self,
        preorder_id: int,
        filled_quantity: int
    ) -> bool:
        """
        Update the quantity_filled field for partial preorder fills.
        
        Args:
            preorder_id: ID of the preorder to update
            filled_quantity: New quantity_filled value
            
        Returns:
            True if update successful, False otherwise
        """
        try:
            cur = get_cursor()
            cur.execute(
                """
                UPDATE preorders
                SET quantity_filled = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'active'
                """,
                (filled_quantity, preorder_id)
            )
            get_connection().commit()
            
            if cur.rowcount > 0:
                # Invalidate cache
                self._active_preorders_cache = None
                
                if self.debug:
                    log_debug(
                        f"[PREORDER] Updated filled quantity: ID={preorder_id}, "
                        f"filled={filled_quantity}"
                    )
                return True
            else:
                return False
        
        except Exception as e:
            if self.debug:
                log_debug(f"[PREORDER] ERROR updating filled quantity: {e}")
            return False
    
    # === Cache Management ===
    
    def _refresh_cache_if_needed(self):
        """
        Refresh the active preorders cache if stale or empty.
        """
        now = datetime.now()
        
        # Check if cache needs refresh
        if (
            self._active_preorders_cache is None
            or self._cache_timestamp is None
            or (now - self._cache_timestamp) > self._cache_ttl
        ):
            self._refresh_cache()
    
    def _refresh_cache(self):
        """
        Load all active preorders from database into memory cache.
        """
        try:
            cur = get_cursor()
            cur.execute(
                """
                SELECT id, item_name, quantity, quantity_filled, price, timestamp
                FROM preorders
                WHERE status = 'active'
                ORDER BY timestamp ASC
                """
            )
            
            rows = cur.fetchall()
            self._active_preorders_cache = [
                {
                    'id': row[0],
                    'item_name': row[1],
                    'quantity': row[2],
                    'quantity_filled': row[3],
                    'price': row[4],
                    'timestamp': row[5]
                }
                for row in rows
            ]
            
            self._cache_timestamp = datetime.now()
            
            if self.debug:
                log_debug(
                    f"[PREORDER] Cache refreshed: {len(self._active_preorders_cache)} "
                    "active preorder(s)"
                )
        
        except Exception as e:
            if self.debug:
                log_debug(f"[PREORDER] ERROR refreshing cache: {e}")
            self._active_preorders_cache = []
            self._cache_timestamp = datetime.now()
    
    def invalidate_cache(self):
        """
        Force cache invalidation (useful for testing or manual refresh).
        """
        self._active_preorders_cache = None
        self._cache_timestamp = None
        
        if self.debug:
            log_debug("[PREORDER] Cache invalidated")
    
    # === SELL-SIDE: Listing Management (Analog to Preorders) ===
    
    def store_listing(
        self,
        item_name: str,
        quantity: int,
        price: float,
        timestamp: datetime
    ) -> int:
        """
        Store a new listing in the database (SELL-SIDE analog to store_preorder).
        
        CRITICAL: Only ONE active listing per item allowed!
        If an active listing already exists for this item:
        1. Mark old listing as 'collected' (auto-collected on replacement)
        2. Store new listing
        
        Args:
            item_name: Corrected item name (after market_json_manager)
            quantity: Quantity being listed for sale
            price: Expected total revenue (gross, before tax)
            timestamp: Game timestamp when listing was placed
            
        Returns:
            Listing ID (database primary key)
        """
        try:
            cur = get_cursor()
            
            # Check for existing active listing for this item
            cur.execute(
                """
                SELECT id, quantity, quantity_sold, price
                FROM listings
                WHERE item_name = ? AND status = 'active'
                """,
                (item_name,)
            )
            existing = cur.fetchone()
            
            if existing:
                old_id, old_qty, old_sold, old_price = existing
                # Mark old listing as collected (auto-collected on replacement)
                cur.execute(
                    """
                    UPDATE listings
                    SET status = 'collected',
                        collected_at = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (timestamp, old_id)
                )
                
                if self.debug:
                    sold_info = f", sold={old_sold}" if old_sold > 0 else ""
                    log_debug(
                        f"[LISTING] Auto-collected old listing on replacement: "
                        f"{item_name} x{old_qty}{sold_info} @ {old_price:,.0f} (ID: {old_id})"
                    )
            
            # Store new listing
            cur.execute(
                """
                INSERT INTO listings 
                (item_name, quantity, price, timestamp, status)
                VALUES (?, ?, ?, ?, 'active')
                """,
                (item_name, quantity, price, timestamp)
            )
            get_connection().commit()
            listing_id = cur.lastrowid
            
            # Invalidate cache
            self._active_listings_cache = None
            
            if self.debug:
                log_debug(
                    f"[LISTING] Stored: {item_name} x{quantity} @ "
                    f"{price:,.0f} Silver (ID: {listing_id}, TS: {timestamp})"
                )
            
            return listing_id
        
        except Exception as e:
            if self.debug:
                log_debug(f"[LISTING] ERROR storing listing: {e}")
            return -1
    
    def find_matching_listing(
        self,
        item_name: str,
        warehouse_delta: int,
        balance_delta: float,
        timestamp: datetime
    ) -> Optional[Dict]:
        """
        Find a matching active listing for auto-collect detection (SELL-SIDE).
        
        Matching Logic:
        1. Item name must match (exact, case-insensitive)
        2. Status must be 'active'
        3. Quantity consistent with warehouse_delta (negative for sales)
        
        NOTE: No time tolerance needed - listings never expire!
              Only ONE active listing per item possible.
        
        Args:
            item_name: Item being sold (from baseline)
            warehouse_delta: Warehouse decrease (negative for sold items)
            balance_delta: Balance increase (sale revenue after tax)
            timestamp: Current transaction timestamp (for logging only)
            
        Returns:
            Dict with listing data, or None if no match found
            Keys: id, item_name, quantity, quantity_sold, price, timestamp
        """
        try:
            # Refresh cache if stale
            self._refresh_listings_cache_if_needed()
            
            if not self._active_listings_cache:
                return None
            
            # Filter by item name (case-insensitive)
            item_lower = item_name.lower()
            candidates = [
                listing for listing in self._active_listings_cache
                if listing['item_name'].lower() == item_lower
            ]
            
            if not candidates:
                return None
            
            # With ONE active listing per item, we should have at most 1 candidate
            if len(candidates) > 1:
                if self.debug:
                    log_debug(
                        f"[LISTING] WARNING: Multiple active listings for '{item_name}' "
                        f"(should not happen with unique constraint!)"
                    )
            
            # Take the first (and should be only) candidate
            candidate = candidates[0]
            
            # Check if there's any sold quantity to collect
            quantity_sold = candidate.get('quantity_sold', 0)
            
            # Validate quantity alignment (warehouse_delta is NEGATIVE for sales)
            abs_warehouse_delta = abs(warehouse_delta)
            
            # For partial sales: we collect the sold portion
            if quantity_sold > 0 and quantity_sold <= abs_warehouse_delta:
                if self.debug:
                    log_debug(
                        f"[LISTING] Match found (partial sale): {candidate['item_name']} "
                        f"x{candidate['quantity']} (sold={quantity_sold}) @ {candidate['price']:,.0f} "
                        f"(ID: {candidate['id']})"
                    )
                return candidate
            # For non-sold listings: standard check
            elif quantity_sold == 0 and candidate['quantity'] <= abs_warehouse_delta:
                if self.debug:
                    log_debug(
                        f"[LISTING] Match found: {candidate['item_name']} "
                        f"x{candidate['quantity']} @ {candidate['price']:,.0f} "
                        f"(ID: {candidate['id']})"
                    )
                return candidate
            else:
                if self.debug:
                    log_debug(
                        f"[LISTING] No quantity match for '{item_name}' "
                        f"(listing_qty={candidate['quantity']}, sold={quantity_sold}, "
                        f"warehouse_delta={warehouse_delta})"
                    )
                return None
        except Exception as e:
            if self.debug:
                log_debug(f"[LISTING] ERROR finding match: {e}")
            return None

    def find_active_listing(self, item_name: str) -> Optional[Dict]:
        """Return the currently active listing for an item (if any)."""
        try:
            self._refresh_listings_cache_if_needed()

            if not self._active_listings_cache:
                return None

            item_lower = item_name.lower()
            for listing in self._active_listings_cache:
                if listing['item_name'].lower() == item_lower:
                    return listing

            return None

        except Exception as e:
            if self.debug:
                log_debug(f"[LISTING] ERROR retrieving active listing: {e}")
            return None

    def get_active_listings(
        self,
        item_name: Optional[str] = None
    ) -> List[Dict]:
        """
        Retrieve all active listings, optionally filtered by item name.
        
        Args:
            item_name: Optional item name filter
            
        Returns:
            List of listing dicts
        """
        try:
            # Refresh cache if needed
            self._refresh_listings_cache_if_needed()
            
            if self._active_listings_cache is None:
                return []
            
            if item_name is None:
                return self._active_listings_cache.copy()
            
            item_lower = item_name.lower()
            return [
                listing for listing in self._active_listings_cache
                if listing['item_name'].lower() == item_lower
            ]
        
        except Exception as e:
            if self.debug:
                log_debug(f"[LISTING] ERROR retrieving active listings: {e}")
            return []
    
    def mark_listing_collected(
        self,
        listing_id: int,
        collected_at: datetime,
        transaction_id: Optional[int] = None
    ) -> bool:
        """
        Mark a listing as collected after successful transaction storage.
        
        Args:
            listing_id: ID of the listing to mark
            collected_at: Timestamp when collection occurred
            transaction_id: Optional foreign key to transactions table
            
        Returns:
            True if update successful, False otherwise
        """
        try:
            cur = get_cursor()
            cur.execute(
                """
                UPDATE listings
                SET status = 'collected',
                    collected_at = ?,
                    collected_tx_id = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'active'
                """,
                (collected_at, transaction_id, listing_id)
            )
            get_connection().commit()
            
            if cur.rowcount > 0:
                # Invalidate cache
                self._active_listings_cache = None
                
                if self.debug:
                    log_debug(
                        f"[LISTING] Marked collected: ID={listing_id}, "
                        f"collected_at={collected_at}, tx_id={transaction_id}"
                    )
                return True
            else:
                if self.debug:
                    log_debug(
                        f"[LISTING] Failed to mark collected: ID={listing_id} "
                        "(not found or already collected)"
                    )
                return False
        
        except Exception as e:
            if self.debug:
                log_debug(f"[LISTING] ERROR marking collected: {e}")
            return False
    
    def cancel_listing(
        self,
        item_name: str,
        quantity: int,
        price: float
    ) -> bool:
        """
        Mark a listing as cancelled (triggered by "Withdrew" log entry).
        
        Match by item_name + quantity + price (all must match).
        
        Args:
            item_name: Item name (corrected)
            quantity: Listing quantity
            price: Listing price (total)
            
        Returns:
            True if listing found and cancelled, False otherwise
        """
        try:
            cur = get_cursor()
            
            # Find matching active listing
            cur.execute(
                """
                SELECT id
                FROM listings
                WHERE item_name = ? 
                  AND quantity = ? 
                  AND price = ?
                  AND status = 'active'
                """,
                (item_name, quantity, price)
            )
            
            row = cur.fetchone()
            if not row:
                if self.debug:
                    log_debug(
                        f"[LISTING] No active listing to cancel: "
                        f"{item_name} x{quantity} @ {price:,.0f}"
                    )
                return False
            
            listing_id = row[0]
            
            # Mark as cancelled
            cur.execute(
                """
                UPDATE listings
                SET status = 'cancelled',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (listing_id,)
            )
            get_connection().commit()
            
            # Invalidate cache
            self._active_listings_cache = None
            
            if self.debug:
                log_debug(
                    f"[LISTING] Cancelled: {item_name} x{quantity} @ {price:,.0f} "
                    f"(ID: {listing_id})"
                )
            
            return True
        
        except Exception as e:
            if self.debug:
                log_debug(f"[LISTING] ERROR cancelling listing: {e}")
            return False
    
    def _refresh_listings_cache_if_needed(self):
        """
        Refresh the active listings cache if stale or empty.
        """
        now = datetime.now()
        
        # Check if cache needs refresh
        if (
            self._active_listings_cache is None
            or self._listings_cache_timestamp is None
            or (now - self._listings_cache_timestamp) > self._cache_ttl
        ):
            self._refresh_listings_cache()
    
    def _refresh_listings_cache(self):
        """
        Load all active listings from database into memory cache.
        """
        try:
            cur = get_cursor()
            cur.execute(
                """
                SELECT id, item_name, quantity, quantity_sold, price, timestamp
                FROM listings
                WHERE status = 'active'
                ORDER BY timestamp ASC
                """
            )
            
            rows = cur.fetchall()
            self._active_listings_cache = [
                {
                    'id': row[0],
                    'item_name': row[1],
                    'quantity': row[2],
                    'quantity_sold': row[3],
                    'price': row[4],
                    'timestamp': row[5]
                }
                for row in rows
            ]
            
            self._listings_cache_timestamp = datetime.now()
            
            if self.debug:
                log_debug(
                    f"[LISTING] Cache refreshed: {len(self._active_listings_cache)} "
                    "active listing(s)"
                )
        
        except Exception as e:
            if self.debug:
                log_debug(f"[LISTING] ERROR refreshing cache: {e}")
            self._active_listings_cache = []
            self._listings_cache_timestamp = datetime.now()


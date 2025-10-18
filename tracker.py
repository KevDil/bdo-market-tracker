import asyncio
import threading
import time
import datetime
import math
import re
import json
import cv2
import hashlib
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
from functools import lru_cache

from config import (
    DEFAULT_REGION,
    POLL_INTERVAL,
    USE_GPU,
    GAME_FRIENDLY_MODE,
    FOCUS_REQUIRED,
    FOCUS_WINDOW_TITLES,
    USE_ASYNC_PIPELINE,
    ASYNC_QUEUE_MAXSIZE,
    ASYNC_WORKER_COUNT,
    MIN_ITEM_QUANTITY,
    MAX_ITEM_QUANTITY,
    get_debug_mode,
    set_debug_mode,
)
from utils import (
    capture_region,
    preprocess,
    log_text,
    detect_window_type,
    detect_tab_from_text,
    log_debug,
    normalize_numeric_str,
    ocr_image_cached,
    check_price_plausibility,
    correct_item_name,
    is_bdo_window_in_foreground,
)
from database import (
    get_cursor,
    get_connection,
    update_tx_timestamp_if_earlier,
    find_existing_tx_by_values,
    save_state,
    load_state,
    fetch_occurrence_indices,
    transaction_exists_by_item_timestamp,
    transaction_exists_exact,
    transaction_exists_any_side,
    transaction_exists_by_values_near_time,
)
from parsing import (
    split_text_into_log_entries,
    extract_details_from_entry,
    parse_timestamp_text
)
from bdo_api_client import get_item_price_range_by_name

# -----------------------
# Performance: Precompiled Regex Patterns
# -----------------------
# These patterns are used frequently in baseline checking and should be precompiled
_WHITESPACE_PATTERN = re.compile(r'\s+')
_COMMA_PATTERN = re.compile(r',')
_TRANSACTION_BASE_PATTERN = r"Transaction\s+of\s+{item}\s*.*?x?\s*{qty}\s*.*?{price}"
_HISTORICAL_VALUE_DUP_TOLERANCE_SECONDS = 90  # 1,5 Minuten Puffer für Scroll-Duplikate

# -----------------------
# Entscheidungslogik: Fälle erkennen & speichern
# -----------------------
class MarketTracker:
    def __init__(self, region=DEFAULT_REGION, poll_interval=POLL_INTERVAL, debug=None):
        if debug is None:
            debug = get_debug_mode(True)
        self.debug = bool(debug)
        self.region = region
        # Game-Friendly Mode: Längeres Poll-Interval bei GPU-Modus reduziert Ruckler
        if GAME_FRIENDLY_MODE and USE_GPU:
            self.poll_interval = max(poll_interval, 0.8)  # Min 0.8s bei GPU (sanfter fürs Spiel)
            if debug:
                log_debug(f"[INIT] Game-Friendly Mode: Poll interval increased to {self.poll_interval}s (GPU + Cache Mode)")
        else:
            # Reduce default poll interval to 0.5s for faster response (was 1.2s)
            # With persistent baseline, we don't need burst-scans anymore!
            self.poll_interval = min(poll_interval, 0.5)  # Max 0.5s between scans
        # CRITICAL FIX: Aggressive burst mode for fast transaction capture
        # Burst scans run at 80ms intervals to catch transaction lines quickly
        self.poll_interval_burst = 0.08  # Was 0.3s, now 0.08s for 12 scans/sec
        self._burst_until = None
        self._burst_fast_scans = 0
        self._request_immediate_rescan = 0
        self.running = False
        self.lock = threading.Lock()
        self._debug_image_lock = threading.Lock()
        # bereits gesehene transaction-signaturen (session), um doppelte Verarbeitung zu verhindern
        # Performance-Optimierung: Deque statt Set verhindert unbegrenztes Wachstum
        from collections import deque
        self.seen_tx_signatures = deque(maxlen=1000)  # Max 1000 neueste Signaturen
        self._batch_content_hashes: set[str] = set()
        # zuletzt gesamter OCR-Text (zum Erkennen von neuen Zeilen)
        self.last_full_text = ""
        # letzter Overview-OCR-Text (nur Overview, für Delta-Vergleich)
        # Load from persistent state if available
        self.last_overview_text = load_state('last_overview_text', default="")
        baseline_loaded = bool(self.last_overview_text)
        db_empty = False
        try:
            cur = get_cursor()
            cur.execute("SELECT COUNT(*) FROM transactions")
            row = cur.fetchone()
            db_empty = (not row) or (row[0] == 0)
        except Exception:
            db_empty = False
        if baseline_loaded and db_empty:
            self.last_overview_text = ""
            save_state('last_overview_text', "")
            baseline_loaded = False
        if self.debug and self.last_overview_text:
            log_debug(f"[INIT] Loaded persistent baseline: {len(self.last_overview_text)} chars, preview: {self.last_overview_text[:100]}...")
        elif self.debug:
            log_debug("[INIT] No persistent baseline found - first run or after reset")

        # Restore the latest UI metrics per tab (buy/sell) so UI-delta inference works across tab switches
        def _load_ui_metrics(key: str) -> dict:
            raw = load_state(key, default="{}")
            if not raw:
                return {}
            try:
                parsed = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(parsed, dict):
                    # ensure nested dicts are copied and numeric fields are ints
                    result = {}
                    for item_key, metrics in parsed.items():
                        if isinstance(metrics, dict):
                            result[item_key] = {
                                mk: int(mv) if isinstance(mv, (int, float)) and mv == int(mv) else mv
                                for mk, mv in metrics.items()
                            }
                        else:
                            result[item_key] = metrics
                    return result
            except Exception:
                pass
            return {}

        self._last_ui_buy_metrics = _load_ui_metrics('last_ui_buy_metrics')
        self._last_ui_sell_metrics = _load_ui_metrics('last_ui_sell_metrics')
        
        # Fenster-Historie: Liste von (timestamp, window_type)
        self.window_history = []  # keep last 5
        # aktueller Zustand der einfachen State-Machine
        self.current_window = 'unknown'
        self.last_overview = None  # 'sell_overview'|'buy_overview'|None
        # Zeit-Guards: letzter verarbeiteter Spiel-Zeitstempel
        self.last_processed_game_ts = None
        # Session-Baseline: erster Overview-Snapshot importiert keine Historie
        # If we have a saved baseline, we consider it initialized
        self._baseline_initialized = baseline_loaded

        # Error tracking for health monitoring
        self.error_count = 0
        self.last_error_time = None
        self.last_error_message = ""
        # Track unit price plausibility lookups to minimise API churn and noisy logs
        self._unit_price_cache = {}
        self._missing_price_items = set()
        self._base_price_cache = {}
        self._last_focus_state = None
        self._last_foreground_title = ""

        occ_state_raw = load_state('tx_occurrence_state_v1', default="{}")
        try:
            parsed_state = json.loads(occ_state_raw) if occ_state_raw else {}
            self._occurrence_state = {str(k): int(v) for k, v in parsed_state.items()}
        except Exception:
            self._occurrence_state = {}
        self._occurrence_state_dirty = False
        self._occurrence_runtime_cache = {}
        # Async pipeline controller placeholder
        self._async_controller = None

        if self.debug:
            log_debug(f"[INIT] Baseline initialized: {self._baseline_initialized}, Poll interval: {self.poll_interval}s")

    def _capture_frame(self):
        """Capture a frame with focus checks and error bookkeeping."""
        if FOCUS_REQUIRED:
            is_focused, current_title = is_bdo_window_in_foreground(FOCUS_WINDOW_TITLES)
            if not is_focused:
                if self._last_focus_state is not False:
                    log_debug(f"[FOCUS] Skip scan - foreground window '{current_title or 'unknown'}'")
                self._last_focus_state = False
                self._last_foreground_title = current_title or ""
                time.sleep(0.05)
                return None
            if self._last_focus_state is not True:
                log_debug("[FOCUS] Game window back in focus - resuming scans")
            self._last_focus_state = True
            self._last_foreground_title = current_title or ""

        try:
            return capture_region(self.region)
        except Exception as exc:
            print("Fehler beim Screenshot:", exc)
            self.error_count += 1
            self.last_error_time = datetime.datetime.now()
            self.last_error_message = f"Screenshot error: {exc}"
            log_debug(f"[ERROR] Screenshot failed: {exc}")
            time.sleep(0.05)
            return None

    def _process_image(self, img, context='sync', allow_debug=True):
        """Run preprocessing, OCR, and downstream processing for a captured image."""
        if img is None:
            return None

        perf_prefix = f"[PERF-{context.upper()}]"
        total_start = time.perf_counter()

        try:
            preprocess_start = time.perf_counter()
            # BALANCED PREPROCESSING: Use adaptive CLAHE but skip denoise
            # Fast mode was too aggressive and hurt OCR quality
            proc = preprocess(img, adaptive=True, denoise=False, fast_mode=False)
            preprocess_time = (time.perf_counter() - preprocess_start) * 1000
            if self.debug:
                log_debug(f"{perf_prefix} Preprocess: {preprocess_time:.1f}ms (balanced mode)")

            if allow_debug and self.debug:
                self._write_debug_images(img, proc, context)

            ocr_start = time.perf_counter()
            # PHASE 2: Multi-Engine OCR with PaddleOCR (primary)
            # PaddleOCR is faster and more accurate for game UIs
            text, was_cached, cache_stats = ocr_image_cached(
                img,
                method='auto',  # Uses config.OCR_ENGINE (default: paddle)
                use_roi=True,
                preprocessed=proc,
                fast_mode=True,  # Still use fast mode for speed
            )
            ocr_time = (time.perf_counter() - ocr_start) * 1000
            if self.debug:
                cache_indicator = " [CACHED]" if was_cached else ""
                log_debug(
                    f"{perf_prefix} OCR: {ocr_time:.1f}ms{cache_indicator} (BALANCED) "
                    f"(cache_hit_rate={cache_stats.get('hit_rate', 0.0):.1f}%)"
                )

            log_text(text)
            if self.debug and context != 'async':
                print(f"OCR ({context}):", text[:700].replace("\n", " "))

            process_start = time.perf_counter()
            self.process_ocr_text(text)
            process_time = (time.perf_counter() - process_start) * 1000
            total_time = (time.perf_counter() - total_start) * 1000

            if self.debug:
                log_debug(f"{perf_prefix} Process: {process_time:.1f}ms, Total scan: {total_time:.1f}ms")

            if self.error_count > 0:
                self.error_count = max(0, self.error_count - 1)

            return text
        except Exception as exc:
            if self.debug:
                log_debug(f"[ERROR-{context.upper()}] {exc}")
            self.error_count += 1
            self.last_error_time = datetime.datetime.now()
            self.last_error_message = f"Processing error: {exc}"
            return None

    def _write_debug_images(self, original_bgr, processed_img, _context: str) -> None:
        """Persist the latest debug screenshots so investigation always has fresh material."""
        latest_orig = "debug_orig.png"
        latest_proc = "debug_proc.png"

        with self._debug_image_lock:
            try:
                Image.fromarray(cv2.cvtColor(original_bgr, cv2.COLOR_BGR2RGB)).save(latest_orig)
                Image.fromarray(processed_img).save(latest_proc)
            except Exception as save_err:
                log_debug(f"[DEBUG] Failed to write debug images: {save_err}")

    def _get_next_sleep_interval(self):
        now = datetime.datetime.now()
        if self._burst_until and now < self._burst_until:
            sleep_iv = 0.08 if self._burst_fast_scans > 0 else self.poll_interval_burst
        else:
            sleep_iv = self.poll_interval
            if self._burst_until and now >= self._burst_until:
                self._burst_until = None
                if self.debug:
                    log_debug("burst scan window expired")
        if sleep_iv <= 0.08 and self._burst_fast_scans > 0:
            self._burst_fast_scans -= 1
        return sleep_iv

    def _get_base_price(self, item_name: str) -> int | None:
        if not item_name:
            return None
        key = (item_name or "").lower()
        if key in self._base_price_cache:
            cached = self._base_price_cache[key]
            return cached if cached else None

        candidates: list[str] = []
        candidates.append(item_name)
        try:
            corrected = correct_item_name(item_name, min_score=80)
            if corrected and corrected.lower() != key:
                candidates.append(corrected)
        except Exception as exc:
            if self.debug:
                log_debug(f"[PRICE] Item correction failed for base price lookup '{item_name}': {exc}")

        base_price: int | None = None
        for candidate in candidates:
            if not candidate:
                continue
            try:
                data = get_item_price_range_by_name(candidate, use_cache=True)
            except Exception as exc:
                if self.debug:
                    log_debug(f"[PRICE] Base price lookup failed for '{candidate}': {exc}")
                continue
            if data and data.get('base_price'):
                base_price = int(data['base_price'])
                break

        # cache result (including None to avoid repeated lookups)
        self._base_price_cache[key] = base_price or 0
        if base_price:
            for cand in candidates:
                if cand:
                    self._base_price_cache[cand.lower()] = base_price
        return base_price

    def _restore_total_with_base_price(self, item_name: str, quantity: int | None, observed_total: int | None) -> int | None:
        if not item_name or not quantity or quantity <= 0 or not observed_total or observed_total <= 0:
            return None
        base_price = self._get_base_price(item_name)
        if not base_price or base_price <= 0:
            return None

        observed_unit = observed_total / quantity
        tolerance = 0.10
        lower = base_price * (1 - tolerance)
        upper = base_price * (1 + tolerance)
        if observed_unit >= lower:
            # already within tolerance, no missing digit suspected
            return None

        magnitude = 10 ** max(0, int(math.log10(base_price)))
        max_attempts = 3
        for _ in range(max_attempts):
            for leading in range(1, 10):
                candidate_total = observed_total + leading * magnitude
                if candidate_total % quantity != 0:
                    continue
                candidate_unit = candidate_total // quantity
                if lower <= candidate_unit <= upper:
                    if self._is_unit_price_plausible(item_name, candidate_unit):
                        return candidate_total
                    # Even if unit plausibility fails (e.g., API outage), accept once within tolerance
                    return candidate_total
            magnitude *= 10

        expected_total = int(round(base_price * quantity))
        if expected_total % quantity == 0 and expected_total > observed_total and lower <= expected_total / quantity <= upper:
            if self._is_unit_price_plausible(item_name, expected_total // quantity):
                return expected_total
            return expected_total
        return None

    def _compile_transaction_pattern(self, item_name, quantity, price):
        parts = []
        if item_name:
            parts = [re.escape(part) for part in _WHITESPACE_PATTERN.split(item_name) if part]
        item_pattern = r"\s+".join(parts)
        qty_pattern = re.escape(str(quantity)) if quantity is not None else ""
        price_pattern = ""
        if price is not None:
            price_int = int(round(price))
            price_str = str(price_int)
            if len(price_str) > 6:
                price_prefix = re.escape(price_str[:3])
                price_suffix = re.escape(price_str[-3:])
                price_pattern = f"{price_prefix}[\\s,\\.\\dOolI]{{0,20}}{price_suffix}"
            else:
                price_pattern = _COMMA_PATTERN.sub(',?', re.escape(price_str))

        def _fmt_escape(value: str) -> str:
            return value.replace('{', '{{').replace('}', '}}')

        item_component = _fmt_escape(item_pattern) if item_pattern else r'.*?'
        qty_component = _fmt_escape(qty_pattern) if qty_pattern else r'.*?'
        price_component = _fmt_escape(price_pattern) if price_pattern else r'.*?'

        pattern_str = _TRANSACTION_BASE_PATTERN.format(
            item=item_component,
            qty=qty_component,
            price=price_component,
        )
        return re.compile(pattern_str, re.IGNORECASE | re.DOTALL)

    def _consume_immediate_rescan_request(self):
        if self._request_immediate_rescan > 0:
            self._request_immediate_rescan -= 1
            return True
        return False

    def _extract_buy_ui_metrics(self, full_text):
        """
        Extrahiert Buy-Overview UI-Metriken je Item:
        - orders
        - ordersCompleted
        - remainingPrice (Zahl neben 'Collect' vor 'Re-list')
        Gibt Dict nach item_lc -> metrics zurück.
        """
        metrics = {}
        try:
            # PERFORMANCE: Use precompiled whitespace pattern
            s = _WHITESPACE_PATTERN.sub(' ', full_text)
            # CRITICAL FIX: Two-pass approach to capture full item names
            # Pass 1: Find all "Orders ... Orders Completed ... Collect ... Re-list" blocks
            # Pass 2: Extract item name by looking backwards from "Orders" keyword
            
            # Find all metric blocks first
            metric_pattern = re.compile(
                r"Orders\s*:?\s*([0-9,\.]+)\s*(?:/)?\s*Orders\s*Completed\s*:?\s*([0-9,\.]+)[\s\S]{0,160}?Coll\w*\s*([0-9,\.]+)\s+[Rr]e-?list",
                re.IGNORECASE,
            )
            
            for m in metric_pattern.finditer(s):
                # Extract metrics
                orders = normalize_numeric_str(m.group(1)) or 0
                oc = normalize_numeric_str(m.group(2)) or 0
                rem = normalize_numeric_str(m.group(3)) or 0
                
                if orders <= 0 or oc <= 0 or rem <= 0:
                    continue
                
                # Now look backwards from the start of "Orders" to find the item name
                # Take up to 100 chars before "Orders" and extract the last valid item name
                before_orders = s[max(0, m.start()-100):m.start()]
                
                # Extract item name: last sequence of letters/spaces/apostrophes before "Orders"
                # Stop at known delimiters like "Re-list", "Collect", numbers-only sequences, "VT"
                name_match = re.search(
                    r"(?:^|Re-?list|Collect|VT|\d{3,})\s*([A-Za-z][A-Za-z' \[\]\(\)\-]{2,})\s*$",
                    before_orders,
                    re.IGNORECASE
                )
                
                if not name_match:
                    # Fallback: take everything that looks like text before "Orders"
                    name_match = re.search(r"([A-Za-z][A-Za-z' \[\]\(\)\-]{2,})\s*$", before_orders)
                
                if name_match:
                    name = name_match.group(1).strip()
                    # Clean up trailing noise
                    name = re.sub(r'\s*[:\d]+$', '', name).strip()
                    # Remove common OCR artifacts at the end
                    name = re.sub(r'\s+(Re-?list|Collect|Cancel|VT)$', '', name, flags=re.IGNORECASE).strip()
                    
                    if len(name) >= 3:  # Valid item name
                        it_lc = name.lower()
                        metrics[it_lc] = {
                            'item': name,
                            'orders': orders,
                            'ordersCompleted': oc,
                            'remainingPrice': rem,
                        }
        except Exception:
            pass
        return metrics

    def _extract_sell_ui_metrics(self, full_text):
        """
        Extrahiert Sell-Overview UI-Metriken je Item:
        - salesCompleted (unter dem Itemnamen)
        - price (Zahl unter dem Datum links von Collect/Relist)
        Gibt Dict nach item_lc -> metrics zurück.
        """
        metrics = {}
        try:
            # PERFORMANCE: Use precompiled whitespace pattern
            s = _WHITESPACE_PATTERN.sub(' ', full_text)
            # Beispiele: "<ItemName> Registration Count : 200 / Sales Completed 200 ... 3,000,000 Collect Re-list"
            # oder: "<ItemName> Sales Completed: 5 ... 1,234,567 Collect Re-list"
            # Try two patterns:
            patterns = [
                # Pattern A: with optional Registration Count, then Sales Completed number, then price before Collect/Re-list
                re.compile(r"([A-Za-z\[\]0-9' :\-\(\)]{4,}?)\s+(?:Registration\s+Count\s*:\s*[0-9,\.]+\s*/\s*)?Sales\s*Completed\s*[:=]?\s*([0-9,\.]+)(?!\s*20\d{2})[\s\S]{0,200}?([0-9,\.]+)\s+Coll(?:ec|ect|ece)\b\s+[Rr]e-?list", re.IGNORECASE),
                # Pattern B: Registration Count and Sales Completed both with numbers, then price
                re.compile(r"([A-Za-z\[\]0-9' :\-\(\)]{4,}?)\s+Registration\s+Count\s*:\s*([0-9,\.]+)\s*/\s*Sales\s*Completed\s*[:=]?\s*([0-9,\.]+)(?!\s*20\d{2})[\s\S]{0,200}?([0-9,\.]+)\s+Coll(?:ec|ect|ece)\b\s+[Rr]e-?list", re.IGNORECASE),
            ]
            for pat in patterns:
                for m in pat.finditer(s):
                    name = (m.group(1) or '').strip()
                    it_lc = name.lower()
                    # determine group indices for sc and price depending on pattern
                    if pat is patterns[0]:
                        sc_raw, pr_raw = m.group(2), m.group(3)
                        sc_end_idx = m.end(2)
                    else:
                        # group(2)=reg count, group(3)=salesCompleted, group(4)=price
                        sc_raw, pr_raw = m.group(3), m.group(4)
                        sc_end_idx = m.end(3)
                    sc = normalize_numeric_str(sc_raw) or 0
                    pr = normalize_numeric_str(pr_raw) or 0
                    # reject obvious years (2000-2099) or date-like continuation right after the number
                    reject_sc = False
                    if 2000 <= sc <= 2099:
                        reject_sc = True
                    else:
                        lookahead = s[sc_end_idx:sc_end_idx+8]
                        if re.search(r"\s*(?:\d{2}[\.-]\d{2}|20\d{2})", lookahead):
                            reject_sc = True
                    if not reject_sc and sc > 0 and pr > 0:
                        metrics[it_lc] = {
                            'item': name,
                            'salesCompleted': sc,
                            'price': pr,
                        }
        except Exception:
            pass
        return metrics

    @lru_cache(maxsize=500)
    def _valid_item_name(self, name: str) -> bool:
        """
        Validiert einen Itemnamen:
        1. Filtert offensichtliches UI-Garbage
        2. Prüft STRIKT gegen item_names.csv Whitelist
        
        Nur Items die in der Whitelist stehen werden akzeptiert!
        """
        if not name:
            return False
        s = (name or "").strip().lower()
        # reject obvious garbage or UI words
        bad = {"collect", "vt", "warehouse", "orders", "order", "completed", "sell", "buy", "desired", "amount", "desired amount", "set price", "register", "quantity"}
        if s in bad:
            return False
        # filter registration count / ui-list labels contaminated by OCR
        if "registration count" in s or s.startswith("sales completed") or "items listed" in s:
            return False
        # reject very short or repetitive placeholders like 'ooo'
        if len(s) < 3:
            return False
        if re.fullmatch(r"o+", s):
            return False
        # reject if too many spaces and contains typical UI phrases (likely header/paragraph)
        if len(s) > 60 and ("warehouse quantity" in s or "lowest price" in s or "there aren't any items" in s or "enter a search term" in s or "balance" in s or "warehouse capacity" in s):
            return False
        
        # STRICT WHITELIST CHECK: Nur Items aus item_names.csv erlauben!
        from utils import _load_item_names
        whitelist = _load_item_names()
        if not whitelist:
            # Whitelist konnte nicht geladen werden - im Zweifel ablehnen
            if self.debug:
                log_debug(f"[VALIDATION] ⚠️ Whitelist not loaded, rejecting '{name}'")
            return False
        
        # Prüfe exakten Match (case-insensitive)
        for valid_name in whitelist:
            if valid_name.lower() == s:
                return True
        
        # Kein exakter Match - Item ist NICHT in Whitelist, ablehnen
        if self.debug:
            log_debug(f"[VALIDATION] ❌ Item '{name}' NOT in whitelist (rejected)")
        return False
        # reject names that are majority digits/punctuation (UI numbers)
        letters = sum(ch.isalpha() for ch in s)
        digits = sum(ch.isdigit() for ch in s)
        if digits > 0 and letters == 0:
            return False
        # require at least one letter
        if not re.search(r"[a-z]", s):
            return False
        return True

    def _normalize_ts_str(self, ts) -> str:
        if isinstance(ts, datetime.datetime):
            return ts.strftime("%Y-%m-%d %H:%M:%S")
        return str(ts) if ts is not None else ""

    def _occurrence_map_key(self, item_name: str, quantity: int, price: int, tx_type: str, ts_str: str) -> str:
        item_lc = (item_name or "").lower()
        return f"{item_lc}|{int(quantity or 0)}|{int(price or 0)}|{tx_type or ''}|{ts_str}"

    def _assign_occurrence_index(self, tx, existing_indices=None) -> int:
        ts_str = self._normalize_ts_str(tx.get('timestamp'))
        key = self._occurrence_map_key(tx.get('item_name'), tx.get('quantity'), tx.get('price'), tx.get('transaction_type'), ts_str)
        runtime = self._occurrence_runtime_cache
        if key not in runtime:
            next_idx = self._occurrence_state.get(key)
            if next_idx is None:
                if existing_indices is None:
                    existing = fetch_occurrence_indices(tx.get('item_name'), tx.get('quantity') or 0, int(tx.get('price') or 0), tx.get('transaction_type'), tx.get('timestamp'))
                else:
                    existing = list(existing_indices)
                next_idx = (max(existing) + 1) if existing else 0
            runtime[key] = next_idx
        idx = runtime[key]
        runtime[key] = idx + 1
        stored_next = self._occurrence_state.get(key, 0)
        if runtime[key] > stored_next:
            self._occurrence_state[key] = runtime[key]
            self._occurrence_state_dirty = True
        return idx

    def _resolve_occurrence_index(self, tx) -> bool:
        try:
            price = tx.get('price')
            qty = tx.get('quantity')
            if price is None or qty is None:
                tx['occurrence_index'] = 0
                return False

            existing = fetch_occurrence_indices(
                tx.get('item_name'),
                int(qty),
                int(price),
                tx.get('transaction_type'),
                tx.get('timestamp'),
            )
            slot = tx.get('occurrence_slot', 0) or 0
            seen_in_prev = bool(tx.get('_seen_in_prev'))

            if existing:
                if seen_in_prev and slot < len(existing):
                    tx['occurrence_index'] = existing[slot]
                    return True

                ts_val = tx.get('timestamp')
                if (
                    seen_in_prev
                    and isinstance(ts_val, datetime.datetime)
                    and isinstance(self.last_processed_game_ts, datetime.datetime)
                    and ts_val < self.last_processed_game_ts
                ):
                    tx['occurrence_index'] = existing[-1]
                    return True

            tx['occurrence_index'] = self._assign_occurrence_index(tx, existing)
            return False
        except Exception:
            # on failure fall back to default behaviour (treat as new occurrence 0)
            tx['occurrence_index'] = tx.get('occurrence_index', 0) or 0
            return False

    def _persist_occurrence_state_if_needed(self, force: bool = False):
        if force or self._occurrence_state_dirty:
            try:
                payload = json.dumps(self._occurrence_state)
                save_state('tx_occurrence_state_v1', payload)
                self._occurrence_state_dirty = False
            except Exception as exc:
                if self.debug:
                    log_debug(f"[OCC] Failed to persist occurrence state: {exc}")

    def _is_unit_price_plausible(self, item_name: str, unit_price: int) -> bool:
        """Check per-item unit price bounds using live BDO market data."""
        if unit_price is None or unit_price <= 0:
            return False

        cache_key = ((item_name or "").lower(), int(unit_price))
        cached = self._unit_price_cache.get(cache_key)
        if cached is not None:
            return cached

        candidates = []
        if item_name:
            candidates.append(item_name)
            try:
                corrected = correct_item_name(item_name, min_score=80)
                if corrected and corrected.lower() != item_name.lower():
                    candidates.append(corrected)
            except Exception as exc:
                if self.debug:
                    log_debug(f"[PRICE] Item correction failed for '{item_name}': {exc}")
        explicit_rejection = False
        evaluated_name = None

        for candidate in candidates:
            if not candidate:
                continue
            evaluated_name = candidate
            try:
                result_buy = check_price_plausibility(candidate, 1, int(unit_price), tx_side='buy')
            except Exception as exc:
                if self.debug:
                    log_debug(f"[PRICE] Plausibility check failed for '{candidate}' @ {unit_price}: {exc}")
                continue

            reason = result_buy.get('reason')
            if reason in ('no_data', 'api_error'):
                continue

            if result_buy.get('plausible'):
                self._unit_price_cache[cache_key] = True
                return True

            # Retry as SELL context to allow for net (post-tax) unit prices
            if reason == 'too_low':
                try:
                    result_sell = check_price_plausibility(candidate, 1, int(unit_price), tx_side='sell')
                except Exception as exc:
                    if self.debug:
                        log_debug(f"[PRICE] Sell plausibility failed for '{candidate}' @ {unit_price}: {exc}")
                else:
                    reason_sell = result_sell.get('reason')
                    if reason_sell in ('no_data', 'api_error'):
                        continue
                    if result_sell.get('plausible'):
                        self._unit_price_cache[cache_key] = True
                        return True
                    reason = reason_sell

            explicit_rejection = True
            break

        if explicit_rejection:
            self._unit_price_cache[cache_key] = False
            return False

        if evaluated_name:
            key = evaluated_name.lower()
        if key not in self._missing_price_items and self.debug:
            log_debug(f"[PRICE] No live bounds for '{evaluated_name}', allowing unit={unit_price}")
            self._missing_price_items.add(key)

        self._unit_price_cache[cache_key] = True
        return True

    def make_tx_sig(self, item, qty, price, tx_type, ts, occurrence_index=None):
        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S") if isinstance(ts, datetime.datetime) else str(ts)
        occ = int(occurrence_index) if occurrence_index is not None else -1
        return (item.lower() if item else "", int(qty) if qty else 0, int(price) if price else 0, tx_type, ts_str, occ)
    
    def make_content_hash(self, tx):
        """Generate a position-aware content-based hash for deduplication.
        
        CRITICAL: This hash includes the surrounding context/position to distinguish
        between multiple identical transactions that happen within seconds.
        
        The hash includes:
        - Normalized raw text from transaction line
        - PRECEDING text (context before the transaction) to make each unique
        - Timestamp from OCR to distinguish same-second transactions
        """
        try:
            # Try to use raw text + context from related entries
            raw_text = None
            context_before = ""
            
            for r in tx.get('raw_related', []):
                if r.get('type') in ('transaction', 'purchased') and r.get('raw'):
                    raw_text = r['raw']
                    ts_text_val = r.get('ts_text', '') or ''
                    if ts_text_val:
                        try:
                            parsed_ctx = parse_timestamp_text(ts_text_val)
                        except Exception:
                            parsed_ctx = None
                        if parsed_ctx:
                            context_before = parsed_ctx.strftime("%Y-%m-%d %H:%M")
                        else:
                            context_before = ts_text_val.strip()
                    break

            if raw_text:
                # Normalize: lowercase, remove extra spaces
                # PERFORMANCE: Use precompiled whitespace pattern
                normalized = _WHITESPACE_PATTERN.sub(' ', raw_text.lower()).strip()
                # Remove all numbers but keep text structure
                normalized = re.sub(r'\d+[\,\.\d]*', 'N', normalized)
                normalized = _WHITESPACE_PATTERN.sub(' ', normalized).strip()
                context_norm = _WHITESPACE_PATTERN.sub(' ', (context_before or '').lower()).strip()
                if context_norm:
                    hash_input = f"{context_norm}|{normalized}"
                else:
                    hash_input = normalized
            else:
                # Fallback: use parsed values; omit timestamp to favor content-based dedupe
                context_norm = _WHITESPACE_PATTERN.sub(' ', (context_before or '').lower()).strip()
                components = [
                    (tx.get('item_name') or '').lower(),
                    str(int(tx.get('quantity') or 0)),
                    str(int(tx.get('price') or 0)),
                    (tx.get('transaction_type') or '').lower()
                ]
                if context_norm:
                    components.append(context_norm)
                hash_input = "|".join(components)

            # Generate SHA256 hash (first 16 chars sufficient)
            return hashlib.sha256(hash_input.encode('utf-8')).hexdigest()[:16]
        except Exception:
            # Fallback: simple hash of item+qty+price+timestamp
            simple = f"{tx.get('item_name', '')}|{tx.get('quantity', 0)}|{int(tx.get('price', 0) or 0)}".lower()
            return hashlib.sha256(simple.encode('utf-8')).hexdigest()[:16]

    def store_transaction_db(self, tx):
        """Speichert eine Transaktion in der DB thread-sicher."""
        item = tx['item_name']
        qty = tx['quantity']
        price = tx['price']
        ttype = tx['transaction_type']
        ts = tx['timestamp']
        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S") if isinstance(ts, datetime.datetime) else str(ts)
        case = tx.get('case')
        occ_idx_raw = tx.get('occurrence_index')
        try:
            occ_idx = int(occ_idx_raw) if occ_idx_raw is not None else 0
        except Exception:
            occ_idx = 0
        
        sig = self.make_tx_sig(item, qty, price, ttype, ts, occ_idx)
        # CRITICAL: Generate content hash for reliable deduplication
        content_hash = self.make_content_hash(tx)
        if content_hash in self._batch_content_hashes:
            if self.debug:
                log_debug(f"[CONTENT-HASH] Skip duplicate in batch: {item} {qty}x @ {price} (hash={content_hash})")
            self.seen_tx_signatures.append(sig)
            return False
        self._batch_content_hashes.add(content_hash)
        if sig in self.seen_tx_signatures:
            if self.debug:
                print("DEBUG: already seen (session):", sig)
            return False
        # CRITICAL: Check content_hash for duplicates (most reliable method)
        # Only skip if hash matches AND timestamp is within 20 minutes (likely OCR duplicate)
        # If timestamp differs by more than 20 minutes, it's likely a legitimate repeat purchase
        # 20 minutes is conservative but safe: most OCR duplicates occur within same session
        try:
            db_cur = get_cursor()
            db_cur.execute(
                "SELECT id, timestamp FROM transactions WHERE content_hash = ?",
                (content_hash,)
            )
            existing_by_hash = db_cur.fetchone()
            if existing_by_hash:
                existing_id, existing_ts_str = existing_by_hash
                # Parse existing timestamp
                try:
                    from datetime import datetime as dt
                    existing_ts = dt.fromisoformat(existing_ts_str)
                    if isinstance(ts, datetime.datetime):
                        time_diff_minutes = abs((ts - existing_ts).total_seconds()) / 60
                        if time_diff_minutes <= 20:
                            # Within 20 minutes - likely OCR duplicate from same session
                            if self.debug:
                                log_debug(f"[CONTENT-HASH] Skip duplicate: {item} {qty}x @ {price} (hash={content_hash}, time_diff={time_diff_minutes:.1f}min, existing={existing_ts_str})")
                            print(f"⚠️ Duplikat erkannt (Content-Hash + Zeit): {str(ttype or '').upper()} - {qty}x {item} (Δ{time_diff_minutes:.1f}min)")
                            self.seen_tx_signatures.append(sig)
                            return False
                        else:
                            # More than 20 minutes apart - legitimate repeat purchase
                            if self.debug:
                                log_debug(f"[CONTENT-HASH] Allow repeat purchase: {item} {qty}x @ {price} (time_diff={time_diff_minutes:.1f}min > 20min)")
                except Exception:
                    # If timestamp parsing fails, skip based on hash alone (conservative)
                    if self.debug:
                        log_debug(f"[CONTENT-HASH] Skip (timestamp parse failed): {item} {qty}x")
                    print(f"⚠️ Duplikat erkannt (Content-Hash): {str(ttype or '').upper()} - {qty}x {item}")
                    self.seen_tx_signatures.append(sig)
                    return False
        except Exception as e:
            if self.debug:
                log_debug(f"[CONTENT-HASH] Check failed: {e}")
        
        # If UI-inferred, double-check database for same item+price in tolerance (ignore qty since UI deltas can drift)
        if tx.get('_ui_inferred') and price is not None and ts:
            try:
                if transaction_exists_by_values_near_time(item, qty or 0, int(price), ts, tolerance_minutes=5, ignore_quantity=True):
                    if self.debug:
                        log_debug(f"[CONTENT-HASH] Skip UI-inferred duplicate: {item} {qty}x @ {price}")
                    self.seen_tx_signatures.append(sig)
                    return False
            except Exception as e:
                if self.debug:
                    log_debug(f"[CONTENT-HASH] UI-inferred duplicate check failed: {e}")

        # CRITICAL: Skip transactions with invalid price OR quantity
        if price is None or price == 0:
            print(f"⚠️ Überspringe unsichere Transaktion (kein Preis): {str(ttype or '').upper()} {qty}x {item} ts={ts_str}")
            self.seen_tx_signatures.append(sig)  # deque uses append, not add
            return False
        if qty is None or qty <= 0:
            print(f"⚠️ Überspringe unsichere Transaktion (keine/ungültige Menge): {str(ttype or '').upper()} {qty}x {item} ts={ts_str}")
            self.seen_tx_signatures.append(sig)  # deque uses append, not add
            return False
        # If a transaction with same (item, qty, price, type) already exists at a different timestamp, avoid duplicating it.
        try:
            existing = find_existing_tx_by_values(item, qty, int(price), ttype, ts_str, occ_idx)
        except Exception:
            existing = None
        if existing is not None:
            # If the new timestamp is earlier, update; if later, skip as duplicate
            try:
                if isinstance(ts, datetime.datetime):
                    updated = update_tx_timestamp_if_earlier(item, qty, int(price), ttype, ts, occ_idx)
                    if updated and self.debug:
                        log_debug(f"updated existing tx timestamp earlier: {ttype} {qty}x {item} -> {ts_str}")
                # In either case, do not insert a second row
                self.seen_tx_signatures.append(sig)  # deque uses append, not add
                return False
            except Exception:
                # proceed to insert path as fallback if helper failed
                pass
        with self.lock:
            try:
                db_cur = get_cursor()
                db_cur.execute(
                    """
                    INSERT OR IGNORE INTO transactions (item_name, quantity, price, transaction_type, timestamp, tx_case, occurrence_index, content_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (item, qty, price, ttype, ts_str, case, occ_idx, content_hash)
                )
                get_connection().commit()
                if db_cur.rowcount == 0:
                    print(f"⚠️ Bereits vorhanden oder ignoriert: {ttype.upper()} - {qty}x {item} ({ts_str})")
                    try:
                        log_debug(f"DB IGNORE duplicate or conflict: {ttype} {qty}x {item} ts={ts_str}")
                    except Exception:
                        pass
                    self.seen_tx_signatures.append(sig)  # deque uses append, not add
                    return False
                else:
                    print(f"✅ Gespeichert: {ttype.upper()} - {qty}x {item} für {price} Silver am {ts_str}")
                    try:
                        log_debug(f"DB SAVE: {ttype} {qty}x {item} price={price} ts={ts_str} case={case}")
                    except Exception:
                        pass
                    self.seen_tx_signatures.append(sig)  # deque uses append, not add
                    return True
            except Exception as e:
                print("DB Error beim Speichern:", e)
                return False

    def process_ocr_text(self, full_text):
        """
        Hauptfunktion:
        - split in entries per timestamp
        - extrahiere details pro entry
        - gruppiere transaction entries mit listed/withdrew bei gleichem timestamp (oder nahe)
        - bestimme finalen case (collect / relist_full / relist_partial)
        - speichere nur neue Transaktionen (neue im Vergleich zur letzten OCR-Ausgabe)
        """
        if not full_text or not full_text.strip():
            return

        # Fenster-Typ erkennen und State updaten
        prev_window = self.current_window
        wtype = detect_window_type(full_text)
        now = datetime.datetime.now()
        self.current_window = wtype
        self.window_history.append((now, wtype))
        if len(self.window_history) > 5:
            self.window_history = self.window_history[-5:]
        
        # Log window transitions
        if self.debug and prev_window != wtype:
            log_debug(f"[WINDOW] Transition: {prev_window} → {wtype}")
        if wtype in ("sell_overview", "buy_overview"):
            self.last_overview = wtype

        # reset per-scan occurrence counters
        self._occurrence_runtime_cache = {}

        # Validierung: Nur Overview-Fenster auswerten
        if wtype not in ("sell_overview", "buy_overview"):
            if self.debug:
                msg = f"window='{wtype}' -> keine Auswertung"
                print("DEBUG:", msg)
                log_debug(msg)
            # Kein Update von last_overview_text hier, damit Delta sauber bleibt
            # Wenn Detail-Fenster aktiv ist, aktiviere einen kurzen Burst-Scan, um das Zurückspringen
            # ins Overview-Fenster mit hoher Wahrscheinlichkeit zu erwischen.
            if wtype in ("buy_item", "sell_item"):
                self._burst_until = now + datetime.timedelta(seconds=4.0)
                # schedule multiple immediate fast scans
                self._burst_fast_scans = max(self._burst_fast_scans, 5)
                # also request immediate re-scans from single_scan (no wait)
                self._request_immediate_rescan = max(self._request_immediate_rescan, 2)
                if self.debug:
                    log_debug(f"burst scan enabled until {self._burst_until} (+{self._burst_fast_scans} fast scans) due to item window '{wtype}'")
            return

        # detect current tab from the whole OCR snapshot (nur zur Diagnose); Entscheidung über Seite strikt aus Window-Type
        current_tab = detect_tab_from_text(full_text)
        if current_tab == "unknown" and self.last_overview:
            current_tab = "sell" if self.last_overview == "sell_overview" else "buy"
        if self.debug:
            msg = f"detected tab={current_tab} window={wtype} prev_window={prev_window}"
            print("DEBUG:", msg)
            log_debug(msg)

        entries = split_text_into_log_entries(full_text)
        if not entries:
            if self.debug:
                msg = "no timestamp-entries found; skipping"
                print("DEBUG:", msg)
                log_debug(msg)
            return

        # CRITICAL PERFORMANCE FIX: Immediate burst scanning when returning from item window
        # Transaction lines appear instantly or within ~200-500ms after returning to overview
        # Old approach: wait 1-3 seconds with slow scans = missed transactions
        # New approach: IMMEDIATE burst of 10-15 fast scans at 80ms intervals = capture within 1-2s
        if prev_window in ("buy_item", "sell_item") and wtype in ("sell_overview", "buy_overview"):
            # AGGRESSIVE: More scans, longer burst window
            self._burst_fast_scans = max(self._burst_fast_scans, 15)  # Was 8, now 15 (1.2s of fast scans)
            self._burst_until = max(self._burst_until or now, now + datetime.timedelta(seconds=3.0))  # Was 4.5s, now 3s
            # Immediate re-scans (no sleep between scans)
            self._request_immediate_rescan = max(self._request_immediate_rescan, 5)  # Was 3, now 5
            if self.debug:
                log_debug(f"[BURST-AGGRESSIVE] Returned from {prev_window} to {wtype} -> {self._burst_fast_scans} fast scans + {self._request_immediate_rescan} immediate rescans (TARGET: <1s capture)")

        # build structured entries
        structured = []
        self._batch_content_hashes.clear()
        for pos, ts_text, snippet in entries:
            details = extract_details_from_entry(ts_text, snippet)
            # include original pos for fallback grouping
            if not details['timestamp']:
                # ohne gültigen Spiel-Zeitstempel nicht verarbeiten
                continue
            structured.append({
                'pos': pos,
                'ts_text': ts_text,
                'type': details['type'],
                'item': details['item'],
                'qty': details['qty'],
                'price': details['price'],
                'timestamp': details['timestamp'],
                'raw': details['raw']
            })

        # sort by timestamp then pos
        structured = sorted(structured, key=lambda x: (x['timestamp'], x['pos']))
        if self.debug:
            log_debug(f"structured_count={len(structured)}")

        # Determine latest snapshot timestamp across all entries
        overall_max_ts = None
        for s in structured:
            ts = s.get('timestamp')
            if isinstance(ts, datetime.datetime):
                if overall_max_ts is None or ts > overall_max_ts:
                    overall_max_ts = ts

        # Build index of observed types per (item, timestamp) to guide conditional anchors on buy_overview
        items_ts_types = {}
        for s in structured:
            it = (s.get('item') or '').lower()
            ts = s.get('timestamp')
            if not it or not isinstance(ts, datetime.datetime):
                continue
            key = (it, ts)
            st = items_ts_types.get(key)
            if st is None:
                st = set()
                items_ts_types[key] = st
            st.add(s.get('type'))

        returning_from_item = prev_window in ("buy_item", "sell_item") and wtype in ("sell_overview", "buy_overview")

        # Ersten Overview-Snapshot behandeln:
        # Ab jetzt: Beim ersten erkannten Overview-Snapshot werden die sichtbareren Logzeilen sofort
        # ausgewertet und gespeichert. Anschließend wird die Baseline initialisiert, sodass weitere
        # Scans nur neue Einträge verarbeiten. Kein Early-Return mehr.
        restrict_min_ts = None
        scan_restrict_min = None
        first_snapshot_mode = False
        if not self._baseline_initialized:
            # Mark that we are processing the very first overview snapshot of this session
            first_snapshot_mode = True
            self._baseline_initialized = True
            if self.debug:
                log_debug("first overview -> process visible log and initialize baseline after saving")

        # On the very first overview snapshot, timestamps can drift due to header/layout OCR ordering.
        # If we see a transaction/purchased anchor for an item with an older timestamp while the snapshot
        # also contains a newer timestamp FOR THE SAME EVENT TYPE, align to the latest snapshot time.
        # WICHTIG: Nur anpassen, wenn der GLEICHE Event-Typ (z.B. transaction) mehrere Timestamps hat.
        # Verschiedene Event-Typen (transaction vs listed) zu verschiedenen Zeiten sind NORMAL und kein Drift!
        if first_snapshot_mode and overall_max_ts is not None:
            try:
                # rebuild items->set((type, timestamp)) mapping per item
                items_type_timestamps = {}  # item -> list of (type, timestamp)
                for s in structured:
                    it = (s.get('item') or '').lower()
                    ts = s.get('timestamp')
                    typ = s.get('type')
                    if not it or not isinstance(ts, datetime.datetime) or not typ:
                        continue
                    if it not in items_type_timestamps:
                        items_type_timestamps[it] = []
                    items_type_timestamps[it].append((typ, ts))
                
                # consider only items where the SAME event type appears with MULTIPLE timestamps
                # and at least one is close to overall_max_ts (within 5 minutes)
                anchor_items = set()
                baseline_items = set()
                if self.last_overview_text:
                    baseline_lower = self.last_overview_text.lower()
                else:
                    baseline_lower = ""

                for it, type_ts_list in items_type_timestamps.items():
                    # Group by type
                    by_type = {}
                    for typ, ts in type_ts_list:
                        if typ not in by_type:
                            by_type[typ] = []
                        by_type[typ].append(ts)
                    
                    # Check if transaction or purchased have multiple timestamps
                    for anchor_type in ['transaction', 'purchased']:
                        if anchor_type in by_type:
                            timestamps = set(by_type[anchor_type])
                            if len(timestamps) > 1:
                                # Multiple timestamps for the same event type - drift detected!
                                max_item_ts = max(timestamps)
                                if abs((overall_max_ts - max_item_ts).total_seconds()) <= 300:  # 5 minutes
                                    # Only adjust if the item existed in the previous baseline snapshot
                                    if baseline_lower:
                                        item_present_before = bool(re.search(re.escape(it), baseline_lower))
                                    else:
                                        item_present_before = False
                                    if item_present_before:
                                        anchor_items.add(it)
                                        if self.debug:
                                            log_debug(f"first snapshot: item '{it}' has {anchor_type} drift (multiple ts for same event), will adjust")
                                        break  # Found drift for this item
                
                # Adjust all entries of items with drift
                for s in structured:
                    itlc = (s.get('item') or '').lower()
                    if itlc in anchor_items and isinstance(s.get('timestamp'), datetime.datetime):
                        if s['timestamp'] < overall_max_ts:
                            if self.debug:
                                old_ts = s['timestamp'].strftime('%H:%M:%S')
                                new_ts = overall_max_ts.strftime('%H:%M:%S')
                                log_debug(f"first snapshot: adjusting '{itlc}' {s.get('type')} ts {old_ts} → {new_ts}")
                            s['timestamp'] = overall_max_ts
            except Exception as e:
                if self.debug:
                    log_debug(f"first snapshot timestamp adjustment error: {e}")
        
        # Fresh Transaction Detection (FIXED)
        # Purpose: Handle "fast collect" scenario where transaction appears with OLD log timestamp
        # but was actually just executed (e.g., collect at 22:06 shows "21:55" in log).
        # 
        # CRITICAL FIX: Only adjust timestamps for transactions that are RECENT (within 60 seconds).
        # Old log entries (e.g., 21:55 when current time is 22:06 = 11 minutes) should NOT be adjusted!
        # 
        # Criteria for "fresh" transaction:
        #   1. Item not in baseline (new in this scan)
        #   2. Transaction timestamp is RECENT (within FRESH_TX_WINDOW seconds)
        #   3. Transaction not already in DB
        # 
        FRESH_TX_WINDOW = 60  # seconds - only adjust if timestamp is within last 60 seconds
        if not first_snapshot_mode and overall_max_ts is not None and self.last_overview_text:
            try:
                # Suche nach frischen Transaction/Purchased-Einträgen (nicht in letzter Baseline)
                baseline_lower = self.last_overview_text.lower()
                
                # Group transactions by item to detect duplicates
                item_transactions = {}  # item_lc -> list of (index, entry)
                for idx, s in enumerate(structured):
                    if s.get('type') in ('transaction', 'purchased') and s.get('item'):
                        item_lc = (s.get('item') or '').lower()
                        if item_lc not in item_transactions:
                            item_transactions[item_lc] = []
                        item_transactions[item_lc].append((idx, s))
                
                for item_lc, entries in item_transactions.items():
                    # Prüfe ob dieses Item mit Transaction/Purchased im Baseline-Text erscheint
                    # Einfache Heuristik: "transaction of <item>" oder "purchased <item>" im Baseline?
                    is_fresh = True
                    for search_pat in [
                        fr'\btransaction\s+of\s+{re.escape(item_lc)}',
                        fr'\b{re.escape(item_lc)}\s+\S*\s+worth\s+\d',
                        fr'\bpurchased\s+{re.escape(item_lc)}',
                    ]:
                        if re.search(search_pat, baseline_lower, re.IGNORECASE):
                            is_fresh = False
                            break
                    
                    if not is_fresh:
                        continue  # Item ist nicht frisch, keine Adjustierung
                    
                    # Item ist frisch! Aber wenn es mehrere Transaktionen gibt,
                    # nur die mit dem NEUESTEN originalen Timestamp adjustieren.
                    # Die anderen sind wirklich historisch.
                    if len(entries) > 1:
                        # Sortiere nach originalem Timestamp (neueste zuerst)
                        entries_sorted = sorted(
                            entries,
                            key=lambda x: x[1].get('timestamp') if isinstance(x[1].get('timestamp'), datetime.datetime) else datetime.datetime.min,
                            reverse=True
                        )
                        # Nur die neueste adjustieren, ABER nur wenn sie noch nicht in DB ist!
                        idx, s = entries_sorted[0]
                        # CRITICAL: Prüfe ob diese spezifische Transaktion bereits in DB existiert
                        item_name = s.get('item', '')
                        qty = s.get('qty', 0) or 0
                        price = s.get('price', 0) or 0
                        ts = s.get('timestamp')
                        if item_name and qty > 0 and price > 0 and isinstance(ts, datetime.datetime):
                            # Prüfe DB für diese exakte Transaktion (item/qty/price)
                            # CRITICAL FIX: Check BOTH buy AND sell to catch sell items on buy_overview
                            # Wenn sie bereits existiert (egal mit welchem Timestamp), NICHT adjustieren!
                            existing_buy = find_existing_tx_by_values(item_name, qty, int(price), 'buy', None, None)
                            existing_sell = find_existing_tx_by_values(item_name, qty, int(price), 'sell', None, None)
                            if existing_buy or existing_sell:
                                existing = existing_buy or existing_sell
                                if self.debug:
                                    tx_type = 'buy' if existing_buy else 'sell'
                                    log_debug(f"[DUPLICATE PREVENTION] '{item_name}' {qty}x @ {price} already in DB as {tx_type} (ID={existing[0]}) - skipping timestamp adjustment")
                                continue  # Diese Transaktion ist bereits in der DB, nicht duplizieren!
                            
                            # CRITICAL FIX: Only adjust if timestamp is RECENT (within FRESH_TX_WINDOW)
                            # This prevents adjusting OLD log entries (e.g., 21:55 when current is 22:06)
                            time_diff_seconds = abs((overall_max_ts - ts).total_seconds())
                            if time_diff_seconds <= FRESH_TX_WINDOW and ts < overall_max_ts:
                                if self.debug:
                                    old_ts = ts.strftime('%Y-%m-%d %H:%M:%S')
                                    new_ts = overall_max_ts.strftime('%Y-%m-%d %H:%M:%S')
                                    log_debug(f"[FRESH-TX] '{s['item']}' (newest of {len(entries)}) within {time_diff_seconds:.0f}s window: adjusting ts {old_ts} → {new_ts}")
                                s['timestamp'] = overall_max_ts
                            elif time_diff_seconds > FRESH_TX_WINDOW:
                                if self.debug:
                                    log_debug(f"[FRESH-TX] Skip '{s['item']}' - timestamp too old ({time_diff_seconds:.0f}s > {FRESH_TX_WINDOW}s window)")
                    else:
                        # Nur eine Transaktion, normale Logik
                        idx, s = entries[0]
                        # CRITICAL: Prüfe ob diese spezifische Transaktion bereits in DB existiert
                        item_name = s.get('item', '')
                        qty = s.get('qty', 0) or 0
                        price = s.get('price', 0) or 0
                        ts = s.get('timestamp')
                        if item_name and qty > 0 and price > 0 and isinstance(ts, datetime.datetime):
                            # Prüfe DB für diese exakte Transaktion (item/qty/price)
                            # CRITICAL FIX: Check BOTH buy AND sell to catch sell items on buy_overview
                            existing_buy = find_existing_tx_by_values(item_name, qty, int(price), 'buy', None, None)
                            existing_sell = find_existing_tx_by_values(item_name, qty, int(price), 'sell', None, None)
                            if existing_buy or existing_sell:
                                existing = existing_buy or existing_sell
                                if self.debug:
                                    tx_type = 'buy' if existing_buy else 'sell'
                                    log_debug(f"[DUPLICATE PREVENTION] '{item_name}' {qty}x @ {price} already in DB as {tx_type} (ID={existing[0]}) - skipping timestamp adjustment")
                                continue  # Diese Transaktion ist bereits in der DB, nicht duplizieren!
                            
                            # CRITICAL FIX: Only adjust if timestamp is RECENT (within FRESH_TX_WINDOW)
                            time_diff_seconds = abs((overall_max_ts - ts).total_seconds())
                            if time_diff_seconds <= FRESH_TX_WINDOW and ts < overall_max_ts:
                                if self.debug:
                                    old_ts = ts.strftime('%Y-%m-%d %H:%M:%S')
                                    new_ts = overall_max_ts.strftime('%Y-%m-%d %H:%M:%S')
                                    log_debug(f"[FRESH-TX] '{s['item']}' within {time_diff_seconds:.0f}s window: adjusting ts {old_ts} → {new_ts}")
                                s['timestamp'] = overall_max_ts
                            elif time_diff_seconds > FRESH_TX_WINDOW:
                                if self.debug:
                                    log_debug(f"[FRESH-TX] Skip '{s['item']}' - timestamp too old ({time_diff_seconds:.0f}s > {FRESH_TX_WINDOW}s window)")
            except Exception as e:
                if self.debug:
                    log_debug(f"fresh transaction detection error: {e}")

        # Keine harte Zeitfenster-Restriktion: Verarbeitung über Baseline-Zeitstempel und DB-Deduplizierung
        skip_prev_delta = False

        if self.debug:
            lines = [
                f"{s['timestamp'].strftime('%Y-%m-%d %H:%M:%S')} {s['type']} item='{s['item']}' qty={s['qty']} price={s['price']}"
                for s in structured
            ]
            for ln in lines:
                log_debug("structured: " + ln)

        # Parse UI metrics from the overview to support fallback price reconstruction
        # CRITICAL: Always try to extract both buy AND sell metrics, regardless of window type
        # This handles fast window switches where buy events appear on sell_overview (or vice versa)
        # The extract functions are safe and return {} if no metrics found
        ui_buy = self._extract_buy_ui_metrics(full_text)  # Always extract, not just on buy_overview
        ui_sell = self._extract_sell_ui_metrics(full_text)  # Always extract, not just on sell_overview
        # Build normalized lookup helper early so UI deltas can reuse it before updates
        def _norm_key(s: str) -> str:
            try:
                return re.sub(r"[^a-z0-9]", "", (s or "").lower())
            except Exception:
                return (s or "").lower()
        # Snapshot previous UI metrics at the very beginning so inference compares against the prior scan
        prev_ui_buy = {}
        if wtype == 'buy_overview':
            if getattr(self, '_last_ui_buy_metrics', None):
                try:
                    prev_ui_buy = {k: dict(v) for k, v in self._last_ui_buy_metrics.items()}
                except Exception:
                    prev_ui_buy = self._last_ui_buy_metrics.copy()
            elif self.last_overview_text:
                try:
                    prev_ui_buy = self._extract_buy_ui_metrics(self.last_overview_text) or {}
                except Exception:
                    prev_ui_buy = {}
        prev_ui_sell = {}
        prev_ui_sell_norm = {}
        if wtype == 'sell_overview':
            if getattr(self, '_last_ui_sell_metrics', None):
                try:
                    prev_ui_sell = {k: dict(v) for k, v in self._last_ui_sell_metrics.items()}
                except Exception:
                    prev_ui_sell = self._last_ui_sell_metrics.copy()
            elif self.last_overview_text:
                try:
                    prev_ui_sell = self._extract_sell_ui_metrics(self.last_overview_text) or {}
                except Exception:
                    prev_ui_sell = {}
            if prev_ui_sell:
                try:
                    for k, v in prev_ui_sell.items():
                        prev_ui_sell_norm[_norm_key(k)] = v
                        nm_prev = (v.get('item') or '')
                        if nm_prev:
                            prev_ui_sell_norm[_norm_key(nm_prev)] = v
                except Exception:
                    prev_ui_sell_norm = {}
        ui_sell_norm = {}
        if ui_sell:
            for k, v in ui_sell.items():
                try:
                    ui_sell_norm[_norm_key(k)] = v
                    # also consider the item's own name field if present
                    nm = (v.get('item') or '')
                    if nm:
                        ui_sell_norm[_norm_key(nm)] = v
                except Exception:
                    continue

        # find transaction entries and group with any listed/withdrew/placed/purchased that have same timestamp & same item (or very close)
        # Determine allowed timestamps: take all timestamps seen in this scan
        unique_ts = sorted({s['timestamp'] for s in structured if isinstance(s['timestamp'], datetime.datetime)}, reverse=True)
        allowed_ts = set(unique_ts)
        # Determine primary anchor types once per window type
        # Select primary anchor types per window
        if first_snapshot_mode:
            # On the very first overview, import the visible log regardless of tab:
            # accept both sides' primary anchors so that recent buys (purchased) and sells (transaction/listed) are captured.
            primary_types_global = {'transaction', 'listed', 'purchased', 'placed'}
        elif wtype == 'buy_overview':
            # On buy tab, default anchors are purchased/placed/listed
            base = {'purchased', 'placed', 'listed'}
            primary_types_global = set(base)
            # Allow 'transaction' as an anchor only if the same item+ts also has a purchased/placed (buy-side) anchor
            # or we're immediately returning from 'sell_item' where a sell cluster should be accepted.
            if 'items_ts_types' in locals():
                for (it, ts), typ_set in items_ts_types.items():
                    if ('purchased' in typ_set or 'placed' in typ_set) and 'transaction' in typ_set:
                        primary_types_global.add('transaction')
                        break
            if 'returning_from_item' in locals() and returning_from_item and prev_window == 'sell_item':
                primary_types_global.update({'listed', 'transaction'})
            
            # Historical transaction detection: Allow ALL 'transaction' as anchors on buy_overview
            # Both buy AND sell transactions can appear in the log (historical entries)
            # We'll determine the correct side later via item category or context
            for s in structured:
                if s['type'] == 'transaction' and s.get('item'):
                    primary_types_global.add('transaction')
                    if self.debug:
                        log_debug(f"[HISTORICAL] Allowing 'transaction' as anchor (will determine buy/sell via category)")
                    break  # Once we know there are transactions, enable them all
        elif wtype == 'sell_overview':
            # On sell overview, consider transaction and listed anchors
            # ALSO accept 'placed' and 'purchased' to capture buy-side events that appear due to timing
            # (e.g., user switched to sell tab but buy events still in transaction log)
            primary_types_global = {'transaction', 'listed', 'placed', 'purchased'}
        else:
            primary_types_global = set()
        # IMPROVED CLUSTERING: Build clusters FIRST by grouping all events with same item+timestamp
        # Then process each cluster once (instead of processing each anchor separately)
        # This ensures Transaction+Placed+Withdrew are grouped together even if all three are anchors
        
        max_dt_withdrew = 600.0 if first_snapshot_mode else 8.0
        max_dt_normal = 600.0 if first_snapshot_mode else 3.0
        
        # Step 1: Build clusters by item+timestamp
        # IMPORTANT: 'purchased' events with different prices are SEPARATE transactions and should NOT be clustered together!
        # Each 'purchased' is a standalone transaction that doesn't need context.
        clusters_dict = {}  # key: (item_lc, timestamp_seconds, price_or_none) -> list of related entries
        processed_indices = set()
        
        purchase_slot_counters = {}

        for i, ent in enumerate(structured):
            if i in processed_indices:
                continue
            if not ent.get('item'):
                if self.debug:
                    log_debug(f"[CLUSTER] Skip entry {i} - no item name")
                continue
            if not isinstance(ent.get('timestamp'), datetime.datetime):
                if self.debug:
                    log_debug(f"[CLUSTER] Skip entry {i} '{ent.get('item')}' - no valid timestamp")
                continue
            
            item_lc = ent['item'].lower()
            ts = ent['timestamp']
            
            # CRITICAL FIX: For 'purchased' events, include price in cluster key to keep separate transactions apart
            # Purchased events are ALWAYS standalone and don't need context from other events
            if ent['type'] == 'purchased' and ent.get('price'):
                # Each purchased with unique price is its own cluster
                cluster = [ent]
                processed_indices.add(i)
                ts_key = int(ts.timestamp())
                slot_key = (item_lc, ts_key, int(ent['price']))
                slot_pos = purchase_slot_counters.get(slot_key, 0)
                ent['_occurrence_slot'] = slot_pos
                purchase_slot_counters[slot_key] = slot_pos + 1
                cluster_key = (item_lc, ts_key, int(ent['price']), slot_pos)  # Include price and slot in key
                if cluster_key not in clusters_dict:
                    clusters_dict[cluster_key] = cluster
                if self.debug:
                    log_debug(f"[CLUSTER] Standalone 'purchased' for '{ent.get('item')}' @ {ts} price={ent['price']}")
                continue
            
            # For other event types, build cluster normally (without price in key)
            cluster = [ent]
            processed_indices.add(i)
            
            if self.debug:
                log_debug(f"[CLUSTER] Building cluster for '{ent.get('item')}' @ {ts} (type={ent.get('type')})")
            
            # Find ALL related entries (same item, close timestamp)
            for j, other in enumerate(structured):
                if j in processed_indices or j == i:
                    continue
                if not other.get('item'):
                    continue
                if other['item'].lower() != item_lc:
                    continue
                if not isinstance(other.get('timestamp'), datetime.datetime):
                    continue
                    
                # Skip if other is a 'purchased' - those are always standalone
                if other['type'] == 'purchased':
                    continue
                    
                dt = abs((other['timestamp'] - ts).total_seconds())
                # Use wider window for withdrew, normal for others
                if other['type'] == 'withdrew' and dt <= max_dt_withdrew:
                    cluster.append(other)
                    processed_indices.add(j)
                elif dt <= max_dt_normal:
                    cluster.append(other)
                    processed_indices.add(j)
            
            # Store cluster (without price in key for non-purchased events)
            ts_key = int(ts.timestamp())
            cluster_key = (item_lc, ts_key, None, 0)  # Price is None for non-purchased clusters
            if cluster_key not in clusters_dict:
                clusters_dict[cluster_key] = cluster
            else:
                # Merge with existing cluster (shouldn't happen with processed_indices tracking)
                clusters_dict[cluster_key].extend(cluster)
        
        # Step 2: Process each cluster and determine if it should be saved
        tx_candidates = []
        created_clusters = set()  # dedupe final transactions
        
        for cluster_key, cluster_entries in clusters_dict.items():
            item_lc = cluster_key[0]
            ts_key = cluster_key[1]
            price_key = cluster_key[2] if len(cluster_key) > 2 else None
            if not cluster_entries:
                continue
                
            # Check if cluster has at least one anchor type
            types_in_cluster = {e['type'] for e in cluster_entries}
            has_anchor = bool(types_in_cluster & primary_types_global)
            
            # Only process clusters with anchor types
            if not has_anchor:
                if self.debug:
                    item_name = cluster_entries[0].get('item', 'unknown')
                    log_debug(f"[CLUSTER] Skip '{item_name}' - no anchor types (has: {types_in_cluster}, need: {primary_types_global})")
                continue
            
            # Check timestamp is in allowed range
            cluster_ts = cluster_entries[0]['timestamp']
            if allowed_ts and cluster_ts not in allowed_ts:
                if self.debug:
                    item_name = cluster_entries[0].get('item', 'unknown')
                    log_debug(f"[CLUSTER] Skip '{item_name}' - timestamp not in allowed range")
                continue
            
            # Use first entry as representative "ent" for anchor logic
            # CRITICAL: Prefer 'transaction' as anchor over 'listed' (transaction = confirmed event, listed = intent)
            related = cluster_entries  # ALL entries in the cluster
            transaction_entries = [r for r in related if r['type'] == 'transaction']
            if transaction_entries:
                transaction_entries_sorted = sorted(
                    transaction_entries,
                    key=lambda r: ((r.get('qty') or 0), (r.get('price') or 0)),
                    reverse=True
                )
                for pos, entry in enumerate(transaction_entries_sorted):
                    entry['_occurrence_slot'] = pos
                transaction_entry = transaction_entries_sorted[0]
            else:
                transaction_entries_sorted = []
                transaction_entry = None
            listed_entry = next((r for r in related if r['type'] == 'listed'), None)
            
            # Anchor priority: transaction > purchased > placed > listed
            if transaction_entry:
                ent = transaction_entry
            elif any(r['type'] == 'purchased' for r in related):
                ent = next(r for r in related if r['type'] == 'purchased')
            elif any(r['type'] == 'placed' for r in related):
                ent = next(r for r in related if r['type'] == 'placed')
            else:
                ent = cluster_entries[0]
            
            # On sell overview, skip listed-only clusters UNLESS UI metrics show completed sales
            if wtype == 'sell_overview' and not transaction_entry and listed_entry and ent['type'] == 'listed':
                # Check if UI metrics show salesCompleted > 0 for this item (fast collect scenario)
                has_sell_ui_evidence = False
                item_lc_check = (ent.get('item') or '').lower()
                if item_lc_check in ui_sell:
                    sc = ui_sell[item_lc_check].get('salesCompleted', 0) or 0
                    if sc > 0:
                        has_sell_ui_evidence = True
                        if self.debug:
                            log_debug(f"[UI-EVIDENCE] Item '{ent.get('item')}' has salesCompleted={sc} - allowing sell without transaction line (fast collect scenario)")
                
                if not has_sell_ui_evidence:
                    if self.debug:
                        log_debug(f"[CLUSTER] Skip 'listed'-only for '{ent.get('item')}' on sell_overview (no transaction)")
                    continue
            # determine case from related types (keep placed/listed separate) and window type
            types_present = {r['type'] for r in related}
            # Do not infer additional types from raw; rely on structured related entries only
            has_listed = 'listed' in types_present
            has_placed = 'placed' in types_present
            has_withdrew = 'withdrew' in types_present
            has_purchased = 'purchased' in types_present

            # Determine transaction side with strong text anchors first, fallback to window type
            side = None
            # Prefer explicit 'sold' over any 'purchased' presence when both appear due to OCR merges
            if side is None and ent.get('sold_flag'):
                side = 'sell'
            if side is None:
                try:
                    raw_text = (ent.get('raw') or '').lower()
                    if re.search(r'\bsold\b', raw_text):
                        side = 'sell'
                except Exception:
                    pass
            if side is None and (has_purchased or ent['type'] == 'purchased'):
                side = 'buy'
            # If only sell-side signals are present (listed/withdrew) and no buy-side (placed/purchased), treat as sell even on buy_overview
            if side is None and (has_listed or has_withdrew) and not (has_placed or has_purchased):
                side = 'sell'
            # If both placed and transaction are present for the same item at the same timestamp, it's very likely a buy-side collect/relist showing in a merged snapshot
            if side is None and has_placed and 'transaction' in types_present:
                side = 'buy'
            # Additional hint: on sell_overview, if we see a placed+transaction cluster for the same item,
            # classify as buy to avoid misclassifying buys shown due to merged frames.
            if side is None and wtype == 'sell_overview' and has_placed and 'transaction' in types_present:
                side = 'buy'
            # CRITICAL: On sell_overview, if we see 'placed' or 'purchased' (even alone), it's a BUY event
            # This handles timing issues where user switched tabs but buy events are still in the visible log
            if side is None and wtype == 'sell_overview' and (has_placed or has_purchased):
                side = 'buy'
                # Check if this is a placed-only event (transaction line already gone)
                has_transaction_same = any(r['type'] == 'transaction' for r in related)
                if has_placed and not has_transaction_same and self.debug:
                    log_debug(f"[MIXED CONTEXT] ⚠️ Detected 'placed' without 'transaction' on sell_overview for '{ent.get('item')}' - transaction line may have been missed due to fast actions!")
                elif self.debug:
                    log_debug(f"[MIXED CONTEXT] Detected buy event (placed/purchased) on sell_overview for '{ent.get('item')}' - treating as buy")
            # If the anchor itself is a placed/listed without purchased and window is buy_overview, bias to buy (after sell-only check)
            if side is None and wtype == 'buy_overview' and ent['type'] in ('placed', 'listed') and not (has_purchased or has_withdrew):
                side = 'buy'
            
            # IMPROVED: Use item category for historical transactions (when no clear anchors)
            # This handles cases like "Transaction of Crystal of Void Destruction" on buy_overview (was a SELL 3min ago)
            # OR "Transaction of Crystallized Despair" on sell_overview (was a BUY just now)
            if side is None and 'transaction' in types_present and not (has_purchased or has_placed or has_listed):
                from utils import get_item_likely_type
                likely_type = get_item_likely_type(ent.get('item', ''))
                if likely_type in ('buy', 'sell'):
                    side = likely_type
                    if self.debug:
                        log_debug(f"[HISTORICAL] Determined side={side} for '{ent['item']}' via item category")
            
            # Final fallback: use window type
            if side is None:
                side = 'sell' if wtype == 'sell_overview' else 'buy'
            if self.debug:
                log_debug(f"anchor item='{ent['item']}' ts={ent['timestamp']} types={types_present} -> side={side}")

            # Case resolution depends on side
            if side == 'sell':
                # Strict requirement: only consider sell cases when an explicit 'transaction' anchor is present
                # EXCEPTION: If UI metrics show salesCompleted > 0, allow sell even without transaction line
                has_transaction_anchor = any(r['type'] == 'transaction' for r in related) or ent['type'] == 'transaction'
                
                # Check UI evidence for fast collect scenarios (transaction line scrolled off)
                has_sell_ui_evidence_anchor = False
                if not has_transaction_anchor:
                    item_lc_check = (ent.get('item') or '').lower()
                    if item_lc_check in ui_sell:
                        sc = ui_sell[item_lc_check].get('salesCompleted', 0) or 0
                        if sc > 0:
                            has_sell_ui_evidence_anchor = True
                            if self.debug:
                                log_debug(f"[UI-EVIDENCE] Allowing sell for '{ent['item']}' with UI evidence (salesCompleted={sc}) despite missing transaction line")
                
                if not has_transaction_anchor and not has_sell_ui_evidence_anchor:
                    if self.debug:
                        log_debug(f"skip sell without transaction anchor for item='{ent['item']}' on {wtype}")
                    continue
                
                # Additional check: If on buy_overview and this is a SELL transaction,
                # verify it's not misclassified using the item category whitelist
                if wtype == 'buy_overview':
                    from utils import get_item_likely_type
                    likely_type = get_item_likely_type(ent.get('item', ''))
                    if likely_type == 'buy':
                        # This item is most_likely_buy, but we're processing as SELL on buy_overview
                        # -> Skip (wrong context, historical transaction on wrong tab)
                        if self.debug:
                            log_debug(f"skip sell transaction for '{ent['item']}' on buy_overview - item is most_likely_buy (wrong context)")
                        continue
                # Quantity-aware decision: if we have both listed and transaction but no withdrew,
                # and their quantities differ, treat as partial relist (common OCR case without explicit 'withdrew').
                tx_qty_rel = next((r.get('qty') for r in related if r.get('type') == 'transaction' and r.get('qty')), None)
                listed_qty_rel = next((r.get('qty') for r in related if r.get('type') == 'listed' and r.get('qty')), None)
                if has_listed and has_withdrew:
                    case = 'relist_partial'
                elif has_listed:
                    if tx_qty_rel is not None and listed_qty_rel is not None and listed_qty_rel != tx_qty_rel:
                        case = 'relist_partial'
                    else:
                        case = 'relist_full'
                else:
                    case = 'collect'
            else:  # buy side
                # Buy overview rules refined:
                # - Consider only placed/listed/withdrew of the SAME item as the anchor.
                # - Purchased/Transaction alone => collect
                # - (Placed OR Listed of same item) + Withdrew of same item => relist_partial
                # - (Placed OR Listed of same item) without withdrew => relist_full
                # Identify whether we have placed/listed/withdrew matching the anchor item
                anchor_item_lc = (ent['item'] or '').lower()
                def same_item(r):
                    return (r.get('item') or '').lower() == anchor_item_lc if anchor_item_lc else False
                # CRITICAL: Only consider listed/placed events with qty (from transaction log)
                # UI-Overview events have qty=None and should NOT trigger preorder-only detection
                has_listed_same = any(r['type'] == 'listed' and same_item(r) and r.get('qty') is not None for r in related)
                has_placed_same = any(r['type'] == 'placed' and same_item(r) and r.get('qty') is not None for r in related)
                has_withdrew_same = any(r['type'] == 'withdrew' and same_item(r) for r in related)
                # In buy_overview, a 'transaction' line is effectively a completed buy, treat it same as 'purchased'
                has_bought_same = (
                    any(r['type'] in ('purchased','transaction') and same_item(r) for r in related)
                    or ent['type'] in ('purchased','transaction')
                )
                relist_flag_same = has_listed_same or has_placed_same
                
                # CRITICAL: Placed/Listed + Withdrew WITHOUT Transaction/Purchased = Preorder Management (NOT a buy!)
                # BUT: Placed/Listed ALONE (without withdrew) can be a historical order → allow it
                # Only skip if BOTH relist_flag AND withdrew are present without actual purchase
                if relist_flag_same and has_withdrew_same and not has_bought_same:
                    if self.debug:
                        log_debug(f"skip preorder-only (placed+withdrew without transaction) for item='{ent['item']}' - no actual purchase")
                    continue
                
                if relist_flag_same:
                    case = 'relist_partial' if has_withdrew_same else 'relist_full'
                else:
                    case = 'collect'

                # Additional inference: If there is a placed + withdrew pair for same item but no purchased/transaction,
                # infer a partial buy ONLY if both entries share the SAME unit price (indicates same order, not cancel+reorder).
                # Purchased quantity = placed_qty − withdrew_qty (>0). Treat as collect.
                if not has_bought_same and has_placed_same and has_withdrew_same:
                    placed_entry = next((r for r in related if r['type'] == 'placed' and same_item(r)), None)
                    withdrew_entry = next((r for r in related if r['type'] == 'withdrew' and same_item(r)), None)
                    if placed_entry and withdrew_entry and placed_entry.get('qty') and withdrew_entry.get('qty'):
                        # compute unit prices and require both to exist and match
                        unit_p = None
                        unit_w = None
                        try:
                            if placed_entry.get('price') and placed_entry['qty'] > 0 and placed_entry['price'] % placed_entry['qty'] == 0:
                                up = placed_entry['price'] // placed_entry['qty']
                                if self._is_unit_price_plausible(placed_entry.get('item') or ent.get('item'), up):
                                    unit_p = up
                        except Exception:
                            unit_p = None
                        try:
                            if withdrew_entry.get('price') and withdrew_entry['qty'] > 0 and withdrew_entry['price'] % withdrew_entry['qty'] == 0:
                                uw = withdrew_entry['price'] // withdrew_entry['qty']
                                if self._is_unit_price_plausible(withdrew_entry.get('item') or ent.get('item'), uw):
                                    unit_w = uw
                        except Exception:
                            unit_w = None
                        # Only infer a buy if unit prices are present and equal (same order/price);
                        # otherwise this is likely a cancel+reorder scenario.
                        if unit_p is not None and unit_w is not None and unit_p == unit_w:
                            inferred_qty = placed_entry['qty'] - withdrew_entry['qty']
                            if inferred_qty and inferred_qty > 0:
                                price_inferred = unit_p * inferred_qty
                                # set buy anchor flag so downstream logic accepts it
                                has_bought_same = True
                                # set quantities/prices on ent for downstream selection
                                ent['qty'] = inferred_qty
                                ent['price'] = price_inferred
                                # mark a synthetic anchor so later relist checks accept
                                ent['_inferred_buy_anchor'] = True
                        else:
                            if self.debug:
                                log_debug(f"skip placed-withdrew inference for item='{anchor_item_lc}' due to unit mismatch or missing units: unit_p={unit_p}, unit_w={unit_w}")
                
                # CRITICAL FIX: Inference from single 'placed' without 'withdrew' or 'transaction'
                # When the transaction line falls out of the visible log due to fast actions,
                # we can infer a completed buy from UI metrics (ordersCompleted > 0)
                # This handles cases like Lion Blood relist where only "Placed order" is visible
                # NOTE: This ONLY works on buy_overview where UI metrics are visible!
                if not has_bought_same and has_placed_same and not has_withdrew_same and wtype == 'buy_overview':
                    placed_entry = next((r for r in related if r['type'] == 'placed' and same_item(r)), None)
                    if placed_entry and placed_entry.get('qty') and placed_entry.get('price'):
                        # Check UI metrics for ordersCompleted
                        item_lc_check = anchor_item_lc
                        ui_metrics = ui_buy.get(item_lc_check)
                        if not ui_metrics:
                            # Try fuzzy matching for UI metrics (OCR errors in item names)
                            corrected_name = correct_item_name(anchor_item_lc)
                            if corrected_name:
                                ui_metrics = ui_buy.get(corrected_name.lower())
                        
                        if ui_metrics:
                            orders_completed = ui_metrics.get('ordersCompleted', 0)
                            if orders_completed > 0:
                                # Transaction happened! Infer bought quantity from ordersCompleted
                                inferred_qty = orders_completed
                                # Calculate unit price from placed order
                                unit_p = None
                                try:
                                    if placed_entry['price'] > 0 and placed_entry['qty'] > 0 and placed_entry['price'] % placed_entry['qty'] == 0:
                                        up = placed_entry['price'] // placed_entry['qty']
                                        if self._is_unit_price_plausible(placed_entry.get('item') or ent.get('item'), up):
                                            unit_p = up
                                except Exception:
                                    unit_p = None
                                
                                if unit_p is not None and inferred_qty > 0:
                                    price_inferred = unit_p * inferred_qty
                                    # set buy anchor flag so downstream logic accepts it
                                    has_bought_same = True
                                    # set quantities/prices on ent for downstream selection
                                    ent['qty'] = inferred_qty
                                    ent['price'] = price_inferred
                                    # mark a synthetic anchor so later relist checks accept
                                    ent['_inferred_buy_anchor'] = True
                                    # Update case based on whether all were bought or partial
                                    if inferred_qty >= placed_entry['qty']:
                                        case = 'collect'  # All bought
                                    else:
                                        case = 'relist_full'  # Partial buy, rest remains as order
                                    if self.debug:
                                        log_debug(f"[INFERENCE] Single 'placed' for '{anchor_item_lc}' with ordersCompleted={orders_completed} → inferred buy {inferred_qty}x @ {unit_p} = {price_inferred}")
                                elif self.debug:
                                    log_debug(f"[INFERENCE] Cannot infer for '{anchor_item_lc}' - unit_p={unit_p}, inferred_qty={inferred_qty}")
                        elif self.debug:
                            log_debug(f"[INFERENCE] No UI metrics found for '{anchor_item_lc}' (checked: {list(ui_buy.keys())[:5]}...)")
                # Merge rule: If we have a placed+withdrew inference for qty, but there is also a transaction line for the
                # same item at this timestamp with a total price (even if without qty), prefer that transaction price with
                # the inferred quantity. This avoids undercounting totals when OCR merges sell/buy text blocks.
                if (has_placed_same or has_listed_same) and has_withdrew_same:
                    tx_price_only = next((r.get('price') for r in related if r.get('type') == 'transaction' and r.get('price')), None)
                    if tx_price_only and (ent.get('qty') or any(r.get('qty') for r in related if r.get('type') in ('placed','withdrew'))):
                        if ent.get('qty') is None:
                            # set inferred qty if not already set
                            placed_entry = next((r for r in related if r['type'] == 'placed' and same_item(r)), None)
                            withdrew_entry = next((r for r in related if r['type'] == 'withdrew' and same_item(r)), None)
                            if placed_entry and withdrew_entry and placed_entry.get('qty') and withdrew_entry.get('qty'):
                                ent['qty'] = placed_entry['qty'] - withdrew_entry['qty']
                        if ent.get('qty'):
                            ent['price'] = tx_price_only
                # If transaction qty is missing but we have a placed qty for same item and no withdrew (i.e., full fill), use placed qty
                if (not has_bought_same or (ent.get('qty') is None)) and has_placed_same and not has_withdrew_same:
                    placed_entry = next((r for r in related if r['type'] == 'placed' and same_item(r) and r.get('qty')), None)
                    if placed_entry and (ent.get('qty') is None or ent.get('qty') <= 0):
                        ent['qty'] = placed_entry['qty']

            # final transaction type strictly from side; do not override with presence of listed/placed
            final_type = side
            ui_backfill_needed = False

            # On buy overview, avoid saving sell-side entries unless there is a strong sell cluster OR item is known to be sell-side
            # Allow sell saves if:
            # 1. The same item has 'transaction' AND 'listed' (clear sell pattern), OR
            # 2. The item is in most_likely_sell category (historical transaction without listed)
            if wtype == 'buy_overview' and final_type == 'sell':
                anchor_item_lc = (ent['item'] or '').lower()
                def same_item3(r):
                    return (r.get('item') or '').lower() == anchor_item_lc if anchor_item_lc else False
                has_tx_same = any(r['type'] == 'transaction' and same_item3(r) for r in related)
                has_listed_same = any(r['type'] == 'listed' and same_item3(r) for r in related)
                
                # Check if item is categorized as sell-side
                from utils import get_item_likely_type
                likely_type = get_item_likely_type(ent.get('item', ''))
                is_known_sell = (likely_type == 'sell')
                
                # Allow if either: (tx+listed cluster) OR (known sell item)
                if not ((has_tx_same and has_listed_same) or is_known_sell):
                    if self.debug:
                        log_debug(f"skip sell-side on buy_overview for item='{ent['item']}' (no tx+listed cluster, not in sell category)")
                    continue
                elif is_known_sell and self.debug:
                    log_debug(f"[HISTORICAL] Allowing sell transaction for '{ent['item']}' on buy_overview (most_likely_sell category)")

            # Prefer transaction/purchased qty+price over listed/placed to avoid using 'Listed for ... Silver' in sell-side
            quantity = ent['qty'] or None
            price = ent['price'] or None
            item_name = ent.get('item') or ""
            if final_type == 'sell':
                # Try to override with a related transaction's values
                # CRITICAL: Prioritize transaction price even if qty is None (price is more reliable in merged OCR text)
                tx_rel = transaction_entry if transaction_entry else None
                if tx_rel is None:
                    tx_rel = next((r for r in related if r['type'] == 'transaction'), None)
                if tx_rel is not None:
                    if tx_rel.get('qty'):
                        quantity = tx_rel['qty']
                    # CRITICAL FIX: Always use transaction price if available (even when qty is None)
                    if tx_rel.get('price'):
                        price = tx_rel['price']
                
                # CRITICAL: If NO transaction line (missing qty or price), use UI metrics directly
                # This handles fast collect scenarios where transaction line scrolled off before OCR scan
                if (quantity is None or price is None or price <= 0 or first_snapshot_mode):
                    try:
                        item_name_raw = item_name
                        item_lc2 = item_name_raw.lower()
                        m_ui = ui_sell.get(item_lc2) if 'ui_sell' in locals() else None
                        if (not m_ui) and 'ui_sell_norm' in locals():
                            m_ui = ui_sell_norm.get(_norm_key(item_name_raw))
                        
                        if m_ui:
                            sc = m_ui.get('salesCompleted') or 0
                            unit_price = m_ui.get('price') or 0
                            
                            if sc > 0 and unit_price > 0:
                                # Calculate quantity from UI if missing
                                if quantity is None or quantity <= 0:
                                    quantity = sc
                                    if self.debug:
                                        log_debug(f"[UI-FALLBACK] Using salesCompleted={sc} for quantity (no transaction line)")
                                
                                # Calculate price from UI. For first snapshot, treat entire line as UI-derived baseline.
                                if price is None or price <= 0 or first_snapshot_mode:
                                    price_calc = unit_price * quantity * 0.88725
                                    price = int(round(price_calc))
                                    tx['_ui_inferred'] = True
                                    if self.debug:
                                        log_debug(f"[UI-FALLBACK] Calculated sell price from UI: {quantity}x * {unit_price} * 0.88725 = {price_calc:.0f} → {price:,}")
                    except Exception as e:
                        if self.debug:
                            log_debug(f"[UI-FALLBACK] Failed for sell event: {e}")
                
                # If price seems truncated (missing leading digit) use UI metrics (per-unit price) to correct:
                # expected_net = unit_price * quantity * 0.88725, and only adjust if expected endswith current price.
                elif quantity and price:
                    try:
                        item_name_raw = item_name
                        item_lc2 = item_name_raw.lower()
                        m_ui = ui_sell.get(item_lc2) if 'ui_sell' in locals() else None
                        if (not m_ui) and 'ui_sell_norm' in locals():
                            m_ui = ui_sell_norm.get(_norm_key(item_name_raw))
                        if m_ui and quantity:
                            unit_price = m_ui.get('price') or 0
                            if unit_price > 0:
                                expected_net = int(round(unit_price * quantity * 0.88725))
                                if expected_net > price:
                                    pstr = str(int(price))
                                    if str(expected_net).endswith(pstr):
                                        price = expected_net
                                        if self.debug:
                                            log_debug(f"[UI-CORRECTION] Corrected truncated sell price: {pstr} → {price:,}")
                    except Exception:
                        pass
            elif final_type == 'buy':
                # Prefer 'purchased' values; if both purchased and transaction exist for same item/ts and differ, we will save both entries.
                # CRITICAL: Don't require qty/price to select entries - we want transaction price even if qty is None
                pur_rel = next((r for r in related if r['type'] == 'purchased'), None)
                tx_rel_same = transaction_entry if transaction_entry else None
                if tx_rel_same is None:
                    tx_rel_same = next((r for r in related if r['type'] == 'transaction'), None)
                if pur_rel is not None:
                    if pur_rel.get('qty'):
                        quantity = pur_rel['qty']
                    if pur_rel.get('price'):
                        price = pur_rel['price']
                elif tx_rel_same is not None:
                    if tx_rel_same.get('qty'):
                        quantity = tx_rel_same['qty']
                    # CRITICAL FIX: Always use transaction price if available (even when qty is None)
                    if tx_rel_same.get('price'):
                        price = tx_rel_same['price']
                else:
                    # If we inferred a buy from placed-withdrew above, use ent's qty/price as inferred values
                    if ent.get('qty') and (quantity is None or quantity <= 0):
                        quantity = ent['qty']
                    if ent.get('price') and (price is None or price <= 0):
                        price = ent['price']
                # If on buy_overview and this is a buy, check if we have buy anchors
                # Note: This check should only apply to BUY transactions, not SELL transactions on buy_overview!
                if wtype == 'buy_overview' and final_type == 'buy':
                    anchor_item_lc = (ent['item'] or '').lower()
                    def same_item3(r):
                        return (r.get('item') or '').lower() == anchor_item_lc if anchor_item_lc else False
                    has_any_buy_anchor = any(r['type'] in ('purchased','placed','withdrew') and same_item3(r) for r in related)
                    
                    # CRITICAL FIX: Check if this transaction is NEW (from delta detection)
                    # NEW transactions don't need whitelist validation - tab position is sufficient proof!
                    # Only HISTORICAL transactions (already in baseline) need whitelist check.
                    is_new_transaction = False
                    if self.last_overview_text:
                        # Check if this transaction was in the previous OCR baseline
                        # Use the same pattern-based matching as delta detection
                        try:
                            pattern = self._compile_transaction_pattern(ent.get('item'), quantity, price)
                            was_in_baseline = pattern.search(self.last_overview_text) is not None
                            is_new_transaction = not was_in_baseline

                            if is_new_transaction and self.debug:
                                log_debug(f"[NEW-TX] '{ent['item']}' is NEW (not in baseline) - skipping whitelist check")
                        except Exception:
                            # If pattern match fails, assume it's new to be safe
                            is_new_transaction = True
                    else:
                        # No baseline yet - treat as new
                        is_new_transaction = True
                    
                    # Historical transaction detection (only for OLD transactions):
                    # If no buy anchors found AND this is a HISTORICAL transaction (was in baseline),
                    # check if this could be from the old log (where "Purchased" line already fell out).
                    # Use item category whitelist (most_likely_buy/most_likely_sell) to infer type.
                    if not has_any_buy_anchor and not is_new_transaction:
                        from utils import get_item_likely_type
                        likely_type = get_item_likely_type(ent.get('item', ''))
                        
                        if likely_type == 'buy':
                            # This item is most likely bought (not sold) -> Accept as historical buy
                            if self.debug:
                                log_debug(f"[HISTORICAL] Transaction of '{ent['item']}' likely BUY (from whitelist) - treating as old log entry")
                        elif likely_type == 'sell':
                            # This item is most likely sold -> Skip (wrong context)
                            if self.debug:
                                log_debug(f"skip buy transaction for '{ent['item']}' - item is most_likely_sell (wrong context)")
                            continue
                        else:
                            # Unknown item, no category -> Skip (ambiguous)
                            if self.debug:
                                log_debug(f"skip buy transaction-only without anchors for item='{ent['item']}' on buy_overview (no category match, HISTORICAL)")
                            continue
                    elif not has_any_buy_anchor and is_new_transaction and self.debug:
                        # NEW transaction without anchors - this is normal for collect button transactions!
                        log_debug(f"[NEW-TX] Allowing NEW transaction of '{ent['item']}' without anchors (tab position = proof)")
                # If price is still missing but we have quantity and unit candidates from placed/withdrew, compute expected total instead of taking placed total
                if (price is None or price <= 0) and (quantity is not None and quantity > 0):
                    # Prefer unit from withdrew (often exact), else from placed
                    unit_from_withdrew = None
                    unit_from_placed = None
                    for r in related:
                        rq, rp = r.get('qty'), r.get('price')
                        if r.get('type') == 'withdrew' and rq and rp and rq > 0 and rp % rq == 0:
                            unit = rp // rq
                            if self._is_unit_price_plausible(r.get('item') or ent.get('item'), unit):
                                unit_from_withdrew = unit
                        if r.get('type') == 'placed' and rq and rp and rq > 0 and rp % rq == 0:
                            unit = rp // rq
                            if self._is_unit_price_plausible(r.get('item') or ent.get('item'), unit):
                                unit_from_placed = unit if unit_from_placed is None else unit_from_placed
                    unit = unit_from_withdrew if unit_from_withdrew is not None else unit_from_placed
                    if unit is not None:
                        price = unit * quantity
                # Additional correction for dropped leading digits in buy totals:
                # If we have a price that's not divisible by quantity, try adding a common OCR-missed leading chunk (10M/100M/1B)
                # and accept the first that yields an integral, plausible unit.
                if price and quantity and quantity > 0 and (price % quantity) != 0:
                    guide_unit = None
                    # prefer using a known unit from placed/withdrew as guidance if available
                    for r in related:
                        rq, rp = r.get('qty'), r.get('price')
                        if r.get('type') in ('withdrew', 'placed') and rq and rp and rq > 0 and rp % rq == 0:
                            u = rp // rq
                            if self._is_unit_price_plausible(r.get('item') or ent.get('item'), u):
                                guide_unit = u
                                break
                    bump_candidates = [2_000_000_000, 1_000_000_000, 100_000_000, 10_000_000]
                    chosen = None
                    for bump in bump_candidates:
                        newp = price + bump
                        if newp % quantity == 0:
                            unit = newp // quantity
                            if self._is_unit_price_plausible(ent.get('item'), unit):
                                if guide_unit is None or abs(unit - guide_unit) <= max(guide_unit // 10, 1):
                                    chosen = newp
                                    break
                    if chosen is None:
                        # fallback: accept the first divisible/plausible even without guide
                        for bump in bump_candidates:
                            newp = price + bump
                            if newp % quantity == 0:
                                unit = newp // quantity
                                if self._is_unit_price_plausible(ent.get('item'), unit):
                                    chosen = newp
                                    break
                    if chosen is not None:
                        price = chosen

                    corrected_buy = self._restore_total_with_base_price(item_name, quantity, price)
                    if corrected_buy is not None:
                        price = corrected_buy

            # Apply fallback price reconstruction using UI metrics when allowed and necessary
            try:
                # UI-Fallback für fehlende/ungültige Preise (z.B. wenn Itemname zu lang und Preis abgeschnitten)
                # Prüfe auf unrealistische Preise mittels BDO Market API (min/max bounds)
                needs_fallback = (price is None or price <= 0)
                if not needs_fallback and quantity is not None and quantity > 0 and price:
                    # Prüfe ob Preis plausibel ist gemäß BDO Market API min/max ranges
                    try:
                        plausibility = check_price_plausibility(item_name, quantity, price, tx_side=final_type)
                        if not plausibility.get('plausible', True):
                            reason = plausibility.get('reason', 'unknown')
                            expected_min = plausibility.get('expected_min')
                            expected_max = plausibility.get('expected_max')
                            
                            # Wenn Preis deutlich außerhalb der erwarteten Range → UI-Fallback versuchen
                            if reason in ('too_low', 'too_high'):
                                if self.debug:
                                    log_debug(f"[PRICE-IMPLAUSIBLE] '{item_name}' {quantity}x @ {price:,}: {reason} (expected: {expected_min:,} - {expected_max:,}) - attempting UI fallback")
                                needs_fallback = True
                    except Exception as e:
                        # API-Check fehlgeschlagen, weiter mit geparsten Preis
                        if self.debug:
                            log_debug(f"[PRICE] API check failed for '{item_name}': {e}")
                
                # CRITICAL: Erkenne ABGESCHNITTENE Preise (lange Itemnamen)
                # Beispiel: "Transaction of Very Long Item Name x100 worth 1,234,567..." 
                # OCR sieht: price=1234567, aber echter Preis ist 1234567890
                # Prüfe gegen UI-Metriken ob Unit-Preis plausibel ist
                if not needs_fallback and price and quantity and quantity > 0 and wtype == 'buy_overview' and final_type == 'buy':
                    item_lc_check = (ent.get('item') or '').lower()
                    if item_lc_check in ui_buy:
                        m = ui_buy[item_lc_check]
                        orders = m.get('orders') or 0
                        oc = m.get('ordersCompleted') or 0
                        rem = m.get('remainingPrice') or 0
                        denom = max(0, orders - oc)
                        
                        # Berechne erwarteten Unit-Preis aus UI
                        if rem > 0 and denom > 0:
                            expected_unit = rem / denom
                            parsed_unit = price / quantity
                            
                            # Wenn geparster Unit-Preis viel kleiner ist als UI Unit-Preis → abgeschnitten!
                            # Beispiel: parsed=12345 aber expected=12345678 → Faktor ~1000x
                            if expected_unit > parsed_unit * 10:  # Mindestens 10x Unterschied
                                if self.debug:
                                    log_debug(f"[PRICE-TRUNCATED] Detected truncated price for '{item_name}': parsed={price:,} (unit={parsed_unit:.0f}) but UI suggests unit={expected_unit:.0f} - using UI fallback")
                                needs_fallback = True
                
                # CRITICAL: Erkenne ABGESCHNITTENE Preise auch für SELL-Seite
                # Gleiche Logik wie für Buy, nur mit sell_overview und ui_sell
                if not needs_fallback and price and quantity and quantity > 0 and wtype == 'sell_overview' and final_type == 'sell':
                    item_lc_check = (ent.get('item') or '').lower()
                    if item_lc_check in ui_sell:
                        m = ui_sell[item_lc_check]
                        pr = m.get('price') or 0  # Unit-Preis
                        
                        if pr > 0:
                            parsed_unit = price / quantity
                            expected_unit_after_tax = pr * 0.88725
                            
                            # Wenn geparster Unit-Preis viel kleiner ist als erwartet → abgeschnitten!
                            if expected_unit_after_tax > parsed_unit * 10:  # Mindestens 10x Unterschied
                                if self.debug:
                                    log_debug(f"[PRICE-TRUNCATED] Detected truncated price for '{item_name}': parsed={price:,} (unit={parsed_unit:.0f}) but UI suggests unit={expected_unit_after_tax:.0f} - using UI fallback")
                                needs_fallback = True
                
                # CRITICAL: Bei Relist-Cases muss die TRANSACTION-Menge verwendet werden, NICHT ordersCompleted!
                # Beispiel: Placed 1000x, Withdrew 912x, Transaction 88x → UI zeigt ordersCompleted=1000
                # aber Transaction-Preis ist für 88x, NICHT für 1000x!
                # Lösung: Verwende quantity aus Transaction-Zeile statt ordersCompleted aus UI
                if needs_fallback and (not first_snapshot_mode):
                    item_lc = (ent.get('item') or '').lower()
                    price_success = False
                    
                    # BUY-Seite: Verwende UI-Metriken zur Preisberechnung
                    if wtype == 'buy_overview' and final_type == 'buy' and item_lc in ui_buy:
                        m = ui_buy[item_lc]
                        orders = m.get('orders') or 0
                        oc = m.get('ordersCompleted') or 0
                        rem = m.get('remainingPrice') or 0
                        denom = max(0, orders - oc)
                        
                        # Bei Relist/Collect: Verwende quantity aus Transaction (tatsächlich gekaufte Menge)
                        # Bei anderen Cases: Verwende ordersCompleted aus UI wenn quantity fehlt
                        if case in ('collect', 'relist_full', 'relist_partial'):
                            effective_qty = quantity if quantity and quantity > 0 else oc
                        else:
                            effective_qty = oc
                        
                        if effective_qty > 0 and rem > 0 and denom > 0:
                            # effective_qty * (remainingPrice / (orders - ordersCompleted))
                            price_calc = effective_qty * (rem / denom)
                            if price_calc > 0:
                                price = int(round(price_calc))
                                price_success = True
                                if self.debug:
                                    log_debug(f"[PRICE] UI fallback (buy, case={case}): qty={effective_qty} * ({rem}/{denom}) = {price_calc:.0f} → {price}")
                    
                    # SELL-Seite: Verwende UI-Metriken zur Preisberechnung
                    elif wtype == 'sell_overview' and final_type == 'sell' and item_lc in ui_sell:
                        m = ui_sell[item_lc]
                        sc = m.get('salesCompleted') or 0
                        pr = m.get('price') or 0
                        
                        # Bei Relist/Collect: Verwende quantity aus Transaction (tatsächlich verkaufte Menge)
                        # Bei anderen Cases: Verwende salesCompleted aus UI wenn quantity fehlt
                        if case in ('collect', 'relist_full', 'relist_partial'):
                            effective_qty = quantity if quantity and quantity > 0 else sc
                        else:
                            effective_qty = sc
                        
                        if effective_qty > 0 and pr > 0:
                            # effective_qty * price * 0.88725
                            price_calc = effective_qty * pr * 0.88725
                            if price_calc > 0:
                                price = int(round(price_calc))
                                price_success = True
                                if self.debug:
                                    log_debug(f"[PRICE] UI fallback (sell, case={case}): qty={effective_qty} * {pr} * 0.88725 = {price_calc:.0f} → {price}")
                    
                    # FALLBACK: Wenn UI-basierte Korrektur fehlschlägt, verwerfe den Eintrag
                    if not price_success and needs_fallback:
                        if self.debug:
                            log_debug(f"[PRICE-ERROR] UI fallback failed for '{item_name}' - discarding entry (no valid price available)")
                        continue
            except Exception:
                pass

            # Conservative sell timestamp alignment: when a transaction+listed/withdrew cluster is present in this scan
            # and the snapshot has a later timestamp, align to the latest snapshot time if the delta is small (<= 3 minutes).
            if final_type == 'sell' and isinstance(ent.get('timestamp'), datetime.datetime) and overall_max_ts is not None:
                try:
                    has_tx = any(r['type'] == 'transaction' for r in related)
                    has_rel = any(r['type'] in ('listed', 'withdrew') for r in related)
                    if has_tx and has_rel and ent['timestamp'] < overall_max_ts:
                        delta_sec = (overall_max_ts - ent['timestamp']).total_seconds()
                        if 0 < delta_sec <= 180:
                            ent['timestamp'] = overall_max_ts
                except Exception:
                    pass
            # Handle buy events: require anchor (purchased/transaction) unless there's UI evidence or first snapshot
            # EXCEPTION 1: On first_snapshot_mode, allow historical placed-only events (no transaction needed)
            # EXCEPTION 2: If UI metrics show ordersCompleted > 0, allow it even without anchor
            #              This handles fast window switches where placed event is visible but transaction already scrolled off
            # IMPORTANT: Apply this check for buy events regardless of window type (buy_overview OR sell_overview)
            #            because fast tab switches can cause buy events to appear on sell_overview
            if final_type == 'buy' and wtype in ('buy_overview', 'sell_overview'):
                anchor_item_lc = (ent['item'] or '').lower()
                def same_item2(r):
                    return (r.get('item') or '').lower() == anchor_item_lc if anchor_item_lc else False
                has_buy_anchor_same = any(r['type'] in ('purchased', 'transaction') and same_item2(r) for r in related) or ent['type'] in ('purchased', 'transaction')
                
                # Check if UI metrics show completed orders for this item
                # Look in ui_buy even if wtype is sell_overview (fast window switch scenario)
                has_ui_evidence = False
                ui_metrics_source = ui_buy if ui_buy else {}
                if anchor_item_lc in ui_metrics_source:
                    oc = ui_metrics_source[anchor_item_lc].get('ordersCompleted', 0) or 0
                    if oc > 0:
                        has_ui_evidence = True
                        if self.debug:
                            log_debug(f"[UI-EVIDENCE] Item '{ent['item']}' has ordersCompleted={oc} - allowing without transaction anchor (wtype={wtype})")
                
                # allow inferred anchors from placed-withdrew logic OR UI evidence
                if not has_buy_anchor_same and not ent.get('_inferred_buy_anchor'):
                    if has_ui_evidence:
                        ui_backfill_needed = True
                        if self.debug:
                            log_debug(f"[UI-EVIDENCE] Accepting '{ent['item']}' without anchor; will backfill price from UI")
                    else:
                        if self.debug:
                            log_debug(f"skip buy relist without purchase anchor for item='{ent['item']}' on buy_overview")
                        continue

            # Still fill missing values with type-aware rules
            # Quantity can be backfilled from any related entry (placed/purchased/transaction all OK)
            if quantity is None:
                for r in related:
                    if r.get('qty'):
                        quantity = r['qty']
                        break
            # Price backfill must be conservative to avoid using placed/listed totals for buys
            if price is None:
                if final_type == 'sell':
                    # For sells, only accept price from a transaction-related entry
                    tx_rel2 = next((r for r in related if r.get('type') == 'transaction' and r.get('price')), None)
                    if tx_rel2 is not None:
                        price = tx_rel2.get('price')
                else:
                    # For buys, only accept price from purchased or transaction entries
                    pur_rel2 = next((r for r in related if r.get('type') == 'purchased' and r.get('price')), None)
                    tx_rel2 = next((r for r in related if r.get('type') == 'transaction' and r.get('price')), None)
                    if pur_rel2 is not None:
                        price = pur_rel2.get('price')
                    elif tx_rel2 is not None:
                        price = tx_rel2.get('price')
            # Price correction using per-unit inference from related entries
            # Apply ONLY to buys to avoid mutating sell prices already parsed from 'worth ... Silver'.
            if final_type == 'buy':
                try:
                    unit_candidates = []
                    for r in related:
                        rq, rp = r.get('qty'), r.get('price')
                        if rq and rp and rq > 0:
                            # only accept integral units with reasonable bounds
                            if rp % rq == 0:
                                unit = rp // rq
                                if self._is_unit_price_plausible(r.get('item') or ent.get('item'), unit):
                                    unit_candidates.append(unit)
                    if unit_candidates and quantity:
                        unit_candidates = sorted(set(unit_candidates))
                        # build expected totals for each candidate
                        expected_totals = [(u, u * quantity) for u in unit_candidates]
                        # if we already have a price, try to find a best match
                        if price:
                            price_str = str(int(price))
                            m = len(price_str)
                            best = None
                            # 1) Prefer totals whose last m digits match observed price (missing leading digit case)
                            for u, et in expected_totals:
                                if str(et).endswith(price_str) and et > price:
                                    best = (u, et)
                                    break
                            # 2) Else pick the closest by absolute difference (within a few units)
                            if best is None:
                                best = min(expected_totals, key=lambda t: abs(t[1] - price))
                                u, et = best
                                # only adjust if reasonably close (<= one unit)
                                if abs(et - price) <= max(1, u):
                                    price = et
                                else:
                                    # common OCR miss: dropped leading 1 (roughly +1B or +100M for BDO-scale)
                                    if any(et - price == jump for jump in (10_000_000, 100_000_000, 1_000_000_000)) and et > price:
                                        price = et
                            else:
                                price = best[1]
                except Exception:
                    pass
            if quantity is None:
                quantity = 1
            
            # CRITICAL: Verwerfe Transaktionen ohne gültigen Preis
            # Verhindert dass OCR-Fehler mit fehlenden führenden Ziffern falsche Preise speichern
            # (z.B. "126,184" statt "585,585,000" bei qty=200)
            if price is None or price <= 0:
                if ui_backfill_needed:
                    price = None  # trigger UI fallback below
                else:
                    if self.debug:
                        log_debug(f"drop candidate: invalid/missing price ({price}) for item='{ent.get('item')}' qty={quantity}")
                    continue

            # Validate and correct item name before saving
            item_name = ent['item'] or ""
            
            # CRITICAL: Letzte Korrektur-Chance gegen Whitelist mit striktem Matching
            # Dies fängt OCR-Fehler wie "F Lion Blood" → "Lion Blood"
            try:
                corrected = correct_item_name(item_name, min_score=80)  # Etwas niedriger für OCR-Fehler
                if corrected and corrected != item_name:
                    if self.debug:
                        log_debug(f"[CORRECTION] Item name corrected: '{item_name}' → '{corrected}'")
                    item_name = corrected
            except Exception as e:
                if self.debug:
                    log_debug(f"[CORRECTION] Failed to correct '{item_name}': {e}")
            
            # STRICT VALIDATION: Nur Items die in item_names.csv stehen werden akzeptiert
            if not self._valid_item_name(item_name):
                if self.debug:
                    log_debug(f"drop candidate: invalid item name '{item_name}' for types={types_present}")
                continue
            
            # Quantity bounds check: MIN_ITEM_QUANTITY (1) bis MAX_ITEM_QUANTITY (5000)
            # Filtert unrealistische Werte (z.B. 0, negative, UI-Noise wie Collect-Amounts > 5000)
            if quantity < MIN_ITEM_QUANTITY or quantity > MAX_ITEM_QUANTITY:
                if self.debug:
                    log_debug(f"drop candidate: quantity {quantity} out of bounds [{MIN_ITEM_QUANTITY}, {MAX_ITEM_QUANTITY}] for item='{item_name}'")
                continue

            if final_type == 'buy' and not has_bought_same and not ent.get('_inferred_buy_anchor'):
                if not transaction_entries_sorted:
                    if isinstance(ent.get('timestamp'), datetime.datetime):
                        if transaction_exists_by_item_timestamp(item_name, ent['timestamp'], final_type, tolerance_seconds=1):
                            if self.debug:
                                log_debug(f"skip placed-only buy for '{item_name}' at {ent['timestamp']} (already recorded buy)" )
                            continue

            if transaction_entry:
                occurrence_slot = transaction_entry.get('_occurrence_slot', 0)
            else:
                occurrence_slot = ent.get('_occurrence_slot', 0) if ent else 0
            tx = {
                'item_name': item_name,
                'quantity': quantity,
                'price': price,
                'timestamp': ent['timestamp'],
                'transaction_type': final_type,
                'case': f"{final_type}_{case}",
                'raw_related': related,
                'occurrence_index': None,
                'occurrence_slot': occurrence_slot
            }
            # If this is buy-side and both purchased and transaction exist with different values, emit a second candidate for the other values.
            if final_type == 'buy' and pur_rel is not None and tx_rel_same is not None:
                alt_qty = tx_rel_same.get('qty') or quantity
                alt_price = tx_rel_same.get('price') or price
                if (alt_qty != quantity) or (alt_price != price):
                    tx_candidates.append({
                        'item_name': item_name,
                        'quantity': alt_qty or 0,
                        'price': alt_price or 0,
                        'timestamp': ent['timestamp'],
                        'transaction_type': final_type,
                        'case': f"{final_type}_{case}",
                        'raw_related': related,
                        'occurrence_index': None,
                        'occurrence_slot': occurrence_slot
                    })
            # Restrict saves after returning from buy item dialog.
            # Default: only items that are true buy anchors for this snapshot (purchased or transaction+placed/withdrew).
            # Exception: allow explicit SELL clusters (transaction+listed of same item) even on buy_overview,
            # especially on the first overview snapshot to import visible older sell lines.
            # ALSO: Allow if UI metrics show ordersCompleted > 0 (handled by earlier check at line 1695)
            if final_type == 'buy':
                has_buy_anchor = any(r['type'] in ('purchased', 'transaction') for r in related)
                
                # Check UI evidence again (same logic as earlier check)
                has_ui_evidence_final = False
                if not has_buy_anchor:
                    anchor_item_lc_final = (item_name or '').lower()
                    ui_metrics_final = ui_buy if ui_buy else {}
                    if anchor_item_lc_final in ui_metrics_final:
                        oc_final = ui_metrics_final[anchor_item_lc_final].get('ordersCompleted', 0) or 0
                        if oc_final > 0:
                            has_ui_evidence_final = True
                
                if not has_buy_anchor and ent.get('type') != 'purchased' and not has_ui_evidence_final:
                    if self.debug:
                        log_debug(f"skip buy without purchase/transaction anchor for item='{item_name}' on {wtype}")
                    continue
            if returning_from_item and prev_window == 'buy_item' and wtype == 'buy_overview':
                # Recompute anchor set similarly to above in case block scope differs
                anchor_set = set()
                try:
                    for (it_lc, ts_key), tset in items_ts_types.items():
                        if ('purchased' in tset) or ('transaction' in tset and (('placed' in tset) or ('withdrew' in tset))):
                            anchor_set.add(it_lc)
                except Exception:
                    anchor_set = set()
                itlc_cur = (tx['item_name'] or '').lower()
                allowed_by_anchor = (not anchor_set) or (itlc_cur in anchor_set)
                allowed_by_sell_cluster = False
                if tx.get('transaction_type') == 'sell':
                    rel = tx.get('raw_related', []) or []
                    has_tx_same = any(r.get('type') == 'transaction' and (r.get('item') or '').lower() == itlc_cur for r in rel)
                    has_listed_same = any(r.get('type') == 'listed' and (r.get('item') or '').lower() == itlc_cur for r in rel)
                    if has_tx_same and has_listed_same:
                        allowed_by_sell_cluster = True
                if not (allowed_by_anchor or allowed_by_sell_cluster):
                    if self.debug:
                        log_debug(f"skip unrelated item '{tx['item_name']}' on post-buy dialog overview (not a buy anchor; sell_cluster={allowed_by_sell_cluster})")
                    continue
            # On buy_overview, drop sell-side listed-only anchors for unrelated items to avoid false saves
            if (not first_snapshot_mode) and wtype == 'buy_overview' and final_type == 'sell' and ent['type'] == 'listed':
                # if none of the related entries are purchased/transaction for the same item, skip
                anchor_item_lc = (ent['item'] or '').lower()
                if not any((r['type'] in ('purchased', 'transaction') and (r.get('item') or '').lower() == anchor_item_lc) for r in related):
                    if self.debug:
                        log_debug(f"skip unrelated sell listed anchor on buy_overview for item='{ent['item']}'")
                    continue

            # Deduplicate per (item, timestamp) cluster to avoid double-saves when anchor appears multiple times (e.g., placed + transaction)
            try:
                ts_key = int(tx['timestamp'].timestamp()) if isinstance(tx['timestamp'], datetime.datetime) else str(tx['timestamp'])
            except Exception:
                ts_key = str(tx['timestamp'])
            # Include qty, price and final type in cluster key to allow multiple entries per item+timestamp when values differ
            cluster_key = (
                tx['item_name'].lower(),
                ts_key,
                int(tx.get('quantity') or 0),
                int(tx.get('price') or 0),
                tx.get('transaction_type'),
                int(tx.get('occurrence_slot') or 0),
            )
            if cluster_key in created_clusters:
                continue
            created_clusters.add(cluster_key)
            tx_candidates.append(tx)

            if final_type == 'sell' and len(transaction_entries_sorted) > 1:
                for extra_entry in transaction_entries_sorted[1:]:
                    extra_qty = extra_entry.get('qty')
                    extra_price = extra_entry.get('price')
                    if not extra_qty and not extra_price:
                        continue
                    extra_quantity = extra_qty or quantity
                    extra_price_value = extra_price or price
                    if extra_quantity < MIN_ITEM_QUANTITY or extra_quantity > MAX_ITEM_QUANTITY:
                        continue
                    if extra_price_value is None or extra_price_value <= 0:
                        continue
                    extra_slot = extra_entry.get('_occurrence_slot', 0) if transaction_entries_sorted else 0
                    extra_cluster_key = (
                        item_name.lower(),
                        ts_key,
                        int(extra_quantity or 0),
                        int(extra_price_value or 0),
                        final_type,
                        int(extra_slot or 0),
                    )
                    if extra_cluster_key in created_clusters:
                        continue
                    created_clusters.add(extra_cluster_key)
                    tx_candidates.append({
                        'item_name': item_name,
                        'quantity': extra_quantity,
                        'price': extra_price_value,
                        'timestamp': ent['timestamp'],
                        'transaction_type': final_type,
                        'case': f"{final_type}_{case}",
                        'raw_related': related,
                        'occurrence_index': None,
                        'occurrence_slot': extra_slot
                    })
        if self.debug:
            log_debug(f"tx_candidates={len(tx_candidates)} allowed_ts={len(allowed_ts)}")

        # Try to infer missing buy transactions directly from UI metrics when no log anchors were parsed.
        if (
            wtype == 'buy_overview'
            and ui_buy
            and (self._baseline_initialized or prev_ui_buy)
        ):
            existing_items = {(t.get('item_name') or '').lower() for t in tx_candidates if t.get('item_name')}
            existing_norm = {_norm_key(t.get('item_name')) for t in tx_candidates if t.get('item_name')}
            for item_lc, metrics in ui_buy.items():
                if item_lc in existing_items or _norm_key(metrics.get('item') or item_lc) in existing_norm:
                    continue
                orders_completed = metrics.get('ordersCompleted') or 0
                collect_amount = metrics.get('remainingPrice') or 0
                if orders_completed <= 0 or collect_amount <= 0:
                    continue
                prev_metrics = prev_ui_buy.get(item_lc) if prev_ui_buy else None
                if not prev_metrics and prev_ui_buy:
                    prev_metrics = prev_ui_buy.get(_norm_key(metrics.get('item') or item_lc))
                prev_completed = prev_metrics.get('ordersCompleted') if prev_metrics else 0
                prev_collect = prev_metrics.get('remainingPrice') if prev_metrics else 0
                delta_qty = orders_completed - (prev_completed or 0)
                delta_price = collect_amount - (prev_collect or 0)
                if delta_qty <= 0 or delta_price <= 0:
                    continue
                if any(r.get('type') in ('transaction', 'purchased', 'placed', 'withdrew') and _norm_key((r.get('item') or '').lower()) == _norm_key(metrics.get('item') or item_lc) for r in tx_candidates for _ in [0]):
                    continue
                if delta_qty < MIN_ITEM_QUANTITY or delta_qty > MAX_ITEM_QUANTITY:
                    continue
                unit_candidate = delta_price // delta_qty if delta_qty else 0
                if unit_candidate <= 0:
                    continue
                raw_name = metrics.get('item') or item_lc
                corrected_name = correct_item_name(raw_name) or raw_name
                
                # CRITICAL FIX: Validate inferred price against market data
                # This prevents using stale UI metrics that produce wrong prices
                try:
                    plausibility = check_price_plausibility(corrected_name, delta_qty, delta_price, tx_side='buy')
                    if not plausibility.get('plausible', True):
                        reason = plausibility.get('reason', 'unknown')
                        expected_min = plausibility.get('expected_min')
                        expected_max = plausibility.get('expected_max')
                        # Skip if price is WAY off (outside 10x range)
                        if reason == 'too_low' and expected_min and delta_price < expected_min * 0.1:
                            if self.debug:
                                log_debug(f"[UI-INFER] SKIP '{corrected_name}' - price {delta_price:,} too low (expected min: {expected_min:,})")
                            continue
                        elif reason == 'too_high' and expected_max and delta_price > expected_max * 10:
                            if self.debug:
                                log_debug(f"[UI-INFER] SKIP '{corrected_name}' - price {delta_price:,} too high (expected max: {expected_max:,})")
                            continue
                        # Warn but allow if within 10x range (might be correct)
                        elif self.debug:
                            log_debug(f"[UI-INFER] ⚠ '{corrected_name}' price {delta_price:,} is {reason} (expected: {expected_min:,} - {expected_max:,})")
                except Exception:
                    pass  # If check fails, proceed anyway
                # CRITICAL FIX: Use current time for UI-inferred transactions, NOT overall_max_ts
                # overall_max_ts comes from OLD transaction log entries which can have stale timestamps
                # UI-inferred means we're detecting a NEW collect/buy that just happened NOW
                ts_for_ui = datetime.datetime.now()
                synthetic_tx = {
                    'item_name': corrected_name,
                    'quantity': delta_qty,
                    'price': int(delta_price),
                    'timestamp': ts_for_ui,
                    'transaction_type': 'buy',
                    'case': 'collect_ui_inferred',
                    'raw_related': [
                        {
                            'type': 'ui_orders',
                            'item': corrected_name,
                            'qty': orders_completed,
                            'price': collect_amount,
                            'ts_text': ts_for_ui.strftime('%Y-%m-%d %H:%M') if isinstance(ts_for_ui, datetime.datetime) else str(ts_for_ui),
                        }
                    ],
                    'occurrence_index': None,
                    'occurrence_slot': 0,
                    '_ui_inferred': True,
                }
                tx_candidates.append(synthetic_tx)
                existing_items.add(item_lc)
                existing_items.add((corrected_name or '').lower())
                if self.debug:
                    log_debug(
                        f"[UI-INFER] Added synthetic buy for '{corrected_name}' qty={delta_qty} price={delta_price} "
                        f"(ordersCompleted Δ{delta_qty}, collect Δ{delta_price})"
                    )

        if (
            wtype == 'sell_overview'
            and ui_sell
            and (prev_ui_sell or self._last_ui_sell_metrics)
        ):
            existing_items = {(t.get('item_name') or '').lower() for t in tx_candidates if t.get('item_name')}
            existing_norm = { _norm_key(t.get('item_name')) for t in tx_candidates if t.get('item_name') }
            for item_lc, metrics in ui_sell.items():
                metrics_item = metrics.get('item') or item_lc
                norm_key = _norm_key(metrics_item)
                if item_lc in existing_items or norm_key in existing_norm:
                    continue
                prev_metrics = prev_ui_sell.get(item_lc) if prev_ui_sell else None
                if not prev_metrics and prev_ui_sell_norm:
                    prev_metrics = prev_ui_sell_norm.get(norm_key)
                if not prev_metrics:
                    continue
                sales_completed = metrics.get('salesCompleted') or 0
                collect_total = metrics.get('price') or 0
                prev_sales = prev_metrics.get('salesCompleted') or 0
                prev_collect = prev_metrics.get('price') or 0
                delta_qty = sales_completed - prev_sales
                delta_collect = collect_total - prev_collect
                if delta_qty <= 0 or delta_collect <= 0:
                    continue
                if delta_qty < MIN_ITEM_QUANTITY or delta_qty > MAX_ITEM_QUANTITY:
                    continue
                corrected_name = correct_item_name(metrics_item) or metrics_item
                if not self._valid_item_name(corrected_name):
                    continue
                # CRITICAL FIX: Use current time for UI-inferred transactions, NOT overall_max_ts
                # overall_max_ts comes from OLD transaction log entries which can have stale timestamps
                # UI-inferred means we're detecting a NEW collect/sell that just happened NOW
                ts_for_ui = datetime.datetime.now()
                synthetic_sell = {
                    'item_name': corrected_name,
                    'quantity': int(delta_qty),
                    'price': int(delta_collect),
                    'timestamp': ts_for_ui,
                    'transaction_type': 'sell',
                    'case': 'sell_collect_ui_inferred',
                    'raw_related': [
                        {
                            'type': 'ui_sales',
                            'item': corrected_name,
                            'qty': sales_completed,
                            'price': collect_total,
                            'ts_text': ts_for_ui.strftime('%Y-%m-%d %H:%M') if isinstance(ts_for_ui, datetime.datetime) else str(ts_for_ui),
                        }
                    ],
                    'occurrence_index': None,
                    'occurrence_slot': 0,
                    '_ui_inferred': True,
                }
                tx_candidates.append(synthetic_sell)
                existing_items.add(corrected_name.lower())
                existing_norm.add(_norm_key(corrected_name))
                if self.debug:
                    log_debug(
                        f"[UI-INFER] Added synthetic sell for '{corrected_name}' qty={delta_qty} price={delta_collect} "
                        f"(salesCompleted Δ{delta_qty}, collect Δ{delta_collect})"
                    )

        # Post-process candidates after a dialog return: adjust timestamps to latest snapshot
        # and keep only items that actually had a purchase/transaction anchor in this scan.
        if 'returning_from_item' in locals() and returning_from_item and wtype == 'buy_overview' and tx_candidates:
            # Determine overall latest timestamp in this snapshot
            latest_ts = None
            for t in tx_candidates:
                if isinstance(t['timestamp'], datetime.datetime):
                    if latest_ts is None or t['timestamp'] > latest_ts:
                        latest_ts = t['timestamp']
            # Build set of purchased/transaction anchor items from candidates' related entries
            anchor_items_from_scan = set()
            for t in tx_candidates:
                for r in t.get('raw_related', []):
                    if r.get('type') in ('purchased', 'transaction') and r.get('item'):
                        anchor_items_from_scan.add((r['item'] or '').lower())
            if anchor_items_from_scan:
                # Adjust timestamps of candidates for those items
                for t in tx_candidates:
                    if (t['item_name'] or '').lower() in anchor_items_from_scan and isinstance(t['timestamp'], datetime.datetime) and latest_ts and t['timestamp'] < latest_ts:
                        t['timestamp'] = latest_ts
                # Filter out candidates not in the anchor set to avoid unrelated relist-only saves
                before = len(tx_candidates)
                tx_candidates = [t for t in tx_candidates if (t['item_name'] or '').lower() in anchor_items_from_scan]
                if self.debug and len(tx_candidates) != before:
                    log_debug(f"filtered non-anchor candidates after dialog return: {before} -> {len(tx_candidates)}")

        if not tx_candidates:
            if self.debug:
                print("DEBUG: no transaction candidates found")
            # Heuristic: On buy_overview, if the UI shows Orders/Collect blocks but we didn't get any candidates (often due to delayed purchase lines),
            # schedule a short burst of immediate re-scans to catch the purchase/transaction appearing a few frames later.
            if wtype == 'buy_overview':
                try:
                    # PERFORMANCE: Use precompiled whitespace pattern
                    s_norm = _WHITESPACE_PATTERN.sub(' ', full_text)
                    has_orders = re.search(r"orders\s+completed", s_norm, re.IGNORECASE) is not None
                    has_collect = re.search(r"\bcollect\b|\bre-?list\b", s_norm, re.IGNORECASE) is not None
                    # try to detect at least one item name before the word 'Orders'
                    potential_items = set()
                    for m in re.finditer(r"([A-Za-z][A-Za-z0-9' :\-\(\)]{4,})\s+Orders(?:\s+Completed)?", s_norm):
                        cand = (m.group(1) or '').strip()
                        if self._valid_item_name(cand) and cand.lower() not in ("buy", "sell"):
                            potential_items.add(cand)
                    if has_orders and has_collect and potential_items:
                        now2 = datetime.datetime.now()
                        # only (re)schedule if not already within an active burst window
                        if not self._burst_until or now2 >= self._burst_until:
                            self._burst_until = now2 + datetime.timedelta(seconds=3.5)
                            self._burst_fast_scans = max(self._burst_fast_scans, 6)
                            self._request_immediate_rescan = max(self._request_immediate_rescan, 2)
                            if self.debug:
                                log_debug(f"buy_overview orders/collect detected without candidates -> scheduling burst re-scans for items={list(potential_items)[:3]}")
                except Exception:
                    pass
            # Similar heuristic for sell_overview: if 'Items Listed'/'Sales Completed' UI blocks and 'Collect' appear but
            # no candidates were found (likely due to delayed transaction line), schedule burst re-scans.
            if wtype == 'sell_overview':
                try:
                    # PERFORMANCE: Use precompiled whitespace pattern
                    s_norm = _WHITESPACE_PATTERN.sub(' ', full_text)
                    has_items_listed = re.search(r"items\s+listed", s_norm, re.IGNORECASE) is not None
                    has_sales_completed = re.search(r"sales\s+completed", s_norm, re.IGNORECASE) is not None
                    has_collect = re.search(r"\bcollect\b|\bre-?list\b", s_norm, re.IGNORECASE) is not None
                    if (has_items_listed or has_sales_completed) and has_collect:
                        now2 = datetime.datetime.now()
                        if not self._burst_until or now2 >= self._burst_until:
                            self._burst_until = now2 + datetime.timedelta(seconds=3.5)
                            self._burst_fast_scans = max(self._burst_fast_scans, 6)
                            self._request_immediate_rescan = max(self._request_immediate_rescan, 2)
                            if self.debug:
                                log_debug("sell_overview UI blocks detected without candidates -> scheduling burst re-scans")
                except Exception:
                    pass
            return

        # Now determine which tx_candidates are NEW relative to previous OCR snapshot:
        # We base this on textual difference: find entries present in new text that were not present in last_full_text
        # Build simple signature set from previous text if available
        prev_entries = set()
        prev_snippets = set()
        prev_max_ts = None
        if self.last_overview_text:
            if self.debug:
                log_debug(f"[DELTA] Baseline exists: {len(self.last_overview_text)} chars")
            prev_entries_raw = split_text_into_log_entries(self.last_overview_text)
            if self.debug:
                log_debug(f"[DELTA] Baseline has {len(prev_entries_raw)} entries")
            for pos, ts_text, snippet in prev_entries_raw:
                # we create a coarse signature: ts_text + normalized snippet
                # PERFORMANCE: Use precompiled whitespace pattern
                normalized_snippet = _WHITESPACE_PATTERN.sub(' ', snippet).strip()[:180]
                key = (ts_text, normalized_snippet)
                prev_entries.add(key)
                # also track snippet-only normalized content to tolerate minor timestamp shifts in OCR layout
                prev_snippets.add(normalized_snippet)
                # track max timestamp in previous snapshot (for robust delta bypass)
                ts_prev = parse_timestamp_text(ts_text)
                if ts_prev is not None:
                    if (prev_max_ts is None) or (ts_prev > prev_max_ts):
                        prev_max_ts = ts_prev
        else:
            if self.debug:
                log_debug("[DELTA] No baseline - all entries will be processed")
        if self.debug:
            log_debug(f"[DELTA] prev_max_ts={prev_max_ts}, tx_candidates={len(tx_candidates)}")

        # Process candidates: if candidate's (ts_text, snippet) not in prev_entries -> treat as new
        baseline_ts_snapshot = self.last_processed_game_ts
        saved_any_ts = []
        batch_seen_sigs = set()
        for tx in tx_candidates:
            saved = False
            # Only process entries within the effective recent time window
            if isinstance(tx['timestamp'], datetime.datetime):
                if restrict_min_ts and tx['timestamp'] < restrict_min_ts:
                    continue
                if scan_restrict_min and tx['timestamp'] < scan_restrict_min:
                    continue

            # prepare signature & baseline comparison before assigning occurrence index
            main_raw = None
            main_ts_text = None
            for r in tx.get('raw_related', []):
                if r.get('type') in ('transaction', 'purchased'):
                    raw_val = r.get('raw')
                    ts_val = r.get('ts_text')
                    if raw_val:
                        main_raw = raw_val
                        main_ts_text = ts_val
                        break
            if main_raw is None:
                # CRITICAL: Fallback signature must match OCR text format
                # Format: "Transaction of {item} x{qty} worth {price} Silver"
                # This allows baseline text matching even when timestamp is missing
                item_str = tx['item_name'] or ''
                qty_str = f"x{tx['quantity']}" if tx['quantity'] else ''
                price_str = f"{tx['price']:,}" if tx['price'] else ''
                main_raw = f"Transaction of {item_str} {qty_str} worth {price_str} Silver"
                if isinstance(tx['timestamp'], datetime.datetime):
                    main_ts_text = tx['timestamp'].strftime("%Y-%m-%d %H:%M")
                else:
                    main_ts_text = str(tx['timestamp'])
            # PERFORMANCE: Use precompiled whitespace pattern
            normalized_main = _WHITESPACE_PATTERN.sub(' ', main_raw).strip()[:180]
            key = (main_ts_text, normalized_main)
            already_seen_in_prev = (key in prev_entries) or (normalized_main in prev_snippets)
            
            # CRITICAL: Robust baseline matching for transactions with similar item+qty+price
            # If normalized text doesn't match, try pattern-based matching in baseline
            if not already_seen_in_prev and self.last_overview_text:
                try:
                    pattern = self._compile_transaction_pattern(
                        tx['item_name'],
                        tx['quantity'],
                        tx['price'],
                    )
                    if pattern.search(self.last_overview_text):
                        already_seen_in_prev = True
                        if self.debug:
                            log_debug(f"[BASELINE-PATTERN] Matched '{tx['item_name']}' {tx['quantity']}x in previous baseline (pattern match)")
                except Exception as e:
                    if self.debug:
                        log_debug(f"[BASELINE-PATTERN] Pattern match failed: {e}")
            
            tx['_main_ts_text'] = main_ts_text
            tx['_normalized_main'] = normalized_main
            tx['_seen_in_prev'] = already_seen_in_prev

            occurrence_reused = self._resolve_occurrence_index(tx)

            # CRITICAL FIX: Intelligent baseline handling for old transactions
            # Problem: When user first opens market, old transactions (09:43, 09:48) appear
            # but baseline had newer timestamp (10:12) -> old transactions were skipped
            # 
            # Solution: If we see transactions OLDER than baseline's prev_max_ts,
            # these are "historical" transactions from reopening the market window.
            # We should process them if they're not in DB yet.
            is_newer_than_prev = False
            is_historical = False  # Transactions older than baseline but newly visible
            
            if isinstance(tx['timestamp'], datetime.datetime) and prev_max_ts is not None:
                is_newer_than_prev = tx['timestamp'] > prev_max_ts
                
                # Check if this is a historical transaction (older than baseline but newly visible)
                # Criteria: timestamp < prev_max_ts AND not seen in previous baseline text
                if tx['timestamp'] < prev_max_ts and not already_seen_in_prev:
                    is_historical = True
                    if self.debug:
                        log_debug(f"[HISTORICAL] Detected old transaction: {tx['item_name']} @ {tx['timestamp']} (baseline was at {prev_max_ts})")
            
            # Check if this exact transaction already exists in DATABASE (not just baseline text)
            already_in_db = occurrence_reused
            already_in_db_any_side = False
            already_in_db_by_values = False
            
            if not already_in_db:
                try:
                    already_in_db = transaction_exists_exact(
                        tx['item_name'],
                        tx['quantity'],
                        int(tx['price'] or 0),
                        tx['transaction_type'],
                        tx['timestamp'],
                        tx.get('occurrence_index', 0)
                    )
                except Exception as e:
                    if self.debug:
                        log_debug(f"[DELTA] DB check failed: {e}")
            
            if not already_in_db:
                try:
                    already_in_db_any_side = transaction_exists_any_side(
                        tx['item_name'],
                        tx['quantity'],
                        int(tx['price'] or 0),
                        tx['timestamp'],
                    )
                except Exception:
                    already_in_db_any_side = False

            if (
                not already_in_db_by_values
                and baseline_ts_snapshot
                and isinstance(tx.get('timestamp'), datetime.datetime)
                and tx['timestamp'] <= baseline_ts_snapshot
            ):
                try:
                    # Nur für ältere/gleich alte Timestamps prüfen – echte neue Transaktionen (ts > baseline)
                    # dürfen nicht blockiert werden.
                    already_in_db_by_values = transaction_exists_by_values_near_time(
                        tx['item_name'],
                        tx['quantity'],
                        int(tx['price'] or 0),
                        tx['timestamp'],
                        tolerance_minutes=max(1, _HISTORICAL_VALUE_DUP_TOLERANCE_SECONDS // 60)
                    )
                    if already_in_db_by_values and self.debug:
                        log_debug(
                            f"[DELTA] Historical duplicate by values: {tx['item_name']} {tx['quantity']}x @ {tx['price']} "
                            f"ts={tx['timestamp']} (within tolerance)"
                        )
                except Exception as exc:
                    if self.debug:
                        log_debug(f"[DELTA] Value-based duplicate check failed: {exc}")
            
            # DISABLED: Value-based deduplication is unreliable
            # Problem: Cannot distinguish between:
            #   1. OCR duplicate (same transaction, wrong timestamp)
            #   2. Real repeat purchase (two identical transactions)
            # Both can happen within seconds/minutes!
            # 
            # Solution: Rely on baseline text comparison instead.
            # If the transaction text appears in previous baseline, it's a duplicate.
            # If it's new text, save it (even if values match existing transaction).
            already_in_db_by_values = False
            
            # Check baseline text (less strict - only for additional filtering)
            if self.debug:
                log_debug(f"[DELTA] Checking {tx['item_name']} @ {tx['timestamp']}: newer={is_newer_than_prev}, seen_in_text={already_seen_in_prev}, in_db={already_in_db}, near_time={already_in_db_by_values}")
            
            # Skip if time-aware deduplication matched (same item/qty/price within short window)
            if already_in_db_by_values:
                if self.debug:
                    log_debug(
                        f"[DELTA] SKIP (time-dedup): {tx['item_name']} {tx['quantity']}x @ {tx['price']} "
                        f"ts={tx['timestamp']}"
                    )
                continue
            
            # CRITICAL FIX: Allow historical transactions if not in DB
            # Skip only if: (not newer AND not historical) AND (already in DB)
            if not skip_prev_delta and (not is_newer_than_prev) and (not is_historical) and already_in_db:
                # Special-case: On buy_overview, if both 'purchased' and 'transaction' exist for this item+timestamp,
                # allow the second entry to be saved even if it appeared in the previous snapshot text (paired buy flow).
                delta_bypass = False
                if wtype == 'buy_overview' and isinstance(tx.get('timestamp'), datetime.datetime):
                    it_lc = (tx.get('item_name') or '').lower()
                    pair_types = items_ts_types.get((it_lc, tx['timestamp']), set()) if 'items_ts_types' in locals() else set()
                    if 'purchased' in pair_types and 'transaction' in pair_types:
                        delta_bypass = True
                if not delta_bypass:
                    # If it’s the first overview snapshot and we’re skipping due to duplication,
                    # but the new candidate has an earlier game timestamp, update the existing DB row’s timestamp.
                    try:
                        if first_snapshot_mode and isinstance(tx.get('timestamp'), datetime.datetime):
                            update_tx_timestamp_if_earlier(
                                tx['item_name'],
                                tx['quantity'],
                                int(tx['price'] or 0),
                                tx['transaction_type'],
                                tx['timestamp'],
                                tx.get('occurrence_index')
                            )
                    except Exception:
                        pass
                    if self.debug:
                        log_debug(f"[DELTA] SKIP (duplicate): {tx['item_name']} {tx['quantity']}x @ {tx['timestamp']} - already in DATABASE")
                    continue

            allow_old_timestamp = not already_in_db and not already_in_db_any_side and not already_seen_in_prev
            # Recency guard: verarbeite nur Einträge mit Spiel-Zeitstempel >= baseline,
            # aber überspringe nur strikt ältere. Gleichzeitige (gleiche Minute) sind erlaubt,
            # wenn sie im Delta neu sind (oben bereits geprüft).
            if baseline_ts_snapshot and isinstance(tx['timestamp'], datetime.datetime):
                if tx['timestamp'] < baseline_ts_snapshot and not allow_old_timestamp:
                    if self.debug:
                        msg = f"older game timestamp -> skip: {tx['timestamp']}"
                        print("DEBUG:", msg)
                        log_debug(msg)
                    continue
                if tx['timestamp'] < baseline_ts_snapshot and allow_old_timestamp and self.debug:
                    log_debug(f"recency guard relaxed for {tx['item_name']} @ {tx['timestamp']} (new text, not in DB)")

            # If an entry with matching item/qty/price/timestamp already exists (regardless of side) and this
            # snapshot is older or equal to the baseline timestamp, skip to avoid scroll-induced duplicates.
            if (
                already_in_db_any_side
                and baseline_ts_snapshot
                and isinstance(tx['timestamp'], datetime.datetime)
                and tx['timestamp'] <= baseline_ts_snapshot
            ):
                if self.debug:
                    log_debug(
                        f"[DELTA] SKIP (duplicate-any-side): {tx['item_name']} {tx['quantity']}x @ {tx['timestamp']}"
                        " matches existing record with same price"
                    )
                continue

            if (
                not already_in_db_any_side
                and baseline_ts_snapshot
                and isinstance(tx['timestamp'], datetime.datetime)
                and tx['timestamp'] <= baseline_ts_snapshot
                and already_in_db_by_values
            ):
                # Bereits weiter oben erkannt, hier nur als zusätzlicher Schutz falls DB-Check seitdem geändert wurde.
                if self.debug:
                    log_debug(
                        f"[DELTA] SKIP (value-dup): {tx['item_name']} {tx['quantity']}x @ {tx['timestamp']} "
                        "matches existing record by value"
                    )
                continue

            # new entry -> attempt to store
            sig = self.make_tx_sig(tx['item_name'], tx['quantity'], tx['price'], tx['transaction_type'], tx['timestamp'], tx.get('occurrence_index'))
            if sig in self.seen_tx_signatures:
                if self.debug:
                    msg = f"already processed session-sig, skip: {sig}"
                    print("DEBUG:", msg)
                    log_debug(msg)
                continue
            if sig in batch_seen_sigs:
                if self.debug:
                    log_debug(f"[DELTA] SKIP (batch duplicate): {sig}")
                continue
            batch_seen_sigs.add(sig)

            # store in DB
            saved = self.store_transaction_db(tx)
            if saved and isinstance(tx['timestamp'], datetime.datetime):
                saved_any_ts.append(tx['timestamp'])
                if self.debug:
                    log_debug(f"[SAVE] ✅ {tx['transaction_type']} {tx['case']} {tx['quantity']}x {tx['item_name']} price={tx['price']} ts={tx['timestamp']}")
            elif self.debug:
                log_debug(f"[SAVE] ❌ FAILED {tx['item_name']} {tx['quantity']}x @ {tx['timestamp']}")

        # Fallback: if nothing saved but candidates exist, force-save the newest candidate per item (respects baseline/recency)
        if not saved_any_ts and tx_candidates:
            latest_per_item = {}
            for t in tx_candidates:
                key = (t['item_name'] or '').lower()
                if key not in latest_per_item or (isinstance(t['timestamp'], datetime.datetime) and isinstance(latest_per_item[key]['timestamp'], datetime.datetime) and t['timestamp'] > latest_per_item[key]['timestamp']):
                    latest_per_item[key] = t
            for item_key, fallback in latest_per_item.items():
                saved = False
                # Only fallback-save anchored candidates: on buy_overview require purchased or (transaction+placed/withdrew);
                # on sell_overview require transaction (sell) anchor.
                if wtype == 'buy_overview':
                    rel = fallback.get('raw_related', [])
                    itlc = (fallback.get('item_name') or '').lower()
                    has_pur = any(r.get('type') == 'purchased' and (r.get('item') or '').lower() == itlc for r in rel)
                    has_tx = any(r.get('type') == 'transaction' and (r.get('item') or '').lower() == itlc for r in rel)
                    has_pl = any(r.get('type') == 'placed' and (r.get('item') or '').lower() == itlc for r in rel)
                    has_wd = any(r.get('type') == 'withdrew' and (r.get('item') or '').lower() == itlc for r in rel)
                    # Accept strong buy anchors only: purchased, or transaction paired with placed/withdrew,
                    # or a placed+withdrew pair (partial fill inference) for the same item.
                    if not (has_pur or (has_tx and (has_pl or has_wd)) or (has_pl and has_wd)):
                        if self.debug:
                            log_debug(f"fallback skip non-anchored candidate on buy_overview: {fallback['item_name']}")
                        continue
                elif wtype == 'sell_overview':
                    rel = fallback.get('raw_related', [])
                    itlc = (fallback.get('item_name') or '').lower()
                    has_tx = any(r.get('type') == 'transaction' and (r.get('item') or '').lower() == itlc for r in rel)
                    if not has_tx:
                        if self.debug:
                            log_debug(f"fallback skip non-transaction candidate on sell_overview: {fallback['item_name']}")
                        continue
                # Ensure recency/baseline
                if isinstance(fallback['timestamp'], datetime.datetime):
                    if (restrict_min_ts and fallback['timestamp'] < restrict_min_ts) or (scan_restrict_min and fallback['timestamp'] < scan_restrict_min) or (self.last_processed_game_ts and fallback['timestamp'] < self.last_processed_game_ts):
                        continue
                try:
                    if (
                        baseline_ts_snapshot
                        and isinstance(fallback['timestamp'], datetime.datetime)
                        and fallback['timestamp'] <= baseline_ts_snapshot
                        and transaction_exists_any_side(
                            fallback['item_name'],
                            fallback['quantity'],
                            int(fallback['price'] or 0),
                            fallback['timestamp'],
                        )
                    ):
                        if self.debug:
                            log_debug(
                                f"fallback skip duplicate-any-side for {fallback['item_name']} "
                                f"{fallback['quantity']}x @ {fallback['timestamp']}"
                            )
                        continue
                except Exception:
                    pass
                sig = self.make_tx_sig(fallback['item_name'], fallback['quantity'], fallback['price'], fallback['transaction_type'], fallback['timestamp'], fallback.get('occurrence_index'))
                if sig in self.seen_tx_signatures or sig in batch_seen_sigs:
                    continue
                batch_seen_sigs.add(sig)
                # ensure occurrence index prepared for fallback before storing
                occurrence_reused_fb = self._resolve_occurrence_index(fallback)
                if occurrence_reused_fb:
                    continue
                saved = self.store_transaction_db(fallback)
                if saved and isinstance(fallback['timestamp'], datetime.datetime):
                    saved_any_ts.append(fallback['timestamp'])
                    if self.debug:
                        log_debug(f"fallback saved tx: {fallback['transaction_type']} {fallback['case']} {fallback['quantity']}x {fallback['item_name']} price={fallback['price']} ts={fallback['timestamp']}")

        # After batch, update last_processed_game_ts to max of saved or keep existing
        if saved_any_ts:
            max_saved = max(saved_any_ts)
            if not self.last_processed_game_ts or max_saved > self.last_processed_game_ts:
                self.last_processed_game_ts = max_saved
            if self.debug:
                log_debug(f"updated baseline last_processed_game_ts={self.last_processed_game_ts}")
            # After successful saves, keep scanning aggressively for any delayed UI rows.
            if wtype in ('buy_overview', 'sell_overview'):
                try:
                    s_norm = re.sub(r"\s+", " ", full_text)
                    has_orders = re.search(r"orders\s+completed", s_norm, re.IGNORECASE) is not None
                    has_items_listed = re.search(r"items\s+listed", s_norm, re.IGNORECASE) is not None
                    has_collect = re.search(r"\bcollect\b|\bre-?list\b", s_norm, re.IGNORECASE) is not None
                    should_burst = False
                    if wtype == 'buy_overview':
                        should_burst = has_orders and has_collect
                    else:
                        has_sales_completed = re.search(r"sales\s+completed", s_norm, re.IGNORECASE) is not None
                        should_burst = (has_items_listed or has_sales_completed or has_orders) and has_collect
                    if should_burst:
                        now2 = datetime.datetime.now()
                        if not self._burst_until or now2 >= self._burst_until:
                            burst_seconds = 3.0 if wtype == 'buy_overview' else 2.5
                            self._burst_until = now2 + datetime.timedelta(seconds=burst_seconds)
                        self._burst_fast_scans = max(self._burst_fast_scans, 6 if wtype == 'buy_overview' else 4)
                        self._request_immediate_rescan = max(self._request_immediate_rescan, 3 if wtype == 'buy_overview' else 2)
                        if self.debug:
                            log_debug(f"post-save: {wtype} UI blocks present -> scheduling follow-up burst re-scans")
                except Exception:
                    pass
        else:
            # If nothing was saved on a buy_overview but we see Orders/Collect blocks, schedule a short burst as above
            if wtype == 'buy_overview':
                try:
                    s_norm = re.sub(r"\s+", " ", full_text)
                    has_orders = re.search(r"orders\s+completed", s_norm, re.IGNORECASE) is not None
                    has_collect = re.search(r"\bcollect\b|\bre-?list\b", s_norm, re.IGNORECASE) is not None
                    potential_items = set()
                    for m in re.finditer(r"([A-Za-z][A-Za-z0-9' :\-\(\)]{4,})\s+Orders(?:\s+Completed)?", s_norm):
                        cand = (m.group(1) or '').strip()
                        if self._valid_item_name(cand) and cand.lower() not in ("buy", "sell"):
                            potential_items.add(cand)
                    if has_orders and has_collect and potential_items:
                        now2 = datetime.datetime.now()
                        if not self._burst_until or now2 >= self._burst_until:
                            self._burst_until = now2 + datetime.timedelta(seconds=3.5)
                            self._burst_fast_scans = max(self._burst_fast_scans, 6)
                            self._request_immediate_rescan = max(self._request_immediate_rescan, 2)
                            if self.debug:
                                log_debug(f"post-save: buy_overview orders/collect without saves -> scheduling burst re-scans for items={list(potential_items)[:3]}")
                except Exception:
                    pass
            # Likewise for sell_overview: if no saves but 'Items Listed'/'Sales Completed' UI and 'Collect' appear, schedule a short burst
            if wtype == 'sell_overview':
                try:
                    s_norm = re.sub(r"\s+", " ", full_text)
                    has_items_listed = re.search(r"items\s+listed", s_norm, re.IGNORECASE) is not None
                    has_sales_completed = re.search(r"sales\s+completed", s_norm, re.IGNORECASE) is not None
                    has_collect = re.search(r"\bcollect\b|\bre-?list\b", s_norm, re.IGNORECASE) is not None
                    if (has_items_listed or has_sales_completed) and has_collect:
                        now2 = datetime.datetime.now()
                        if not self._burst_until or now2 >= self._burst_until:
                            self._burst_until = now2 + datetime.timedelta(seconds=3.5)
                            self._burst_fast_scans = max(self._burst_fast_scans, 6)
                            self._request_immediate_rescan = max(self._request_immediate_rescan, 2)
                            if self.debug:
                                log_debug("post-save: sell_overview UI blocks without saves -> scheduling burst re-scans")
                except Exception:
                    pass

        # finally update last_overview_text (nur Overview) ONLY if at least one tx was saved
        # This prevents advancing the delta-baseline on snapshots where filters blocked saving,
        # ensuring we can still capture those entries on the next scan.
        if saved_any_ts:
            old_len = len(self.last_overview_text)
            new_len = len(full_text)
            self.last_overview_text = full_text
            # Save to persistent state so it survives app restarts
            save_state('last_overview_text', full_text)
            if self.debug:
                log_debug(f"[BASELINE] Updated & persisted: {old_len} → {new_len} chars, saved {len(saved_any_ts)} transactions")
        elif self.debug:
            log_debug(f"[BASELINE] NOT updated (no transactions saved)")

        # Persist latest UI metrics per tab so inference can compute deltas on the next scan (even across tab switches)
        if wtype == 'buy_overview':
            try:
                self._last_ui_buy_metrics = {k: dict(v) for k, v in ui_buy.items()}
            except Exception:
                self._last_ui_buy_metrics = ui_buy.copy() if isinstance(ui_buy, dict) else {}
            try:
                save_state('last_ui_buy_metrics', json.dumps(self._last_ui_buy_metrics))
            except Exception:
                pass
        elif wtype == 'sell_overview':
            try:
                self._last_ui_sell_metrics = {k: dict(v) for k, v in ui_sell.items()}
            except Exception:
                self._last_ui_sell_metrics = ui_sell.copy() if isinstance(ui_sell, dict) else {}
            try:
                save_state('last_ui_sell_metrics', json.dumps(self._last_ui_sell_metrics))
            except Exception:
                pass

        self._persist_occurrence_state_if_needed()

    # -----------------------
    # Scanning loops
    # -----------------------
    def single_scan(self):
        img = self._capture_frame()
        if img is None:
            return

        if not self.running:
            return

        self._process_image(img, context='sync', allow_debug=True)

        while self._request_immediate_rescan > 0 and self.running:
            time.sleep(0.05)
            img2 = self._capture_frame()
            if img2 is None or not self.running:
                break
            self._process_image(img2, context='quick', allow_debug=False)
            self._request_immediate_rescan -= 1

    def auto_track(self):
        if USE_ASYNC_PIPELINE:
            if self.running:
                print("Auto-Tracking läuft bereits.")
                return
            self.running = True
            print("▶ Auto-Tracking gestartet (async pipeline) ...")
            controller = AsyncPipelineController(
                tracker=self,
                queue_size=ASYNC_QUEUE_MAXSIZE,
                worker_count=ASYNC_WORKER_COUNT,
            )
            self._async_controller = controller
            try:
                controller.run()
            except Exception as exc:
                print("Fehler beim Auto-Scan:", exc)
            finally:
                self._async_controller = None
                self.running = False
                print("⏹ Auto-Tracking gestoppt.")
            return

        self.running = True
        print("▶ Auto-Tracking gestartet ...")
        while self.running:
            try:
                self.single_scan()
            except Exception as e:
                print("Fehler beim Auto-Scan:", e)
            sleep_iv = self._get_next_sleep_interval()

            # Interruptible sleep: Sleep in small chunks and check self.running
            # This allows quick response to stop() even with longer sleep intervals
            elapsed = 0.0
            sleep_chunk = 0.1  # Check every 100ms
            while elapsed < sleep_iv and self.running:
                chunk = min(sleep_chunk, sleep_iv - elapsed)
                time.sleep(chunk)
                elapsed += chunk
        print("⏹ Auto-Tracking gestoppt.")

    def stop(self):
        self.running = False
        if self._async_controller:
            self._async_controller.request_stop()

    # Optional: Ausgabe der Fenster-Historie (Debug)
    def print_window_history(self):
        print("Letzte Fenster:")
        for ts, w in self.window_history[-5:]:
            print(" ", ts.strftime("%H:%M:%S"), w)


class AsyncPipelineController:
    """Manage the asynchronous capture → OCR pipeline."""

    def __init__(self, tracker: MarketTracker, queue_size: int = 3, worker_count: int = 1) -> None:
        self.tracker = tracker
        self.queue_size = max(1, int(queue_size))
        self.worker_count = max(1, int(worker_count))
        self.queue: asyncio.Queue | None = None
        self.executor = ThreadPoolExecutor(max_workers=self.worker_count + 1)
        self.loop: asyncio.AbstractEventLoop | None = None
        self._capture_task: asyncio.Task | None = None
        self._worker_tasks: list[asyncio.Task] = []
        self._stop_requested = False
        self._sentinel_inserted = False

    def run(self) -> None:
        try:
            asyncio.run(self._run())
        finally:
            self.executor.shutdown(wait=True)

    def request_stop(self) -> None:
        self._stop_requested = True
        if self.loop:
            self.loop.call_soon_threadsafe(self._initiate_stop)

    def _initiate_stop(self) -> None:
        if self._capture_task and not self._capture_task.done():
            self._capture_task.cancel()

    async def _run(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.queue = asyncio.Queue(maxsize=self.queue_size)

        self._capture_task = asyncio.create_task(self._capture_loop(), name="mt-capture")
        self._worker_tasks = [
            asyncio.create_task(self._worker_loop(idx), name=f"mt-worker-{idx}")
            for idx in range(self.worker_count)
        ]

        try:
            await self._capture_task
        except asyncio.CancelledError:
            pass
        finally:
            self._stop_requested = True
            if self.queue and not self._sentinel_inserted:
                for _ in range(self.worker_count):
                    await self.queue.put(None)
                self._sentinel_inserted = True
            if self.queue:
                await self.queue.join()
            await asyncio.gather(*self._worker_tasks, return_exceptions=True)

    async def _capture_loop(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            while not self._stop_requested and self.tracker.running:
                frame = await loop.run_in_executor(self.executor, self.tracker._capture_frame)
                if frame is None:
                    if self._stop_requested or not self.tracker.running:
                        break
                    await asyncio.sleep(0.05)
                    continue

                payload = {
                    'image': frame,
                    'captured_at': time.perf_counter(),
                }

                if self.queue is None:
                    break

                # CRITICAL FIX: Drop old frames if queue is full
                # We ONLY care about the LATEST state, old frames are USELESS
                # This prevents 10+ second latency when OCR is slow
                try:
                    # Try to put with no wait - if queue full, drop oldest and retry
                    if self.queue.full():
                        try:
                            # Drop oldest frame (FIFO - get without blocking)
                            old_frame = self.queue.get_nowait()
                            self.queue.task_done()  # Mark old frame as done
                            if self.tracker.debug:
                                log_debug("[ASYNC] Dropped stale frame (queue full)")
                        except asyncio.QueueEmpty:
                            pass  # Race condition - queue emptied between check and get
                    
                    await self.queue.put(payload)
                except asyncio.CancelledError:
                    raise

                if self._stop_requested or not self.tracker.running:
                    break

                if self.tracker._consume_immediate_rescan_request():
                    await self._interruptible_sleep(0.05)
                    continue

                sleep_iv = self.tracker._get_next_sleep_interval()
                await self._interruptible_sleep(sleep_iv)
        finally:
            self._stop_requested = True

    async def _worker_loop(self, worker_id: int) -> None:
        loop = asyncio.get_running_loop()
        if self.queue is None:
            return

        while True:
            item = await self.queue.get()
            if item is None:
                self.queue.task_done()
                break

            if not self.tracker.running and self._stop_requested:
                self.queue.task_done()
                continue

            try:
                await loop.run_in_executor(
                    self.executor,
                    self.tracker._process_image,
                    item['image'],
                    'async',
                    self.tracker.debug,
                )
                if self.tracker.debug:
                    captured_at = item.get('captured_at')
                    if captured_at is not None:
                        latency_ms = (time.perf_counter() - captured_at) * 1000
                        log_debug(f"[PERF-ASYNC] Queue latency: {latency_ms:.1f}ms")
            except Exception as exc:
                log_debug(f"[ASYNC] Worker {worker_id} error: {exc}")
            finally:
                self.queue.task_done()

    async def _interruptible_sleep(self, duration: float) -> None:
        if duration <= 0:
            await asyncio.sleep(0)
            return

        elapsed = 0.0
        step = 0.1
        while elapsed < duration and not self._stop_requested and self.tracker.running:
            slice_len = min(step, duration - elapsed)
            await asyncio.sleep(slice_len)
            elapsed += slice_len

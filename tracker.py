import asyncio
import threading
import time
import datetime
import math
import re
import json
import cv2
import hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
from functools import lru_cache
from typing import Optional, Dict, Tuple, Any

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
    is_bdo_window_in_foreground,
    normalize_numeric_str,
    ocr_image_cached,
    get_preprocessed_frame,
    set_preprocessed_frame,
    detect_log_roi,
    detect_window_label_roi,
    detect_metrics_roi,
    detect_detail_item_name_roi,
    detect_detail_balance_roi,
    detect_detail_warehouse_roi,
    detect_detail_preorder_input_roi,
    easyocr_uses_gpu,
    get_easyocr_device_name,
    check_price_plausibility,
    compute_roi_stats_signature,
    compare_roi_signatures,
    # Legacy hash functions (kept for backwards compatibility)
    compute_roi_hash,
    get_roi_hash_cached,
    set_roi_hash_cached,
    MARKET_SELL_NET_FACTOR,
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
    parse_timestamp_text,
    normalize_numeric_str
)
from bdo_api_client import get_item_price_range_by_name
from market_json_manager import get_base_price_from_cache, correct_item_name
from preorder_manager import PreorderManager

# -----------------------
# Performance: Precompiled Regex Patterns
# -----------------------
# These patterns are used frequently in baseline checking and should be precompiled
_WHITESPACE_PATTERN = re.compile(r'\s+')
_COMMA_PATTERN = re.compile(r',')
_TRANSACTION_BASE_PATTERN = r"Transaction\s+of\s+{item}\s*.*?x?\s*{qty}\s*.*?{price}"
_SILVER_WORD_PATTERN = r"s\s*[iIl1](?:\s*[lIl1_])*(?:\s*[vV])?(?:\s*[eE])?(?:\s*[rR_])*"
_PRICE_HINT_PATTERN = re.compile(
    rf"(?:worth|for)\s+([0-9OolI\|,\.\s_]{{3,}})\s+{_SILVER_WORD_PATTERN}",
    re.IGNORECASE,
)
_GENERIC_SILVER_PATTERN = re.compile(
    rf"([0-9OolI\|,\.\s_]{{3,}})\s+{_SILVER_WORD_PATTERN}",
    re.IGNORECASE,
)
_HISTORICAL_VALUE_DUP_TOLERANCE_SECONDS = 90  # 1,5 Minuten Puffer für Scroll-Duplikate

# -----------------------
# Entscheidungslogik: Fälle erkennen & speichern
# -----------------------
class MarketTracker:
    def __init__(self, region=DEFAULT_REGION, poll_interval=POLL_INTERVAL, debug=None):
        if debug is None:
            debug = get_debug_mode(False)
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
        self._async_controller = None
        self.lock = threading.Lock()
        self._debug_image_lock = threading.Lock()
        self._use_fast_preprocess = USE_GPU
        self._fast_preprocess_failures = 0
        self._fast_preprocess_cooldown = 0
        self._fast_preprocess_recovery = 0
        self._scan_counter = 0
        # REMOVED: _metrics_refresh_seconds (5-Sekunden-Timer) - Metrics nur bei Transaktionen gebraucht!
        self._last_metrics_text = ""
        self._last_label_text = ""
        self._pending_metrics_refresh = True
        self._last_metrics_refresh_ts: datetime.datetime | None = None
        self._latest_log_text = ""
        self._easyocr_uses_gpu = easyocr_uses_gpu()
        self._easyocr_device = get_easyocr_device_name()
        self._burst_source = None
        if self.debug:
            log_debug(f"[INIT] EasyOCR device: {self._easyocr_device}")
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
        self._last_ui_buy_fill_sync: dict[str, int] = {}
        
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
        
        # Detail-Window Transaction Monitoring State
        self._detail_window_active = False  # True wenn in Detail-Fenster (buy_item/sell_item)
        self._detail_window_type = None  # 'sell_item' oder 'buy_item'
        self._detail_window_item = None  # Item-Name aus Detail-Fenster
        self._detail_window_hint: str | None = None  # Fallback-Klassifikation aus Label-OCR
        self._detail_detail_snapshot_ts: datetime.datetime | None = None
        self._detail_input_cache: dict[str, dict | None] = {
            'baseline': None,
            'refresh': None,
        }
        self._detail_input_cache_ttl: dict[str, float] = {
            'baseline': 6.0,
            'refresh': 4.0,
        }
        self._detail_input_refresh_pending: bool = False
        self._detail_input_refresh_reason: str | None = None
        self._detail_input_refresh_window: str | None = None
        self._detail_pending_log_snapshots: list[dict] = []
        self._detail_pending_snapshot_hashes: set[str] = set()
        self._detail_relist_autocollect_signature: tuple[str, int, int] | None = None
        self._detail_relist_instant_signature: tuple[str, int, int] | None = None
        self._detail_relist_new_preorder_signature: tuple[str, int, int] | None = None
        self._relist_side_effect_signatures: dict[tuple, float] = {}
        self._relist_side_effect_ttl = 120.0
        self._pending_relist_events: dict[str, dict] = {}
        self._pending_relist_ttl_seconds = 12.0
        
        # Preorder Manager (Phase 3: Auto-Collect Detection)
        self._preorder_manager = PreorderManager(debug=self.debug)
        
        self._detail_baseline_balance = None  # Baseline Balance beim Fenster-Eintritt
        self._detail_baseline_warehouse = None  # Baseline Warehouse beim Fenster-Eintritt
        self._detail_last_metrics = None  # Letzte bekannte Metriken (dict)
        self._detail_confirmation_pending = False  # True wenn Bestätigung erwartet wird
        self._detail_confirmation_timestamp = None  # Timestamp der letzten erkannten Änderung
        self._detail_confirmation_timeout = 5.0  # Sekunden bis Timeout (Reset)
        # Partial Delta Accumulation (handles asynchronous Balance/Warehouse updates)
        self._detail_partial_balance_delta = 0  # Akkumulierter Balance-Delta
        self._detail_partial_warehouse_delta = 0  # Akkumulierter Warehouse-Delta
        self._detail_balance_delta_timestamp = None  # Zeitpunkt des ersten balance_delta (für Timeout)
        self._force_detail_metric_refresh = False
        self._detail_last_delta_activity: datetime.datetime | None = None

        # Preorder duplicate guard
        self._recent_preorder_hashes: dict[tuple[str, int, int, int], float] = {}
        self._recent_preorder_ttl = 3.0  # seconds

        # Listing duplicate guard
        self._recent_listing_hashes: dict[tuple[str, int, int, int], float] = {}
        self._recent_listing_ttl = 3.0  # seconds
        
        # Sync-Tracking: Verhindert Plausibility Check bei partial updates
        self._detail_balance_changed_once = False  # True wenn Balance sich mindestens 1x geändert hat
        self._detail_warehouse_changed_once = False  # True wenn Warehouse sich mindestens 1x geändert hat

        # Detail-/ROI-State: muss vor erster Verarbeitung existieren
        self._detail_needs_baseline_capture = False
        self._detail_baseline_captured = False
        self._detail_window_entry_item = None
        self._detail_await_preorder_check = False
        self._detail_preorder_check_baseline = None
        self._detail_last_transaction_saved = None
        self._detail_ui_orders_completed: int | None = None
        self._log_capture_failed = False

        self._last_roi_signatures = {
            "log": None,
            "label": None,
            "metrics": None,
        }
        self._last_roi_results = {
            "log": "",
            "label": "",
            "metrics": "",
        }
        self._roi_skip_counters = {
            "log": 0,
            "label": 0,
            "metrics": 0,
        }
        self._roi_force_refresh_threshold = 10
        self._metrics_refresh_failures = 0

        self._needs_log_text = True
        self._needs_metrics_text = False
        self._needs_detail_balance = False
        self._needs_detail_warehouse = False
        self._needs_detail_inputs = False

        self._roi_usage_last_scan = {
            'label': 'not_run',
            'log': 'not_run',
            'metrics': 'not_run',
            'detail_balance': 'not_run',
            'detail_warehouse': 'not_run',
            'detail_inputs': 'not_run',
        }
        self._roi_usage_session_stats = {
            'scans_total': 0,
            'label': {'ocr': 0, 'cache': 0, 'skipped': 0, 'failed': 0},
            'log': {'ocr': 0, 'cache': 0, 'skipped': 0, 'failed': 0},
            'metrics': {'ocr': 0, 'cache': 0, 'skipped': 0, 'failed': 0},
            'detail_balance': {'ocr': 0, 'cache': 0, 'skipped': 0, 'failed': 0},
            'detail_warehouse': {'ocr': 0, 'cache': 0, 'skipped': 0, 'failed': 0},
            'detail_inputs': {'ocr': 0, 'cache': 0, 'skipped': 0, 'failed': 0},
        }

        self._detail_metric_state = 'idle'
        self._window_detection_history = []
        self._stable_window = 'unknown'
        self._last_metrics_refresh_time = None

        self._pending_log_fallback_txs = []
        self._log_fallback_recent_hashes = deque(maxlen=64)
        self._log_fallback_seen_hashes: set[str] = set()
        self._log_fallback_ttl_seconds = 5.0

    def _prune_pending_relist_events(self) -> None:
        if not self._pending_relist_events:
            return

        now = datetime.datetime.now()
        cutoff = now - datetime.timedelta(seconds=self._pending_relist_ttl_seconds)
        stale_keys = []
        for key, payload in self._pending_relist_events.items():
            detected_at = payload.get('detected_at') if isinstance(payload, dict) else None
            if isinstance(detected_at, datetime.datetime) and detected_at < cutoff:
                stale_keys.append(key)
        for key in stale_keys:
            self._pending_relist_events.pop(key, None)
            if self.debug:
                log_debug(f"[RELIST] 🧹 Pending relist event expired for key='{key}'")

        
        # Frame-Perfect Baseline Capture (FIX: Pig Blood Issue)
        self._detail_needs_baseline_capture = False  # True direkt nach Window-Transition
        self._detail_baseline_captured = False  # True nachdem erste Baseline gesetzt wurde
        self._detail_window_entry_item = None  # Item-Name beim Window-Entry (für Log-Fallback)
        
        # Rolling Baseline + Preorder Detection (Phase 1 & 2)
        self._detail_await_preorder_check = False  # True nach Transaction-Save (wartet auf Preorder-Platzierung)
        self._detail_preorder_check_baseline = None  # Baseline für Preorder-Check (dict: balance, warehouse, timestamp)
        self._detail_last_transaction_saved = None  # Timestamp der letzten gespeicherten Transaction
        
        # Async pipeline controller placeholder
        self._async_controller = None
        self._log_capture_failed = False
        
        # ROI-Diffing: State für Statistical Signature-based Change Detection
        self._last_roi_signatures = {
            "log": None,      # Statistical signature des letzten Log-ROI
            "label": None,    # Statistical signature des letzten Label-ROI
            "metrics": None,  # Statistical signature des letzten Metrics-ROI
        }
        self._last_roi_results = {
            "log": "",       # Cached OCR result
            "label": "",
            "metrics": "",
        }
        self._roi_skip_counters = {
            "log": 0,        # Anzahl aufeinanderfolgender Skips
            "label": 0,
            "metrics": 0,
        }
        self._roi_force_refresh_threshold = 10  # Force-Refresh nach N Skips
        self._metrics_refresh_failures = 0  # Counter für ROI-Detection-Failures
        
        # === Bedarfsgesteuerte ROI-OCR Flags (Phase 1) ===
        self._needs_log_text = True          # Log-ROI wird initial benötigt
        self._needs_metrics_text = False     # Metrics-ROI nur bei Bedarf
        self._needs_detail_balance = False   # Detail-Balance-ROI Bedarf
        self._needs_detail_warehouse = False # Detail-Warehouse-ROI Bedarf
        self._needs_detail_inputs = False    # Detail-Input-ROI Bedarf

        # ROI-Usage Tracking (pro Scan & Session)
        self._roi_usage_last_scan = {
            'label': 'not_run',
            'log': 'not_run',
            'metrics': 'not_run',
            'detail_balance': 'not_run',
            'detail_warehouse': 'not_run',
            'detail_inputs': 'not_run',
        }
        self._roi_usage_session_stats = {
            'scans_total': 0,
            'label': {'ocr': 0, 'cache': 0, 'skipped': 0, 'failed': 0},
            'log': {'ocr': 0, 'cache': 0, 'skipped': 0, 'failed': 0},
            'metrics': {'ocr': 0, 'cache': 0, 'skipped': 0, 'failed': 0},
            'detail_balance': {'ocr': 0, 'cache': 0, 'skipped': 0, 'failed': 0},
            'detail_warehouse': {'ocr': 0, 'cache': 0, 'skipped': 0, 'failed': 0},
            'detail_inputs': {'ocr': 0, 'cache': 0, 'skipped': 0, 'failed': 0},
        }

        # Detail-Window State Machine (idle → baseline → delta)
        self._detail_metric_state = 'idle'
        
        # Window-Detection-Hysteresis: Requires 2 consecutive same detections
        self._window_detection_history = []  # Last 3 detections
        self._stable_window = 'unknown'  # Last confirmed stable window
        
        # Metrics-Refresh-Rate-Limiting: Minimum delay between refreshes
        self._last_metrics_refresh_time = None
        
        # Log-Fallback für fehlende Detail-Window Transaktionen
        self._pending_log_fallback_txs = []
        self._log_fallback_recent_hashes = deque(maxlen=64)
        self._log_fallback_seen_hashes: set[str] = set()
        self._log_fallback_ttl_seconds = 5.0
        
        # Preorder Tracking (NEW)
        self._preorder_manager = PreorderManager(debug=self.debug)

        # Stelle sicher, dass Detail-Window-State konsistent initialisiert ist
        self._reset_detail_window_state(reason="init")

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

    def _process_image(self, img, context='sync', allow_debug=True, metrics=None):
        """Run preprocessing, OCR, and downstream processing for a captured image."""
        if img is None:
            return None

        perf_prefix = f"[PERF-{context.upper()}]"
        total_start = time.perf_counter()

        # Store current frame for use in detail-window monitoring
        self._current_frame = img
        self._current_frame_proc = None  # Will be set after preprocessing

        detail_window_detected = False
        now_dt = datetime.datetime.now()

        try:
            # Reset ROI usage tracking for this scan
            self._roi_usage_last_scan = {
                'label': 'not_run',
                'log': 'not_run',
                'metrics': 'not_run',
                'detail_balance': 'not_run',
                'detail_warehouse': 'not_run',
                'detail_inputs': 'not_run',
            }

            use_fast_preprocess = self._use_fast_preprocess and self._fast_preprocess_cooldown <= 0
            if not use_fast_preprocess and self._fast_preprocess_cooldown > 0:
                # count down cooldown after each slow run
                self._fast_preprocess_cooldown = max(0, self._fast_preprocess_cooldown - 1)

            frame_hash = None
            try:
                frame_hash = hashlib.blake2s(img.tobytes(), digest_size=16).hexdigest()
            except Exception:
                frame_hash = None

            preprocess_time = 0.0
            preprocess_cache_hit = False
            proc = None
            if frame_hash:
                cached_proc = get_preprocessed_frame(frame_hash)
                if cached_proc is not None:
                    proc = cached_proc
                    preprocess_cache_hit = True
                    if self.debug:
                        log_debug(f"{perf_prefix} Preprocess cache hit (frame)")

            if proc is None:
                preprocess_start = time.perf_counter()
                # BALANCED PREPROCESSING: Use adaptive CLAHE but skip denoise
                # Fast mode was too aggressive and hurt OCR quality
                proc = preprocess(img, adaptive=True, denoise=False, fast_mode=use_fast_preprocess)
                preprocess_elapsed = time.perf_counter() - preprocess_start
                preprocess_time = preprocess_elapsed * 1000
                if frame_hash:
                    set_preprocessed_frame(frame_hash, proc)
                if self.debug:
                    log_debug(f"{perf_prefix} Preprocess: {preprocess_time:.1f}ms (balanced mode)")
            
            # Store preprocessed frame for detail-window monitoring
            self._current_frame_proc = proc
            
            if metrics is not None:
                metrics["preprocess_ms"] = preprocess_time
                metrics["preprocess_fast_mode"] = use_fast_preprocess
                metrics["preprocess_cache_hit"] = preprocess_cache_hit

            # ========================================
            # ROI-DIFFING: Change Detection vor OCR
            # ========================================
            # Detect all three ROIs
            label_roi = detect_window_label_roi(img)
            log_roi = detect_log_roi(img)
            metrics_roi = detect_metrics_roi(img)

            if allow_debug and self.debug:
                self._write_debug_images(
                    original_bgr=img,
                    processed_img=proc,
                    context=context,
                    rois={
                        "label": label_roi,
                        "log": log_roi,
                        "metrics": metrics_roi,
                    },
                    window_type=self._detail_window_type if detail_window_detected else None,
                )
            
            # Compute hashes for change detection
            roi_changed = {
                "log": False,
                "label": False,
                "metrics": False,
            }
            
            roi_stats_start = time.perf_counter()
            for roi_name, roi_coords in [
                ("label", label_roi),
                ("log", log_roi),
                ("metrics", metrics_roi),
            ]:
                if roi_coords is None:
                    # No ROI detected -> force OCR
                    roi_changed[roi_name] = True
                    continue
                
                # Compute statistical signature for this ROI
                current_sig = compute_roi_stats_signature(proc, roi_coords)
                last_sig = self._last_roi_signatures.get(roi_name)
                
                if current_sig and last_sig and compare_roi_signatures(current_sig, last_sig):
                    # ROI unchanged (within threshold) -> skip OCR
                    self._roi_skip_counters[roi_name] += 1
                    roi_changed[roi_name] = False
                    if self.debug and self._scan_counter > 1:
                        log_debug(f"[ROI-STATS] {roi_name.upper()}-ROI unchanged (skip #{self._roi_skip_counters[roi_name]})")
                else:
                    # ROI changed -> run OCR
                    self._last_roi_signatures[roi_name] = current_sig
                    self._roi_skip_counters[roi_name] = 0
                    roi_changed[roi_name] = True
                if self.debug:
                    log_debug(
                        f"[ROI-STATS] counters after {roi_name}: "
                        f"log={self._roi_skip_counters['log']}, "
                        f"label={self._roi_skip_counters['label']}, "
                        f"metrics={self._roi_skip_counters['metrics']}"
                    )
            
            roi_stats_time = (time.perf_counter() - roi_stats_start) * 1000
            if metrics is not None and self.debug:
                metrics["roi_stats_ms"] = roi_stats_time
            
            # Force-Refresh Heuristiken
            force_refresh = (
                self._request_immediate_rescan > 0 or
                any(count >= self._roi_force_refresh_threshold 
                    for count in self._roi_skip_counters.values())
            )
            
            if force_refresh:
                if self.debug:
                    reasons = []
                    if self._request_immediate_rescan > 0:
                        reasons.append(f"burst_rescan={self._request_immediate_rescan}")
                    for key, count in self._roi_skip_counters.items():
                        if count >= self._roi_force_refresh_threshold:
                            reasons.append(f"{key}_skip_limit={count}")
                    log_debug(f"[ROI-STATS] Force refresh: {', '.join(reasons) if reasons else 'manual trigger'}")
                
                for key in roi_changed:
                    roi_changed[key] = True

            # First, OCR the label ROI to determine window context.
            label_text = ""
            label_ms = 0.0
            label_roi_skipped = False
            if label_roi:
                if roi_changed["label"]:
                    label_start = time.perf_counter()
                    label_text, label_cached, label_stats = ocr_image_cached(
                        img,
                        method='auto',
                        use_roi=True,
                        preprocessed=proc,
                        fast_mode=use_fast_preprocess,
                        roi=label_roi,
                        roi_label="label",
                        cache_tag="label",
                    )
                    label_ms = (time.perf_counter() - label_start) * 1000
                    if label_text:
                        self._last_label_text = label_text
                        self._last_roi_results["label"] = label_text
                    if metrics is not None:
                        metrics["label_cache_hit"] = bool(label_cached)
                        metrics["label_cache_age_s"] = label_stats.get("cache_age")
                        metrics["label_ms"] = label_ms
                    self._roi_usage_last_scan['label'] = 'cache' if label_cached else 'ocr'
                else:
                    # Use cached result from last scan
                    label_text = self._last_roi_results["label"]
                    label_roi_skipped = True
                    if metrics is not None:
                        metrics["roi_label_skipped"] = True
                        metrics["label_ms"] = 0.0
                    self._roi_usage_last_scan['label'] = 'cache'
            else:
                self._roi_usage_last_scan['label'] = 'failed'

            cached_label = self._last_label_text if not label_text else label_text
            label_lower = (cached_label or "").lower()

            overview_anchor = bool(
                re.search(
                    r"(sales\s+completed|orders\s+completed|items\s+listed)",
                    label_lower,
                )
            )
            detail_hint = bool(re.search(r"(set\s*price|desired\s*price)", label_lower))
            detail_window_detected = detail_hint and not overview_anchor

            detail_window_type_hint: str | None = None
            if detail_window_detected:
                if any(keyword in label_lower for keyword in ["set price", "register"]):
                    detail_window_type_hint = "sell_item"
                elif any(keyword in label_lower for keyword in ["desired price", "desired amount"]):
                    detail_window_type_hint = "buy_item"

            if detail_window_detected:
                if detail_window_type_hint:
                    self._detail_window_hint = detail_window_type_hint
            elif not self._detail_window_active and self._detail_window_hint:
                self._detail_window_hint = None

            if allow_debug and self.debug:
                self._write_debug_images(
                    original_bgr=img,
                    processed_img=proc,
                    context=context,
                    rois={
                        "label": label_roi,
                        "log": log_roi,
                        "metrics": metrics_roi,
                    },
                    window_type=detail_window_type_hint,
                )

            text = ""
            was_cached = False
            log_stats: dict[str, Any] | dict = {}
            log_ms = 0.0
            log_roi_skipped = False

            if detail_window_detected:
                # Detail-Fenster enthalten keinen Log-Text – Log-OCR überspringen
                self._roi_usage_last_scan['log'] = 'skipped'
                log_roi_skipped = True
                if self._needs_log_text:
                    self._set_need_flag('log_text', False, "detail_window_skip")
            else:
                if log_roi and (roi_changed["log"] or force_refresh or self._needs_log_text):
                    log_start = time.perf_counter()
                    text, was_cached, log_stats = ocr_image_cached(
                        img,
                        method='auto',
                        use_roi=True,
                        preprocessed=proc,
                        fast_mode=use_fast_preprocess,
                        roi=log_roi,
                        roi_label="log",
                        cache_tag="log",
                    )
                    log_ms = (time.perf_counter() - log_start) * 1000
                    self._roi_usage_last_scan['log'] = 'cache' if was_cached else 'ocr'
                    self._last_roi_results["log"] = text or ""
                    self._latest_log_text = text or ""
                    self._set_need_flag('log_text', False, "log_ocr_success" if text else "log_ocr_empty")
                    self._log_capture_failed = not bool(text)
                elif log_roi:
                    text = self._last_roi_results["log"]
                    self._latest_log_text = text or ""
                    self._roi_usage_last_scan['log'] = 'cache'
                    log_roi_skipped = True
                    self._roi_skip_counters['log'] = self._roi_skip_counters.get('log', 0) + 1
                    self._set_need_flag('log_text', False, "log_cache_hit")
                    self._log_capture_failed = not bool(text)
                else:
                    self._roi_usage_last_scan['log'] = 'failed'
                    self._latest_log_text = ""
                    self._roi_skip_counters['log'] = self._roi_skip_counters.get('log', 0) + 1
                    self._set_need_flag('log_text', True, "log_roi_missing")
                    text = ""
                    self._log_capture_failed = True

            if metrics is not None:
                if log_roi_skipped:
                    metrics["roi_log_skipped"] = True
                if self._roi_usage_last_scan['log'] == 'failed':
                    metrics["roi_log_failed"] = True
                metrics["log_ms"] = log_ms
                metrics["log_cache_hit"] = bool(was_cached)
                if isinstance(log_stats, dict):
                    metrics["log_cache_age_s"] = log_stats.get("cache_age")
                    metrics["log_cache_size"] = log_stats.get("cache_size")

            if detail_window_detected:
                # Detail-Fenster: letzte Log-Erkennung behalten (für Fallbacks)
                text = ""

            # CRITICAL FIX: Metrics-ROI wird NUR bei echten Transaktionen gebraucht!
            # Laut AGENTS.md: "Detail-/Metrics-ROI wird nach Fensterwechseln, Burst-Rescans, 
            # Detail-Hinweisen oder wenn im Fenster-Label keine Overview-Anker erkannt werden sofort neu ausgelesen"
            # 
            # ALTE LOGIK (FALSCH): 5-Sekunden-Timer + "not overview_anchor" -> ständiges Auslesen
            # NEUE LOGIK: Nur bei Fensterwechsel, Burst oder Detail-Hinweisen
            refresh_metrics = False
            metrics_text = ""
            if self._needs_metrics_text:
                refresh_metrics = True
            elif self._pending_metrics_refresh:
                refresh_metrics = True
            elif self._scan_counter <= 1:
                refresh_metrics = True
            elif self._request_immediate_rescan > 0:
                refresh_metrics = True
            elif detail_hint and not detail_window_detected:
                refresh_metrics = True

            metrics_refresh_ran = False
            metrics_roi_skipped = False
            if detail_window_detected:
                refresh_metrics = False
                self._pending_metrics_refresh = True
                self._roi_usage_last_scan['metrics'] = 'not_run'

            if refresh_metrics and roi_changed["metrics"]:
                # Metrics-ROI hat sich geändert UND Refresh ist angefordert
                if metrics_roi:
                    metrics_text, metrics_cached, metrics_stats = ocr_image_cached(
                        img,
                        method='auto',
                        use_roi=True,
                        preprocessed=proc,
                        fast_mode=use_fast_preprocess,
                        roi=metrics_roi,
                        roi_label="metrics",
                        cache_tag="metrics",
                    )
                    if metrics_text:
                        self._last_metrics_text = metrics_text
                        self._last_roi_results["metrics"] = metrics_text
                    metrics_refresh_ran = True
                    if metrics is not None:
                        metrics["metrics_cache_hit"] = bool(metrics_cached)
                        metrics["metrics_cache_size"] = metrics_stats.get("cache_size")
                        metrics["metrics_cache_age_s"] = metrics_stats.get("cache_age")
                    self._pending_metrics_refresh = False
                    self._metrics_refresh_failures = 0  # Reset counter on success
                    self._last_metrics_refresh_time = now_dt  # Update rate-limiting timer
                    self._last_metrics_refresh_ts = now_dt
                    self._roi_usage_last_scan['metrics'] = 'cache' if metrics_cached else 'ocr'
                    self._set_need_flag('metrics_text', False, "metrics_ocr_success")
                else:
                    # ROI detection failed - count failure
                    self._metrics_refresh_failures += 1
                    if self._metrics_refresh_failures >= 3:
                        # Give up after 3 failures to prevent stuck state
                        self._pending_metrics_refresh = False
                        self._metrics_refresh_failures = 0
                        if self.debug:
                            log_debug("[ROI-STATS] Cleared stuck metrics_refresh after 3 ROI detection failures")
                        self._set_need_flag('metrics_text', False, "metrics_detection_failed")
                    else:
                        # Retry on next scan
                        self._pending_metrics_refresh = True
            elif refresh_metrics and not roi_changed["metrics"]:
                # Refresh angefordert, aber Metrics-ROI unverändert -> Use cached
                metrics_text = self._last_roi_results["metrics"]
                metrics_roi_skipped = True
                self._pending_metrics_refresh = False  # Clear flag after using cache
                self._last_metrics_refresh_time = now_dt  # Update rate-limiting timer
                if self.debug:
                    log_debug(f"{perf_prefix} Metrics-OCR skipped via ROI-Diff")
                if metrics is not None:
                    metrics["roi_metrics_skipped"] = True
                self._pending_metrics_refresh = False  # Mark as refreshed
                self._metrics_refresh_failures = 0  # Reset counter
                self._last_metrics_refresh_ts = now_dt
                self._roi_usage_last_scan['metrics'] = 'cache'
                self._roi_skip_counters['metrics'] = self._roi_skip_counters.get('metrics', 0) + 1
                self._set_need_flag('metrics_text', False, "metrics_cache_hit")
            if metrics is not None:
                metrics["metrics_refresh"] = metrics_refresh_ran
            if not refresh_metrics and not detail_window_detected:
                self._roi_usage_last_scan['metrics'] = 'skipped'
                self._roi_skip_counters['metrics'] = self._roi_skip_counters.get('metrics', 0) + 1
                if self._needs_metrics_text:
                    self._set_need_flag('metrics_text', False, "metrics_skip_overview")
            if refresh_metrics and not metrics_roi:
                self._roi_usage_last_scan['metrics'] = 'failed'
                self._roi_skip_counters['metrics'] = self._roi_skip_counters.get('metrics', 0) + 1
                self._set_need_flag('metrics_text', False, "metrics_roi_missing")
            cached_metrics = self._last_metrics_text if not metrics_text else metrics_text
            if detail_window_detected:
                cached_metrics = ""

            # DETAIL-WINDOW: Extrahiere Item-Name, Balance und Warehouse aus Detail-Fenstern
            detail_window_text = ""
            if detail_window_detected and cached_label:
                # Bestimme Fenstertyp
                detected_detail_type = detail_window_type_hint
                if not detected_detail_type:
                    label_text_lower = cached_label.lower()
                    if 'set price' in label_text_lower or 'register' in label_text_lower:
                        detected_detail_type = 'sell_item'
                    elif 'desired price' in label_text_lower or 'desired amount' in label_text_lower:
                        detected_detail_type = 'buy_item'
                    else:
                        detected_detail_type = None
                
                if detected_detail_type:
                    self._detail_window_hint = detected_detail_type
                    # Import Detail-ROI-Funktionen
                    from utils import detect_detail_item_name_roi, detect_detail_balance_roi, detect_detail_warehouse_roi
                    
                    # ⚡ PERFORMANCE FIX: Cache Item Name across scans
                    # Item name NEVER changes während einer Detail-Session
                    item_name_text = self._detail_window_item or ""
                    if not item_name_text:
                        item_name_roi = detect_detail_item_name_roi(proc, detected_detail_type)
                        if item_name_roi:
                            item_name_text, _, _ = ocr_image_cached(
                                img,
                                method='auto',
                                use_roi=True,
                                preprocessed=proc,
                                fast_mode=use_fast_preprocess,
                                roi=item_name_roi,
                                roi_label="detail_item_name",
                                cache_tag="detail_item_name",
                            )
                            if item_name_text:
                                self._detail_window_item = item_name_text

                    balance_text = self._last_detail_balance_text if hasattr(self, "_last_detail_balance_text") else ""
                    warehouse_text = self._last_detail_warehouse_text if hasattr(self, "_last_detail_warehouse_text") else ""

                    balance_roi = detect_detail_balance_roi(proc, detected_detail_type)
                    warehouse_roi = detect_detail_warehouse_roi(proc, detected_detail_type)

                    if balance_roi and (self._needs_detail_balance or detail_window_detected):
                        balance_text, balance_cached, _ = ocr_image_cached(
                            img,
                            method='auto',
                            use_roi=True,
                            preprocessed=proc,
                            fast_mode=use_fast_preprocess,
                            roi=balance_roi,
                            roi_label="detail_balance",
                            cache_tag="detail_balance",
                        )
                        self._last_detail_balance_text = balance_text or ""
                        self._roi_usage_last_scan['detail_balance'] = 'cache' if balance_cached else 'ocr'
                        if balance_text and balance_text.strip():
                            self._set_need_flag('detail_balance', False, "detail_balance_ocr")
                        else:
                            self._set_need_flag('detail_balance', True, "detail_balance_empty")

                    elif balance_roi:
                        self._roi_usage_last_scan['detail_balance'] = 'skipped'
                    elif balance_text:
                        self._roi_usage_last_scan['detail_balance'] = 'cache'
                    else:
                        self._roi_usage_last_scan['detail_balance'] = 'not_run'

                    if warehouse_roi and (self._needs_detail_warehouse or detail_window_detected):
                        warehouse_text, warehouse_cached, _ = ocr_image_cached(
                            img,
                            method='auto',
                            use_roi=True,
                            preprocessed=proc,
                            fast_mode=use_fast_preprocess,
                            roi=warehouse_roi,
                            roi_label="detail_warehouse",
                            cache_tag="detail_warehouse",
                        )
                        self._last_detail_warehouse_text = warehouse_text or ""
                        self._roi_usage_last_scan['detail_warehouse'] = 'cache' if warehouse_cached else 'ocr'
                        if warehouse_text and warehouse_text.strip():
                            self._set_need_flag('detail_warehouse', False, "detail_warehouse_ocr")
                        else:
                            self._set_need_flag('detail_warehouse', True, "detail_warehouse_empty")

                    elif warehouse_roi:
                        self._roi_usage_last_scan['detail_warehouse'] = 'skipped'
                    elif warehouse_text:
                        self._roi_usage_last_scan['detail_warehouse'] = 'cache'
                    else:
                        self._roi_usage_last_scan['detail_warehouse'] = 'not_run'

                    if not hasattr(self, "_last_detail_balance_text"):
                        self._last_detail_balance_text = balance_text
                    if not hasattr(self, "_last_detail_warehouse_text"):
                        self._last_detail_warehouse_text = warehouse_text

                    # Kombiniere Detail-Window-Text
                    detail_parts = []
                    if item_name_text:
                        detail_parts.append(item_name_text)
                    if balance_text:
                        detail_parts.append(balance_text)
                    if warehouse_text:
                        detail_parts.append(warehouse_text)
                    detail_window_text = "\n".join(part for part in detail_parts if part)
                    
                    if self.debug and detail_window_text:
                        log_debug(f"[DETAIL] Extracted detail window metrics:\n{detail_window_text[:200]}")

            combined_parts = []
            if cached_label:
                combined_parts.append(cached_label)
            if detail_window_text:
                # Bei Detail-Fenstern: Label + Detail-ROIs (kein Log-Text)
                combined_parts.append(detail_window_text)
            elif text:
                # Bei Overview-Fenstern: Log-Text
                combined_parts.append(text)
            if not detail_window_detected:
                self._last_detail_balance_text = ""
                self._last_detail_warehouse_text = ""
            if cached_metrics and not detail_window_detected:
                # Metrics nur bei Overview-Fenstern
                combined_parts.append(cached_metrics)
            full_text = "\n".join(part for part in combined_parts if part)

            log_text(full_text)
            if self.debug and context != 'async':
                preview = full_text[:700].replace("\n", " ") if full_text else ""
                print(f"OCR ({context}):", preview)

            process_start = time.perf_counter()
            self.process_ocr_text(full_text)
            process_elapsed = time.perf_counter() - process_start
            process_time = process_elapsed * 1000
            total_elapsed = time.perf_counter() - total_start
            total_time = total_elapsed * 1000

            if self.debug:
                log_debug(f"{perf_prefix} Process: {process_time:.1f}ms, Total scan: {total_time:.1f}ms")

            if metrics is not None:
                metrics["postprocess_ms"] = process_time
                metrics["total_ms"] = total_time
                metrics["ocr_text_length"] = len(text) if text else 0
                metrics["label_text_length"] = len(cached_label) if cached_label else 0
                metrics["metrics_text_length"] = len(cached_metrics) if cached_metrics else 0

            text_length = len(text) if text else 0
            if use_fast_preprocess:
                if not was_cached and text_length < 20:
                    self._fast_preprocess_failures += 1
                    if self._fast_preprocess_failures >= 2:
                        self._use_fast_preprocess = False
                        self._fast_preprocess_cooldown = 5
                        self._fast_preprocess_recovery = 0
                        if self.debug:
                            log_debug("[PERF] Fast preprocess disabled due to short OCR result")
                else:
                    self._fast_preprocess_failures = 0
                    self._fast_preprocess_recovery = 0
            else:
                if text_length > 40:
                    self._fast_preprocess_recovery += 1
                else:
                    self._fast_preprocess_recovery = 0
                if self._fast_preprocess_cooldown == 0 and self._fast_preprocess_recovery >= 3:
                    self._use_fast_preprocess = True
                    self._fast_preprocess_failures = 0
                    if self.debug:
                        log_debug("[PERF] Fast preprocess re-enabled after stable scans")

            if self.error_count > 0:
                self.error_count = max(0, self.error_count - 1)

            # ROI usage aggregation & debug output (Phase 1 instrumentation)
            self._roi_usage_session_stats['scans_total'] += 1
            for roi_name, status in self._roi_usage_last_scan.items():
                roi_stats = self._roi_usage_session_stats.get(roi_name)
                if not roi_stats:
                    continue
                if status in roi_stats:
                    roi_stats[status] += 1

            if self.debug or get_debug_mode('roi_stats'):
                ocr_count = sum(1 for status in self._roi_usage_last_scan.values() if status == 'ocr')
                cache_count = sum(1 for status in self._roi_usage_last_scan.values() if status == 'cache')
                skip_count = sum(1 for status in self._roi_usage_last_scan.values() if status == 'skipped')
                failed_count = sum(1 for status in self._roi_usage_last_scan.values() if status == 'failed')
                log_debug(
                    f"[ROI-STATS] Scan #{self._scan_counter}: "
                    f"OCR={ocr_count}, Cache={cache_count}, Skipped={skip_count}, Failed={failed_count} | "
                    f"Details: {self._roi_usage_last_scan}"
                )

            return text
        except Exception as exc:
            if self.debug:
                log_debug(f"[ERROR-{context.upper()}] {exc}")
            self.error_count += 1
            self.last_error_time = datetime.datetime.now()
            self.last_error_message = f"Processing error: {exc}"
            if metrics is not None:
                metrics.setdefault("error", str(exc))
            # fallback to balanced preprocessing after errors
            self._use_fast_preprocess = False
            self._fast_preprocess_cooldown = max(self._fast_preprocess_cooldown, 5)
            self._fast_preprocess_recovery = 0
            return None

    def _set_need_flag(self, flag_name: str, value: bool, reason: str = "") -> None:
        """Setzt Bedarf-Flags für ROI-OCR mit optionalem Debug-Log."""
        attr_name = f"_needs_{flag_name}"
        if not hasattr(self, attr_name):
            if self.debug:
                log_debug(f"[ROI-FLAG] Ignoring unknown flag '{flag_name}' (reason: {reason})")
            return

        current_value = getattr(self, attr_name)
        if current_value == value:
            return

        setattr(self, attr_name, value)
        if self.debug:
            action = "ENABLED" if value else "DISABLED"
            log_debug(f"[ROI-FLAG] {flag_name}: {action} | Reason: {reason}")

    def _schedule_metrics_refresh(self, reason: str = "") -> None:
        """Plants Metrics-ROI-OCR mit einfachem Rate-Limiting."""
        now = datetime.datetime.now()
        time_since_last_refresh = None
        if self._last_metrics_refresh_time is not None:
            time_since_last_refresh = (now - self._last_metrics_refresh_time).total_seconds()

        is_burst = (self._burst_until and now < self._burst_until) or self._request_immediate_rescan > 0
        if is_burst or time_since_last_refresh is None or time_since_last_refresh >= 1.0:
            self._pending_metrics_refresh = True
            self._set_need_flag('metrics_text', True, reason or "schedule_metrics_refresh")
        else:
            if self.debug:
                log_debug(
                    f"[METRICS-REFRESH] Skipped (rate limit {time_since_last_refresh:.2f}s < 1.0s) | Reason: {reason}"
                )
            self._pending_metrics_refresh = True
            self._set_need_flag('metrics_text', True, "metrics_refresh_rate_limited")

    DETAIL_DELTA_IDLE_TIMEOUT = 2.5  # seconds of inactivity allowed in delta-state before reverting to baseline

    def _set_detail_metric_state(self, state: str, reason: str = "") -> None:
        """Verwaltet den Detail-Window-State (idle/baseline/delta) und zugehörige Flags."""
        valid_states = ("idle", "baseline", "delta")
        if state not in valid_states:
            if self.debug:
                log_debug(f"[DETAIL-STATE] Invalid state '{state}' (reason: {reason})")
            return

        previous_state = getattr(self, "_detail_metric_state", "idle")
        if previous_state == state:
            return

        now = datetime.datetime.now()
        self._detail_metric_state = state

        if state == "idle":
            self._set_need_flag('detail_balance', False, "detail_state_idle")
            self._set_need_flag('detail_warehouse', False, "detail_state_idle")
            self._set_need_flag('detail_inputs', False, "detail_state_idle")
            self._detail_last_delta_activity = None
        elif state == "baseline":
            self._set_need_flag('detail_balance', True, "detail_state_baseline")
            self._set_need_flag('detail_warehouse', True, "detail_state_baseline")
            if self._detail_window_type == 'buy_item':
                self._set_need_flag('detail_inputs', True, "detail_state_baseline")
            self._detail_last_delta_activity = now
        elif state == "delta":
            # delta-state nutzt on-demand Flags, kein Default-Toggle nötig
            self._detail_last_delta_activity = now

        if self.debug:
            log_debug(f"[DETAIL-STATE] {previous_state} → {state} | Reason: {reason}")

    def get_roi_usage_summary(self) -> dict[str, Any]:
        """Gibt aggregierte ROI-Nutzungsstatistiken der aktuellen Session zurück."""
        summary: dict[str, Any] = {'scans_total': self._roi_usage_session_stats['scans_total']}
        total_scans = self._roi_usage_session_stats['scans_total']

        for roi_name in ['label', 'log', 'metrics', 'detail_balance', 'detail_warehouse', 'detail_inputs']:
            roi_stats = self._roi_usage_session_stats.get(roi_name, {})
            roi_summary = dict(roi_stats)
            total_activations = sum(roi_stats.values())
            roi_summary['total_activations'] = total_activations
            if total_scans > 0:
                roi_summary['activation_rate'] = (total_activations / total_scans) * 100.0
            else:
                roi_summary['activation_rate'] = 0.0

            if total_activations > 0:
                roi_summary['ocr_rate'] = (roi_stats['ocr'] / total_activations) * 100.0 if roi_stats['ocr'] else 0.0
                roi_summary['cache_rate'] = (roi_stats['cache'] / total_activations) * 100.0 if roi_stats['cache'] else 0.0
                roi_summary['skip_rate'] = (roi_stats['skipped'] / total_activations) * 100.0 if roi_stats['skipped'] else 0.0
                roi_summary['failed_rate'] = (roi_stats['failed'] / total_activations) * 100.0 if roi_stats['failed'] else 0.0
            else:
                roi_summary['ocr_rate'] = 0.0
                roi_summary['cache_rate'] = 0.0
                roi_summary['skip_rate'] = 0.0
                roi_summary['failed_rate'] = 0.0

            summary[roi_name] = roi_summary

        return summary

    def _write_debug_images(
        self,
        original_bgr,
        processed_img,
        context: str,
        rois: Optional[dict[str, tuple[int, int, int, int] | None]] = None,
        window_type: str | None = None,
    ) -> None:
        """Persist the latest debug screenshots so investigation always has fresh material."""
        debug_dir = Path("debug")
        try:
            debug_dir.mkdir(exist_ok=True)
        except Exception:
            pass

        latest_orig = debug_dir / "debug_orig.png"
        latest_proc = debug_dir / "debug_proc.png"

        def _save_image(arr, path, color=True):
            if arr is None or arr.size == 0:
                return
            img = arr
            if color and arr.ndim == 3:
                img = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
            try:
                Image.fromarray(img).save(path)
            except Exception:
                pass

        def _save_roi_from_coords(tag: str, roi):
            if not roi:
                return
            x, y, w, h = roi
            if w <= 0 or h <= 0:
                return
            roi_bgr = original_bgr[y:y+h, x:x+w]
            roi_proc = None
            try:
                roi_proc = processed_img[y:y+h, x:x+w]
            except Exception:
                roi_proc = None
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            _save_image(roi_bgr, debug_dir / f"debug_{tag}_{timestamp}_orig.png", color=True)
            if roi_proc is not None and roi_proc.size > 0:
                _save_image(roi_proc, debug_dir / f"debug_{tag}_{timestamp}_proc.png", color=False)

        with self._debug_image_lock:
            try:
                _save_image(original_bgr, latest_orig, color=True)
                _save_image(processed_img, latest_proc, color=False)
                
                # Save ROIs based on provided coordinates
                roi_map = rois or {}
                for tag, coords in roi_map.items():
                    _save_roi_from_coords(tag, coords)

                # Detail-window specific ROIs if requested
                if window_type in {"buy_item", "sell_item"}:
                    try:
                        preorder_roi = detect_detail_preorder_input_roi(processed_img, window_type)
                    except Exception:
                        preorder_roi = None
                    detail_rois = {
                        "detail_item_name": detect_detail_item_name_roi(processed_img, window_type),
                        "detail_balance": detect_detail_balance_roi(processed_img, window_type),
                        "detail_warehouse": detect_detail_warehouse_roi(processed_img, window_type),
                        "detail_preorder_input": preorder_roi,
                    }
                    for tag, coords in detail_rois.items():
                        _save_roi_from_coords(f"{tag}_{window_type}", coords)
            except Exception as save_err:
                log_debug(f"[DEBUG] Failed to write debug images: {save_err}")

    def _get_next_sleep_interval(self):
        now = datetime.datetime.now()
        if self._burst_until and now < self._burst_until:
            if self._burst_source == 'item_window':
                sleep_iv = 0.08 if self._burst_fast_scans > 0 else self.poll_interval_burst
            else:
                sleep_iv = self.poll_interval
        else:
            sleep_iv = self.poll_interval
            if self._burst_until and now >= self._burst_until:
                self._burst_until = None
                self._burst_source = None
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
        corrected, valid = self._safe_correct_item_name(item_name, min_score=80)
        if corrected and corrected.lower() != key:
            candidates.append(corrected)

        # CRITICAL FIX: Use BDO API instead of market.json for base_price!
        # market.json is ONLY used for item_name → item_id resolution
        # Actual prices must come from BDO Trade Market API
        base_price: int | None = None
        for candidate in candidates:
            if not candidate:
                continue
            try:
                # Get live price data from BDO API
                data = get_item_price_range_by_name(candidate, use_cache=True)
                if data and data.get('base_price'):
                    base_price = int(data['base_price'])
                    if self.debug:
                        log_debug(f"[PRICE] Base price from BDO API for '{candidate}': {base_price:,}")
                    break
            except Exception as exc:
                if self.debug:
                    log_debug(f"[PRICE] BDO API lookup failed for '{candidate}': {exc}")
                continue

        # cache result (including None to avoid repeated lookups)
        self._base_price_cache[key] = base_price or 0
        if base_price:
            for cand in candidates:
                if cand:
                    self._base_price_cache[cand.lower()] = base_price
        return base_price
    
    def _calculate_expected_qty(
        self,
        balance_delta: float,
        item_name: str
    ) -> int:
        """
        Calculate expected purchase quantity from balance delta.
        
        This is used for auto-collect detection: if warehouse_delta > expected_qty,
        the surplus might be from a preorder auto-collect.
        
        Algorithm:
        1. Get base price from BDO API
        2. Estimate unit price as 92.5% of base (middle of 85%-100% range)
        3. Calculate quantity = balance_delta / estimated_unit_price
        4. Round to nearest 1000 (most purchases are in 1k increments)
        5. If < 1000, round to nearest 100
        
        Args:
            balance_delta: Balance decrease (positive value!)
            item_name: Item name for base price lookup
            
        Returns:
            Estimated purchase quantity (0 if cannot determine)
        """
        if balance_delta <= 0:
            return 0
        
        base_price = self._get_base_price(item_name)
        if base_price is None or base_price <= 0:
            return 0
        
        # Use middle of price range (92.5% of base price)
        # Price range is 85%-100% for purchases
        estimated_unit_price = base_price * 0.925
        
        # Calculate raw quantity
        estimated_qty = balance_delta / estimated_unit_price if estimated_unit_price else 0

        # Round to nearest 1000 (most purchases are 1k, 2k, 5k, etc.)
        if estimated_qty >= 500:
            estimated_qty_rounded = round(estimated_qty / 1000) * 1000
        # If < 1000, round to nearest 100
        elif estimated_qty >= 50:
            estimated_qty_rounded = round(estimated_qty / 100) * 100
        # If < 100, use raw value
        else:
            estimated_qty_rounded = int(estimated_qty)
        
        return max(1, estimated_qty_rounded)

    def _safe_correct_item_name(
        self,
        raw_name: str | None,
        min_score: int = 86
    ) -> tuple[str | None, bool]:
        """
        Wrapper around market_json_manager.correct_item_name with defensive fallbacks.
        """
        if raw_name is None:
            return None, False

        try:
            candidate = str(raw_name).strip()
        except Exception:
            candidate = ""

        if not candidate:
            return None, False

        try:
            corrected_name, is_valid = correct_item_name(candidate, min_score=min_score)
            corrected = corrected_name or candidate
            return corrected, bool(is_valid)
        except Exception as exc:
            if self.debug:
                log_debug(f"[ITEM-NAME] Correction failed for '{candidate}': {exc}")
            return candidate, False

    def _invalidate_detail_input_cache(self, kind: str | None = None) -> None:
        if not hasattr(self, '_detail_input_cache'):
            return

        if kind is None:
            for key in list(self._detail_input_cache.keys()):
                self._detail_input_cache[key] = None
        elif kind in self._detail_input_cache:
            self._detail_input_cache[kind] = None

        if kind is None or kind == 'refresh':
            self._detail_input_refresh_pending = False
            self._detail_input_refresh_reason = None
            self._detail_input_refresh_window = None

    def _cache_detail_input_fields(
        self,
        *,
        kind: str,
        fields: dict[str, int | float | str | None],
        window_type: str,
        source: str = "",
        timestamp: datetime.datetime | None = None,
    ) -> None:
        if not fields or kind not in self._detail_input_cache:
            return

        normalized: dict[str, int] = {}
        for key in ("quantity", "price"):
            if key not in fields:
                return
            value = fields.get(key)
            if value is None:
                return
            try:
                normalized[key] = int(value)
            except Exception:
                try:
                    normalized[key] = int(float(value))
                except Exception:
                    return

        entry = {
            'fields': normalized,
            'timestamp': timestamp or datetime.datetime.now(),
            'window_type': window_type,
            'source': source,
        }
        self._detail_input_cache[kind] = entry

        if kind == 'refresh':
            self._detail_input_refresh_pending = False
            self._detail_input_refresh_reason = None
            self._detail_input_refresh_window = None

    def _get_detail_input_fields(
        self,
        *,
        window_type: str | None = None,
        prefer_refresh: bool = True,
        max_age_override: float | None = None,
    ) -> tuple[dict[str, int] | None, datetime.datetime | None, str | None]:
        if not hasattr(self, '_detail_input_cache'):
            return None, None, None

        now = datetime.datetime.now()
        order = ['refresh', 'baseline'] if prefer_refresh else ['baseline', 'refresh']

        for kind in order:
            entry = self._detail_input_cache.get(kind)
            if not entry:
                continue
            fields = entry.get('fields')
            timestamp = entry.get('timestamp')
            cached_window = entry.get('window_type')

            if window_type and cached_window and cached_window != window_type:
                continue

            ttl = max_age_override if max_age_override is not None else self._detail_input_cache_ttl.get(kind, 5.0)
            if timestamp and ttl is not None:
                try:
                    age = (now - timestamp).total_seconds()
                except Exception:
                    age = ttl + 1.0
                if age > ttl:
                    if self.debug:
                        log_debug(
                            f"[DETAIL-CACHE] {kind} entry expired (age={age:.2f}s > ttl={ttl:.2f}s, window={cached_window})"
                        )
                    self._detail_input_cache[kind] = None
                    continue

            if fields:
                return fields.copy(), timestamp, kind

        return None, None, None

    def _request_detail_input_refresh(self, window_type: str, reason: str = "") -> None:
        if window_type not in ('buy_item', 'sell_item'):
            return

        if self._detail_input_refresh_pending and self._detail_input_refresh_window == window_type:
            return

        cached_fields, _, kind = self._get_detail_input_fields(window_type=window_type, prefer_refresh=True)
        if cached_fields and kind == 'refresh':
            return

        self._detail_input_refresh_pending = True
        self._detail_input_refresh_reason = reason or f"refresh_needed_{window_type}"
        self._detail_input_refresh_window = window_type
        self._set_need_flag('detail_inputs', True, self._detail_input_refresh_reason)

    def _extract_preorder_input_fields(
        self,
        img,
        proc_img,
        window_type: str
    ) -> Optional[Dict]:
        """
        Extrahiert Preorder-Eingabewerte aus Detail-Fenster Input-ROI.
        
        CRITICAL: Wird für Relist-Detection verwendet!
        Diese Methode liest die tatsächlich eingegebenen Werte aus den Input-Feldern.
        
        Buy-Item Felder:
        - "Desired Price": Stückpreis (z.B. 154,000)
        - "Desired Amount": Anzahl (z.B. 5000)
        
        Sell-Item Felder:
        - "Set Price": Stückpreis
        - "Register Quantity": Anzahl
        
        Args:
            img: Original BGR image
            proc_img: Preprocessed image
            window_type: 'buy_item' oder 'sell_item'
            
        Returns:
            Dict mit {'price': int, 'quantity': int} oder None
        """
        try:
            status = 'not_run'

            if not getattr(self, '_needs_detail_inputs', False):
                if self.debug:
                    log_debug("[PREORDER-INPUT] Skip OCR (flag disabled)")
                status = 'skipped'
                self._roi_usage_last_scan['detail_inputs'] = status
                return None
            
            # Get preorder input ROI
            roi = detect_detail_preorder_input_roi(proc_img, window_type)
            if not roi:
                if self.debug:
                    log_debug("[PREORDER-INPUT] ROI detection failed")
                status = 'failed'
                self._roi_usage_last_scan['detail_inputs'] = status
                return None
            
            # OCR des Input-Bereichs
            ocr_start = time.perf_counter()
            input_text, was_cached, cache_stats = ocr_image_cached(
                img,
                method='auto',
                use_roi=True,
                preprocessed=proc_img,
                fast_mode=False,  # Verwende hohe Qualität!
                roi=roi,
                roi_label="preorder_input",
                cache_tag="preorder_input",
            )
            ocr_time = (time.perf_counter() - ocr_start) * 1000
            
            status = 'cache' if was_cached else 'ocr'
            self._roi_usage_last_scan['detail_inputs'] = status

            if not input_text or len(input_text) < 3:
                if self.debug:
                    log_debug(f"[PREORDER-INPUT] OCR empty ({ocr_time:.1f}ms)")
                # Flag aktiv lassen, damit nächster Scan erneut versucht
                return None
            
            if self.debug:
                log_debug(f"[PREORDER-INPUT] OCR ({ocr_time:.1f}ms): {input_text[:200]}")
            
            result = {}
            
            # Extrahiere Preis
            if window_type == 'buy_item':
                price_label = 'Desired Price'
            else:
                price_label = 'Set Price'
            
            # Price patterns - sehr flexibel!
            price_patterns = [
                rf'{price_label}[:\s]*([0-9,\.]+)',
                r'Price[:\s]*([0-9,\.]+)',
                # Fallback: Finde große Zahlen (>10000)
                r'([0-9,\.]{6,})',  # Mindestens 6 Ziffern (100,000+)
            ]
            
            for pattern in price_patterns:
                match = re.search(pattern, input_text, re.IGNORECASE)
                if match:
                    price = normalize_numeric_str(match.group(1))
                    if price and price >= 1000:  # Mindestpreis
                        result['price'] = int(price)
                        if self.debug:
                            log_debug(f"[PREORDER-INPUT] Extracted price: {price:,} (pattern: {pattern})")
                        break
            
            # Extrahiere Menge
            if window_type == 'buy_item':
                qty_label = 'Desired Amount'
            else:
                qty_label = 'Register Quantity'
            
            # Quantity patterns
            qty_patterns = [
                rf'{qty_label}[:\s]*([0-9,\.]+)',
                r'Amount[:\s]*([0-9,\.]+)',
                r'Quantity[:\s]*([0-9,\.]+)',
                # Fallback: Finde kleinere Zahlen (1-5000 range)
                r'\b([1-5][0-9]{3})\b',  # 1000-5999
                r'\b([1-9][0-9]{2})\b',  # 100-999
            ]
            
            for pattern in qty_patterns:
                match = re.search(pattern, input_text, re.IGNORECASE)
                if match:
                    qty = normalize_numeric_str(match.group(1))
                    if qty and 1 <= qty <= 5000:  # Plausible range
                        result['quantity'] = int(qty)
                        if self.debug:
                            log_debug(f"[PREORDER-INPUT] Extracted quantity: {qty:,} (pattern: {pattern})")
                        break
            
            # Validierung: Beide Werte müssen vorhanden sein
            if 'price' not in result or 'quantity' not in result:
                if self.debug:
                    log_debug(
                        f"[PREORDER-INPUT] Incomplete extraction: "
                        f"price={'price' in result}, quantity={'quantity' in result}"
                    )
                return None
            
            # Plausibility check: Gesamtpreis sollte sinnvoll sein
            total_price = result['price'] * result['quantity']
            if total_price < 1000 or total_price > 1_000_000_000_000:  # 1k - 1T Silver
                if self.debug:
                    log_debug(
                        f"[PREORDER-INPUT] Implausible total: "
                        f"{result['quantity']}x @ {result['price']:,} = {total_price:,}"
                    )
                return None
            
            if self.debug:
                log_debug(
                    f"[PREORDER-INPUT] ✅ SUCCESS: {result['quantity']:,}x @ {result['price']:,} "
                    f"(total: {total_price:,})"
                )
            
            self._needs_detail_inputs = False
            return result
            
        except Exception as e:
            if self.debug:
                log_debug(f"[PREORDER-INPUT] ERROR: {e}")
            self._roi_usage_last_scan['detail_inputs'] = 'failed'
            return None

    def _check_for_preorder_autocollect(
        self,
        item_name: str | None,
        warehouse_delta: int,
        balance_delta: float,
        timestamp: datetime.datetime,
        fallback_unit_price: int | None = None,
        fallback_qty: int | None = None,
        fallback_autocollect_qty: int | None = None,
    ) -> Optional[Dict]:
        """
        Check if warehouse increase indicates preorder auto-collect.
        
        Auto-collect detection logic:
        1. warehouse_delta > expected purchase quantity
        2. Matching active preorder exists for this item
        3. Quantity alignment: warehouse_delta ≈ purchase_qty + preorder_qty
        
        Args:
            item_name: Item being purchased (from baseline)
            warehouse_delta: Warehouse increase
            balance_delta: Balance decrease (negative)
            timestamp: Current transaction timestamp
            
        Returns:
            Dict with preorder data if match found:
                {'id': int, 'quantity': int, 'price': float, 'quantity_filled': int}
            None if no preorder auto-collect detected
        """
        try:
            # Sanity check: warehouse_delta must be positive
            if warehouse_delta <= 0:
                return None

            # Get base price for estimation
            base_price = self._get_base_price(item_name)
            inferred_unit_price = None

            if base_price is not None:
                inferred_unit_price = base_price
            elif fallback_unit_price and fallback_unit_price > 0:
                inferred_unit_price = fallback_unit_price
                if self.debug:
                    log_debug(
                        f"[PREORDER-CHECK] Using cached unit price for '{item_name}': {fallback_unit_price:,}"
                    )

            if inferred_unit_price is None:
                if self.debug:
                    log_debug(
                        f"[PREORDER-CHECK] Cannot estimate purchase qty: "
                        f"no base_price and no fallback price for '{item_name}'"
                    )
                return None

            # Estimate purchase quantity from balance change
            # balance_delta is negative, so abs() it
            estimated_purchase_qty = abs(balance_delta) / inferred_unit_price if inferred_unit_price else 0

            # If balance delta is zero (pure preorder collect) rely on cached quantity when present
            if balance_delta == 0 and fallback_qty:
                estimated_purchase_qty = fallback_qty

            # Check if warehouse increase is significantly larger than purchase
            # Allow 10% tolerance for price variations
            if estimated_purchase_qty <= 0 or warehouse_delta <= estimated_purchase_qty * 1.1:
                # Warehouse increase matches purchase - no auto-collect
                return None

            missing_qty = max(0, warehouse_delta - estimated_purchase_qty)

            if self.debug:
                log_debug(
                    f"[PREORDER-CHECK] Potential auto-collect: warehouse_delta={warehouse_delta}, "
                    f"est_purchase={estimated_purchase_qty:.1f}, missing≈{missing_qty:.1f} "
                    f"(unit_price={inferred_unit_price:,.0f})"
                )

            # Query PreorderManager for matching preorder
            if fallback_autocollect_qty and fallback_autocollect_qty > 0 and item_name:
                try:
                    self._preorder_manager.update_quantity_filled_by_item(
                        item_name,
                        int(fallback_autocollect_qty),
                    )
                except Exception:
                    pass

            matching_preorder = self._preorder_manager.find_matching_preorder(
                item_name=item_name,
                warehouse_delta=warehouse_delta,
                balance_delta=balance_delta,
                timestamp=timestamp
            )

            if not matching_preorder and fallback_autocollect_qty and fallback_autocollect_qty > 0 and item_name:
                try:
                    active_po = self._preorder_manager.get_active_preorders(item_name)
                except Exception:
                    active_po = []
                if active_po:
                    candidate = dict(active_po[0])
                    qty_total = candidate.get('quantity') or 0
                    qty_filled = min(int(fallback_autocollect_qty), int(qty_total) if qty_total else int(fallback_autocollect_qty))
                    if qty_filled > 0:
                        candidate['quantity_filled'] = qty_filled
                        matching_preorder = candidate
                        if self.debug:
                            log_debug(
                                f"[PREORDER-CHECK] Using UI fallback for '{item_name}': filled={qty_filled}"
                            )

            if matching_preorder:
                matching_preorder['_auto_collect_estimate'] = {
                    'inferred_unit_price': inferred_unit_price,
                    'estimated_purchase_qty': estimated_purchase_qty,
                    'warehouse_delta': warehouse_delta,
                }

            return matching_preorder

        except Exception as e:
            if self.debug:
                log_debug(f"[PREORDER-CHECK] ERROR: {e}")
            return None

    def _normalize_detail_item_name(self, raw_name: str | None) -> str | None:
        if not raw_name:
            return None
        corrected, is_valid = self._safe_correct_item_name(raw_name)
        if is_valid:
            return corrected
        return raw_name

    def _sanitize_log_snapshot(self, text: str | None) -> str:
        lines: list[str] = []
        for line in (text or "").splitlines():
            low = line.lower()
            if re.search(r"20\d{2}[.\-/]\d{2}[.\-/]\d{2}\s+\d{2}[:\.,\-]\d{2}", line):
                lines.append(line)
                continue
            if any(tok in low for tok in ("transaction", "placed order", "withdrew", "listed", "purchased", "sold ", "sold")):
                lines.append(line)
                continue
        return "\n".join(lines)

    def _buffer_detail_log_snapshot(
        self,
        text: str | None,
        source_window: str,
        captured_at: datetime.datetime,
        prev_window: str | None,
    ) -> None:
        if not text:
            return
        sanitized = text.strip()
        if not sanitized:
            return
        normalized = " ".join(sanitized.lower().split())
        try:
            text_hash = hashlib.blake2s(normalized.encode("utf-8"), digest_size=12).hexdigest()
        except Exception:
            text_hash = f"fallback-{captured_at.timestamp()}"
        if text_hash in self._detail_pending_snapshot_hashes:
            return
        self._detail_pending_snapshot_hashes.add(text_hash)
        self._detail_pending_log_snapshots.append(
            {
                "text": sanitized,
                "hash": text_hash,
                "captured_at": captured_at,
                "source_window": source_window,
                "prev_window": prev_window,
            }
        )
        if len(self._detail_pending_log_snapshots) > 12:
            oldest = self._detail_pending_log_snapshots.pop(0)
            old_hash = oldest.get("hash")
            if old_hash and old_hash in self._detail_pending_snapshot_hashes:
                self._detail_pending_snapshot_hashes.remove(old_hash)
        if self.debug:
            log_debug(
                f"[DETAIL-PENDING] buffered snapshot hash={text_hash[:8]} source={source_window} prev={prev_window}"
            )

    def _consume_detail_log_snapshots(self, target_window: str) -> list[dict]:
        if not self._detail_pending_log_snapshots:
            return []
        snapshots = self._detail_pending_log_snapshots
        self._detail_pending_log_snapshots = []
        self._detail_pending_snapshot_hashes.clear()
        structured_entries: list[dict] = []
        for snap in snapshots:
            raw_text = snap.get("text") or ""
            entries = split_text_into_log_entries(raw_text)
            if not entries:
                sanitized = self._sanitize_log_snapshot(raw_text)
                if sanitized:
                    entries = split_text_into_log_entries(sanitized)
            for pos, ts_text, snippet in entries:
                details = extract_details_from_entry(ts_text, snippet)
                if not details.get("timestamp"):
                    continue
                if details.get("type") not in {"transaction", "placed", "listed", "withdrew", "purchased"}:
                    continue
                structured_entries.append(
                    {
                        "pos": pos,
                        "ts_text": ts_text,
                        "type": details.get("type"),
                        "item": details.get("item"),
                        "qty": details.get("qty"),
                        "price": details.get("price"),
                        "timestamp": details.get("timestamp"),
                        "raw": details.get("raw"),
                        "raw_price_hint": details.get("raw_price_hint"),
                        "_detail_buffered": True,
                        "_buffer_source_window": snap.get("source_window"),
                        "_buffer_prev_window": snap.get("prev_window"),
                        "_buffer_target_window": target_window,
                        "_buffer_captured_at": snap.get("captured_at"),
                    }
                )
        if self.debug and structured_entries:
            log_debug(f"[DETAIL-PENDING] replay {len(structured_entries)} entries into {target_window}")
        return structured_entries

    def _handle_preorder_cancellation(self, item_name, quantity, price) -> None:
        if item_name is None:
            return
        try:
            qty = int(quantity)
        except (TypeError, ValueError):
            return
        try:
            total_price = float(price)
        except (TypeError, ValueError):
            return
        normalized_name = self._normalize_detail_item_name(item_name)
        if not normalized_name:
            return
        cancelled = self._preorder_manager.cancel_preorder(normalized_name, qty, total_price)
        if not cancelled:
            self._preorder_manager.cancel_listing(normalized_name, qty, total_price)

    def _handle_preorder_or_listing_collection(self, item_name, quantity, price, timestamp, window_type) -> None:
        if item_name is None:
            return
        try:
            qty = int(quantity)
        except (TypeError, ValueError):
            return
        try:
            total_price = float(price)
        except (TypeError, ValueError):
            total_price = 0.0
        normalized_name = self._normalize_detail_item_name(item_name)
        if not normalized_name:
            return
        ts_value = timestamp if isinstance(timestamp, datetime.datetime) else datetime.datetime.now()
        handled = False
        if window_type == 'buy_overview':
            matching_preorder = self._preorder_manager.find_matching_preorder(
                item_name=normalized_name,
                warehouse_delta=qty,
                balance_delta=-abs(total_price),
                timestamp=ts_value
            )
            if matching_preorder:
                marked = self._preorder_manager.mark_collected(
                    preorder_id=matching_preorder['id'],
                    collected_at=ts_value,
                    transaction_id=None
                )
                if not marked:
                    if self.debug:
                        log_debug(
                            f"[DETAIL] ⚠️ Failed to mark preorder ID={matching_preorder['id']} as collected"
                        )
                else:
                    filled_existing = matching_preorder.get('quantity_filled') or 0
                    total_quantity = matching_preorder.get('quantity') or qty
                    new_filled = min(total_quantity, max(filled_existing, qty))
                    if new_filled > filled_existing:
                        self._preorder_manager.update_quantity_filled(
                            preorder_id=matching_preorder['id'],
                            filled_quantity=new_filled
                        )
                    handled = True

        if not handled and window_type == 'sell_overview':
            matching_listing = self._preorder_manager.find_matching_listing(
                item_name=normalized_name,
                warehouse_delta=-abs(qty),
                balance_delta=abs(total_price),
                timestamp=ts_value
            )
            if matching_listing:
                marked_listing = self._preorder_manager.mark_listing_collected(
                    listing_id=matching_listing['id'],
                    collected_at=ts_value,
                    transaction_id=None
                )
                if not marked_listing and self.debug:
                    log_debug(
                        f"[DETAIL] ⚠️ Failed to mark listing ID={matching_listing['id']} as collected"
                    )

    def _reconstruct_missing_preorder_from_log(
        self,
        item_name: str,
        withdrew_qty: int,
        withdrew_price: float,
        transaction_qty: int,
        timestamp: datetime.datetime
    ) -> Optional[Dict]:
        """
        FIX 1: Reconstruct missing preorder from transaction log entries.
        
        When a preorder is relisted, the transaction log shows:
        - "Withdrew order of Item x2812 for 98,420,000 silver" (unfilled portion)
        - "Transaction of Item x2188 for 76,580,000 Silver" (filled portion)
        - "Placed order of Item x5000 for 175,500,000 Silver" (new preorder)
        
        This function reconstructs the original preorder details:
        - Original quantity = withdrew_qty + transaction_qty
        - Filled quantity = transaction_qty
        - Unit price estimation from withdrawn amount
        
        Args:
            item_name: Item name
            withdrew_qty: Quantity withdrawn (unfilled portion)
            withdrew_price: Price refunded for withdrawn orders
            transaction_qty: Quantity collected (filled portion)
            timestamp: Transaction timestamp
            
        Returns:
            Dict with reconstructed preorder data:
                {'quantity': int, 'quantity_filled': int, 'price': float, 'unit_price': float}
            None if reconstruction fails
        """
        try:
            # Calculate original preorder quantity
            original_qty = withdrew_qty + transaction_qty
            
            if original_qty <= 0:
                return None
            
            # Estimate unit price from withdrawn amount
            # withdrew_price is the refund for unfilled orders
            # So: unit_price ≈ withdrew_price / withdrew_qty
            if withdrew_qty > 0 and withdrew_price > 0:
                unit_price_estimate = withdrew_price / withdrew_qty
            else:
                # Fallback: try to estimate from transaction price
                # But transaction price might be COLLECTED price (different from preorder price)
                # Better to use base price as last resort
                base_price = self._get_base_price(item_name)
                unit_price_estimate = base_price if base_price else None
            
            if unit_price_estimate is None or unit_price_estimate <= 0:
                if self.debug:
                    log_debug(
                        f"[PREORDER-RECONSTRUCT] Failed: cannot estimate unit price for {item_name}"
                    )
                return None
            
            # Reconstruct original preorder total
            original_preorder_total = unit_price_estimate * original_qty
            
            reconstructed = {
                'quantity': original_qty,
                'quantity_filled': transaction_qty,
                'price': original_preorder_total,
                'unit_price': unit_price_estimate,
                'timestamp': timestamp,
                '_reconstructed': True  # Flag to indicate this is synthetic
            }
            
            if self.debug:
                log_debug(
                    f"[PREORDER-RECONSTRUCT] ✅ Reconstructed preorder for {item_name}:\n"
                    f"   Original: {original_qty:,}x (filled={transaction_qty:,})\n"
                    f"   Withdrew: {withdrew_qty:,}x @ {withdrew_price:,.0f}\n"
                    f"   Unit price estimate: {unit_price_estimate:,.0f}\n"
                    f"   Total: {original_preorder_total:,.0f}"
                )
            
            return reconstructed
        
        except Exception as e:
            if self.debug:
                log_debug(f"[PREORDER-RECONSTRUCT] ERROR: {e}")
            return None

    def _check_for_auto_preorder_creation(
        self,
        item_name: str,
        warehouse_delta: int,
        balance_delta: float,
        timestamp: datetime.datetime
    ) -> Optional[Tuple[int, float, int, float]]:
        """
        Check if insufficient stock caused auto-preorder creation.
        
        Detection logic:
        1. balance_delta (price paid) suggests quantity X
        2. warehouse_delta (received) shows quantity Y < X
        3. Difference (X - Y) = auto-preorder quantity
        
        Example:
            Attempt to buy 5000x @ 40M
            Only 2000x available
            Game buys 2k and creates 3k preorder
        
        Args:
            item_name: Item name
            warehouse_delta: Actual warehouse increase (2000)
            balance_delta: Total price paid (-40M)
            timestamp: Transaction timestamp
            
        Returns:
            Tuple (purchase_qty, purchase_price, preorder_qty, preorder_price)
            or None if no auto-preorder detected
        """
        try:
            # Sanity checks
            if warehouse_delta <= 0 or balance_delta >= 0:
                return None
            
            # Get base price for estimation
            base_price = self._get_base_price(item_name)
            if base_price is None:
                return None
            
            # Estimate total quantity user attempted to buy
            total_price = abs(balance_delta)
            estimated_total_qty = total_price / base_price
            
            # Check if warehouse received LESS than expected
            # Allow 5% tolerance for rounding
            if warehouse_delta >= estimated_total_qty * 0.95:
                # Received full amount - no auto-preorder
                return None
            
            # Calculate quantities
            purchase_qty = warehouse_delta
            preorder_qty = int(round(estimated_total_qty - purchase_qty))
            
            # Sanity check: preorder must be significant (at least 10% of total)
            if preorder_qty < estimated_total_qty * 0.1:
                return None
            
            # Split price proportionally
            purchase_price = total_price * (purchase_qty / estimated_total_qty)
            preorder_price = total_price * (preorder_qty / estimated_total_qty)
            
            if self.debug:
                log_debug(
                    f"[AUTO-PREORDER] Detected: {item_name} "
                    f"(attempted={estimated_total_qty:.0f}, received={purchase_qty}, "
                    f"preorder={preorder_qty}) "
                    f"purchase_price={purchase_price:,.0f}, preorder_price={preorder_price:,.0f}"
                )
            
            return (purchase_qty, purchase_price, preorder_qty, preorder_price)
        
        except Exception as e:
            if self.debug:
                log_debug(f"[AUTO-PREORDER] ERROR: {e}")
            return None

    def _restore_total_with_base_price(self, item_name: str, quantity: int | None, observed_total: int | None) -> int | None:
        if not item_name or not quantity or quantity <= 0 or not observed_total or observed_total <= 0:
            return None
        base_price = self._get_base_price(item_name)
        if not base_price or base_price <= 0:
            return None

        observed_unit = observed_total / quantity
        tolerance = 0.15
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

    def _extract_price_hint(self, entry: dict | None) -> tuple[int | None, str | None]:
        if not entry:
            return (None, None)
        raw = entry.get('raw') if isinstance(entry, dict) else None
        if not raw:
            return (None, None)
        hint_match = _PRICE_HINT_PATTERN.search(raw)
        generic_match = None
        if not hint_match:
            generic_match = _GENERIC_SILVER_PATTERN.search(raw)
        match_obj = hint_match or generic_match
        if not match_obj:
            return (None, None)
        raw_value = match_obj.group(1)
        raw_compact = raw_value.replace(' ', '')
        has_placeholder = '_' in raw_compact
        trimmed = raw_value.strip()
        ends_with_digit = bool(trimmed) and trimmed[-1] in "0123456789OolI|"
        hint_mode = 'suffix'
        if has_placeholder or not ends_with_digit:
            hint_mode = 'prefix'
        placeholder_count = raw_value.count('_')
        if isinstance(entry, dict):
            entry['_price_hint_mode'] = hint_mode
            entry['_price_hint_placeholders'] = placeholder_count
            entry['_price_hint_raw'] = raw_value

        value = normalize_numeric_str(raw_value)
        if value is None or value <= 0:
            return (None, None)
        digit_count = sum(1 for ch in raw_value if ch.isdigit() or ch in 'OolI')
        if digit_count <= 0:
            digits = str(value)
        else:
            digits = f"{value:0{digit_count}d}"
        return (value, digits)

    def _merge_hint_with_expected(self, expected_total: int | None, hint_digits: str | None) -> int | None:
        if not expected_total or not hint_digits:
            return expected_total
        digits_clean = re.sub(r'\D', '', hint_digits)
        if not digits_clean:
            return expected_total
        expected_str = str(int(expected_total))
        if len(digits_clean) >= len(expected_str):
            return int(digits_clean)
        prefix = expected_str[:-len(digits_clean)]
        if not prefix:
            return int(digits_clean)
        return int(prefix + digits_clean)

    def _recover_sell_price(self, item_name: str, quantity: int, price: int | None, entry: dict | None) -> int | None:
        if not item_name or not quantity or quantity <= 0:
            return price

        base_price = self._get_base_price(item_name)
        hint_value, hint_digits = self._extract_price_hint(entry)
        hint_suffix = re.sub(r'\D', '', hint_digits or '') if hint_digits else ''
        hint_mode = 'suffix'
        placeholder_count = 0
        ui_unit_price = None
        if isinstance(entry, dict):
            hint_mode = entry.get('_price_hint_mode') or 'suffix'
            placeholder_count = int(entry.get('_price_hint_placeholders') or 0)
            ui_unit_price = entry.get('_ui_unit_price') or entry.get('_ui_price')

        reference_totals: list[int] = []
        expected_total_base: int | None = None
        expected_total_ui: int | None = None
        if ui_unit_price and ui_unit_price > 0:
            try:
                expected_total_ui = int(round(float(ui_unit_price) * quantity * MARKET_SELL_NET_FACTOR))
            except Exception:
                expected_total_ui = None
            if expected_total_ui and expected_total_ui > 0:
                reference_totals.append(expected_total_ui)
        if base_price and base_price > 0:
            expected_total_base = int(round(base_price * quantity * MARKET_SELL_NET_FACTOR))
            reference_totals.append(expected_total_base)

        primary_expected = reference_totals[0] if reference_totals else None

        suspicious = price is None or price <= 0
        if not suspicious and reference_totals:
            try:
                for ref in reference_totals:
                    if ref and ref > 0 and price < ref * 0.6:
                        suspicious = True
                        break
            except Exception:
                pass

        if not suspicious:
            return price

        candidate_values: list[int] = []
        if hint_digits and hint_mode != 'prefix':
            for ref in reference_totals:
                if ref:
                    merged = self._merge_hint_with_expected(ref, hint_digits)
                    if merged:
                        candidate_values.append(int(merged))

        candidate_values.extend(ref for ref in reference_totals if ref)

        if hint_value and hint_value > 0:
            candidate_values.append(int(hint_value))

        if price and price > 0:
            candidate_values.append(int(price))

        seen_candidates = set()
        ordered_candidates: list[int] = []
        for cand in candidate_values:
            if cand is None or cand <= 0:
                continue
            if cand not in seen_candidates:
                seen_candidates.add(cand)
                ordered_candidates.append(int(cand))

        def _candidate_valid(val: int) -> bool:
            if val is None or val <= 0 or not quantity or quantity <= 0:
                return False
            if hint_suffix:
                val_str = str(int(val))
                if hint_mode == 'prefix':
                    if not val_str.startswith(hint_suffix):
                        return False
                else:
                    if not val_str.endswith(hint_suffix):
                        return False
            if ui_unit_price and ui_unit_price > 0:
                try:
                    unit_pre_tax_ui = val / (quantity * MARKET_SELL_NET_FACTOR)
                except ZeroDivisionError:
                    return False
                diff_ratio_ui = abs(unit_pre_tax_ui - ui_unit_price) / float(ui_unit_price)
                if diff_ratio_ui > 0.15:
                    return False
            if base_price and base_price > 0:
                try:
                    unit_pre_tax = val / (quantity * MARKET_SELL_NET_FACTOR)
                except ZeroDivisionError:
                    return False
                if unit_pre_tax <= 0:
                    return False
                diff_ratio = abs(unit_pre_tax - base_price) / float(base_price)
                if diff_ratio > 0.15:
                    return False
            return True

        for cand in ordered_candidates:
            if _candidate_valid(cand):
                if self.debug:
                    log_debug(
                        f"[SELL-RECOVER] Reconstructed price for '{item_name}' qty={quantity}: {cand:,} "
                        f"(base={base_price}, ui={ui_unit_price}, hint={hint_value}, mode={hint_mode}, placeholders={placeholder_count})"
                    )
                return cand

        if primary_expected and _candidate_valid(primary_expected):
            if self.debug:
                log_debug(f"[SELL-RECOVER] Fallback to expected net price for '{item_name}': {primary_expected:,}")
            return primary_expected

        if hint_value and hint_value > 0:
            valid_hint = False
            hint_str = str(int(hint_value))
            if not hint_suffix:
                valid_hint = True
            elif hint_mode == 'prefix':
                valid_hint = hint_str.startswith(hint_suffix)
            else:
                valid_hint = hint_str.endswith(hint_suffix)
            if valid_hint and _candidate_valid(int(hint_value)):
                if self.debug:
                    log_debug(f"[SELL-RECOVER] Using raw hint price for '{item_name}': {hint_value:,}")
                return int(hint_value)

        if price and price > 0 and _candidate_valid(price):
            if self.debug:
                log_debug(f"[SELL-RECOVER] Keeping original parsed price for '{item_name}': {price:,}")
            return price

        return price

    def _process_overview_text(
        self,
        full_text: str,
        window_type: str,
        prev_window: str | None = None,
        entry: dict | None = None,
        raw_related: list[dict] = [],
    ) -> int | None:
        if not full_text:
            return None

        hint_values: list[int] = []
        hint_suffixes: list[str] = []

        def _collect_hint(source: dict | None):
            if not source:
                return
            source_type = source.get('type') if isinstance(source, dict) else None
            if source_type and source_type not in ('transaction', 'purchased'):
                return
            raw_hint = source.get('raw_price_hint')
            if raw_hint:
                try:
                    hint_int = int(raw_hint)
                except Exception:
                    hint_int = None
                if hint_int and hint_int > 0:
                    hint_values.append(hint_int)
                    hint_suffixes.append(str(hint_int))
            val, digits = self._extract_price_hint(source)
            if val and val > 0:
                hint_values.append(int(val))
            if digits:
                suffix = re.sub(r'\D', '', digits)
                if suffix:
                    hint_suffixes.append(suffix)

        _collect_hint(entry if isinstance(entry, dict) else None)
        for rel in raw_related or []:
            _collect_hint(rel if isinstance(rel, dict) else None)

        if not hint_values and price:
            return price

        try:
            base_price = self._get_base_price(item_name)
        except Exception:
            base_price = None
        tolerance = 0.18
        lower = base_price * (1 - tolerance) if base_price else None
        upper = base_price * (1 + tolerance) if base_price else None

        candidates: list[int] = []
        anchor_totals: list[int] = []
        if price and price > 0:
            anchor_totals.append(int(price))
            candidates.append(int(price))
        if base_price and base_price > 0:
            base_total = int(round(base_price * quantity))
            anchor_totals.append(base_total)
            candidates.append(base_total)
        if price and price > 0 and hint_suffixes:
            price_str = str(int(price))
            for suffix in hint_suffixes:
                digits = re.sub(r'\D', '', suffix)
                if not digits:
                    continue
                if len(digits) >= len(price_str):
                    candidates.append(int(digits))
                else:
                    merged = int(price_str[:-len(digits)] + digits)
                    candidates.append(merged)
        candidates.extend(int(v) for v in hint_values if v and v > 0)

        for suffix in hint_suffixes:
            if not suffix:
                continue
            for anchor in anchor_totals:
                merged = self._merge_hint_with_expected(anchor, suffix)
                if merged:
                    candidates.append(int(merged))

        unique_candidates: list[int] = []
        seen = set()
        for cand in candidates:
            if cand and cand not in seen:
                seen.add(cand)
                unique_candidates.append(int(cand))

        def _suffix_match(val: int) -> bool:
            if not hint_suffixes:
                return True
            val_str = str(int(val))
            return any(val_str.endswith(sfx) for sfx in hint_suffixes if sfx)

        valid_candidates: list[int] = []
        for cand in unique_candidates:
            unit = cand / quantity
            plausible = True
            if base_price and upper:
                try:
                    if unit > upper:
                        plausible = False
                except Exception:
                    pass
            if not plausible:
                continue
            if not self._is_unit_price_plausible(item_name, int(round(unit))):
                continue
            if not _suffix_match(cand):
                continue
            valid_candidates.append(cand)

        if self.debug:
            log_debug(f"[BUY-RECOVER] hints={hint_suffixes} candidates={valid_candidates} raw={hint_values}")
        if valid_candidates:
            reference = None
            if price and price > 0:
                reference = int(price)
            elif hint_values:
                reference = max(hint_values)
            elif base_price and base_price > 0:
                reference = int(round(base_price * quantity))
            else:
                reference = valid_candidates[0]
            chosen = min(valid_candidates, key=lambda val: abs(val - reference))
            if self.debug:
                log_debug(f"[BUY-RECOVER] Reconstructed price for '{item_name}' qty={quantity}: {chosen:,} hints={hint_values}")
            return chosen

        if price and price > 0:
            return int(price)
        return None

    def _infer_quantity_from_price(self, item_name: str, observed_total: int | None) -> int | None:
        if not item_name or not observed_total or observed_total <= 0:
            return None

        try:
            base_price = self._get_base_price(item_name)
        except Exception:
            base_price = None
        if not base_price or base_price <= 0:
            return None

        approx = observed_total / base_price
        candidates = []
        primary = int(round(approx)) if approx > 0 else 0
        for q in (primary, math.floor(approx), math.ceil(approx)):
            if q not in candidates:
                candidates.append(q)
        # also try neighbours to compensate rounding
        if primary > 0:
            for delta in (-1, 1):
                cand = primary + delta
                if cand > 0 and cand not in candidates:
                    candidates.append(cand)

        valid_candidates = []
        for qty in candidates:
            if qty <= 0 or qty > MAX_ITEM_QUANTITY:
                continue
            unit_price = observed_total / qty
            try:
                if self._is_unit_price_plausible(item_name, unit_price):
                    valid_candidates.append((qty, unit_price))
                    continue
            except Exception:
                pass
            # fallback: accept if total roughly matches base price within tolerance
            tolerance = 0.2
            lower = base_price * (1 - tolerance) * qty
            upper = base_price * (1 + tolerance) * qty
            if lower <= observed_total <= upper:
                valid_candidates.append((qty, unit_price))

        if not valid_candidates:
            return None

        # Prefer candidate closest to approx quantity
        valid_candidates.sort(key=lambda item: abs(item[0] - approx))
        chosen_qty = int(valid_candidates[0][0])
        if chosen_qty <= 0 or chosen_qty > MAX_ITEM_QUANTITY:
            return None
        return chosen_qty

    def _reconstruct_ui_price(
        self,
        item_name: str,
        delta_qty: int,
        observed_delta_price: int,
        anchor_entries: list[dict],
    ) -> int | None:
        if not item_name or delta_qty <= 0:
            return None

        candidate_units: list[int] = []
        for entry in anchor_entries:
            qty = entry.get('qty')
            price = entry.get('price')
            if not qty or not price or qty <= 0 or price <= 0:
                continue
            try:
                if price % qty == 0:
                    unit = price // qty
                    if unit > 0 and self._is_unit_price_plausible(item_name, unit):
                        candidate_units.append(unit)
            except Exception:
                continue

        if observed_delta_price > 0 and observed_delta_price % delta_qty == 0:
            unit = observed_delta_price // delta_qty
            if unit > 0 and self._is_unit_price_plausible(item_name, unit):
                candidate_units.insert(0, unit)

        if candidate_units:
            chosen_unit = candidate_units[0]
            return int(chosen_unit * delta_qty)

        try:
            base_price = self._get_base_price(item_name)
        except Exception:
            base_price = None
        if base_price and base_price > 0 and self._is_unit_price_plausible(item_name, base_price):
            return int(base_price * delta_qty)

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

    def _is_value_duplicate_with_time_tolerance(self, item_name, quantity, price, timestamp, tolerance_minutes=2):
        """
        FIX 2: Timestamp-Toleranz gegen OCR-Duplikate
        
        Prüft ob eine Transaktion mit gleichen Werten (Item, Menge, Preis) aber leicht 
        unterschiedlichem Timestamp bereits in der DB existiert.
        
        Problem: OCR kann Timestamps inkonsistent lesen (10:30 vs 10:31), was zu Duplikaten führt.
        Lösung: Prüfe ob eine Transaktion mit ±tolerance_minutes existiert.
        
        Args:
            item_name: Item-Name
            quantity: Menge
            price: Preis
            timestamp: Timestamp (datetime oder string)
            tolerance_minutes: Zeittoleranz in Minuten (default: 2)
        
        Returns:
            True wenn Duplikat gefunden, False sonst
        """
        try:
            # Parse timestamp if string
            if isinstance(timestamp, str):
                ts_obj = datetime.datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
            elif isinstance(timestamp, datetime.datetime):
                ts_obj = timestamp
            else:
                return False
            
            ts_min = (ts_obj - datetime.timedelta(minutes=tolerance_minutes)).strftime('%Y-%m-%d %H:%M:%S')
            ts_max = (ts_obj + datetime.timedelta(minutes=tolerance_minutes)).strftime('%Y-%m-%d %H:%M:%S')
            
            # Query DB for matching transaction within time window
            with get_cursor() as cursor:
                cursor.execute('''
                    SELECT COUNT(*) FROM transactions
                    WHERE item_name = ?
                      AND quantity = ?
                      AND ABS(price - ?) < 1000
                      AND timestamp BETWEEN ? AND ?
                ''', (item_name, int(quantity), int(price), ts_min, ts_max))
                
                count = cursor.fetchone()[0]
                return count > 0
        except Exception as e:
            if self.debug:
                log_debug(f"[TIMESTAMP-TOLERANCE] Check failed: {e}")
            return False

    def _consume_immediate_rescan_request(self):
        if self._request_immediate_rescan > 0:
            self._request_immediate_rescan -= 1
            return True
        return False

    def _sync_preorder_fill_from_ui(
        self,
        metrics_entry: dict,
        orders_completed: int,
        fallback_key: str,
    ) -> None:
        """Aktualisiert quantity_filled eines aktiven Preorders basierend auf UI-Metriken."""
        if not metrics_entry or orders_completed is None or orders_completed <= 0:
            return

        raw_name = (metrics_entry.get('item') or fallback_key or '').strip()
        if not raw_name:
            return

        try:
            corrected_name, is_valid = self._safe_correct_item_name(raw_name, min_score=80)
        except Exception:
            corrected_name, is_valid = raw_name, True

        target_name = corrected_name if corrected_name and is_valid else raw_name
        if not target_name:
            return

        norm_key = target_name.lower()
        last_synced = self._last_ui_buy_fill_sync.get(norm_key, 0)
        if orders_completed <= last_synced:
            return

        try:
            updated = self._preorder_manager.update_quantity_filled_by_item(target_name, orders_completed)
        except Exception:
            updated = False

        if updated:
            self._last_ui_buy_fill_sync[norm_key] = orders_completed

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
                r"Orders\s*[:;]?\s*([0-9,\.]+)\s*(?:/)?\s*Orders\s*Completed\s*[:;]?\s*([0-9,\.]+)([\s\S]{0,200}?Collect[\s\S]{0,120}?Re-?list)",
                re.IGNORECASE,
            )
            
            for m in metric_pattern.finditer(s):
                # Extract metrics
                orders = normalize_numeric_str(m.group(1)) or 0
                oc = normalize_numeric_str(m.group(2)) or 0
                tail_segment = m.group(3) or ''
                rem = 0
                if tail_segment:
                    try:
                        collect_part = tail_segment.lower().split('collect', 1)[-1]
                    except Exception:
                        collect_part = tail_segment
                    number_matches = re.findall(r'([0-9,\.]+)', collect_part)
                    last_large = None
                    for num_txt in number_matches:
                        val = normalize_numeric_str(num_txt)
                        if val is None or val <= 0:
                            continue
                        if val >= 1000:
                            last_large = val
                    if last_large is not None:
                        rem = last_large
                    elif number_matches:
                        fallback_val = normalize_numeric_str(number_matches[-1])
                        rem = fallback_val or 0
                
                if orders <= 0 or oc <= 0 or rem <= 0:
                    continue
                
                # Now look backwards from the start of "Orders" to find the item name
                # Take up to 100 chars before "Orders" and extract the last valid item name
                before_orders = s[max(0, m.start()-100):m.start()]
                segments = [seg.strip() for seg in re.split(r'\d[\d\s,\.]*', before_orders) if seg.strip()]
                name = segments[-1] if segments else before_orders.strip()
                if name:
                    name = re.sub(r'\b(?:Orders|Order|Completed|Collect|Re-?list|VT|Balance)\b', '', name, flags=re.IGNORECASE).strip()
                    name = re.sub(r'[:;/]+$', '', name).strip()
                if name and len(name) >= 3 and any(ch.isalpha() for ch in name):
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

    def _extract_detail_window_metrics(self, ocr_text: str, window_type: str) -> dict | None:
        """
        Extrahiert Metriken aus Detail-Fenster (Buy-Item / Sell-Item).
        
        Extrahierte Daten:
        - balance: Aktueller Kontostand (Silver)
        - warehouse_qty: Aktueller Lagerbestand (Anzahl Items)
        - item_name: Name des Items (falls erkannt)
        - set_price: Eingestellter Preis (bei Sell-Item, optional)
        - desired_price: Gewünschter Preis (bei Buy-Item, optional)
        - quantity: Eingestellte Menge (optional)
        
        Args:
            ocr_text: OCR-Text aus Detail-Window (kombiniert aus allen ROIs)
            window_type: 'sell_item' oder 'buy_item'
        
        Returns:
            dict mit Metriken oder None
        """
        if not ocr_text:
            # Kein text -> keine Metriken, vorherige Flags sollen erneuten OCR erzwingen
            self._set_need_flag('detail_balance', True, "detail_extract_empty_text")
            self._set_need_flag('detail_warehouse', True, "detail_extract_empty_text")
            return None
        
        try:
            # Normalisiere Text (PRESERVE NEWLINES für Item-Name-Extraction!)
            # Ersetze nur wiederholte Spaces/Tabs, aber NICHT Newlines
            s = re.sub(r'[ \t]+', ' ', ocr_text)  # Nur horizontale Whitespaces
            s = s.replace('：', ':').replace('．', '.').replace('／', '/')
            
            metrics = {}
            
            # 1. Balance extrahieren
            # Pattern: "Balance: 1,234,567,890 Silver" oder "Balance 1,234,567,890" (Detail-ROI)
            balance_match = re.search(r'balance\s*[:]?\s*([0-9OolI\|,\.]+)', s, re.IGNORECASE)
            if balance_match:
                balance_val = normalize_numeric_str(balance_match.group(1))
                if balance_val is not None:
                    metrics['balance'] = balance_val

            desired_match = re.search(r'(desired\s+price)\s*[:]?\s*([0-9OolI\|,\.]+)', s, re.IGNORECASE)
            if desired_match:
                desired_val = normalize_numeric_str(desired_match.group(2))
                if desired_val is not None:
                    metrics['desired_price'] = desired_val

            desired_amount_match = re.search(r'(desired\s+amount)\s*[:]?\s*([0-9OolI\|,\.]+)', s, re.IGNORECASE)
            if desired_amount_match:
                desired_amount_val = normalize_numeric_str(desired_amount_match.group(2))
                if desired_amount_val is not None:
                    metrics['desired_amount'] = desired_amount_val
                    metrics['quantity'] = desired_amount_val

            set_price_match = re.search(r'(set\s+price)\s*[:]?\s*([0-9OolI\|,\.]+)', s, re.IGNORECASE)
            if set_price_match:
                set_price_val = normalize_numeric_str(set_price_match.group(2))
                if set_price_val is not None:
                    metrics['set_price'] = set_price_val

            register_qty_match = re.search(r'(register\s+quantity)\s*[:]?\s*([0-9OolI\|,\.]+)', s, re.IGNORECASE)
            if register_qty_match:
                register_val = normalize_numeric_str(register_qty_match.group(2))
                if register_val is not None:
                    metrics['register_quantity'] = register_val
                    metrics['quantity'] = register_val

            warehouse_patterns = [
                r'(?:warehouse\s+quantity|warehouse|wh)\s*[:]??\s*([0-9OolI\|,\.]+)',
                r'([0-9OolI\|,\.]+)\s*(?:warehouse\s+quantity|warehouse|wh)'
            ]

            # 2. Warehouse Quantity extrahieren
            # Zusätzliche Sonderfälle:
            # - OCR liefert "Warehouse Quantity" und Zahl erst im Folgescan
            # - Zahl steht auf separater Zeile ("Warehouse Quantity"\n"3")
            # - Zahl enthält nur Whitespaces → erneuten Scan erzwingen

            # Pattern 1: "In Stock" (Sell-Detail-ROI)
            # ⚡ FIX: Sell-Side nutzt "In Stock" statt "Warehouse Quantity"!
            in_stock_pattern = re.compile(
                r'In\s+Stock\s*[:;]?\s*([0-9,\.]+)',
                re.IGNORECASE,
            )
            m = in_stock_pattern.search(s)
            if m:
                wh_val = normalize_numeric_str(m.group(1))
                if wh_val is not None:
                    metrics['warehouse_qty'] = wh_val
            
            # Pattern 2: "Warehouse Quantity" (Buy-Overview + Buy-Detail)
            if 'warehouse_qty' not in metrics:
                warehouse_pattern_overview = re.compile(
                    r'(?:Warehouse\s*(?:Quantity)?|WH)\s*[:;]?\s*([0-9,\.]+)',
                    re.IGNORECASE,
                )
                m = warehouse_pattern_overview.search(s)
                if m:
                    wh_val = normalize_numeric_str(m.group(1))
                    if wh_val is not None:
                        metrics['warehouse_qty'] = wh_val
                    elif self.debug:
                        log_debug("[DETAIL-EXTRACT] Warehouse match ohne Zahl → erneutes OCR notwendig")
            
            # Pattern 3: Alt-Detail-ROI-Format (Zahl ZUERST)
            if 'warehouse_qty' not in metrics:
                warehouse_pattern_detail = re.compile(
                    r'([0-9,\.]+)\s+Warehouse\s+Quantity',
                    re.IGNORECASE,
                )
                for line in s.split('\n'):
                    m = warehouse_pattern_detail.search(line)
                    if m:
                        wh_val = normalize_numeric_str(m.group(1))
                        if wh_val is not None:
                            metrics['warehouse_qty'] = wh_val
                            break

            # Pattern 4: "Warehouse Quantity" / "In Stock" gefolgt von separater Zeile mit Zahl
            if 'warehouse_qty' not in metrics:
                lines = [ln.strip() for ln in s.split('\n') if ln.strip()]
                for idx, line in enumerate(lines[:-1]):
                    if re.search(r'(warehouse\s*(quantity)?|in\s*stock)', line, re.IGNORECASE):
                        candidate = normalize_numeric_str(lines[idx + 1])
                        if candidate is not None:
                            metrics['warehouse_qty'] = candidate
                            break

            if 'warehouse_qty' not in metrics:
                if self.debug:
                    log_debug("[DETAIL-EXTRACT] Warehouse-Wert fehlt weiterhin – Flags bleiben aktiv")
                self._set_need_flag('detail_warehouse', True, "detail_extract_missing_warehouse")
            
            # 3. Item-Name extrahieren (aus Item-Name-ROI)
            # Pattern: Suche nach zusammenhängendem Text ohne UI-Keywords
            # Oft Format: "<ItemName>" oder "[Grade] ItemName"
            # Detail-ROI liefert oft Timestamp-Präfix: "2025.10.20 19.23 ItemName"
            
            # Entferne Timestamp-Präfix wenn vorhanden
            s_cleaned = re.sub(
                r'^\d{4}\.\d{2}\.\d{2}\s+\d{2}\.\d{2}\s+',  # Timestamp-Präfix (YYYY.MM.DD HH.MM)
                '',
                s
            )
            
            # Versuche Item-Name am Anfang des Textes zu finden
            lines = s_cleaned.split('\n')
            for line in lines[:10]:  # Erste 10 Zeilen prüfen
                line = line.strip()
                if not line or len(line) < 3:
                    continue
                # Filtere UI-Keywords und Zahlen-dominierte Zeilen
                line_lower = line.lower()
                if any(kw in line_lower for kw in ['balance', 'warehouse', 'set price', 'desired', 'register', 'quantity', 'silver', 'max', 'min', 'collect', 're-list']):
                    continue
                # Filtere Zeilen die hauptsächlich aus Zahlen/Kommas bestehen
                alpha_count = sum(c.isalpha() for c in line)
                if alpha_count < 3:
                    continue
                # Bereinige Grade-Brackets
                cleaned = re.sub(r'\[.*?\]', '', line).strip()
                if cleaned and len(cleaned) >= 3:
                    # Entferne führende/trailing Sonderzeichen
                    cleaned = re.sub(r'^[^A-Za-z0-9]+', '', cleaned)
                    cleaned = re.sub(r'[^A-Za-z0-9\s\-\'\(\)]+$', '', cleaned).strip()
                    if cleaned:
                        metrics['item_name'] = cleaned
                        break
            
            # Debug-Logging für extrahierte Metriken
            if self.debug and metrics:
                log_debug(f"[DETAIL-EXTRACT] Extracted metrics for {window_type}:")
                log_debug(f"   Balance: {metrics.get('balance')}")
                log_debug(f"   Warehouse: {metrics.get('warehouse_qty')}")
                log_debug(f"   Item: {metrics.get('item_name')}")
                if len(s) <= 200:
                    log_debug(f"   OCR Text: {s}")
                else:
                    log_debug(f"   OCR Preview: {s[:200]}...")
            
            # Return-Logik: Balance ist Pflicht, Warehouse optional
            # (Warehouse-Änderung ist nicht immer sofort sichtbar)
            if 'balance' in metrics:
                return metrics

            # Keine Balance erkannt → Flags aktiv halten und None zurückgeben
            if self.debug:
                log_debug(f"[DETAIL-EXTRACT] No balance found in metrics, returning None")
            self._set_need_flag('detail_balance', True, "detail_extract_missing_balance")
            if 'warehouse_qty' not in metrics:
                self._set_need_flag('detail_warehouse', True, "detail_extract_missing_balance")
            return None
            
        except Exception as e:
            if self.debug:
                log_debug(f"[DETAIL] Error extracting detail window metrics: {e}")
            self._set_need_flag('detail_balance', True, "detail_extract_exception")
            self._set_need_flag('detail_warehouse', True, "detail_extract_exception")
            return None

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
            ts_val = tx.get('timestamp')
            last_processed = self.last_processed_game_ts if isinstance(self.last_processed_game_ts, datetime.datetime) else None
            ts_datetime = ts_val if isinstance(ts_val, datetime.datetime) else None

            if existing:
                historical_reference = False
                if ts_datetime and last_processed:
                    try:
                        historical_reference = (last_processed - ts_datetime) >= datetime.timedelta(seconds=1)
                    except Exception:
                        historical_reference = ts_datetime < last_processed
                reuse_index = None

                if slot < len(existing) and (seen_in_prev or historical_reference):
                    reuse_index = existing[slot]
                elif historical_reference:
                    reuse_index = existing[-1]
                elif seen_in_prev and ts_datetime and last_processed and ts_datetime < last_processed:
                    reuse_index = existing[-1]

                if reuse_index is not None:
                    tx['occurrence_index'] = reuse_index
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
        - For Detail-Window: Microsecond-precision timestamp to prevent collisions
        """
        try:
            # SPECIAL HANDLING: Detail-Window transactions need microsecond precision
            if tx.get('_from_detail_window'):
                ts = tx.get('timestamp')
                if isinstance(ts, datetime.datetime):
                    # Include microseconds for sub-second distinction
                    ts_precise = ts.strftime("%Y-%m-%d %H:%M:%S.%f")
                else:
                    ts_precise = str(ts)
                
                components = [
                    (tx.get('item_name') or '').lower(),
                    str(int(tx.get('quantity') or 0)),
                    str(int(tx.get('price') or 0)),
                    (tx.get('transaction_type') or '').lower(),
                    ts_precise,
                    'detail_window'  # Marker to prevent collision with log-based
                ]
                hash_input = "|".join(components)
                return hashlib.sha256(hash_input.encode('utf-8')).hexdigest()[:16]
            
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

    def _make_log_fallback_hash(self, entry: dict) -> str:
        """Build a stable hash for log-fallback candidates (item/qty/price/timestamp)."""
        try:
            item = (entry.get('item') or '').lower()
            qty = int(entry.get('qty') or 0)
            price = int(entry.get('price') or 0)
            ts = entry.get('timestamp')
            if isinstance(ts, datetime.datetime):
                ts_str = ts.strftime('%Y-%m-%d %H:%M:%S')
            else:
                ts_str = str(ts or '')
            raw = f"{item}|{qty}|{price}|{ts_str}"
        except Exception:
            raw = str(entry)
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]

    def _check_missing_detail_window_transactions(self, structured_entries: list[dict], window_type: str) -> list[dict]:
        """Analyse transaction-log to recover purchases missed in detail-window monitoring."""
        if not self._detail_window_entry_item:
            return []

        item_name = self._detail_window_entry_item
        item_lc = item_name.lower()
        missing: list[dict] = []

        pending_event = self._pending_relist_events.get(item_lc)

        for entry in structured_entries:
            if entry.get('type') not in ('purchased', 'transaction'):
                continue
            raw_item = (entry.get('item') or '').lower()
            if raw_item != item_lc:
                continue

            qty = entry.get('qty')
            price = entry.get('price')
            ts = entry.get('timestamp')
            if not qty or not price or not isinstance(ts, datetime.datetime):
                continue

            if qty < MIN_ITEM_QUANTITY or qty > MAX_ITEM_QUANTITY:
                continue

            hash_val = self._make_log_fallback_hash(entry)
            if hash_val in self._log_fallback_seen_hashes:
                continue

            already_exact = transaction_exists_exact(
                item_name,
                int(qty),
                int(price),
                'buy',
                ts,
                0,
            )
            already_any_side = transaction_exists_any_side(
                item_name,
                int(qty),
                int(price),
                ts,
            )
            if already_exact or already_any_side:
                self._log_fallback_seen_hashes.add(hash_val)
                continue

            normalized_qty = int(qty)
            normalized_price = int(price)

            if normalized_qty <= 0 or normalized_price <= 0:
                continue

            normalized_row = {
                'item_name': item_name,
                'quantity': normalized_qty,
                'price': normalized_price,
                'timestamp': ts,
                'transaction_type': 'buy',
                'case': 'buy_collect_log_fallback',
                'raw_related': [entry],
                'occurrence_index': None,
                '_from_detail_window': False,
            }

            content_hash = self.make_content_hash(normalized_row)
            if content_hash in self._log_fallback_recent_hashes:
                continue

            self._log_fallback_recent_hashes.append(content_hash)
            self._log_fallback_seen_hashes.add(hash_val)
            missing.append(normalized_row)

            if pending_event is not None:
                pending_event['fallback_attached'] = True
                pending_event['fallback_entry'] = normalized_row

        return missing

    def store_transaction_db(self, tx):
        """Speichert eine Transaktion in der DB thread-sicher."""
        item = tx['item_name']
        qty = tx['quantity']
        price = tx.get('price')
        ttype = tx['transaction_type']
        ts = tx['timestamp']
        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S") if isinstance(ts, datetime.datetime) else str(ts)
        case = tx.get('tx_case') or tx.get('case')  # Support both keys
        occ_idx_raw = tx.get('occurrence_index')
        try:
            occ_idx = int(occ_idx_raw) if occ_idx_raw is not None else 0
        except Exception:
            occ_idx = 0

        # Versuche fehlende Preise frühzeitig zu rekonstruieren, bevor Dedupe greift
        if (price is None or price <= 0) and tx.get('_recovered_price'):
            try:
                recovered_val = int(tx['_recovered_price'])
                if recovered_val > 0:
                    price = recovered_val
                    tx['price'] = recovered_val
            except Exception:
                pass

        if (price is None or price <= 0) and (ttype or '').lower() == 'sell':
            raw_related = tx.get('raw_related') or []
            candidate_qty = qty if isinstance(qty, (int, float)) else None
            for raw_entry in raw_related:
                if not isinstance(raw_entry, dict):
                    continue
                entry_qty = candidate_qty
                if not entry_qty:
                    entry_qty = raw_entry.get('qty')
                try:
                    entry_qty_int = int(entry_qty) if entry_qty is not None else 0
                except Exception:
                    entry_qty_int = 0
                recovered_price = self._recover_sell_price(item, entry_qty_int, price, raw_entry)
                if recovered_price and recovered_price > 0:
                    price = int(recovered_price)
                    tx['price'] = price
                    tx['_recovered_price'] = price
                    raw_entry['_recovered_price'] = price
                    break

        sig = self.make_tx_sig(item, qty, price or 0, ttype, ts, occ_idx)
        # CRITICAL: Generate content hash for reliable deduplication
        content_hash = self.make_content_hash(tx)
        ts_dt = ts if isinstance(ts, datetime.datetime) else None
        last_processed = self.last_processed_game_ts if isinstance(self.last_processed_game_ts, datetime.datetime) else None

        if ts_dt and last_processed:
            try:
                historical_gap = (last_processed - ts_dt) >= datetime.timedelta(seconds=1)
            except Exception:
                historical_gap = ts_dt < last_processed
        else:
            historical_gap = False

        if ts_dt and last_processed and historical_gap and (tx.get('occurrence_slot', 0) or 0) == 0:
            try:
                existing_indices = fetch_occurrence_indices(item, int(qty), int(price), ttype, ts_dt)
            except Exception:
                existing_indices = []
            if existing_indices:
                if occ_idx not in existing_indices:
                    tx['occurrence_index'] = existing_indices[-1]
                if self.debug:
                    log_debug(
                        f"[CONTENT-HASH] Historical duplicate guard skipped {ttype} {qty}x {item} "
                        f"ts={ts_dt} indices={existing_indices}"
                    )
                self.seen_tx_signatures.append(sig)
                return False
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
                                log_debug(f"[CONTENT-HASH] Skip duplicate: {item} {qty}x already captured by detail-window (id={existing_id}, ts={existing_ts_str})")
                                if abs(int(price) - int(existing_ts_str)) > 0:
                                    log_debug(f"[CONTENT-HASH] 🔶 Price difference detected: Detail-Window={existing_ts_str:,}, Log-based={price:,} (preferring Detail-Window)")
                            print(f"⚠️ Duplikat erkannt (Content-Hash + Zeit): {str(ttype or '').upper()} - {qty}x {item}")
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
        
        # ADDITIONAL: Check for near-duplicate (Detail-Window vs Log-based)
        # If log-based parsing tries to save a transaction that was already captured
        # by detail-window monitoring (within 2 minutes), skip it
        if price is not None and not tx.get('_from_detail_window'):
            try:
                db_cur = get_cursor()
                # Round timestamp to minute for comparison
                if isinstance(ts, datetime.datetime):
                    ts_minute = ts.strftime("%Y-%m-%d %H:%M")
                    
                    # FIX #3: Price-Similarity Check (±10% tolerance)
                    # Verhindert dass zwei verschiedene Preise für selbe Transaktion gespeichert werden
                    PRICE_TOLERANCE = 0.10  # ±10%
                    price_min = int(price * (1 - PRICE_TOLERANCE))
                    price_max = int(price * (1 + PRICE_TOLERANCE))
                    
                    # Check for similar transaction within ±2 minutes AND ±10% price
                    db_cur.execute(
                        """
                        SELECT id, timestamp, tx_case, price FROM transactions 
                        WHERE item_name = ? AND quantity = ? 
                        AND CAST(price AS INTEGER) BETWEEN ? AND ?
                        AND transaction_type = ?
                        AND datetime(timestamp) BETWEEN datetime(?, '-2 minutes') AND datetime(?, '+2 minutes')
                        LIMIT 1
                        """,
                        (item, int(qty), price_min, price_max, ttype, ts_str, ts_str)
                    )
                    near_duplicate = db_cur.fetchone()
                    if near_duplicate:
                        existing_id, existing_ts, existing_case, existing_price = near_duplicate
                        # If existing was from detail-window, skip log-based duplicate
                        if existing_case and 'ui_inferred' in str(existing_case):
                            if self.debug:
                                log_debug(f"[DEDUPE-LOG] Skip log-based duplicate: {item} {qty}x already captured by detail-window (id={existing_id}, ts={existing_ts})")
                                if abs(int(price) - int(existing_price)) > 0:
                                    log_debug(f"[DEDUPE-LOG] 🔶 Price difference detected: Detail-Window={existing_price:,}, Log-based={price:,} (preferring Detail-Window)")
                            print(f"⚠️ Duplikat erkannt (Detail-Window hatte bereits erfasst): {str(ttype or '').upper()} - {qty}x {item}")
                            self.seen_tx_signatures.append(sig)
                            return False
            except Exception as e:
                if self.debug:
                    log_debug(f"[DEDUPE-LOG] Check failed: {e}")
        
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
        if price is not None:
            try:
                existing = find_existing_tx_by_values(item, qty, int(price), ttype, ts_str, occ_idx)
            except Exception:
                existing = None
        else:
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
        else:
            if ts_dt:
                if last_processed and ts_dt > last_processed:
                    pass
                else:
                    try:
                        if price is not None and transaction_exists_by_values_near_time(item, qty or 0, int(price), ts_dt, tolerance_minutes=5):
                            if self.debug:
                                log_debug(f"[CONTENT-HASH] Skip near-time duplicate: {item} {qty}x @ {price} around {ts_dt}")
                            self.seen_tx_signatures.append(sig)
                            return False
                    except Exception as exc:
                        if self.debug:
                            log_debug(f"[CONTENT-HASH] Near-time duplicate check failed: {exc}")
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

    def _reset_detail_window_state(self, reason: str = "manual_reset") -> None:
        """Setzt den kompletten Detail-Window-State zurück (Baseline, Deltas, Caches)."""
        self._detail_window_item = None
        self._detail_window_active = False
        self._detail_window_type = None
        self._detail_window_opened_at: datetime.datetime | None = None
        self._detail_baseline: dict[str, Any] | None = None
        self._detail_baseline_balance = None
        self._detail_baseline_warehouse = None
        self._detail_detail_snapshot_ts = None
        self._detail_last_metrics = None
        self._detail_last_delta_activity = None
        self._detail_confirmation_pending = False
        self._detail_confirmation_timestamp = None
        self._detail_partial_balance_delta = 0
        self._detail_partial_warehouse_delta = 0
        self._detail_pending_collect_qty = 0
        self._detail_balance_delta_timestamp = None
        self._detail_balance_changed_once = False
        self._detail_warehouse_changed_once = False
        self._detail_needs_baseline_capture = False
        self._detail_baseline_captured = False
        self._detail_window_entry_item = None
        self._detail_window_hint = None
        self._detail_input_cache = {
            'baseline': None,
            'refresh': None,
        }
        self._detail_await_preorder_check = False
        self._detail_preorder_check_baseline = None
        self._detail_last_transaction_saved = None
        self._detail_ui_orders_completed = None
        self._detail_relist_autocollect_signature = None
        self._detail_relist_instant_signature = None
        self._detail_relist_new_preorder_signature = None
        self._detail_pending_log_snapshots = []
        self._detail_pending_snapshot_hashes.clear()
        self._force_detail_metric_refresh = False
        self._last_detail_balance_text = ""
        self._last_detail_warehouse_text = ""
        self._set_need_flag('detail_inputs', False, "detail_state_reset")
        self._set_detail_metric_state("idle", reason)
        if self.debug:
            log_debug(f"[DETAIL] State reset ({reason})")

    def _force_save_pending_transaction(self) -> bool:
        """
        Persist a pending balance-only transaction when the detail window closes.
        """
        if not self._detail_window_active or self._detail_window_type != 'buy_item':
            return False

        if self._detail_partial_balance_delta >= 0:
            return False

        if self._detail_partial_warehouse_delta != 0:
            return False

        if not self._detail_balance_delta_timestamp:
            return False

        total_spent = abs(int(self._detail_partial_balance_delta))
        if total_spent <= 0:
            return False

        metrics = self._detail_last_metrics or {}
        desired_price = None
        price_source = "metrics"
        quantity_hint = None

        candidate_price = metrics.get('desired_price')
        if isinstance(candidate_price, (int, float)) and candidate_price > 0:
            desired_price = int(candidate_price)
        else:
            # Fallback: try to estimate from transaction price
            # But transaction price might be COLLECTED price (different from preorder price)
            # Better to use base price as last resort
            base_price = self._get_base_price(item_name)
            desired_price = base_price if base_price else None

        if desired_price is None or desired_price <= 0:
            if self.debug:
                log_debug(
                    f"[DETAIL] 🔶 Pending balance-only transaction but desired price missing - skipping force-save"
                )
            return False

        qty_estimate = total_spent / desired_price
        quantity = int(round(qty_estimate)) if qty_estimate > 0 else 0
        if quantity_hint is None:
            qty_val = metrics.get('quantity')
            if isinstance(qty_val, (int, float)):
                quantity_hint = int(qty_val)

        if quantity_hint and quantity <= 0:
            quantity = int(quantity_hint)
        elif quantity_hint:
            expected_total = desired_price * int(quantity_hint)
            tolerance = max(desired_price * 0.1, 1000)
            if abs(expected_total - total_spent) <= tolerance:
                quantity = int(quantity_hint)

        if quantity <= 0:
            if self.debug:
                log_debug("[DETAIL] 🔶 Force-save aborted: could not estimate quantity")
            return False

        MAX_ACCUMULATED_PURCHASE = 500000
        if quantity > MAX_ACCUMULATED_PURCHASE:
            if self.debug:
                log_debug(f"[DETAIL] 🔶 Force-save aborted: quantity {quantity} exceeds max {MAX_ACCUMULATED_PURCHASE}")
            return False

        raw_item_name = (
            metrics.get('item_name')
            or self._detail_window_item
            or getattr(self, '_detail_window_entry_item', None)
        )
        corrected_name, is_valid = self._safe_correct_item_name(raw_item_name)
        if not corrected_name or not is_valid:
            if self.debug:
                log_debug(f"[DETAIL] 🔶 Force-save aborted: invalid item name '{raw_item_name}'")
            return False

        if self.debug:
            log_debug("[DETAIL] 🔶 Window closed with pending balance-only transaction!")
            log_debug(
                f"[DETAIL] 🔶 Forcing balance-only save now (Δbalance={self._detail_partial_balance_delta:+,}, "
                f"price_source={price_source}, desired_price={desired_price:,})"
            )

        tx = {
            'item_name': corrected_name,
            'quantity': int(quantity),
            'price': total_spent,
            'transaction_type': 'buy',
            'tx_case': 'buy_collect_balance_only_forced',
            'timestamp': datetime.datetime.now(),
            '_from_detail_window': True,
        }

        saved = self.store_transaction_db(tx)
        if saved and self.debug:
            log_debug(
                f"[DETAIL] 🔶 Forced balance-only transaction saved: "
                f"{quantity:,}x {corrected_name} @ {total_spent:,} Silver"
            )
        return saved

    def _capture_detail_debug_images(self, label: str, img, proc_img) -> None:
        """Saves detail window debug images when debug is enabled."""
        if not self.debug or img is None or proc_img is None:
            return

        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        base_dir = Path('debug') / 'detail_window'
        base_dir.mkdir(parents=True, exist_ok=True)

        try:
            orig_path = base_dir / f'{label}_{ts}_orig.png'
            proc_path = base_dir / f'{label}_{ts}_proc.png'
            cv2.imwrite(str(orig_path), img)
            cv2.imwrite(str(proc_path), proc_img)
        except Exception as e:
            log_debug(f"[DETAIL-DEBUG] Failed to write debug images: {e}")

    def _detect_preorder_placement(
        self,
        item_name: str,
        balance_delta: float,
        current_metrics: dict,
        timestamp: datetime.datetime,
        img=None,
        proc_img=None,
        cached_input: Optional[dict] = None,
        cached_timestamp: Optional[datetime.datetime] = None
    ) -> bool:
        """
        Detect when user places a preorder in detail-window.
        
        CRITICAL NEW LOGIC (Strategy 1 - Detail-Window Input Fields):
        1. Extract ACTUAL preorder values from input field ROI
        2. Use OCR on "Desired Price" + "Desired Amount" fields
        3. Only fallback to balance_delta calculation if ROI extraction fails
        
        Detection Logic:
        1. balance_delta < 0 (silver spent)
        2. warehouse_delta == 0 OR > 0 (no items yet, or auto-collect happened)
        3. PRIMARY: Extract quantity/price from input fields (RELIST-safe!)
        4. FALLBACK: Calculate quantity from balance_delta / base_price (OLD buggy method)
        
        CRITICAL: This must NOT interfere with existing delta logic!
        We return True after storing preorder and updating baseline.
        
        Args:
            item_name: Item name (from baseline)
            balance_delta: Balance decrease (negative)
            current_metrics: Current UI metrics dict
            timestamp: Current timestamp
            img: Original BGR image (for ROI extraction)
            proc_img: Preprocessed image (for ROI extraction)
            
        Returns:
            True if preorder detected and stored, False otherwise
        """
        try:
            preorder_qty = None
            # Example Trace of Nature:
            #   - Old preorder: 5000x @ 770M (filled: 219x)
            #   - Click "Relist" → Auto-collect: 219x @ 33.7M
            #   - balance_delta = -33,726,000 (auto-collect!)
            #   - Input fields show: 5000x @ 154,000 (NEW preorder!)
            #   - OLD BUGGY CALC: 33.7M / 153,819 ≈ 219 → rounds to 200x ❌
            #   - NEW ROI EXTRACT: Reads "5000" from field → CORRECT! ✅
            
            if (preorder_qty is None or preorder_unit_price is None) and img is not None and proc_img is not None:
                input_fields = self._extract_preorder_input_fields(
                    img=img,
                    proc_img=proc_img,
                    window_type='buy_item'
                )
                
                if input_fields and 'price' in input_fields and 'quantity' in input_fields:
                    preorder_qty = input_fields['quantity']
                    preorder_unit_price = input_fields['price']
                    preorder_total_price = preorder_unit_price * preorder_qty
                    extraction_method = "input_fields_roi"
                    
                    if self.debug:
                        log_debug(
                            f"[PREORDER-DETECT] ✅ ROI Extraction SUCCESS: "
                            f"{preorder_qty:,}x @ {preorder_unit_price:,} "
                            f"(total {preorder_total_price:,}, method: {extraction_method})"
                        )
            
            # ═══════════════════════════════════════════════════════════════
            # STRATEGY 2 (FALLBACK): Calculate from balance_delta
            # ═══════════════════════════════════════════════════════════════
            # WARNING: This is UNRELIABLE for relist scenarios!
            # Only use if ROI extraction failed
            
            if preorder_qty is None or (preorder_unit_price is None and preorder_total_price is None):
                if self.debug:
                    log_debug(
                        f"[PREORDER-DETECT] ⚠️ ROI extraction failed, "
                        f"falling back to balance_delta calculation"
                    )
                
                # Calculate preorder price from balance_delta
                preorder_total_price = abs(balance_delta)
                
                # Get base price for quantity calculation
                base_price = self._get_base_price(item_name)
                
                if base_price is None or base_price <= 0:
                    if self.debug:
                        log_debug(
                            f"[PREORDER-DETECT] Cannot get base price for '{item_name}'"
                        )
                    return False
                
                # Calculate quantity using _calculate_expected_qty helper
                # This rounds to 1000/100/1 based on magnitude
                preorder_qty = self._calculate_expected_qty(preorder_total_price, item_name)
                extraction_method = "balance_delta_calculation"
                
                if self.debug:
                    log_debug(
                        f"[PREORDER-DETECT] Calculated: {preorder_qty:,}x total={preorder_total_price:,} "
                        f"(method: {extraction_method})"
                    )
            
            # Ensure both unit and total price are set
            if preorder_unit_price is None and preorder_qty and preorder_total_price is not None:
                preorder_unit_price = preorder_total_price / preorder_qty

            if preorder_total_price is None and preorder_unit_price is not None and preorder_qty:
                preorder_total_price = preorder_unit_price * preorder_qty

            if preorder_total_price is not None:
                preorder_total_price = int(round(preorder_total_price))

            if preorder_unit_price is not None:
                preorder_unit_price = int(round(preorder_unit_price))

            if preorder_qty and preorder_unit_price and abs(balance_delta) > 0:
                delta_vs_total = abs(abs(balance_delta) - (preorder_qty * preorder_unit_price))
                tolerance = max(5000, int(preorder_unit_price * 0.02 * max(1, preorder_qty)))
                if delta_vs_total > tolerance:
                    if self.debug:
                        log_debug(
                            f"[PREORDER-DETECT] ⚠️ Plausibility mismatch: "
                            f"Δbalance={abs(balance_delta):,} vs qty*price={preorder_qty * preorder_unit_price:,} "
                            f"(diff {delta_vs_total:,} > tolerance {tolerance:,})"
                        )
                    # Refresh anfordern und abbrechen; möglicherweise wurden UI-Werte geändert
                    self._request_detail_input_refresh('buy_item', 'preorder_mismatch_retry')
                    return False

            # ═══════════════════════════════════════════════════════════════
            # Validation & Storage
            # ═══════════════════════════════════════════════════════════════
            
            if preorder_qty <= 0 or preorder_qty > 5000:
                if self.debug:
                    log_debug(
                        f"[PREORDER-DETECT] Quantity {preorder_qty} out of range (1-5000)"
                    )
                return False
            
            if preorder_total_price is None or preorder_total_price <= 0:
                if self.debug:
                    log_debug(
                        f"[PREORDER-DETECT] Total price {preorder_total_price} invalid"
                    )
                return False
            
            # Sanity check: implied unit price must be plausible
            if preorder_unit_price is None or preorder_unit_price <= 0:
                if self.debug:
                    log_debug("[PREORDER-DETECT] Unable to determine unit price")
                return False

            implied_unit_price = preorder_unit_price
            base_price = self._get_base_price(item_name)

            if base_price and base_price > 0:
                min_price = base_price * 0.85
                max_price = base_price * 1.15

                if not (min_price <= implied_unit_price <= max_price):
                    if self.debug:
                        log_debug(
                            f"[PREORDER-DETECT] Price implausible: "
                            f"{implied_unit_price:,.0f} not in range "
                            f"[{min_price:,.0f}, {max_price:,.0f}]"
                        )
                    # Don't fail for ROI extraction - it's authoritative!
                    if extraction_method != "input_fields_roi":
                        return False
            
            # Store preorder
            corrected_name, _ = self._safe_correct_item_name(item_name)
            corrected_name = corrected_name or item_name
            
            dedupe_key = (
                corrected_name.lower(),
                int(preorder_qty),
                int(round(preorder_unit_price)),
                int(round(preorder_total_price))
            )
            now_ts = datetime.datetime.now().timestamp()
            self._recent_preorder_hashes = {
                k: v for k, v in self._recent_preorder_hashes.items()
                if (now_ts - v) < self._recent_preorder_ttl
            }
            last_seen = self._recent_preorder_hashes.get(dedupe_key)

            if last_seen and (now_ts - last_seen) < self._recent_preorder_ttl:
                if self.debug:
                    log_debug(
                        f"[PREORDER-DETECT] Duplicate detected within 2s for {corrected_name} "
                        f"x{preorder_qty} @ {preorder_unit_price:,.0f} (total {preorder_total_price:,.0f}) – skipping store"
                    )
                return True

            self._capture_detail_debug_images('preorder', img, proc_img)
            preorder_id = self._preorder_manager.store_preorder(
                item_name=corrected_name,
                quantity=preorder_qty,
                price=preorder_total_price,
                timestamp=timestamp
            )

            if preorder_id > 0:
                now_saved = datetime.datetime.now()
                self._recent_preorder_hashes[dedupe_key] = now_ts
                self._detail_last_transaction_saved = now_saved
                self._detail_baseline_balance = current_metrics.get('balance', self._detail_baseline_balance)
                self._detail_baseline_warehouse = current_metrics.get('warehouse_qty', self._detail_baseline_warehouse)
                self._detail_last_metrics = current_metrics.copy() if isinstance(current_metrics, dict) else {
                    'balance': self._detail_baseline_balance,
                    'warehouse_qty': self._detail_baseline_warehouse,
                }
                self._detail_partial_balance_delta = 0
                self._detail_partial_warehouse_delta = 0
                self._detail_balance_changed_once = False
                self._detail_warehouse_changed_once = False
                self._cache_detail_input_fields(
                    kind='refresh',
                    fields={'quantity': int(preorder_qty), 'price': int(preorder_unit_price)},
                    window_type='buy_item',
                    source='preorder_detect_saved',
                    timestamp=now_saved,
                )
                self._set_need_flag('detail_inputs', False, 'preorder_detect_saved')
                if self.debug:
                    log_debug(
                        f"[PREORDER-PLACED] ✅ Detected: {corrected_name} "
                        f"x{preorder_qty:,} @ {preorder_total_price:,.0f} Silver "
                        f"(unit: {implied_unit_price:,.0f}, method: {extraction_method}, ID: {preorder_id})"
                    )
                return True
            else:
                return False
        
        except Exception as e:
            if self.debug:
                log_debug(f"[PREORDER-DETECT] ERROR: {e}")
            return False

    def _detect_listing_placement(
        self,
        item_name: str,
        warehouse_delta: int,
        current_metrics: dict,
        timestamp: datetime.datetime,
        img=None,
        proc_img=None,
        cached_input: Optional[dict] = None,
        cached_timestamp: Optional[datetime.datetime] = None
    ) -> bool:
        """
        Detect when user places a listing (sell order) in detail-window.
        
        CRITICAL NEW LOGIC (Strategy 1 - Detail-Window Input Fields):
        1. Extract ACTUAL listing values from input field ROI
        2. Use OCR on "Set Price" + "Register Quantity" fields
        3. Only fallback to warehouse_delta calculation if ROI extraction fails
        
        Detection Logic (Sell-Side analog to preorder):
        1. warehouse_delta < 0 (items moved TO market)
        2. balance_delta ≈ 0 (no silver received yet)
        3. PRIMARY: Extract quantity/price from input fields (RELIST-safe!)
        4. FALLBACK: Quantity = abs(warehouse_delta), price = base_price * qty
        
        CRITICAL: This must NOT interfere with existing delta logic!
        We return True after storing listing and updating baseline.
        
        Args:
            item_name: Item name (from baseline)
            warehouse_delta: Warehouse decrease (negative)
            current_metrics: Current UI metrics dict
            timestamp: Current timestamp
            img: Original BGR image (for ROI extraction)
            proc_img: Preprocessed image (for ROI extraction)
            
        Returns:
            True if listing detected and stored, False otherwise
        """
        try:
            listing_qty = None
            listing_unit_price = None
            listing_price = None
            extraction_method = "unknown"
            
            # ═══════════════════════════════════════════════════════════════
            # STRATEGY 1 (PRIMARY): Use cached baseline input fields when fresh
            # ═══════════════════════════════════════════════════════════════

            cache_used = False
            if cached_input and isinstance(cached_input, dict) and cached_timestamp:
                try:
                    cache_age = (datetime.datetime.now() - cached_timestamp).total_seconds()
                except Exception:
                    cache_age = None

                if cache_age is not None and cache_age <= 5.0:
                    try:
                        listing_qty = int(cached_input.get('quantity'))
                        listing_unit_price = int(cached_input.get('price'))
                    except Exception:
                        listing_qty = cached_input.get('quantity')
                        listing_unit_price = cached_input.get('price')

                    if listing_qty and listing_unit_price:
                        listing_price = listing_unit_price * listing_qty
                        extraction_method = "cached_input_fields"
                        cache_used = True
                        if self.debug:
                            log_debug(
                                f"[LISTING-DETECT] ✅ Using cached input fields: "
                                f"{listing_qty:,}x @ {listing_unit_price:,}/ea "
                                f"(total: {listing_price:,})"
                            )

            # ═══════════════════════════════════════════════════════════════
            # STRATEGY 2: On-demand extraction if cache missing (same frame)
            # ═══════════════════════════════════════════════════════════════

            if not cache_used and img is not None and proc_img is not None:
                input_fields = self._extract_preorder_input_fields(
                    img=img,
                    proc_img=proc_img,
                    window_type='sell_item'
                )

                if input_fields and 'price' in input_fields and 'quantity' in input_fields:
                    try:
                        listing_qty = int(input_fields['quantity'])
                        listing_unit_price = int(input_fields['price'])
                    except Exception:
                        listing_qty = input_fields['quantity']
                        listing_unit_price = input_fields['price']

                    if listing_qty and listing_unit_price:
                        listing_price = listing_unit_price * listing_qty
                        extraction_method = "input_fields_roi"
                        if self.debug:
                            log_debug(
                                f"[LISTING-DETECT] ✅ ROI Extraction SUCCESS: "
                                f"{listing_qty:,}x @ {listing_unit_price:,}/ea "
                                f"(total: {listing_price:,}, method: {extraction_method})"
                            )
            
            # ═══════════════════════════════════════════════════════════════
            # STRATEGY 2 (FALLBACK): Calculate from warehouse_delta
            # ═══════════════════════════════════════════════════════════════
            
            if listing_qty is None or (listing_price is None and listing_unit_price is None):
                if self.debug:
                    log_debug(
                        f"[LISTING-DETECT] ⚠️ ROI extraction failed, "
                        f"falling back to warehouse_delta calculation"
                    )
                
                # Quantity = items moved to market
                listing_qty = abs(warehouse_delta)

                # Get base price
                base_price = self._get_base_price(item_name)

                if base_price is None:
                    if self.debug:
                        log_debug(
                            f"[LISTING-DETECT] Cannot determine base price for '{item_name}'"
                        )
                    return False
                
                # Calculate listing price (GROSS before tax)
                listing_unit_price = base_price
                listing_price = listing_unit_price * listing_qty
                extraction_method = "warehouse_delta_calculation"

                if self.debug:
                    log_debug(
                        f"[LISTING-DETECT] Calculated: {listing_qty:,}x @ {listing_unit_price:,}/ea "
                        f"(total: {listing_price:,}, method: {extraction_method})"
                    )

            # Ensure both unit and total price are set
            if listing_unit_price is None and listing_qty and listing_price is not None:
                listing_unit_price = listing_price / listing_qty

            if listing_price is None and listing_unit_price is not None and listing_qty:
                listing_price = listing_unit_price * listing_qty

            if listing_price is not None:
                listing_price = int(round(listing_price))

            if listing_unit_price is not None:
                listing_unit_price = int(round(listing_unit_price))

            # ═══════════════════════════════════════════════════════════════
            # Validation & Storage
            # ═══════════════════════════════════════════════════════════════

            if listing_qty <= 0 or listing_qty > 5000:
                if self.debug:
                    log_debug(
                        f"[LISTING-DETECT] Quantity {listing_qty} out of range (1-5000)"
                    )
                return False
            
            if listing_price is None or listing_price <= 0:
                # Versuche durch Refresh neue Eingaben zu erhalten
                self._request_detail_input_refresh(window_type, 'force_save_missing_price')
                if self.debug:
                    log_debug(
                        f"[DETAIL] 🔶 Force-save aborted: desired price missing"
                    )
                return False

            if listing_unit_price is None or listing_unit_price <= 0:
                if self.debug:
                    log_debug("[LISTING-DETECT] Unable to determine unit price")
                return False

            # Store listing
            corrected_name, valid = self._safe_correct_item_name(item_name)
            corrected_name = corrected_name or item_name

            dedupe_key = (
                corrected_name.lower(),
                int(listing_qty),
                int(round(listing_unit_price)),
                int(round(listing_price))
            )
            now_ts = datetime.datetime.now().timestamp()
            self._recent_listing_hashes = {
                k: v for k, v in self._recent_listing_hashes.items()
                if (now_ts - v) < self._recent_listing_ttl
            }
            last_seen = self._recent_listing_hashes.get(dedupe_key)

            if last_seen and (now_ts - last_seen) < self._recent_listing_ttl:
                if self.debug:
                    log_debug(
                        f"[LISTING-DETECT] Duplicate detected within 2s for {corrected_name} "
                        f"x{listing_qty} @ {listing_unit_price:,.0f} (total {listing_price:,.0f}) – skipping store"
                    )
                return True

            listing_id = self._preorder_manager.store_listing(
                item_name=corrected_name,
                quantity=listing_qty,
                price=listing_price,
                timestamp=timestamp
            )

            if listing_id > 0:
                unit_price = listing_unit_price
                self._recent_listing_hashes[dedupe_key] = now_ts
                if self.debug:
                    log_debug(
                        f"[LISTING-PLACED] ✅ Detected: {corrected_name} "
                        f"x{listing_qty:,} @ {listing_price:,.0f} Silver "
                        f"(unit: {unit_price:,.0f}, method: {extraction_method}, ID: {listing_id})"
                    )
                return True
            else:
                return False
        
        except Exception as e:
            if self.debug:
                log_debug(f"[LISTING-DETECT] ERROR: {e}")
            return False

    def _infer_transaction_from_deltas(
        self,
        window_type: str,
        balance_delta: int,
        warehouse_delta: int,
        current_metrics: dict,
        last_metrics: dict,
        ocr_text: str = "",
        preorder_correction: Optional[Dict] = None  # NEW parameter
    ) -> dict | None:
        """
        Leitet Transaktion aus Balance- und Warehouse-Deltas ab.
        
        WICHTIG: BDO updated Balance und Warehouse ASYNCHRON!
        Daher akkumulieren wir Deltas über mehrere Scans:
        - Scan 1: Balance -100k, Warehouse +0 → Akkumuliere
        - Scan 2: Balance +0, Warehouse +5000 → Transaktion komplett!
        
        Regeln:
        
        Sell-Item Window:
        - Balance steigt → Verkauf erfolgreich
        - Warehouse sinkt → Ware wurde entnommen
        - Preis = Balance-Delta / Tax-Factor (0.88725)
        - Menge = abs(Warehouse-Delta)
        - Typ = 'sell'
        
        Buy-Item Window:
        - Balance sinkt → Kauf erfolgreich
        - Warehouse steigt → Ware wurde hinzugefügt
        - Preis = abs(Balance-Delta)
        - Menge = Warehouse-Delta
        - Typ = 'buy'
        
        Args:
            window_type: 'sell_item' oder 'buy_item'
            balance_delta: Änderung der Balance (positiv = mehr Geld)
            warehouse_delta: Änderung der Warehouse (positiv = mehr Items)
            current_metrics: Aktuelle Metriken (mit set_price/desired_price/quantity)
            last_metrics: Letzte Metriken vor Änderung
        
        Returns:
            dict mit Transaction-Daten oder None (None = noch nicht komplett, weiter akkumulieren)
        """
        try:
            TAX_FACTOR = 0.88725  # BDO Central Market Tax
            
            # ========== DELTA ACCUMULATION ==========
            # ========== SMART RESET: Neue Transaction-Erkennung ==========
            # Wenn BEIDE Deltas sich in DIESEM Scan ändern, beginnt eine neue Transaction
            # → Verwerfe alte partielle Akkumulation (verhindert Pig Blood 3-TX-Bug)
            both_changed_now = (balance_delta != 0 and warehouse_delta != 0)
            
            had_incomplete_accumulation = (
                (self._detail_partial_balance_delta != 0 and self._detail_partial_warehouse_delta == 0) or
                (self._detail_partial_balance_delta == 0 and self._detail_partial_warehouse_delta != 0)
            )
            
            if both_changed_now and had_incomplete_accumulation:
                if self.debug:
                    log_debug(f"[DETAIL] 🔄 New transaction detected (both deltas changed simultaneously)")
                    log_debug(f"[DETAIL] ❌ Discarding incomplete accumulation: balance={self._detail_partial_balance_delta:+,}, warehouse={self._detail_partial_warehouse_delta:+,}")
                
                # Reset: Starte frische Akkumulation mit aktuellen Werten
                self._detail_partial_balance_delta = 0
                self._detail_partial_warehouse_delta = 0
            
            # Akkumuliere Balance-Deltas
            if balance_delta != 0:
                # Merke Zeitpunkt des ersten balance_delta (für Timeout)
                if self._detail_partial_balance_delta == 0 and balance_delta < 0:
                    self._detail_balance_delta_timestamp = datetime.datetime.now()
                    if self.debug:
                        log_debug(f"[DETAIL] Started balance_delta timer at {self._detail_balance_delta_timestamp}")
                
                self._detail_partial_balance_delta += balance_delta
                if self.debug:
                    log_debug(f"[DETAIL] Accumulated balance delta: {self._detail_partial_balance_delta:+,} (this scan: {balance_delta:+,})")
            
            # Akkumuliere Warehouse-Deltas
            if warehouse_delta != 0:
                self._detail_partial_warehouse_delta += warehouse_delta
                if self._detail_partial_balance_delta == 0:
                    self._detail_pending_collect_qty += warehouse_delta
                if self.debug:
                    log_debug(f"[DETAIL] Accumulated warehouse delta: {self._detail_partial_warehouse_delta:+,} (this scan: {warehouse_delta:+,})")
                
                # Reset timer wenn warehouse_delta endlich kommt
                if self._detail_balance_delta_timestamp:
                    elapsed = (datetime.datetime.now() - self._detail_balance_delta_timestamp).total_seconds()
                    if self.debug:
                        log_debug(f"[DETAIL] Warehouse delta received after {elapsed:.2f}s")
                    self._detail_balance_delta_timestamp = None
            
            # ========== VALIDATION MIT AKKUMULIERTEN DELTAS ==========
            if window_type == 'sell_item':
                # Sell: Balance steigt, Warehouse sinkt
                # Prüfe ob BEIDE Deltas jetzt vorhanden sind
                if self._detail_partial_balance_delta <= 0 or self._detail_partial_warehouse_delta >= 0:
                    # Noch nicht beide Deltas vorhanden → Weiter akkumulieren
                    if self.debug and (balance_delta != 0 or warehouse_delta != 0):
                        log_debug(f"[DETAIL] Sell-Transaction incomplete: balance_delta={self._detail_partial_balance_delta}, warehouse_delta={self._detail_partial_warehouse_delta} (waiting for both)")
                    return None
                
                # BEIDE Deltas vorhanden → Transaction erstellen
                gross_price = int(self._detail_partial_balance_delta / TAX_FACTOR)
                quantity = abs(self._detail_partial_warehouse_delta)
                
                # Plausibilitätsprüfung: Vergleiche mit set_price falls vorhanden
                set_price = current_metrics.get('set_price')
                if not set_price and last_metrics:
                    set_price = last_metrics.get('set_price')
                if set_price:
                    expected_gross = set_price * quantity
                    # Toleriere 5% Abweichung
                    if abs(gross_price - expected_gross) / expected_gross > 0.05:
                        if self.debug:
                            log_debug(f"[DETAIL] Sell price mismatch: calculated={gross_price}, expected={expected_gross}")
                        # Nutze set_price wenn plausibel
                        gross_price = expected_gross
                
                transaction_type = 'sell'
                tx_case = 'sell_collect_ui_inferred'  # Detail-Window via UI-Delta-Inferenz
                
            elif window_type == 'buy_item':
                # Buy: Balance sinkt, Warehouse steigt
                
                # SPEZIALFALL: Warehouse-Only Delta (Preorder-Collect ohne Kauf)
                # Wenn warehouse_delta > 0 ABER balance_delta = 0:
                # → Preorder wurde collected, aber noch kein neuer Kauf
                # → Ignoriere diesen Delta, warte auf echten Kauf (balance_delta < 0)
                if self._detail_partial_warehouse_delta > 0 and self._detail_partial_balance_delta == 0:
                    if self.debug:
                        log_debug(f"[DETAIL] Preorder-Collect detected: warehouse +{self._detail_partial_warehouse_delta}, balance unchanged")
                        log_debug(f"[DETAIL] Waiting for actual purchase (balance negative) before saving transaction")
                    return None
                
                # FIX #2: "Placed order" Erkennung
                # Wenn warehouse_delta = 0 ABER balance_delta negativ:
                # → Möglicherweise wurde gleichzeitig gekauft UND neue Preorder gesetzt (Netto-Delta = 0)
                # → Suche nach "Placed order" im OCR-Text um echte Menge zu ermitteln
                if self._detail_partial_balance_delta < 0 and self._detail_partial_warehouse_delta == 0:
                    # Versuche "Placed order" zu extrahieren aus dem übergebenen OCR-Text
                    placed_patterns = [
                        r'placed\s+(?:order|preorder).*?x\s*[,\s]*(\d+(?:[,\.]\d+)*)',  # "Placed order x5,000"
                        r'placed.*?(\d+(?:[,\.]\d+)*)\s*x',  # "Placed 5,000 x"
                    ]
                    
                    placed_qty = None
                    for pattern in placed_patterns:
                        m = re.search(pattern, ocr_text, re.IGNORECASE)
                        if m:
                            qty_str = m.group(1).replace(',', '').replace('.', '')
                            try:
                                placed_qty = int(qty_str)
                                if 1 <= placed_qty <= 5000:
                                    if self.debug:
                                        log_debug(f"[DETAIL] ✅ 'Placed order' detected: {placed_qty}x (warehouse_delta was 0)")
                                    # Setze warehouse_delta auf placed_qty
                                    # → Eigentlicher Kauf war: balance_delta negativ, warehouse +placed_qty
                                    self._detail_partial_warehouse_delta = placed_qty
                                    break
                            except ValueError:
                                pass
                    
                    if placed_qty is None and self.debug:
                        log_debug(f"[DETAIL] ⚠️ warehouse_delta=0 but balance negative - no 'Placed order' found, waiting...")
                
                # Prüfe ob BEIDE Deltas jetzt vorhanden sind
                if self._detail_partial_balance_delta >= 0 or self._detail_partial_warehouse_delta <= 0:
                    # BALANCE-ONLY FALLBACK DEAKTIVIERT
                    # Ohne desired_price-Extraktion können wir Quantity nicht schätzen
                    # → Warte IMMER auf warehouse_delta
                    # → Log-based parsing als Fallback für verpasste Transaktionen
                    if self.debug and (balance_delta != 0 or warehouse_delta != 0):
                        if self._detail_balance_delta_timestamp:
                            elapsed = (datetime.datetime.now() - self._detail_balance_delta_timestamp).total_seconds()
                            log_debug(f"[DETAIL] Buy-Transaction incomplete: balance_delta={self._detail_partial_balance_delta}, warehouse_delta={self._detail_partial_warehouse_delta} (waiting {elapsed:.2f}s, log-based fallback active)")
                        else:
                            log_debug(f"[DETAIL] Buy-Transaction incomplete: balance_delta={self._detail_partial_balance_delta}, warehouse_delta={self._detail_partial_warehouse_delta} (waiting for both)")
                    return None
                
                # BEIDE Deltas vorhanden → Transaction erstellen
                gross_price = abs(self._detail_partial_balance_delta)
                quantity = self._detail_partial_warehouse_delta
                
                # NEW: Apply preorder correction if provided
                if preorder_correction:
                    preorder_price = preorder_correction['price']
                    preorder_qty = preorder_correction.get('quantity_filled', preorder_correction['quantity'])
                    
                    # Calculate proportional preorder contribution
                    preorder_total_qty = preorder_correction['quantity']
                    preorder_contribution = preorder_price * (preorder_qty / preorder_total_qty)
                    
                    # Add preorder price to calculated price
                    gross_price_original = gross_price
                    gross_price = gross_price + preorder_contribution
                    
                    if self.debug:
                        log_debug(
                            f"[PREORDER-CORRECTION] Price adjusted: "
                            f"{gross_price_original:,.0f} (balance) + {preorder_contribution:,.0f} (preorder) "
                            f"= {gross_price:,.0f} Silver"
                        )
                
                transaction_type = 'buy'
                tx_case = 'buy_collect_ui_inferred'  # Detail-Window via UI-Delta-Inferenz
                
            else:
                return None
            
            # Item-Name aus Metriken holen
            item_name = current_metrics.get('item_name')
            if not item_name and last_metrics:
                item_name = last_metrics.get('item_name')
            if not item_name:
                item_name = self._detail_window_item
            if not item_name:
                if self.debug:
                    log_debug("[DETAIL] Transaction rejected: No item name available")
                return None
            
            # Validiere und korrigiere Item-Name
            corrected_result = self._safe_correct_item_name(item_name)
            if not corrected_result[0]:
                if self.debug:
                    log_debug(f"[DETAIL] Transaction rejected: Item name '{item_name}' not in whitelist")
                return None

            corrected_name = corrected_result[0]
            
            # Validiere Menge - erlaubt jetzt akkumulierte Käufe bis 500000
            MAX_SINGLE_PURCHASE = 5000
            MAX_ACCUMULATED_PURCHASE = 500000  # Akkumulierte Käufe (z.B. 100x 5000)
            
            if not (1 <= quantity <= MAX_ACCUMULATED_PURCHASE):
                if self.debug:
                    log_debug(f"[DETAIL] Transaction rejected: Invalid quantity {quantity} (max {MAX_ACCUMULATED_PURCHASE})")
                return None
            
            # Warnung bei großen akkumulierten Käufen
            if quantity > MAX_SINGLE_PURCHASE:
                estimated_purchases = quantity // MAX_SINGLE_PURCHASE
                if self.debug:
                    log_debug(f"[DETAIL] ⚠️ Accumulated purchase detected: {quantity}x ≈ {estimated_purchases} buys @ {MAX_SINGLE_PURCHASE}x each")
            
            # Erstelle Transaction-Dict
            tx_timestamp = current_metrics.get('timestamp') or datetime.datetime.now()

            transaction = {
                'item_name': corrected_name,
                'quantity': quantity,
                'price': gross_price,
                'transaction_type': transaction_type,
                'timestamp': tx_timestamp,
                'tx_case': tx_case,
                '_from_detail_window': True,  # Markierung für Deduplication
            }
            if preorder_correction:
                transaction['_preorder_auto_collect'] = preorder_correction.get('_auto_collect_estimate')

            if self.debug:
                log_debug(f"[DETAIL] ✅ Inferred transaction: {transaction_type} {quantity}x {corrected_name} @ {gross_price} Silver (total)")
                log_debug(f"[DETAIL] Transaction details: tx_case={tx_case}, from_detail_window=True, timestamp={transaction['timestamp']}")

            # Reset partial deltas nach erfolgreicher Transaktion
            self._detail_partial_balance_delta = 0
            self._detail_partial_warehouse_delta = 0
            self._detail_balance_delta_timestamp = None  # Reset timer
            
            return transaction
            
        except Exception as e:
            if self.debug:
                log_debug(f"[DETAIL] Error inferring transaction from deltas: {e}")
            return None

    def _monitor_detail_window(self, window_type: str, ocr_text: str):
        """
        Überwacht Detail-Fenster und erkennt Transaktionen durch Balance/Warehouse-Deltas.
        
        State-Machine:
        1. IDLE → Detail-Fenster erkannt → Baseline erfassen → MONITORING
        2. MONITORING → Balance/Warehouse-Änderung → TRANSACTION_DETECTED
        3. TRANSACTION_DETECTED → Transaktion speichern → Baseline updaten → MONITORING
        4. MONITORING → Timeout (5s ohne Änderung) → IDLE
        
        Args:
            window_type: 'sell_item' oder 'buy_item'
            ocr_text: Kombinierter OCR-Text (Label + Item-Name + Balance + Warehouse)
        
        Returns:
            None (speichert Transaktion direkt wenn erkannt)
        """
        now = datetime.datetime.now()
        
        # Get current frame for preorder input extraction
        img = getattr(self, '_current_frame', None)
        proc_img = getattr(self, '_current_frame_proc', None)
        
        # Extrahiere aktuelle Metriken
        current_metrics = self._extract_detail_window_metrics(ocr_text, window_type)
        
        if not current_metrics:
            # ⚡ CRITICAL FIX: If metrics extraction fails BUT we have baseline,
            # use LAST KNOWN metrics to allow delta detection with incomplete data
            if self._detail_window_active and hasattr(self, '_detail_last_metrics') and self._detail_last_metrics:
                # OCR failed but we're monitoring → Keep using last known state
                # This allows us to detect changes even if one OCR scan fails
                current_metrics = self._detail_last_metrics.copy()
                
                if self.debug:
                    log_debug(
                        f"[DETAIL] ⚠️ Metrics extraction failed → Using last known state "
                        f"(Balance={current_metrics.get('balance')}, Warehouse={current_metrics.get('warehouse_qty')})"
                    )
            else:
                # No baseline yet OR no last metrics → Can't proceed
                if self._detail_confirmation_pending and self._detail_confirmation_timestamp:
                    elapsed = (now - self._detail_confirmation_timestamp).total_seconds()
                    if elapsed > self._detail_confirmation_timeout:
                        if self.debug:
                            log_debug(f"[DETAIL] Timeout after {elapsed:.1f}s - resetting state")
                        self._reset_detail_window_state()
                return
        
        # 1. Detail-Fenster-Eintritt: Multi-Sample Baseline Capture
        if not self._detail_window_active:
            # MULTI-SAMPLE BASELINE CAPTURE (FIX: Birch Sap Issue)
            # Problem: Erster OCR-Scan kommt ~150ms nach Window-Open
            #          Game-Transaktionen passieren in 40-100ms
            #          → Warehouse bereits kontaminiert (z.B. 10000 statt 0)
            # Lösung: Nimm 3-5 schnelle Samples und wähle MINIMUM als Baseline
            #         Rationale: Wenn Warehouse wächst (0→5000→10000), ist MIN=0 die echte Baseline
            
            balance = current_metrics.get('balance')
            warehouse = current_metrics.get('warehouse_qty')
            
            # ⚡ CRITICAL FIX: Wenn warehouse=None im ERSTEN Scan nach Window-Open,
            # ist das der PERFEKTE Moment! OCR hat die Zahl noch nicht erfasst weil
            # das Window gerade erst öffnet. ASSUME 0 als Baseline!
            if balance is None:
                if self.debug:
                    log_debug(f"[DETAIL] Waiting for Balance (balance={balance}, warehouse={warehouse})")
                return
            
            if warehouse is None:
                if self.debug:
                    log_debug(f"[DETAIL] ⚡ Warehouse=None detected - PERFECT timing! Using 0 as baseline.")
                warehouse = 0  # Frame-perfect: Window just opened, warehouse not yet rendered/scanned
            
            # � CRITICAL FIX: NO multi-sampling! It's too slow (~8s) and burst-mode expires!
            # warehouse=None is ALREADY the perfect moment - use it immediately!
            samples = [{'balance': balance, 'warehouse': warehouse, 'time': datetime.datetime.now()}]
            
            # Wähle konservativste Warehouse-Menge als Baseline:
            # - Buy-Window: MIN (Warehouse wächst bei Käufen: 0→5k→10k → MIN=0)
            # - Sell-Window: MAX (Warehouse sinkt bei Verkäufen: 15k→10k→5k → MAX=15k)
            if window_type == 'buy_item':
                baseline_warehouse = min(s['warehouse'] for s in samples)
            else:  # sell_item
                baseline_warehouse = max(s['warehouse'] for s in samples)

            # Balance vom ersten Sample (sollte stabil sein)
            baseline_balance = samples[0]['balance']

            # ⚡ BASELINE SET: Nutze konservativste Warehouse-Menge
            self._detail_window_active = True
            self._detail_window_type = window_type
            self._detail_baseline_balance = baseline_balance
            self._detail_baseline_warehouse = baseline_warehouse
            raw_item_name = current_metrics.get('item_name')
            self._detail_window_item = self._normalize_detail_item_name(raw_item_name)
            self._detail_window_entry_item = raw_item_name  # Für Log-Fallback
            self._detail_ui_orders_completed = None
            if window_type == 'buy_item':
                metrics_map = getattr(self, '_last_ui_buy_metrics', {}) or {}
                lookup_key = (self._detail_window_item or raw_item_name or '').lower()
                ui_entry = metrics_map.get(lookup_key)
                if not ui_entry and lookup_key:
                    try:
                        for cached_key, cached_entry in metrics_map.items():
                            if (cached_entry.get('item') or '').lower() == lookup_key:
                                ui_entry = cached_entry
                                break
                    except Exception:
                        ui_entry = None
                if ui_entry:
                    oc_val = ui_entry.get('ordersCompleted')
                    try:
                        oc_int = int(oc_val)
                    except Exception:
                        try:
                            from parsing import normalize_numeric_str  # local import to avoid cycle
                            oc_int = normalize_numeric_str(str(oc_val))
                        except Exception:
                            oc_int = None
                    if isinstance(oc_int, int) and oc_int > 0:
                        self._detail_ui_orders_completed = oc_int
                        if self.debug:
                            log_debug(
                                f"[DETAIL] UI fallback ordersCompleted={oc_int} for '{self._detail_window_item}'"
                            )
            self._detail_baseline_captured = True
            self._detail_needs_baseline_capture = False
            self._detail_detail_snapshot_ts = datetime.datetime.now()
            self._force_detail_metric_refresh = True
            self._set_detail_metric_state("delta", "baseline_captured")

            # Reset Delta-Akkumulation
            self._detail_partial_balance_delta = 0
            self._detail_partial_warehouse_delta = 0
            self._detail_balance_delta_timestamp = None

            # ✅ CRITICAL FIX: Proaktive Input-Field-Extraktion
            # Erfasse die initialen Detail-Inputs und speichere sie getrennt als "baseline".
            self._invalidate_detail_input_cache()

            if window_type in ('buy_item', 'sell_item') and img is not None and proc_img is not None:
                purpose = "preorder" if window_type == 'buy_item' else "listing"
                self._set_need_flag('detail_inputs', True, "detail_baseline_capture")
                if self.debug:
                    log_debug(f"[DETAIL] 🔍 Extracting {purpose} input fields from baseline frame...")

                try:
                    input_fields = self._extract_preorder_input_fields(
                        img=img,
                        proc_img=proc_img,
                        window_type=window_type
                    )

                    if input_fields and 'quantity' in input_fields and 'price' in input_fields:
                        self._cache_detail_input_fields(
                            kind='baseline',
                            fields=input_fields,
                            window_type=window_type,
                            source='baseline_capture',
                            timestamp=now
                        )

                        cached_fields, _, _ = self._get_detail_input_fields(
                            window_type=window_type,
                            prefer_refresh=False
                        )
                        if cached_fields and self.debug:
                            total = cached_fields['price'] * cached_fields['quantity']
                            log_debug(
                                f"[DETAIL] ✅ {purpose.title()} baseline cached: "
                                f"{cached_fields['quantity']:,}x @ {cached_fields['price']:,} "
                                f"(total: {total:,})"
                            )
                    else:
                        self._set_need_flag('detail_inputs', True, "detail_input_incomplete")
                        if self.debug:
                            log_debug(f"[DETAIL] ⚠️ Input field extraction failed (incomplete data)")
                except Exception as e:
                    self._set_need_flag('detail_inputs', True, "detail_input_error")
                    if self.debug:
                        log_debug(f"[DETAIL] ⚠️ Input field extraction error: {e}")

            if self.debug:
                log_debug(
                    f"[DETAIL] ⚡ BASELINE CAPTURED\n"
                    f"   Window: {window_type}\n"
                    f"   Item: {self._detail_window_item}\n"
                    f"   Warehouse: {baseline_warehouse:,}\n"
                    f"   Balance: {baseline_balance:,}\n"
                    f"   🎯 Ready to detect transactions (burst-mode active for 30s @ 80ms polling)"
                )
            return
        
        # 2. Überprüfe ob Fenstertyp geändert hat (sollte nicht passieren)
        if self._detail_window_type != window_type:
            if self.debug:
                log_debug(f"[DETAIL] Window type changed from {self._detail_window_type} to {window_type} - resetting")
            self._reset_detail_window_state()
            # Rekursiv aufrufen um neue Baseline zu setzen
            self._monitor_detail_window(window_type, ocr_text)
            return
        
        # NEW (Phase 2): Post-Transaction Preorder Check
        # Check if we're waiting for a preorder placement after a successful transaction
        # This handles the case where user buys items, THEN places a new preorder
        if self._detail_await_preorder_check and window_type == 'buy_item':
            check_baseline = self._detail_preorder_check_baseline
            now = datetime.datetime.now()
            time_elapsed = (now - check_baseline['timestamp']).total_seconds()
            
            # Wait at least 0.5s for UI to settle after transaction
            if time_elapsed >= 0.5:
                # Get current metrics
                current_balance = current_metrics.get('balance')
                current_warehouse = current_metrics.get('warehouse_qty')
                
                # Check if both metrics are available
                if current_balance is not None and current_warehouse is not None:
                    # Calculate delta RELATIVE to post-transaction baseline
                    balance_delta_new = current_balance - check_baseline['balance']
                    warehouse_delta_new = current_warehouse - check_baseline['warehouse']
                    
                    # CRITICAL FIX: Accept BOTH patterns:
                    # Pattern 1: balance↓, warehouse=0 → Simple Preorder
                    # Pattern 2: balance↓, warehouse↑ → Preorder + Auto-Collect (Relist case!)
                    if balance_delta_new < 0:
                        if self.debug:
                            log_debug(
                                f"[PREORDER-CHECK] ✅ Pattern match: balance {balance_delta_new:+,}, "
                                f"warehouse {warehouse_delta_new:+} → Preorder detected!"
                            )
                        
                        # If warehouse increased, it's likely auto-collect from OLD preorder
                        if warehouse_delta_new > 0:
                            if self.debug:
                                log_debug(
                                    f"[PREORDER-CHECK] Warehouse surplus: +{warehouse_delta_new}x "
                                    "(likely auto-collect from previous preorder)"
                                )
                        
                        # Detect and store preorder
                        preorder_detected = self._detect_preorder_placement(
                            item_name=self._detail_window_item,
                            balance_delta=balance_delta_new,
                            current_metrics=current_metrics,
                            timestamp=now,
                            img=img,
                            proc_img=proc_img
                        )
                        
                        if preorder_detected:
                            # Reset check
                            self._detail_await_preorder_check = False
                            self._detail_preorder_check_baseline = None
                            
                            # Update baseline AGAIN (preorder consumed balance, auto-collect added warehouse)
                            self._detail_baseline_balance = current_balance
                            self._detail_baseline_warehouse = current_warehouse
                            self._detail_last_metrics = current_metrics.copy()
                            
                            if self.debug:
                                log_debug(
                                    f"[PREORDER-CHECK] Baseline updated after preorder: "
                                    f"Balance={current_balance:,}, Warehouse={current_warehouse:,}"
                                )
                            
                            # Return early - preorder handled
                            return
                    
                    # Timeout after 3 seconds (no preorder placed)
                    if time_elapsed > 3.0:
                        self._detail_await_preorder_check = False
                        self._detail_preorder_check_baseline = None
                        
                        if self.debug:
                            log_debug(
                                "[PREORDER-CHECK] Timeout (3s) - no preorder placement detected"
                            )
        
        # 3. Vergleiche Balance und Warehouse mit Baseline
        current_balance = current_metrics.get('balance')
        current_warehouse = current_metrics.get('warehouse_qty')
        
        # FIX #2: Prüfe ob Fenster geschlossen wurde (None-Metriken)
        # WICHTIG: Wenn baseline_warehouse=0 (warehouse=None beim Capture), toleriere warehouse=None!
        # Dies passiert in den ersten Frames nach Window-Open wenn OCR langsam ist
        if current_balance is None:
            if self.debug:
                log_debug("[DETAIL] Metrics incomplete (balance=None) - waiting for next scan")
            return
        
        if current_warehouse is None:
            # Wenn Baseline=0 gesetzt wurde (warehouse=None beim Capture), ersetze None mit 0
            if self._detail_baseline_warehouse == 0:
                current_warehouse = 0  # Same as baseline - no change detected
                if self.debug:
                    log_debug("[DETAIL] Warehouse=None (same as baseline=0) - treating as 0")
            else:
                # Warehouse should not be None if baseline != 0 → Window likely closed
                if self.debug:
                    log_debug("[DETAIL] Metrics incomplete (warehouse=None, baseline!=0) - window closed?")
                return
        
        # 4. Prüfe ob Änderung vorhanden
        balance_changed = (
            self._detail_baseline_balance is not None and
            current_balance != self._detail_baseline_balance
        )
        warehouse_changed = (
            self._detail_baseline_warehouse is not None and
            current_warehouse != self._detail_baseline_warehouse
        )
        
        if not balance_changed and not warehouse_changed:
            # Keine Änderung → Weiter warten
            # Update last_metrics für spätere Vergleiche
            self._detail_last_metrics = current_metrics

            # Delta-State: Timeout zurück nach Baseline, wenn zu lange inaktiv
            if self._detail_metric_state == "delta":
                now_idle = datetime.datetime.now()
                last_activity = self._detail_last_delta_activity
                if last_activity is None:
                    self._detail_last_delta_activity = now_idle
                else:
                    try:
                        elapsed_idle = (now_idle - last_activity).total_seconds()
                    except Exception:
                        elapsed_idle = 0.0
                    if elapsed_idle >= self.DETAIL_DELTA_IDLE_TIMEOUT:
                        if self.debug:
                            log_debug(f"[DETAIL] Delta idle for {elapsed_idle:.2f}s → fallback to baseline")
                        self._set_detail_metric_state("baseline", "delta_idle_timeout")
                        self._detail_needs_baseline_capture = True
                        self._force_detail_metric_refresh = True
                        self._detail_last_delta_activity = now_idle
                        return

            # Update Item-Name falls jetzt erkannt
            if not self._detail_window_item and current_metrics.get('item_name'):
                self._detail_window_item = self._normalize_detail_item_name(current_metrics.get('item_name'))
                if self.debug:
                    log_debug(f"[DETAIL] Item name detected: {self._detail_window_item}")
            
            # 🚀 CRITICAL: Maintain burst-mode while in detail-window!
            # We need rapid polling (80ms) to catch individual transactions
            # Normal polling (500ms+) is too slow and causes multi-transaction batching
            now = datetime.datetime.now()
            if self._burst_until is None or now >= self._burst_until:
                self._burst_until = now + datetime.timedelta(seconds=10.0)  # Keep burst active
                if self.debug:
                    log_debug(f"[DETAIL] 🚀 Burst-mode extended (rapid polling @ 80ms)")
            
            return
        
        # 5. Änderung erkannt → Transaktion verarbeiten
        
        # Track welche Werte sich SEIT LETZTEM SCAN geändert haben (für Sync-Check)
        # WICHTIG: Vergleiche mit last_metrics, nicht mit baseline!
        # Grund: Balance/Warehouse könnten sich in verschiedenen Frames updaten
        balance_changed_this_scan = False
        warehouse_changed_this_scan = False
        
        if self._detail_last_metrics:
            # Vergleiche mit letztem Scan
            last_balance = self._detail_last_metrics.get('balance')
            last_warehouse = self._detail_last_metrics.get('warehouse_qty')
            balance_changed_this_scan = (last_balance is not None and current_balance != last_balance)
            warehouse_changed_this_scan = (last_warehouse is not None and current_warehouse != last_warehouse)
        else:
            # Erster Scan nach Baseline: Prüfe nur ob überhaupt Änderung seit Baseline
            balance_changed_this_scan = balance_changed
            warehouse_changed_this_scan = warehouse_changed
        
        # Setze permanente Flags (bleiben True bis Transaktion abgeschlossen)
        if balance_changed_this_scan:
            self._detail_balance_changed_once = True
            self._force_detail_metric_refresh = True
            self._detail_last_delta_activity = datetime.datetime.now()
        if warehouse_changed_this_scan:
            self._detail_warehouse_changed_once = True
            self._force_detail_metric_refresh = True
            self._detail_last_delta_activity = datetime.datetime.now()
        
        if self.debug:
            balance_delta = current_balance - self._detail_baseline_balance if self._detail_baseline_balance is not None else 0
            warehouse_delta = current_warehouse - self._detail_baseline_warehouse if self._detail_baseline_warehouse is not None else 0
            log_debug(
                f"[DETAIL] Change detected in {window_type}\n"
                f"   Balance: {self._detail_baseline_balance} → {current_balance} (Δ {balance_delta:+,})\n"
                f"   Warehouse: {self._detail_baseline_warehouse} → {current_warehouse} (Δ {warehouse_delta:+})"
            )
        
        # 6. Berechne Deltas
        # CRITICAL FIX: Use `is not None` instead of truthy check!
        # baseline=0 is VALID and must calculate delta (e.g., 10000 - 0 = +10000)
        balance_delta = current_balance - self._detail_baseline_balance if self._detail_baseline_balance is not None else 0
        warehouse_delta = current_warehouse - self._detail_baseline_warehouse if self._detail_baseline_warehouse is not None else 0
        
        # 🔍 SYNC-CHECK: Warte bis BEIDE Werte sich geändert haben (nicht nur einer!)
        # Problem: Balance und Warehouse updaten nicht synchron (1-4 Frames verzögert)
        # Beispiel: Frame 1 hat Balance=-1.1M (Preorder) + Warehouse=+0 (noch nicht updated)
        #           Frame 2 hat Balance=-1.1M (gleich)     + Warehouse=+5339 (jetzt updated)
        # Lösung: Wenn NUR EINER sich geändert hat (nicht beide), warte auf nächsten Scan
        #         Wenn BEIDE sich geändert haben (synchron), fahre fort
        balance_and_warehouse_both_changed = (
            balance_changed_this_scan and warehouse_changed_this_scan
        )
        only_one_value_changed = (
            (balance_changed_this_scan and not warehouse_changed_this_scan) or
            (warehouse_changed_this_scan and not balance_changed_this_scan)
        )
        
        if only_one_value_changed:
            if self.debug:
                log_debug(f"[DETAIL] ⏸️ Partial update detected - only one value changed this scan")
                log_debug(f"[DETAIL]    Balance changed: {balance_changed_this_scan}, Warehouse changed: {warehouse_changed_this_scan}")
                log_debug(f"[DETAIL]    Waiting for both values to update before plausibility check...")
            # Update last_metrics trotzdem (für nächsten Scan)
            self._detail_last_metrics = current_metrics
            self._detail_last_delta_activity = datetime.datetime.now()
            return
        
        # ===== NEW: PREORDER PLACEMENT DETECTION =====
        # CRITICAL: Detect preorder when balance↓
        # This MUST happen BEFORE plausibility check to avoid false rejections
        # 
        # Two scenarios:
        # 1. Simple Preorder: balance↓, warehouse=0 (no items yet)
        # 2. Relist + Auto-Collect: balance↓, warehouse↑ (old preorder collected during relist)
        if balance_delta < 0 and window_type == 'buy_item':
            # Anforderungen an Refresh-Cache: bei Balance- oder Warehouseänderung frische Eingaben anfordern
            if balance_changed_this_scan or warehouse_changed_this_scan:
                self._request_detail_input_refresh('buy_item', 'detail_delta_detected')

            # Check if this is a preorder scenario
            # Heuristic: If warehouse increased, it's likely auto-collect from old preorder
            # In this case, the new preorder quantity should be in UI metrics
            is_simple_preorder = (warehouse_delta == 0)
            is_relist_with_autocollect = (warehouse_delta > 0)
            
            # ═══════════════════════════════════════════════════════════════
            # RELIST PATTERN DETECTION (Phase 2 Fix)
            # ═══════════════════════════════════════════════════════════════
            # Pattern: balance↓ (new preorder placed) + warehouse↑ (auto-collect from old preorder)
            # This happens when user clicks "Relist" on a partially-filled preorder
            # 
            # Expected behavior:
            # 1. Save auto-collect transaction (warehouse_delta items @ collected price)
            # 2. Mark old preorder as 'collected'
            # 3. Create new preorder with values from cached input fields
            
            relist_log_candidates: list[dict] = []
            if self._pending_log_fallback_txs:
                current_item_lc = (self._detail_window_item or '').lower()
                for pending in self._pending_log_fallback_txs:
                    if (pending.get('item_name') or '').lower() == current_item_lc:
                        relist_log_candidates.append(pending)

            autocollect_candidates = relist_log_candidates
            consume_log_fallback_entry: dict | None = None
            if is_relist_with_autocollect or autocollect_candidates:
                self._prune_pending_relist_events()
                if self.debug:
                    log_debug(
                        f"[RELIST-DETECT] ✅ Pattern matched: "
                        f"balance {balance_delta:+,} (new preorder), "
                        f"warehouse {warehouse_delta:+} (auto-collect + possible instant buy)"
                    )
                
                # ═══════════════════════════════════════════════════════════════
                # CRITICAL: Transaction-Log is ONLY visible in Overview!
                # Cannot rely on fallback - must save everything NOW in Detail-Window!
                # ═══════════════════════════════════════════════════════════════
                
                # 1. Find matching old preorder
                corrected_tuple = self._safe_correct_item_name(self._detail_window_item or "") if self._detail_window_item else (None, False)
                corrected_name = corrected_tuple[0]
                pending_key = None
                if corrected_name:
                    pending_key = corrected_name.lower()
                elif self._detail_window_item:
                    pending_key = self._detail_window_item.lower()
                pending_event = self._pending_relist_events.get(pending_key) if pending_key else None

                matching_preorder = self._preorder_manager.find_matching_preorder(
                    item_name=corrected_name or self._detail_window_item,
                    warehouse_delta=warehouse_delta,
                    balance_delta=balance_delta,
                    timestamp=datetime.datetime.now()
                )

                expected_autocollect_qty: int | None = None
                autocollect_total: int | None = None

                if not matching_preorder and autocollect_candidates:
                    fallback_entry = autocollect_candidates[-1]
                    fallback_qty = fallback_entry.get('quantity') or fallback_entry.get('quantity_filled')
                    fallback_price = fallback_entry.get('price')
                    if fallback_qty and fallback_price:
                        expected_autocollect_qty = int(fallback_qty)
                        autocollect_total = int(fallback_price)
                        matching_preorder = {
                            'id': None,
                            'item_name': corrected_name or self._detail_window_item,
                            'quantity': expected_autocollect_qty,
                            'price': autocollect_total,
                        }
                        consume_log_fallback_entry = fallback_entry
                        if self.debug:
                            log_debug(
                                f"[RELIST] ⚠️ Using log fallback for autocollect: qty={expected_autocollect_qty}, price={autocollect_total}"
                            )
                        if pending_event is not None:
                            pending_event['fallback_attached'] = True
                            pending_event['fallback_entry'] = fallback_entry
                    else:
                        if self.debug:
                            log_debug("[RELIST] ❌ Log fallback missing quantity/price – skipping autocollect")
                        if pending_event is None:
                            # Ensure we wait for future fallback data instead of aborting permanently
                            detected_at = datetime.datetime.now()
                            if pending_key:
                                self._pending_relist_events[pending_key] = {
                                    'item_name': corrected_name or self._detail_window_item,
                                    'detected_at': detected_at,
                                    'balance_delta': balance_delta,
                                    'warehouse_delta': warehouse_delta,
                                    'baseline_balance': self._detail_baseline_balance,
                                    'baseline_warehouse': self._detail_baseline_warehouse,
                                    'window_type': window_type,
                                    'metrics': current_metrics.copy(),
                                }
                                if self.debug:
                                    log_debug(
                                        f"[RELIST] ⏳ Pending relist event created for {self._detail_window_item} – awaiting fallback"
                                    )
                        return

                if not matching_preorder:
                    if pending_event is None and pending_key:
                        detected_at = datetime.datetime.now()
                        self._pending_relist_events[pending_key] = {
                            'item_name': corrected_name or self._detail_window_item,
                            'detected_at': detected_at,
                            'balance_delta': balance_delta,
                            'warehouse_delta': warehouse_delta,
                            'baseline_balance': self._detail_baseline_balance,
                            'baseline_warehouse': self._detail_baseline_warehouse,
                            'window_type': window_type,
                            'metrics': current_metrics.copy(),
                        }
                        pending_event = self._pending_relist_events.get(pending_key)
                        if self.debug:
                            log_debug(
                                f"[RELIST] ⏳ Pending relist event created for {self._detail_window_item} – waiting for log fallback"
                            )
                    else:
                        if pending_event is not None:
                            pending_event['balance_delta'] = balance_delta
                            pending_event['warehouse_delta'] = warehouse_delta
                            pending_event['metrics'] = current_metrics.copy()
                            pending_event['updated_at'] = datetime.datetime.now()
                            if pending_event.get('fallback_entry'):
                                fallback_data = pending_event['fallback_entry']
                                expected_autocollect_qty = int(fallback_data.get('quantity') or fallback_data.get('quantity_filled') or 0)
                                autocollect_total = int(fallback_data.get('price') or 0)
                                if expected_autocollect_qty > 0 and autocollect_total > 0:
                                    matching_preorder = {
                                        'id': None,
                                        'item_name': corrected_name or self._detail_window_item,
                                        'quantity': expected_autocollect_qty,
                                        'price': autocollect_total,
                                    }
                                    if self.debug:
                                        log_debug(
                                            f"[RELIST] ♻️ Using pending fallback entry for autocollect: "
                                            f"qty={expected_autocollect_qty}, price={autocollect_total}"
                                        )
                                else:
                                    fallback_data = None
                        if matching_preorder is None:
                            # Wenn trotz Fallback noch kein Match existiert und keine zusätzlichen Kandidaten vorliegen, warten wir weiter
                            if not autocollect_candidates:
                                return
                            # andernfalls geht es mit den vorhandenen Kandidaten weiter (siehe oben)
                            matching_preorder = matching_preorder  # noop für Klarheit
                        if matching_preorder is None and self.debug:
                            log_debug(f"[RELIST] ⏸️ Deferred relist handling for {self._detail_window_item} – no matching preorder yet")
                        if matching_preorder is None and not autocollect_candidates:
                            return

                # Expected auto-collect quantity from old preorder
                if expected_autocollect_qty is None:
                    qty_filled = matching_preorder.get('quantity_filled') if matching_preorder else None
                    if qty_filled and qty_filled > 0:
                        expected_autocollect_qty = int(qty_filled)
                    else:
                        expected_autocollect_qty = int(matching_preorder['quantity'])
                actual_warehouse_delta = warehouse_delta
                if actual_warehouse_delta == 0 and expected_autocollect_qty:
                    actual_warehouse_delta = expected_autocollect_qty
                instant_buy_qty = 0
                if actual_warehouse_delta > expected_autocollect_qty:
                    instant_buy_qty = actual_warehouse_delta - expected_autocollect_qty

                if autocollect_total is None:
                    preorder_unit_price = matching_preorder['price'] / matching_preorder['quantity']
                    autocollect_total = int(round(preorder_unit_price * expected_autocollect_qty))
                else:
                    preorder_unit_price = autocollect_total / expected_autocollect_qty if expected_autocollect_qty else 0
                
                if self.debug:
                    log_debug(
                        f"[RELIST] Auto-collect: {expected_autocollect_qty:,}x @ {preorder_unit_price:,.0f} "
                        f"= {autocollect_total:,.0f} Silver"
                    )
                if expected_autocollect_qty <= 0 or autocollect_total <= 0:
                    if self.debug:
                        log_debug("[RELIST] ❌ Invalid autocollect values – aborting relist handler")
                    return
                
                # 4. Save auto-collect transaction
                corrected_name, _ = self._safe_correct_item_name(self._detail_window_item)
                corrected_name = corrected_name or self._detail_window_item

                if not corrected_name:
                    if self.debug:
                        log_debug("[RELIST] ❌ Kein gültiger Item-Name für Auto-Collect ermittelbar")
                else:
                    timestamp_now = datetime.datetime.now()
                    autocollect_signature = (
                        corrected_name.lower(),
                        int(expected_autocollect_qty),
                        int(autocollect_total),
                    )

                    if self._detail_relist_autocollect_signature == autocollect_signature:
                        if self.debug:
                            log_debug(
                                f"[RELIST] 🔁 Auto-collect bereits in dieser Session gespeichert: "
                                f"{expected_autocollect_qty:,}x {corrected_name}"
                            )
                        # Baselines synchronisieren, damit keine erneuten Saves ausgelöst werden
                        self._detail_last_transaction_saved = timestamp_now
                        self._detail_baseline_balance = current_balance
                        self._detail_baseline_warehouse = current_warehouse
                        self._detail_last_metrics = current_metrics.copy()
                        if consume_log_fallback_entry and consume_log_fallback_entry in self._pending_log_fallback_txs:
                            self._pending_log_fallback_txs.remove(consume_log_fallback_entry)
                        return
                    else:
                        autocollect_tx = {
                            'item_name': corrected_name,
                            'quantity': int(expected_autocollect_qty),
                            'price': int(autocollect_total),
                            'transaction_type': 'buy',
                            'tx_case': 'buy_collect',
                            'timestamp': timestamp_now,
                            'occurrence_index': 0,
                            '_from_detail_window': True,
                            'raw_related': [
                                {
                                    'source': 'detail_relist_autocollect',
                                    'preorder_id': matching_preorder['id'],
                                    'warehouse_delta': warehouse_delta,
                                    'balance_delta': balance_delta,
                                }
                            ],
                        }

                        try:
                            saved = self.store_transaction_db(autocollect_tx)
                        except Exception as e:
                            saved = False
                            if self.debug:
                                log_debug(f"[RELIST] ❌ Auto-collect speichern fehlgeschlagen: {e}")
                        else:
                            if saved:
                                if self.debug:
                                    log_debug(
                                        f"[DETAIL] ✅ Transaction saved (auto-collect): "
                                        f"{expected_autocollect_qty:,}x {corrected_name} @ {autocollect_total:,}"
                                    )
                                if consume_log_fallback_entry and consume_log_fallback_entry in self._pending_log_fallback_txs:
                                    self._pending_log_fallback_txs.remove(consume_log_fallback_entry)
                                if matching_preorder.get('id'):
                                    marked = self._preorder_manager.mark_collected(
                                        preorder_id=matching_preorder['id'],
                                        collected_at=timestamp_now,
                                        transaction_id=None,
                                    )
                                    if not marked and self.debug:
                                        log_debug(
                                            f"[RELIST] ⚠️ Failed to mark old preorder ID={matching_preorder['id']} as collected"
                                        )
                                    elif self.debug:
                                        log_debug(
                                            f"[RELIST] ✅ Old preorder ID={matching_preorder['id']} marked collected"
                                        )
                                else:
                                    self._preorder_manager.record_legacy_preorder(
                                        item_name=corrected_name,
                                        quantity=int(expected_autocollect_qty),
                                        price=int(autocollect_total),
                                        collected_at=timestamp_now,
                                        status='collected'
                                    )
                                self._detail_relist_autocollect_signature = autocollect_signature
                                if pending_key:
                                    self._pending_relist_events.pop(pending_key, None)
                                self._detail_last_transaction_saved = timestamp_now
                                self._detail_baseline_balance = current_balance
                                self._detail_baseline_warehouse = current_warehouse
                                self._detail_last_metrics = current_metrics.copy()
                            elif self.debug:
                                log_debug(
                                    f"[RELIST] ⚠️ Auto-collect nicht gespeichert (Dedupe oder Plausibilität): "
                                    f"{expected_autocollect_qty:,}x {corrected_name}"
                                )
                
                # 5. Calculate and save NEW preorder (moved from step 6)
                # ⚠️ CRITICAL FIX: Cached Input Fields are captured TOO EARLY!
                # When Detail-Window opens, UI auto-fills with default values (e.g., 1x @ 14,100).
                # Baseline captures THOSE values BEFORE user changes them.
                # 
                # ✅ SOLUTION: Use Balance-Delta as source of truth!
                # Balance-Delta = new_preorder_total (user's actual input)
                # Warehouse-Delta = auto-collect qty + instant buy qty
                
                # Calculate new preorder from balance delta
                total_balance_decrease = abs(balance_delta)
                new_preorder_total = total_balance_decrease
                
                # If instant buy occurred, subtract its cost
                if instant_buy_qty > 0:
                    # Instant buy uses current market price
                    # We need to reverse-calculate instant buy cost
                    # Problem: We don't know instant buy price yet
                    # 
                    # Heuristic: Assume instant buy price ≈ auto-collect price (same item)
                    instant_buy_total = preorder_unit_price * instant_buy_qty
                    new_preorder_total = total_balance_decrease - instant_buy_total
                    
                    if self.debug:
                        log_debug(
                            f"[RELIST] Instant buy cost estimated: {instant_buy_qty:,}x @ "
                            f"{preorder_unit_price:,.0f} = {instant_buy_total:,.0f}"
                        )
                
                # Calculate new preorder quantity
                fallback_qty_local = locals().get('fallback_qty')
                previous_preorder_qty = None
                if matching_preorder:
                    prev_qty = matching_preorder.get('quantity')
                    if prev_qty and prev_qty > 0:
                        previous_preorder_qty = int(prev_qty)

                if fallback_qty_local and fallback_qty_local > 0:
                    new_preorder_qty = int(fallback_qty_local)
                elif previous_preorder_qty is not None:
                    new_preorder_qty = previous_preorder_qty
                else:
                    # Expected: warehouse_delta = auto-collect + instant buy
                    # So: new_preorder_qty = original qty (same as auto-collected qty if no instant buy)
                    new_preorder_qty = expected_autocollect_qty - instant_buy_qty
                
                if new_preorder_qty <= 0:
                    if self.debug:
                        log_debug(f"[RELIST] No new preorder needed (instant buy filled everything)")
                else:
                    # Verify new_preorder_total is reasonable
                    if new_preorder_total > 0:
                        try:
                            preorder_timestamp = current_metrics.get('timestamp') or datetime.datetime.now()

                            # Primär: Verwende ROI-Cache falls aktuell verfügbar (max 3s alt)
                            metrics_qty = None
                            metrics_price = None
                            cached_fields, cached_ts, cached_kind = self._get_detail_input_fields(
                                window_type='buy_item',
                                prefer_refresh=True,
                                max_age_override=3.0,
                            )
                            if cached_fields and cached_ts:
                                try:
                                    cand_qty = int(cached_fields.get('quantity'))
                                    if cand_qty > 0:
                                        metrics_qty = cand_qty
                                except Exception:
                                    metrics_qty = None
                                try:
                                    cand_price = int(cached_fields.get('price'))
                                    if cand_price > 0:
                                        metrics_price = cand_price
                                except Exception:
                                    metrics_price = None
                                if self.debug and metrics_qty and metrics_price:
                                    age = (timestamp_now - cached_ts).total_seconds()
                                    log_debug(
                                        f"[RELIST] Using {cached_kind} input cache for new preorder: "
                                        f"qty={metrics_qty:,}, price={metrics_price:,} (age={age:.1f}s)"
                                    )

                            if metrics_qty and metrics_price:
                                new_preorder_qty = metrics_qty
                                new_preorder_unit_price = metrics_price
                                new_preorder_total = new_preorder_qty * new_preorder_unit_price
                                if self.debug:
                                    log_debug(
                                        f"[RELIST] ROI cache reused for new preorder: "
                                        f"{new_preorder_qty:,}x @ {new_preorder_unit_price:,}"
                                    )
                            else:
                                new_preorder_unit_price = new_preorder_total / new_preorder_qty if new_preorder_qty > 0 else 0

                            dedupe_key = (
                                corrected_name.lower(),
                                int(new_preorder_qty),
                                int(round(new_preorder_unit_price)) if new_preorder_unit_price else 0,
                                int(round(new_preorder_total))
                            )
                            now_ts = datetime.datetime.now().timestamp()
                            self._recent_preorder_hashes = {
                                k: v for k, v in self._recent_preorder_hashes.items()
                                if (now_ts - v) < self._recent_preorder_ttl
                            }
                            last_seen = self._recent_preorder_hashes.get(dedupe_key)

                            if last_seen and (now_ts - last_seen) < self._recent_preorder_ttl:
                                if self.debug:
                                    log_debug(
                                        f"[RELIST] Duplicate detected within 2s for {corrected_name} "
                                        f"x{new_preorder_qty} @ {new_preorder_unit_price:,.0f} (total {new_preorder_total:,.0f}) – skipping store"
                                    )
                            else:
                                self._capture_detail_debug_images('relist_new_preorder', img, proc_img)
                                relist_signature = (
                                    corrected_name.lower(),
                                    int(new_preorder_qty),
                                    int(round(new_preorder_total))
                                )

                                if self._detail_relist_new_preorder_signature == relist_signature:
                                    if self.debug:
                                        log_debug(
                                            f"[RELIST] 🔁 New preorder already stored this session: "
                                            f"{new_preorder_qty:,}x {corrected_name}"
                                        )
                                else:
                                    self._capture_detail_debug_images('relist_new_preorder', img, proc_img)
                                    preorder_id = self._preorder_manager.store_preorder(
                                        item_name=corrected_name,
                                        quantity=new_preorder_qty,
                                        price=new_preorder_total,
                                        timestamp=preorder_timestamp
                                    )
                                    if preorder_id > 0:
                                        now_saved = datetime.datetime.now()
                                        self._recent_preorder_hashes[dedupe_key] = now_ts
                                        self._detail_relist_new_preorder_signature = relist_signature
                                        self._detail_last_transaction_saved = now_saved
                                        self._detail_baseline_balance = current_balance
                                        self._detail_baseline_warehouse = current_warehouse
                                        self._detail_last_metrics = current_metrics.copy()
                                        self._detail_partial_balance_delta = 0
                                        self._detail_partial_warehouse_delta = 0
                                        self._detail_balance_changed_once = False
                                        self._detail_warehouse_changed_once = False
                                        self._cache_detail_input_fields(
                                            kind='refresh',
                                            fields={'quantity': int(new_preorder_qty), 'price': int(new_preorder_unit_price)},
                                            window_type='buy_item',
                                            source='relist_new_preorder_saved',
                                            timestamp=now_saved,
                                        )
                                        self._set_need_flag('detail_inputs', False, 'relist_new_preorder_saved')


                            if self.debug:
                                log_debug(
                                    f"[RELIST] ✅ New preorder saved: {new_preorder_qty:,}x @ "
                                    f"{new_preorder_unit_price:,.0f} = {new_preorder_total:,.0f}"
                                )
                        
                        except Exception as e:
                            if self.debug:
                                log_debug(f"[RELIST] ❌ Failed to save new preorder: {e}")
                    else:
                        if self.debug:
                            log_debug(f"[RELIST] ❌ Invalid new preorder total: {new_preorder_total:,}")
                
                # Save instant buy transaction (if any)
                instant_buy_total = 0
                if instant_buy_qty > 0:
                    instant_buy_total = int(round(preorder_unit_price * instant_buy_qty)) if preorder_unit_price > 0 else 0
                    new_preorder_total = max(total_balance_decrease - instant_buy_total, 0)

                if instant_buy_qty > 0 and instant_buy_total > 0:
                    
                    if instant_buy_total > 0:
                        instant_signature = (
                            (corrected_name or (self._detail_window_item or "")).lower(),
                            int(instant_buy_qty),
                            int(instant_buy_total),
                        )
                        if self._detail_relist_instant_signature == instant_signature:
                            if self.debug:
                                log_debug(
                                    f"[RELIST] 🔁 Instant-Buy bereits gespeichert: "
                                    f"{instant_buy_qty:,}x {corrected_name}"
                                )
                        else:
                            instant_buy_tx = {
                                'item_name': corrected_name,
                                'quantity': int(instant_buy_qty),
                                'price': int(instant_buy_total),
                                'transaction_type': 'buy',
                                'tx_case': 'buy_collect_instant',
                                'timestamp': datetime.datetime.now(),
                                'occurrence_index': 0,
                                '_from_detail_window': True,
                                'raw_related': [
                                    {
                                        'source': 'detail_relist_instant',
                                        'warehouse_delta': warehouse_delta,
                                        'balance_delta': balance_delta,
                                    }
                                ],
                            }

                            try:
                                saved_instant = self.store_transaction_db(instant_buy_tx)
                            except Exception as e:
                                saved_instant = False
                                if self.debug:
                                    log_debug(f"[RELIST] ❌ Instant-Buy speichern fehlgeschlagen: {e}")
                            else:
                                if saved_instant:
                                    if self.debug:
                                        log_debug(
                                            f"[DETAIL] ✅ Transaction saved (instant buy): "
                                            f"{instant_buy_qty:,}x {corrected_name} @ {instant_buy_total:,}"
                                        )
                                    self._detail_relist_instant_signature = instant_signature
                                    self._detail_last_transaction_saved = datetime.datetime.now()
                                elif self.debug:
                                    log_debug(
                                        f"[RELIST] ⚠️ Instant-Buy nicht gespeichert (Dedupe oder Plausibilität): "
                                        f"{instant_buy_qty:,}x {corrected_name}"
                                    )
                
                # ✅ Update last metrics to prevent duplicate detection
                self._detail_last_metrics = current_metrics.copy()
                
                # All done - return to avoid duplicate processing
                return
            
            if is_simple_preorder or is_relist_with_autocollect:
                if self.debug and is_relist_with_autocollect:
                    log_debug(
                        f"[PREORDER-CHECK] Possible relist with auto-collect: "
                        f"balance {balance_delta:+,}, warehouse {warehouse_delta:+}"
                    )
                
                # Attempt preorder detection
                preorder_detected = self._detect_preorder_placement(
                    item_name=self._detail_window_item,
                    balance_delta=balance_delta,
                    current_metrics=current_metrics,
                    timestamp=datetime.datetime.now(),
                    img=img,
                    proc_img=proc_img
                )
                
                if preorder_detected:
                    # IMPORTANT: Update rolling baseline for next transaction
                    self._detail_baseline_balance = current_balance
                    self._detail_baseline_warehouse = current_warehouse
                    self._detail_last_metrics = current_metrics.copy()
                    
                    # Reset delta accumulators
                    self._detail_partial_balance_delta = 0
                    self._detail_partial_warehouse_delta = 0
                    self._detail_balance_changed_once = False
                    self._detail_warehouse_changed_once = False
                    
                    if self.debug:
                        log_debug(
                            f"[PREORDER-PLACED] Rolling baseline updated after preorder placement "
                            f"(balance={current_metrics.get('balance'):,.0f}, "
                            f"warehouse={current_metrics.get('warehouse_qty'):,})"
                        )
                    
                    # CRITICAL: Return early - no transaction to infer yet
                    return
        # ===== END PREORDER PLACEMENT DETECTION =====
        
        # ===== NEW: LISTING PLACEMENT DETECTION =====
        # CRITICAL: Detect listing when balance unchanged (balance_delta ≈ 0) but warehouse↓
        # This MUST happen BEFORE plausibility check to avoid false rejections
        # Sell-side analog to preorder placement: items moved TO market, no silver received yet
        if abs(balance_delta) < 1000 and warehouse_delta < 0 and window_type == 'sell_item':
            self._request_detail_input_refresh('sell_item', 'listing_delta_detected')
            cached_fields, cached_ts, cached_kind = self._get_detail_input_fields(
                window_type='sell_item',
                prefer_refresh=True,
                max_age_override=3.0,
            )
            # Listing placement detected!
            listing_detected = self._detect_listing_placement(
                item_name=self._detail_window_item,
                warehouse_delta=warehouse_delta,
                current_metrics=current_metrics,
                timestamp=datetime.datetime.now(),
                img=img,
                proc_img=proc_img,
                cached_input=cached_fields,
                cached_timestamp=cached_ts
            )

            if listing_detected:
                # IMPORTANT: Update rolling baseline for next transaction
                self._detail_baseline_balance = current_balance
                self._detail_baseline_warehouse = current_warehouse
                self._detail_last_metrics = current_metrics.copy()

                # Verbrauchte Refresh-Werte nach erfolgreichem Listing zurücksetzen
                self._invalidate_detail_input_cache('refresh')
                
                # Reset delta accumulators
                self._detail_partial_balance_delta = 0
                self._detail_partial_warehouse_delta = 0
                self._detail_balance_changed_once = False
                self._detail_warehouse_changed_once = False
                
                if self.debug:
                    log_debug(
                        f"[LISTING-PLACED] Rolling baseline updated after listing placement "
                        f"(warehouse={current_metrics.get('warehouse_qty'):,})"
                    )
                
                # CRITICAL: Return early - no transaction to infer yet
                return
        # ===== END LISTING PLACEMENT DETECTION =====
        
        # 🔍 PLAUSIBILITY CHECK: Validate balance_delta vs warehouse_delta
        # Prevent OCR errors from creating invalid transactions
        # Example: OCR reads "169,682,222,830" instead of "169,671,122,830" (missing leading "1")
        # This causes balance_delta = -369k instead of -11.4M for a 5002x purchase
        if warehouse_delta != 0 and balance_delta != 0:
            # Get item name for base price lookup
            # CRITICAL: Use _detail_window_item (from baseline capture) instead of current_metrics
            # Reason: OCR can corrupt item name during transaction (e.g., "Birch Sap" → "Sap Birch '43,180")
            # _detail_window_item is captured at window entry when OCR is cleaner
            item_name = self._detail_window_item or current_metrics.get('item_name')
            
            # Get base price for this item (±15% tolerance)
            base_price = None
            if item_name:
                try:
                    base_price = self._get_base_price(item_name)
                except Exception as e:
                    if self.debug:
                        log_debug(f"[DETAIL] ⚠️ Failed to get base price for '{item_name}': {e}")
            
            # Calculate price range based on base_price ±15%
            tolerance = 0.15
            if base_price and base_price > 0:
                min_price_per_item = int(base_price * (1 - tolerance))
                max_price_per_item = int(base_price * (1 + tolerance))
                
                # For sell transactions, apply tax factor (net proceeds = 88.725% of sale price)
                if window_type == 'sell_item':
                    min_price_per_item = int(min_price_per_item * MARKET_SELL_NET_FACTOR)
                    max_price_per_item = int(max_price_per_item * MARKET_SELL_NET_FACTOR)
            else:
                # Fallback: Use reasonable min/max bounds if base_price unavailable
                min_price_per_item = 100
                max_price_per_item = 1_000_000_000_000  # 1T per item (theoretical max)
            
            if window_type == 'buy_item':
                # Buy: balance should DECREASE (negative delta)
                # warehouse should INCREASE (positive delta)
                if balance_delta > 0:
                    if self.debug:
                        log_debug(f"[DETAIL] ⚠️ PLAUSIBILITY FAIL: Buy with positive balance_delta={balance_delta:+,} - OCR error likely!")
                        log_debug(f"[DETAIL] Waiting for next scan with correct balance...")
                    return
                if warehouse_delta < 0:
                    if self.debug:
                        log_debug(f"[DETAIL] ⚠️ PLAUSIBILITY FAIL: Buy with negative warehouse_delta={warehouse_delta:+,} - OCR error likely!")
                        log_debug(f"[DETAIL] Waiting for next scan with correct warehouse...")
                    return
                
                # NEW (Phase 3): Check for warehouse surplus BEFORE price check
                # If warehouse increased MORE than expected from balance, it might be preorder auto-collect
                expected_qty = self._calculate_expected_qty(abs(balance_delta), item_name)
                warehouse_surplus = warehouse_delta - expected_qty
                
                # CRITICAL FIX: Always use expected_qty for plausibility check when surplus detected
                # The surplus is likely from preorder auto-collect, which shouldn't affect price validation
                if warehouse_surplus > 0 and expected_qty > 0:
                    # Use expected_qty (purchase amount) for price check, NOT total warehouse_delta
                    effective_qty_for_price_check = expected_qty
                    
                    # Try to find matching preorder for the surplus
                    preorder = self._preorder_manager.find_matching_preorder(
                        item_name=item_name,
                        warehouse_delta=warehouse_surplus,
                        balance_delta=abs(balance_delta),
                        timestamp=datetime.datetime.now()
                    )
                    
                    if preorder:
                        if self.debug:
                            log_debug(
                                f"[PREORDER-AUTOCOLLECT] Warehouse surplus detected: "
                                f"{warehouse_surplus}x (expected {expected_qty}x, actual {warehouse_delta}x)"
                            )
                            log_debug(
                                f"[PREORDER-AUTOCOLLECT] Matched preorder ID={preorder['id']}: "
                                f"{preorder['quantity']}x @ {preorder['price']:,.0f} Silver"
                            )
                            log_debug(
                                f"[PREORDER-AUTOCOLLECT] Adjusting plausibility check: "
                                f"effective_qty={effective_qty_for_price_check}x (purchase only)"
                            )
                    else:
                        if self.debug:
                            log_debug(
                                f"[PREORDER-AUTOCOLLECT] Warehouse surplus detected: "
                                f"{warehouse_surplus}x (expected {expected_qty}x from balance, actual {warehouse_delta}x)"
                            )
                            log_debug(
                                f"[PREORDER-AUTOCOLLECT] No matching preorder found, but using expected_qty "
                                f"for price check (surplus likely from auto-collect)"
                            )
                else:
                    # No surplus - normal purchase
                    effective_qty_for_price_check = warehouse_delta
                
                # Check price per item is within base_price ±15%
                # Use effective_qty (which might be adjusted for preorder surplus)
                implied_price_per_item = abs(balance_delta) / abs(effective_qty_for_price_check)
                if implied_price_per_item < min_price_per_item:
                    if self.debug:
                        log_debug(f"[DETAIL] ⚠️ PLAUSIBILITY FAIL: Implied price {implied_price_per_item:.0f} < {min_price_per_item:,} Silver/item")
                        if base_price:
                            log_debug(f"[DETAIL] Item '{item_name}': base_price={base_price:,} (range: {min_price_per_item:,} - {max_price_per_item:,})")
                        log_debug(f"[DETAIL] balance_delta={balance_delta:,}, warehouse_delta={warehouse_delta:+,}, effective_qty={effective_qty_for_price_check}")
                        log_debug(f"[DETAIL] Likely OCR error in balance - waiting for next scan...")
                    return
                if implied_price_per_item > max_price_per_item:
                    if self.debug:
                        log_debug(f"[DETAIL] ⚠️ PLAUSIBILITY FAIL: Implied price {implied_price_per_item:,.0f} > {max_price_per_item:,} Silver/item")
                        if base_price:
                            log_debug(f"[DETAIL] Item '{item_name}': base_price={base_price:,} (range: {min_price_per_item:,} - {max_price_per_item:,})")
                        log_debug(f"[DETAIL] balance_delta={balance_delta:,}, warehouse_delta={warehouse_delta:+,}, effective_qty={effective_qty_for_price_check}")
                        log_debug(f"[DETAIL] Likely OCR error in balance - waiting for next scan...")
                    return
            
            elif window_type == 'sell_item':
                # Sell: balance should INCREASE (positive delta)
                # warehouse should DECREASE (negative delta)
                if balance_delta < 0:
                    if self.debug:
                        log_debug(f"[DETAIL] ⚠️ PLAUSIBILITY FAIL: Sell with negative balance_delta={balance_delta:+,} - OCR error likely!")
                        log_debug(f"[DETAIL] Waiting for next scan with correct balance...")
                    return
                if warehouse_delta > 0:
                    if self.debug:
                        log_debug(f"[DETAIL] ⚠️ PLAUSIBILITY FAIL: Sell with positive warehouse_delta={warehouse_delta:+,} - OCR error likely!")
                        log_debug(f"[DETAIL] Waiting for next scan with correct warehouse...")
                    return
                
                # Check price per item is within base_price ±15% (after tax)
                implied_price_per_item = abs(balance_delta) / abs(warehouse_delta)
                if implied_price_per_item < min_price_per_item:
                    if self.debug:
                        log_debug(f"[DETAIL] ⚠️ PLAUSIBILITY FAIL: Implied price {implied_price_per_item:.0f} < {min_price_per_item:,} Silver/item (net)")
                        if base_price:
                            log_debug(f"[DETAIL] Item '{item_name}': base_price={base_price:,}, net_range={min_price_per_item:,} - {max_price_per_item:,}")
                        log_debug(f"[DETAIL] balance_delta={balance_delta:,}, warehouse_delta={warehouse_delta:+,}")
                        log_debug(f"[DETAIL] Likely OCR error in balance - waiting for next scan...")
                    return
                if implied_price_per_item > max_price_per_item:
                    if self.debug:
                        log_debug(f"[DETAIL] ⚠️ PLAUSIBILITY FAIL: Implied price {implied_price_per_item:,.0f} > {max_price_per_item:,} Silver/item (net)")
                        if base_price:
                            log_debug(f"[DETAIL] Item '{item_name}': base_price={base_price:,}, net_range={min_price_per_item:,} - {max_price_per_item:,}")
                        log_debug(f"[DETAIL] balance_delta={balance_delta:,}, warehouse_delta={warehouse_delta:+,}")
        # NEW: Check for preorder auto-collect scenario (BEFORE transaction inference)
        preorder_correction = None
        if window_type == 'buy_item' and warehouse_delta > 0 and balance_delta < 0:
            detail_item = self._detail_window_item or current_metrics.get('item_name')

            fallback_unit_price = None
            fallback_qty = None
            fallback_autocollect_qty = self._detail_ui_orders_completed
            cached_fields, cached_ts, cached_kind = self._get_detail_input_fields(
                window_type='buy_item',
                prefer_refresh=True,
                max_age_override=5.0,
            )
            if cached_fields and cached_ts:
                cache_age = (datetime.datetime.now() - cached_ts).total_seconds()
                try:
                    fallback_unit_price = int(cached_fields.get('price'))
                except Exception:
                    fallback_unit_price = None
                try:
                    fallback_qty = int(cached_fields.get('quantity'))
                except Exception:
                    fallback_qty = None
                if self.debug and (fallback_unit_price or fallback_qty):
                    log_debug(
                        f"[PREORDER-CHECK] Using {cached_kind} cache for fallback values (age={cache_age:.1f}s): "
                        f"qty={fallback_qty}, price={fallback_unit_price}"
                    )
            preorder_correction = self._check_for_preorder_autocollect(
                item_name=detail_item,
                warehouse_delta=warehouse_delta,
                balance_delta=balance_delta,
                timestamp=datetime.datetime.now(),
                fallback_unit_price=fallback_unit_price,
                fallback_qty=fallback_qty,
                fallback_autocollect_qty=fallback_autocollect_qty,
            )

            if preorder_correction and self.debug:
                qty_display = preorder_correction.get('quantity_filled')
                if not qty_display or qty_display <= 0:
                    qty_display = preorder_correction['quantity']
                log_debug(
                    f"[PREORDER-AUTOCOLLECT] Detected: {detail_item} "
                    f"x{qty_display:,} @ {preorder_correction['price']:,.0f} Silver"
                )

        # 7. Bestimme Transaktionstyp und -werte
        transaction = self._infer_transaction_from_deltas(
            window_type,
            balance_delta,
            warehouse_delta,
            current_metrics,
            self._detail_last_metrics or {},
            ocr_text,  # Übergebe OCR-Text für "Placed order" Detection
            preorder_correction=preorder_correction  # NEW: Pass preorder data
        )
        
        if transaction:
            # 8. Speichere Transaktion
            success = self.store_transaction_db(transaction)
            if success and self.debug:
                log_debug(f"[DETAIL] ✅ Transaction saved successfully")
            elif not success and self.debug:
                log_debug(f"[DETAIL] ⚠️ Transaction not saved (duplicate or error)")
            
            # NEW: Mark preorder as collected if this transaction included preorder auto-collect
            if success and preorder_correction:
                self._preorder_manager.mark_collected(
                    preorder_id=preorder_correction['id'],
                    collected_at=transaction['timestamp'],
                    transaction_id=transaction.get('db_id')
                )

                if self.debug:
                    log_debug(
                        f"[PREORDER-COLLECTED] Marked preorder ID={preorder_correction['id']} "
                        "as collected"
                    )
            
            # Reset Partial-Deltas für nächste Transaktion
            # WICHTIG: pending_collect_qty wird NICHT hier resetted, nur in _infer_transaction_from_deltas
            # wenn es tatsächlich kombiniert wurde
            self._detail_partial_balance_delta = 0
            self._detail_partial_warehouse_delta = 0
            self._detail_balance_delta_timestamp = None
            
            # Reset Sync-Flags für nächste Transaktion
            self._detail_balance_changed_once = False
            self._detail_warehouse_changed_once = False
            
            # 9. Update Rolling Baseline AFTER successful transaction
            # This ensures each subsequent transaction is measured from the NEW state
            self._detail_baseline_balance = current_balance
            self._detail_baseline_warehouse = current_warehouse
            if self.debug:
                log_debug(f"[DETAIL] 🔄 Rolling baseline updated: Balance={current_balance:,}, Warehouse={current_warehouse:,}")
            
            # NEW (Phase 2): Setup Preorder Check after successful transaction
            # Wait 0.5s, then check if balance decreased again WITHOUT warehouse change
            # This detects new preorder placements that happen AFTER a purchase
            if window_type == 'buy_item':
                self._detail_await_preorder_check = True
                self._detail_preorder_check_baseline = {
                    'balance': current_balance,
                    'warehouse': current_warehouse,
                    'timestamp': datetime.datetime.now()
                }
                self._detail_last_transaction_saved = datetime.datetime.now()
                
                if self.debug:
                    log_debug(
                        "[PREORDER-CHECK] Waiting for possible preorder placement "
                        "(will check in 0.5s if balance decreased without warehouse change)"
                    )
        
        # ALWAYS update last_metrics, even if transaction failed
        self._detail_last_metrics = current_metrics
        self._detail_confirmation_pending = False
        # Allow cache reuse after deltas settled
        if self._force_detail_metric_refresh and not self._detail_window_active:
            self._force_detail_metric_refresh = False

    def process_ocr_text(self, full_text):
        """
        Hauptfunktion:
        - split in entries per timestamp
        - extrahiere details pro entry
        - gruppiere transaction entries mit listed/withdrew bei gleichem timestamp (oder nahe)
        - bestimme finalen case (collect / relist_full / relist_partial)
        - speichere nur neue Transaktionen (neue im Vergleich zur letzten OCR-Ausgabe)

        === ROI-FLAG-KONSUMENTEN (Phase 1 Logging) ===

        `_needs_log_text`
            Gesetzt: bei Overview-Fenstern oder wenn kein Label erkannt wird.
            Verwendet: Scan-Pipeline entscheidet, ob Log-ROI erneut OCR benötigt.
            Zurückgesetzt: nach erfolgreichem Log-OCR oder wenn Detail-Fenster aktiv ist.

        `_needs_metrics_text`
            Gesetzt: durch `_schedule_metrics_refresh()` (Fensterwechsel, UI-Inferenz, Burst-Scans).
            Verwendet: Metrics-ROI wird nur bei aktivem Flag evaluiert.
            Zurückgesetzt: nach erfolgreichem Metrics-OCR oder bei drei aufeinanderfolgenden Fehlschlägen.

        `_needs_detail_balance` / `_needs_detail_warehouse`
            Gesetzt: `_set_detail_metric_state("baseline")` oder Burst-Scans im Detail-Fenster.
            Verwendet: Detail-ROI-OCR nur bei aktivem Flag, sonst Cache/Skip.
            Zurückgesetzt: `_set_detail_metric_state("idle")` oder nach erfolgreichem Detail-OCR.

        `_needs_detail_inputs`
            Gesetzt: während Baseline in Buy-Detailfenstern oder bei Preorder/Listing-Erkennung.
            Verwendet: `_extract_preorder_input_fields` führt OCR nur bei aktivem Flag aus.
            Zurückgesetzt: nach erfolgreichem Input-OCR.

        Diese Dokumentation dient als Referenz für Phase-1-Instrumentierung. Funktionales Verhalten
        bleibt unverändert, bis die nachfolgenden Phasen die Flags produktiv einsetzen.
        """
        
        if not full_text or not full_text.strip():
            return

        # Fenster-Typ erkennen und State updaten
        prev_window = self.current_window
        detected_wtype = detect_window_type(full_text)
        if detected_wtype == "unknown":
            detail_hint_type = self._detail_window_hint or getattr(self, "_detail_window_type", None)
            if detail_hint_type in ("buy_item", "sell_item"):
                detected_wtype = detail_hint_type
                if self.debug:
                    log_debug(f"[WINDOW] Fallback to detail hint → {detected_wtype}")
        now = datetime.datetime.now()
        
        # HYSTERESIS: Require 2 consecutive same detections before accepting transition
        # EXCEPTION: Detail-windows (buy_item/sell_item) need IMMEDIATE transition!
        # Reason: Transactions happen within 40-100ms, hysteresis delay (~150ms) misses them
        is_detail_window = detected_wtype in ("buy_item", "sell_item")
        
        self._window_detection_history.append(detected_wtype)
        if len(self._window_detection_history) > 3:
            self._window_detection_history = self._window_detection_history[-3:]
        
        history_len = len(self._window_detection_history)
        last_two_same = (
            history_len >= 2 and
            self._window_detection_history[-1] == self._window_detection_history[-2]
        )
        detail_oscillation = (
            history_len == 3 and
            self._window_detection_history[0] in ("buy_item", "sell_item") and
            self._window_detection_history[1] in ("buy_overview", "sell_overview") and
            self._window_detection_history[2] == self._window_detection_history[0]
        )

        if is_detail_window or last_two_same or detail_oscillation:
            wtype = self._window_detection_history[-1]
            if detail_oscillation:
                # auf Overview zwingen, damit Log/OCR wieder aktiv wird
                wtype = self._window_detection_history[1]
                self._set_need_flag('detail_balance', True, "detail_window_oscillation")
                self._set_need_flag('detail_warehouse', True, "detail_window_oscillation")
            if wtype != self._stable_window:
                if self.debug:
                    transition_type = "IMMEDIATE" if is_detail_window else "Stable"
                    if detail_oscillation:
                        transition_type = "FORCED"
                    log_debug(f"[WINDOW-HYSTERESIS] {transition_type} transition confirmed: {self._stable_window} → {wtype}")
                self._stable_window = wtype
        else:
            wtype = self._stable_window if self._stable_window != 'unknown' else detected_wtype
            if self.debug:
                log_debug(f"[WINDOW-HYSTERESIS] Unstable detection {detected_wtype}, using stable state {wtype}")
        
        self.current_window = wtype
        self.window_history.append((now, wtype))
        if len(self.window_history) > 5:
            self.window_history = self.window_history[-5:]
        
        # Log window transitions
        if self.debug and prev_window != wtype:
            log_debug(f"[WINDOW] Transition: {prev_window} → {wtype}")
        if prev_window != wtype:
            # ⚡ Frame-Perfect Baseline Capture: Bei Transition zu Detail-Window
            if wtype in ("buy_item", "sell_item"):
                # CRITICAL: Reset kompletten Detail-Window State bei neuer Transition!
                # Sonst bleibt alte Baseline aktiv (z.B. warehouse=6870 von vorherigem Item)
                self._reset_detail_window_state()
                self._set_detail_metric_state("baseline", "detail_window_entered")
                
                self._detail_needs_baseline_capture = True
                self._detail_baseline_captured = False
                # 🚨 CRITICAL: Force IMMEDIATE rescan to capture baseline BEFORE first transaction
                # Normal polling (150ms) is too slow - transactions happen within 40-100ms!
                self._request_immediate_rescan = 3  # 3 rapid scans @ ~40ms intervals
                if self.debug:
                    log_debug(f"[DETAIL] ⚡ Baseline capture scheduled with IMMEDIATE rescan (3x rapid)")
            
            # RATE-LIMITING: Only set refresh flag if enough time has passed
            # or if we're in a burst scan (which overrides rate limits)
            time_since_last_refresh = None
            if self._last_metrics_refresh_time is not None:
                time_since_last_refresh = (now - self._last_metrics_refresh_time).total_seconds()
            
            is_burst = (self._burst_until and now < self._burst_until) or self._request_immediate_rescan > 0
            
            if is_burst or time_since_last_refresh is None or time_since_last_refresh >= 1.0:
                self._pending_metrics_refresh = True
                if self.debug:
                    log_debug(f"[METRICS-REFRESH] Scheduled on window transition (burst={is_burst}, time_since_last={time_since_last_refresh}s)")
            else:
                if self.debug:
                    log_debug(f"[METRICS-REFRESH] Skipped due to rate-limiting (time_since_last={time_since_last_refresh:.2f}s < 1.0s)")
            
            # ROI-DIFFING: Reset Signaturen bei Fensterwechsel; Skip-Counter nur für betroffene ROIs zurücksetzen
            self._last_roi_signatures = {"log": None, "label": None, "metrics": None}
            for key in self._roi_skip_counters:
                self._roi_skip_counters[key] = 0
            if self.debug:
                log_debug("[ROI-STATS] Signatures reset due to window transition")
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
            # Detail-Window-Monitoring: Überwache Balance/Warehouse-Deltas
            if wtype in ("buy_item", "sell_item"):
                # Aktiviere Detail-Window-Monitoring
                self._monitor_detail_window(wtype, full_text)

                
                # 🚀 CRITICAL FIX: Extended burst duration for detail-window monitoring
                # Must stay active during baseline capture AND subsequent transaction monitoring
                # User can make multiple purchases within seconds - need 80ms polling throughout
                self._burst_until = now + datetime.timedelta(seconds=30.0)  # Was 4.0, now 30.0
                self._burst_source = 'item_window'
                # schedule multiple immediate fast scans
                self._burst_fast_scans = max(self._burst_fast_scans, 5)
                # also request immediate re-scans from single_scan (no wait)
                self._request_immediate_rescan = max(self._request_immediate_rescan, 2)
                # Flags aktiv lassen, bis erste verlässliche Deltas erfasst wurden
                self._set_need_flag('detail_balance', True, "detail_window_active")
                self._set_need_flag('detail_warehouse', True, "detail_window_active")
                self._buffer_detail_log_snapshot(
                    text=self._latest_log_text,
                    source_window=wtype,
                    captured_at=now,
                    prev_window=prev_window,
                )
                if self.debug:
                    log_debug(f"[BURST] 🚀 Detail-window burst enabled until {self._burst_until} (+{self._burst_fast_scans} fast scans, 80ms polling)")

            else:
                # Nicht in Detail-Fenster → Reset State
                if self._detail_window_active:
                    # ═══════════════════════════════════════════════════════════════
                    # REMOVED: RELIST DETECTION AT WINDOW EXIT
                    # ═══════════════════════════════════════════════════════════════
                    # This block was DISABLED because:
                    # 1. Cached Input Fields captured TOO EARLY (at window open with auto-fill values)
                    # 2. Caused duplicate preorder creation with WRONG prices
                    # 3. Relist detection now handled CORRECTLY in Detail-Window delta block (L3856-4093)
                    #    using Balance-Delta as source of truth instead of cached fields
                    
                    # OLD LOGIC (DISABLED):
                    # if (hasattr(self, '_detail_cached_input_fields') and 
                    #     self._detail_window_type == 'buy_item'):
                    #     ... create preorder from cached fields ...
                    
                    # ═══════════════════════════════════════════════════════════════
                    # PHASE 3: Transaction-Log Fallback (BACKUP ONLY)
                    # ═══════════════════════════════════════════════════════════════
                    # This is a FALLBACK for cases where Detail-Window closed too fast
                    # Primary detection happens in Detail-Window (relist block above)
                    # Only parse overview log if it's still visible
                    
                    if hasattr(self, '_detail_window_entry_item') and self._detail_window_entry_item and wtype in ('buy_overview', 'sell_overview'):
                        item_escaped = re.escape(self._detail_window_entry_item)
                        corrected_name, _ = self._safe_correct_item_name(self._detail_window_entry_item)
                        corrected_name = corrected_name or self._detail_window_entry_item
                        
                        # Check for "Transaction of" (auto-collect) - only if not already saved
                        pattern_transaction = (
                            rf"Transaction\s+of\s+{item_escaped}\s+[xX]?(\d[\d,]+)"
                            rf"\s+.*?(\d[\d,\.\s]+)\s+[Ss]ilver"
                        )
                        matches_transaction = re.finditer(pattern_transaction, full_text, re.IGNORECASE)
                        
                        for match in matches_transaction:
                            try:
                                autocollect_qty_str = match.group(1).replace(',', '')
                                autocollect_price_str = match.group(2)
                                
                                autocollect_qty = int(autocollect_qty_str)
                                autocollect_price = normalize_numeric_str(autocollect_price_str)
                                
                                if autocollect_price and autocollect_price > 0:
                                    conn = get_connection()
                                    cur = conn.cursor()
                                    cur.execute('''
                                        SELECT COUNT(*) FROM transactions
                                        WHERE item_name = ?
                                          AND quantity = ?
                                          AND ABS(price - ?) < 1000
                                          AND timestamp >= datetime('now', '-30 seconds')
                                    ''', (corrected_name, autocollect_qty, autocollect_price))
                                    already_saved = cur.fetchone()[0] > 0

                                    if not already_saved:
                                        fallback_tx = {
                                            'item_name': corrected_name,
                                            'quantity': autocollect_qty,
                                            'price': autocollect_price,
                                            'transaction_type': 'buy',
                                            'tx_case': 'buy_collect',
                                            'timestamp': now,
                                            'occurrence_index': 0,
                                            '_from_detail_window': False,
                                            'raw_related': [
                                                {
                                                    'source': 'detail_log_fallback_autocollect',
                                                    'log_line': match.group(0),
                                                }
                                            ],
                                        }

                                        saved = False
                                        try:
                                            saved = self.store_transaction_db(fallback_tx)
                                        except Exception as store_err:
                                            if self.debug:
                                                log_debug(f"[DETAIL-FALLBACK] ❌ Failed to store auto-collect: {store_err}")
                                        
                                        if saved:
                                            if self.debug:
                                                log_debug(
                                                    f"[DETAIL-FALLBACK] ✅ Auto-collect saved: "
                                                    f"{corrected_name} x{autocollect_qty} @ {autocollect_price:,}"
                                                )
                                            matching_preorder = self._preorder_manager.find_matching_preorder(
                                                item_name=corrected_name,
                                                warehouse_delta=autocollect_qty,
                                                balance_delta=-autocollect_price,
                                                timestamp=now
                                            )
                                            if matching_preorder:
                                                marked = self._preorder_manager.mark_collected(
                                                    preorder_id=matching_preorder['id'],
                                                    collected_at=now,
                                                    transaction_id=None
                                                )
                                                if self.debug:
                                                    if marked:
                                                        log_debug(f"[DETAIL-FALLBACK] ✅ Marked preorder ID={matching_preorder['id']} as collected")
                                                    else:
                                                        log_debug(f"[DETAIL-FALLBACK] ⚠️ Failed to mark preorder ID={matching_preorder['id']} as collected")
                                        elif self.debug:
                                            log_debug(
                                                f"[DETAIL-FALLBACK] ⚠️ Auto-collect not stored (duplicate/plausibility): "
                                                f"{corrected_name} x{autocollect_qty}"
                                            )
                            except Exception as e:
                                if self.debug:
                                    log_debug(f"[DETAIL-FALLBACK] Error processing auto-collect: {e}")

                        # Neue Preorder aus Log ableiten, falls Detail-Fenster zu früh geschlossen wurde
                        pattern_placed = (
                            rf"Placed\s+order\s+of\s+{item_escaped}\s+[xX]?(\d[\d,]+)"
                            rf"\s+for\s+([\d,\.\s]+)\s+[Ss]ilver"
                        )
                        matches_placed = re.finditer(pattern_placed, full_text, re.IGNORECASE)
                        for match in matches_placed:
                            try:
                                placed_qty = int(match.group(1).replace(',', ''))
                                placed_price = normalize_numeric_str(match.group(2))
                                if not placed_qty or placed_qty <= 0 or not placed_price or placed_price <= 0:
                                    continue

                                now_ts = datetime.datetime.now().timestamp()
                                self._recent_preorder_hashes = {
                                    k: v for k, v in self._recent_preorder_hashes.items()
                                    if (now_ts - v) < self._recent_preorder_ttl
                                }
                                dedupe_key = (
                                    corrected_name.lower(),
                                    int(placed_qty),
                                    int(placed_price)
                                )
                                last_seen = self._recent_preorder_hashes.get(dedupe_key)
                                if last_seen and (now_ts - last_seen) < self._recent_preorder_ttl:
                                    if self.debug:
                                        log_debug(
                                            f"[DETAIL-FALLBACK] Duplicate preorder detected via log for {corrected_name} "
                                            f"x{placed_qty} @ {placed_price:,} – skipping"
                                        )
                                    continue

                                preorder_id = self._preorder_manager.store_preorder(
                                    item_name=corrected_name,
                                    quantity=placed_qty,
                                    price=placed_price,
                                    timestamp=now
                                )
                                if preorder_id > 0:
                                    self._recent_preorder_hashes[dedupe_key] = now_ts
                                    if self.debug:
                                        log_debug(
                                            f"[DETAIL-FALLBACK] ✅ Stored preorder from log: {corrected_name} "
                                            f"x{placed_qty} @ {placed_price:,} (ID={preorder_id})"
                                        )
                            except Exception as e:
                                if self.debug:
                                    log_debug(f"[DETAIL-FALLBACK] Error processing preorder placement: {e}")
                    
                    # 🔴 FIX #2: Force-Save BEVOR Reset!
                    self._force_save_pending_transaction()
                    
                    if self.debug:
                        log_debug("[DETAIL] Left detail window - resetting state")
                    self._reset_detail_window_state()
                    self._set_detail_metric_state("idle", "detail_exit")
            # Kein Update von last_overview_text hier, damit Delta sauber bleibt
            return

        # detect current tab from the whole OCR snapshot (nur zur Diagnose); Entscheidung über Seite strikt aus Window-Type
        current_tab = detect_tab_from_text(full_text)
        if current_tab == "unknown" and self.last_overview:
            current_tab = "sell" if self.last_overview == "sell_overview" else "buy"
        if self.debug:
            msg = f"detected tab={current_tab} window={wtype} prev_window={prev_window}"
            print("DEBUG:", msg)
            log_debug(msg)

        buffered_structured = []
        if self._detail_pending_log_snapshots:
            buffered_structured = self._consume_detail_log_snapshots(wtype)
        log_text_source = (getattr(self, '_latest_log_text', '') or '').strip()
        entries = split_text_into_log_entries(log_text_source) if log_text_source else []

        # Fallback: only attempt to parse the full snapshot when log ROI failed in an overview window.
        fallback_used = False
        if not entries and self._log_capture_failed and wtype in ("sell_overview", "buy_overview"):
            sanitized = self._sanitize_log_snapshot(full_text)
            if sanitized:
                entries = split_text_into_log_entries(sanitized)
                fallback_used = True

        if not entries:
            if self.debug and self._log_capture_failed and wtype in ("sell_overview", "buy_overview"):
                log_debug("[LOG] skip scan: log ROI empty; no entries parsed")
            return
        elif fallback_used and self.debug:
            log_debug("[LOG] fallback snapshot used for log parsing")
        if not entries:
            if self.debug:
                msg = "no timestamp-entries found; skipping"
                print("DEBUG:", msg)
                log_debug(msg)
            return

        # CRITICAL PERFORMANCE FIX: Immediate burst scanning when returning from item window
        # Transaction lines appear instantly or within ~200-500ms after returning to overview
        # Old approach: wait 1-3 seconds with slow scans = missed transactions
        # New approach: IMMEDIATE burst of 5-8 fast scans at 80ms intervals = capture within 1s
        # FIX 3: Reduced from 15+5=20 scans to 5+3=8 scans
        # Reason: Too many scans increase timestamp-variation risk (OCR reads 10:30 vs 10:31)
        if prev_window in ("buy_item", "sell_item") and wtype in ("sell_overview", "buy_overview"):
            # REDUCED: Fewer scans to minimize timestamp OCR variations
            self._burst_fast_scans = max(self._burst_fast_scans, 5)  # Was 15, now 5 (400ms of fast scans)
            self._burst_until = max(self._burst_until or now, now + datetime.timedelta(seconds=2.0))  # Was 3s, now 2s
            self._burst_source = 'item_window'
            # Immediate re-scans (no sleep between scans)
            self._request_immediate_rescan = max(self._request_immediate_rescan, 3)  # Was 5, now 3
            if self.debug:
                log_debug(f"[BURST-OPTIMIZED] Returned from {prev_window} to {wtype} -> {self._burst_fast_scans} fast scans + {self._request_immediate_rescan} immediate rescans (8 scans total, optimized for timestamp consistency)")
        # build structured entries
        structured = []
        self._batch_content_hashes.clear()
        for pos, ts_text, snippet in entries:
            details = extract_details_from_entry(ts_text, snippet)
            # include original pos for fallback grouping
            if not details['timestamp']:
                continue
            if details['type'] not in {'transaction', 'placed', 'listed', 'withdrew', 'purchased'}:
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
                'raw': details['raw'],
                'raw_price_hint': details.get('raw_price_hint')
            })

        # sort by timestamp then pos
        if buffered_structured:
            existing_keys = {
                (
                    entry.get('type'),
                    (entry.get('item') or '').lower(),
                    entry.get('qty'),
                    entry.get('price'),
                    entry.get('timestamp')
                )
                for entry in structured
            }
            for buffered in buffered_structured:
                key = (
                    buffered.get('type'),
                    (buffered.get('item') or '').lower(),
                    buffered.get('qty'),
                    buffered.get('price'),
                    buffered.get('timestamp'),
                )
                if key in existing_keys:
                    continue
                structured.append(buffered)
                existing_keys.add(key)
        structured = sorted(structured, key=lambda x: (x['timestamp'], x['pos']))
        if self.debug:
            log_debug(f"structured_count={len(structured)}")
        
        # NEW: Detect and handle preorder/listing events from transaction log
        for s in structured:
            # Preorder cancellation (Buy-side: "Withdrew order")
            if s.get('type') == 'withdrew' and s.get('item') and s.get('qty') and s.get('price'):
                self._handle_preorder_cancellation(
                    item_name=s['item'],
                    quantity=s['qty'],
                    price=s['price']
                )
            
            # Preorder/Listing collection (Both sides: "Transaction of")
            # When user clicks Collect button, transaction log shows "Transaction of Item x5000"
            # We need to mark the corresponding preorder (buy-side) or listing (sell-side) as collected
            if s.get('type') == 'transaction' and s.get('item') and s.get('qty') and s.get('price'):
                self._handle_preorder_or_listing_collection(
                    item_name=s['item'],
                    quantity=s['qty'],
                    price=s['price'],
                    timestamp=s.get('timestamp') or datetime.datetime.now(),
                    window_type=wtype  # Pass window type to determine buy vs sell
                )
        
        # 🔍 LOG-FALLBACK: Prüfe fehlende Detail-Window Transaktionen
        # MUSS HIER passieren, bevor structured weiter gefiltert wird
        returning_from_item = prev_window in ("buy_item", "sell_item") and wtype in ("sell_overview", "buy_overview")
        if returning_from_item and self._detail_window_entry_item:
            missing_txs = self._check_missing_detail_window_transactions(structured, wtype)
            if missing_txs:
                if self.debug:
                    log_debug(f"[LOG-FALLBACK] Found {len(missing_txs)} missing transaction(s) from detail window")
                now_ts = datetime.datetime.now()
                ttl_cutoff = now_ts.timestamp() - self._log_fallback_ttl_seconds
                pending = []
                for tx in missing_txs:
                    ts_val = tx.get('timestamp') if isinstance(tx.get('timestamp'), datetime.datetime) else None
                    if not ts_val:
                        continue
                    ts_epoch = ts_val.timestamp()
                    if ts_epoch < ttl_cutoff:
                        continue
                    new_entry = {
                        **tx,
                        '_fallback_source': 'detail_window',
                        '_fallback_detected_at': now_ts,
                        '_fallback_timestamp_epoch': ts_epoch,
                    }
                    pending.append(new_entry)
                self._pending_log_fallback_txs = pending
            else:
                self._pending_log_fallback_txs = []

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
                            try:
                                delta_seconds = abs((overall_max_ts - s['timestamp']).total_seconds())
                            except Exception:
                                delta_seconds = None
                            if delta_seconds is not None and delta_seconds > 120:
                                continue
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
        if getattr(self, '_last_ui_buy_metrics', None):
            try:
                prev_ui_buy = {k: dict(v) for k, v in self._last_ui_buy_metrics.items()}
            except Exception:
                prev_ui_buy = self._last_ui_buy_metrics.copy()

        ui_buy_delta_detected = False
        if wtype == 'buy_overview' and ui_buy and prev_ui_buy:
            for item_lc, metrics in ui_buy.items():
                orders_curr = metrics.get('ordersCompleted') or 0
                if orders_curr > 0:
                    self._sync_preorder_fill_from_ui(metrics, orders_curr, item_lc)

                prev_metrics = prev_ui_buy.get(item_lc)
                if not prev_metrics:
                    continue
                orders_prev = prev_metrics.get('ordersCompleted') or 0
                collect_curr = metrics.get('remainingPrice') or 0
                collect_prev = prev_metrics.get('remainingPrice') or 0
                if orders_curr > orders_prev or collect_curr > collect_prev:
                    ui_buy_delta_detected = True
                    # Bei Relist-Metrik-Auswertung quantity_filled aktualisieren
                    metrics['quantity_filled'] = orders_curr
                    break

        prev_ui_sell = {}
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

        if ui_buy and not prev_ui_buy:
            for item_lc, metrics in ui_buy.items():
                orders_curr = metrics.get('ordersCompleted') or 0
                if orders_curr > 0:
                    self._sync_preorder_fill_from_ui(metrics, orders_curr, item_lc)

        prev_ui_sell_norm = {}
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

                other_ts = other.get('timestamp')
                # Skip if other is a 'purchased' - those are always standalone
                if other['type'] == 'purchased':
                    continue

                dt = abs((other_ts - ts).total_seconds())
                same_ts = isinstance(other_ts, datetime.datetime) and other_ts == ts
                if first_snapshot_mode and not same_ts:
                    continue
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
                def _tx_sort_key(entry):
                    has_price = 1 if (entry.get('price') or 0) > 0 else 0
                    has_qty = 1 if (entry.get('qty') or 0) > 0 else 0
                    ts_score = 0
                    ts_entry = entry.get('timestamp')
                    try:
                        if isinstance(ts_entry, datetime.datetime) and 'overall_max_ts' in locals() and isinstance(overall_max_ts, datetime.datetime):
                            # prefer timestamps closest to the newest timestamp seen in this snapshot
                            ts_score = -abs((overall_max_ts - ts_entry).total_seconds())
                    except Exception:
                        ts_score = 0
                    return (
                        has_price,
                        ts_score,
                        has_qty,
                        entry.get('qty') or 0,
                        entry.get('price') or 0,
                    )

                transaction_entries_sorted = sorted(
                    transaction_entries,
                    key=_tx_sort_key,
                    reverse=True
                )
                for pos, entry in enumerate(transaction_entries_sorted):
                    entry['_occurrence_slot'] = pos
                transaction_entry = transaction_entries_sorted[0]
            else:
                transaction_entries_sorted = []
                transaction_entry = None
            listed_entry = next((r for r in related if r['type'] == 'listed'), None)
            pur_rel = next((r for r in related if r['type'] == 'purchased'), None)
            tx_rel_same = transaction_entry or next((r for r in related if r['type'] == 'transaction'), None)
            
            # Anchor priority: transaction > purchased > placed > listed
            if transaction_entry:
                ent = transaction_entry
            elif any(r['type'] == 'purchased' for r in related):
                ent = next(r for r in related if r['type'] == 'purchased')
            elif any(r['type'] == 'placed' for r in related):
                ent = next(r for r in related if r['type'] == 'placed')
            else:
                ent = cluster_entries[0]
            
            # ⚡ FIX: RELIST-PATTERN DETECTION
            # Detect relist pattern: transaction + listed/placed at same timestamp
            # This happens when user clicks "Relist" - old order auto-collected, new order created
            is_relist_cluster = False
            placed_entry = next((r for r in related if r['type'] == 'placed'), None)
            
            if transaction_entry and (listed_entry or placed_entry):
                tx_ts = transaction_entry.get('timestamp')
                new_order_entry = listed_entry if listed_entry else placed_entry
                new_order_ts = new_order_entry.get('timestamp') if new_order_entry else None
                
                if tx_ts and new_order_ts and tx_ts == new_order_ts:
                    is_relist_cluster = True
                    if self.debug:
                        log_debug(f"[RELIST] Detected relist pattern for '{ent.get('item')}' : transaction + {'listed' if listed_entry else 'placed'} at {tx_ts}")
                    
                    # FIX 1: Log-based Preorder Reconstruction
                    # Check if we have withdrew + transaction (indicating missing preorder in DB)
                    withdrew_entry = next((r for r in related if r['type'] == 'withdrew'), None)
                    
                    if withdrew_entry and transaction_entry:
                        # We have all pieces to reconstruct the original preorder
                        withdrew_qty = withdrew_entry.get('qty', 0)
                        withdrew_price = withdrew_entry.get('price', 0)
                        transaction_qty = transaction_entry.get('qty', 0)
                        
                        if withdrew_qty > 0 and transaction_qty > 0 and withdrew_price > 0:
                            # Try to reconstruct missing preorder
                            reconstructed = self._reconstruct_missing_preorder_from_log(
                                item_name=ent.get('item', ''),
                                withdrew_qty=withdrew_qty,
                                withdrew_price=withdrew_price,
                                transaction_qty=transaction_qty,
                                timestamp=tx_ts
                            )
                            
                            if reconstructed:
                                # Store reconstructed preorder in transaction_entry metadata
                                # This will be used later for price correction
                                transaction_entry['_reconstructed_preorder'] = reconstructed
                                if self.debug:
                                    log_debug(
                                        f"[RELIST] ✅ Attached reconstructed preorder to transaction: "
                                        f"{transaction_qty:,}x @ {reconstructed['unit_price']:,.0f}"
                                    )

                    # Ensure relist transaction provides a net price for downstream consumers
                    if transaction_entry:
                        relist_item = transaction_entry.get('item') or ent.get('item') or ''
                        relist_qty = transaction_entry.get('qty') or ent.get('qty') or 0
                        candidate_price = transaction_entry.get('price') or 0

                        recovered_cluster_price = None
                        if relist_item and relist_qty:
                            recovered_cluster_price = self._recover_sell_price(
                                relist_item,
                                int(relist_qty),
                                candidate_price,
                                transaction_entry
                            )

                        if (not recovered_cluster_price or recovered_cluster_price <= 0) and listed_entry and listed_entry.get('price') and relist_qty:
                            try:
                                recovered_cluster_price = int(round(listed_entry.get('price') * MARKET_SELL_NET_FACTOR))
                            except Exception:
                                recovered_cluster_price = None

                        if (not recovered_cluster_price or recovered_cluster_price <= 0) and transaction_entry.get('raw_price_hint'):
                            try:
                                recovered_cluster_price = int(transaction_entry['raw_price_hint'])
                            except Exception:
                                recovered_cluster_price = None

                        if recovered_cluster_price and recovered_cluster_price > 0:
                            recovered_cluster_price = int(recovered_cluster_price)
                            transaction_entry['_recovered_price'] = recovered_cluster_price
                            transaction_entry['_cluster_net_price'] = recovered_cluster_price
                            if not transaction_entry.get('price') or transaction_entry.get('price') <= 0:
                                transaction_entry['price'] = recovered_cluster_price
            
            # On sell overview, skip listed-only clusters UNLESS UI metrics show completed sales OR it's a relist
            if wtype == 'sell_overview' and not transaction_entry and listed_entry and ent['type'] == 'listed':
                # Check if this is part of a relist cluster (don't skip new listing in relist!)
                is_part_of_relist = any(
                    r['type'] == 'transaction' and r.get('timestamp') == ent.get('timestamp')
                    for r in related
                )
                
                if is_part_of_relist:
                    # This is the NEW listing in a relist - DON'T skip!
                    if self.debug:
                        log_debug(f"[RELIST] Keeping listed entry for '{ent.get('item')}' - part of relist cluster")
                else:
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

            if side is None:
                qty_hint = ent.get('qty')
                if not qty_hint and transaction_entry and transaction_entry.get('qty'):
                    qty_hint = transaction_entry.get('qty')
                price_hint_total = ent.get('price')
                if price_hint_total is None and transaction_entry:
                    price_hint_total = transaction_entry.get('price')
                if qty_hint and qty_hint > 0 and price_hint_total and price_hint_total > 0:
                    reference_units: list[float] = []
                    try:
                        base_price_local = self._get_base_price(ent.get('item'))
                    except Exception:
                        base_price_local = None
                    if base_price_local:
                        reference_units.append(float(base_price_local))
                    ui_price_try = None
                    try:
                        key_lookup = (ent.get('item') or '').lower()
                        ui_metric = ui_sell.get(key_lookup) if 'ui_sell' in locals() else None
                        if (not ui_metric) and 'ui_sell_norm' in locals():
                            ui_metric = ui_sell_norm.get(_norm_key(ent.get('item') or ''))
                        if ui_metric:
                            ui_price_try = ui_metric.get('price')
                    except Exception:
                        ui_price_try = None
                    if ui_price_try:
                        try:
                            reference_units.append(float(ui_price_try))
                        except Exception:
                            pass
                    if reference_units:
                        buy_unit = float(price_hint_total) / float(qty_hint)
                        try:
                            sell_unit = float(price_hint_total) / (float(qty_hint) * MARKET_SELL_NET_FACTOR)
                        except ZeroDivisionError:
                            sell_unit = None
                        if sell_unit is not None and sell_unit > 0:
                            try:
                                diff_buy = min(abs(buy_unit - ref) for ref in reference_units if ref)
                            except ValueError:
                                diff_buy = None
                            try:
                                diff_sell = min(abs(sell_unit - ref) for ref in reference_units if ref)
                            except ValueError:
                                diff_sell = None
                            if diff_buy is not None and diff_sell is not None:
                                if diff_buy <= diff_sell * 0.8:
                                    side = 'buy'
                                    if self.debug:
                                        log_debug(f"[PRICE-HINT] Side bias→buy for '{ent['item']}' (diff_buy={diff_buy:.2f}, diff_sell={diff_sell:.2f})")
                                elif diff_sell <= diff_buy * 0.8:
                                    side = 'sell'
                                    if self.debug:
                                        log_debug(f"[PRICE-HINT] Side bias→sell for '{ent['item']}' (diff_sell={diff_sell:.2f}, diff_buy={diff_buy:.2f})")
            
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

                # Additional inference: If there is a placed+withdrew inference for qty, but there is also a transaction line for the
                # same item at this timestamp with a total price (even if without qty), prefer that transaction price with
                # the inferred quantity. This avoids undercounting totals when OCR merges sell/buy text blocks.
                if (has_placed_same or has_listed_same) and has_withdrew_same:
                    tx_price_only = next((r.get('price') for r in related if r['type'] == 'transaction' and r.get('price')), None)
                    if tx_price_only and (ent.get('qty') or any(r.get('qty') for r in related if r['type'] in ('placed','withdrew'))):
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
                        allow_from_placed = True
                        ts_ent = ent.get('timestamp')
                        ts_placed = placed_entry.get('timestamp')
                        try:
                            if isinstance(ts_ent, datetime.datetime) and isinstance(ts_placed, datetime.datetime):
                                if abs((ts_ent - ts_placed).total_seconds()) > 120:
                                    allow_from_placed = False
                        except Exception:
                            pass
                        if allow_from_placed:
                            ent['qty'] = placed_entry['qty']

            # final transaction type strictly from side; do not override with presence of listed/placed
            final_type = side
            ui_backfill_needed = False
            ent_type = ent.get('type')
            if final_type == 'buy' and ent_type == 'placed':
                if self.debug:
                    log_debug(f"skip placed-only entry for item='{ent.get('item')}'")
                continue

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
            
            # CRITICAL: Letzte Korrektur-Chance gegen Whitelist mit striktem Matching
            # Dies fängt OCR-Fehler wie "F Lion Blood" → "Lion Blood"
            try:
                corrected, _ = self._safe_correct_item_name(item_name, min_score=80)  # Etwas niedriger für OCR-Fehler
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
                'occurrence_slot': occurrence_slot,
                '_is_relist': is_relist_cluster,  # Store relist flag for later processing
                '_listed_entry': listed_entry,     # Store listed entry for relist handling
                '_placed_entry': placed_entry      # Store placed entry for relist handling
            }
            
            # FIX 1: Apply reconstructed preorder price correction
            # If transaction_entry has _reconstructed_preorder metadata, use it for price correction
            if transaction_entry and transaction_entry.get('_reconstructed_preorder'):
                reconstructed = transaction_entry['_reconstructed_preorder']
                
                # Calculate corrected price: transaction price = collected price (not preorder price)
                # Use reconstructed unit_price for accuracy
                corrected_price = reconstructed['unit_price'] * quantity
                
                if self.debug:
                    log_debug(
                        f"[RELIST] Applying reconstructed preorder price correction:\n"
                        f"   Original price: {price:,.0f}\n"
                        f"   Reconstructed unit price: {reconstructed['unit_price']:,.0f}\n"
                        f"   Corrected price: {corrected_price:,.0f}"
                    )
                
                tx['price'] = corrected_price
                tx['_price_corrected_by_reconstruction'] = True
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
            
            # ⚡ RELIST HANDLING: Process relist pattern (transaction + listed/placed at same timestamp)
            if tx.get('_is_relist'):
                pending_payload = {
                    'tx_item': tx.get('item_name'),
                    'tx_qty': tx.get('quantity'),
                    'tx_price': tx.get('price'),
                    'tx_timestamp': tx.get('timestamp'),
                    'tx_type': tx.get('transaction_type'),
                    'listed_entry': tx.get('_listed_entry'),
                    'placed_entry': tx.get('_placed_entry'),
                }

                item_norm = (tx.get('item_name') or '').lower()
                if item_norm and item_norm in ui_buy:
                    ui_entry = ui_buy[item_norm]
                    orders_completed = ui_entry.get('ordersCompleted')
                    if isinstance(orders_completed, int) and orders_completed > 0:
                        pending_payload['ui_orders_completed'] = orders_completed

                tx['_pending_relist'] = pending_payload

            if final_type in ('sell', 'buy') and len(transaction_entries_sorted) > 1:
                for extra_entry in transaction_entries_sorted[1:]:
                    extra_qty = extra_entry.get('qty')
                    extra_price = extra_entry.get('price')
                    if not extra_qty and not extra_price:
                        continue
                    extra_quantity = extra_qty or quantity
                    extra_price_value = extra_price or price
                    if extra_quantity is None or extra_quantity < MIN_ITEM_QUANTITY or extra_quantity > MAX_ITEM_QUANTITY:
                        continue
                    if extra_price_value is None or extra_price_value <= 0:
                        continue
                    extra_slot = extra_entry.get('_occurrence_slot', 0) if transaction_entries_sorted else 0
                    extra_timestamp = extra_entry.get('timestamp') if isinstance(extra_entry.get('timestamp'), datetime.datetime) else ent['timestamp']
                    extra_cluster_key = (
                        item_name.lower(),
                        int(extra_timestamp.timestamp()) if isinstance(extra_timestamp, datetime.datetime) else ts_key,
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
                        'timestamp': extra_timestamp,
                        'transaction_type': final_type,
                        'case': f"{final_type}_{case}",
                        'raw_related': related,
                        'occurrence_index': None,
                        'occurrence_slot': extra_slot
                    })
        if self.debug:
            log_debug(f"tx_candidates={len(tx_candidates)} allowed_ts={len(allowed_ts)}")
        
        # 🔍 LOG-FALLBACK: Füge fehlende Detail-Window Transaktionen hinzu
        if self._pending_log_fallback_txs:
            ttl_cutoff = datetime.datetime.now().timestamp() - self._log_fallback_ttl_seconds
            filtered_pending = []
            for pending in self._pending_log_fallback_txs:
                detected_epoch = pending.get('_fallback_timestamp_epoch')
                if detected_epoch is None:
                    detected_epoch = pending.get('timestamp').timestamp() if isinstance(pending.get('timestamp'), datetime.datetime) else None
                if detected_epoch is None or detected_epoch < ttl_cutoff:
                    continue
                hash_val = self._make_log_fallback_hash({
                    'item': pending.get('item_name'),
                    'qty': pending.get('quantity'),
                    'price': pending.get('price'),
                    'timestamp': pending.get('timestamp'),
                })
                if hash_val in self._log_fallback_seen_hashes:
                    continue
                self._log_fallback_seen_hashes.add(hash_val)
                filtered_pending.append(pending)
            if filtered_pending and self.debug:
                log_debug(f"[LOG-FALLBACK] Applying {len(filtered_pending)} pending detail transactions")
            tx_candidates.extend(filtered_pending)
            self._pending_log_fallback_txs = []

        if ui_buy_delta_detected:
            self._schedule_metrics_refresh("ui_inference_buy")

        if (
            wtype == 'sell_overview'
            and ui_sell
            and (prev_ui_sell or self._last_ui_sell_metrics)
        ):
            existing_items = {(t.get('item_name') or '').lower() for t in tx_candidates if t.get('item_name')}
            existing_norm = { _norm_key(t.get('item_name')) for t in tx_candidates if t.get('item_name') }
            for item_lc, metrics in ui_sell.items():
                if item_lc in existing_items or _norm_key(metrics.get('item') or item_lc) in existing_norm:
                    continue
                prev_metrics = prev_ui_sell.get(item_lc) if prev_ui_sell else None
                if not prev_metrics and prev_ui_sell_norm:
                    prev_metrics = prev_ui_sell_norm.get(_norm_key(metrics.get('item') or item_lc))
                if not prev_metrics:
                    continue
                sales_completed = metrics.get('salesCompleted') or 0
                collect_total = metrics.get('price') or 0
                prev_sales = prev_metrics.get('salesCompleted') or 0
                prev_collect = prev_metrics.get('price') or 0
                delta_qty = sales_completed - prev_sales
                delta_price = collect_total - prev_collect
                if delta_qty <= 0 or delta_price <= 0:
                    continue
                ui_sell_delta_detected = True
                if delta_qty < MIN_ITEM_QUANTITY or delta_qty > MAX_ITEM_QUANTITY:
                    continue

                corrected_name, _ = self._safe_correct_item_name(metrics.get('item') or item_lc)
                corrected_name = corrected_name or metrics.get('item') or item_lc
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
                    # Adjust timestamps only when the original timestamp ist recent (within FRESH_TX_WINDOW)
                    for t in tx_candidates:
                        if (t['item_name'] or '').lower() in anchor_items_from_scan and isinstance(t['timestamp'], datetime.datetime) and latest_ts and t['timestamp'] < latest_ts:
                            try:
                                delta_seconds = (latest_ts - t['timestamp']).total_seconds()
                            except Exception:
                                delta_seconds = None
                            if delta_seconds is not None and 0 < delta_seconds <= FRESH_TX_WINDOW:
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
                            self._burst_source = 'overview_followup'
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
                            self._burst_source = 'overview_followup'
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
            
            baseline_gap = False

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
            
            # FIX 2: Timestamp-Toleranz-basierte Duplikatserkennung
            # Check if this transaction exists with slightly different timestamp (±2min)
            # This catches OCR-induced timestamp variations (e.g., 10:30 vs 10:31)
            # 
            # CRITICAL SAFEGUARDS to prevent blocking real new transactions:
            # 1. Only check if NOT newer than baseline (old/historical transactions)
            # 2. Only check if already in baseline text (seen before)
            # 3. Skip for truly new transactions (not in baseline, timestamp > prev_max_ts)
            timestamp_duplicate = False
            
            # SAFEGUARD: Never check timestamp tolerance for NEW transactions
            # New transactions should use their actual log timestamp
            should_check_timestamp_tolerance = (
                isinstance(tx['timestamp'], datetime.datetime)
                and already_seen_in_prev  # CRITICAL: Only if seen in previous baseline
                and not is_newer_than_prev  # CRITICAL: Not for new transactions
            )
            
            if should_check_timestamp_tolerance:
                try:
                    timestamp_duplicate = self._is_value_duplicate_with_time_tolerance(
                        tx['item_name'],
                        tx['quantity'],
                        int(tx['price'] or 0),
                        tx['timestamp'],
                        tolerance_minutes=2
                    )
                    if timestamp_duplicate and self.debug:
                        log_debug(
                            f"[DELTA] Timestamp-tolerance duplicate: {tx['item_name']} {tx['quantity']}x @ {tx['price']} "
                            f"ts={tx['timestamp']} (±2min match found) - SAFE: is_newer={is_newer_than_prev}, seen_prev={already_seen_in_prev}"
                        )
                except Exception as e:
                    if self.debug:
                        log_debug(f"[DELTA] Timestamp-tolerance check failed: {e}")
            
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
                log_debug(f"[DELTA] Checking {tx['item_name']} @ {tx['timestamp']}: newer={is_newer_than_prev}, seen_in_text={already_seen_in_prev}, in_db={already_in_db}, near_time={already_in_db_by_values}, ts_dup={timestamp_duplicate}")
            
            # FIX 2: Skip if timestamp-tolerance duplicate detected
            # NOTE: timestamp_duplicate is ONLY True for old transactions that were seen before
            # New transactions (is_newer_than_prev=True OR not already_seen_in_prev) are NEVER blocked
            if timestamp_duplicate:
                if self.debug:
                    log_debug(
                        f"[DELTA] SKIP (timestamp-duplicate): {tx['item_name']} {tx['quantity']}x @ {tx['price']} "
                        f"ts={tx['timestamp']} - OCR timestamp variation detected (±2min) - OLD transaction rescanned"
                    )
                continue
            
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

            if already_seen_in_prev and not already_in_db and not already_in_db_any_side:
                baseline_gap = True
                is_historical = True
                if self.debug:
                    log_debug(
                        f"[DELTA] Baseline gap detected for {tx['item_name']} "
                        f"{tx['quantity']}x @ {tx['timestamp']} - importing despite previous snapshot"
                    )

            allow_old_timestamp = (
                not already_in_db
                and not already_in_db_any_side
                and (not already_seen_in_prev or baseline_gap)
            )
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
            if saved:
                self._apply_relist_side_effects(tx)
                if isinstance(tx['timestamp'], datetime.datetime):
                    if not tx.get('_ui_inferred'):
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
                if saved:
                    self._apply_relist_side_effects(fallback)
                    if isinstance(fallback['timestamp'], datetime.datetime):
                        if not fallback.get('_ui_inferred'):
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
                            self._burst_source = 'overview_followup'
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
                            self._burst_source = 'overview_followup'
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
                            self._burst_source = 'overview_followup'
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

    def _apply_relist_side_effects(self, tx: dict) -> None:
        if not tx or not tx.get('_pending_relist'):
            return

        payload = tx['_pending_relist']
        tx_item = payload.get('tx_item')
        tx_qty = payload.get('tx_qty')
        tx_price = payload.get('tx_price')
        tx_timestamp = payload.get('tx_timestamp')
        tx_type = payload.get('tx_type')

        try:
            occurrence_idx = tx.get('occurrence_index')
            ts_bucket = None
            if isinstance(tx_timestamp, datetime.datetime):
                ts_bucket = int(tx_timestamp.timestamp())
            signature = (tx_type, (tx_item or '').lower(), int(tx_qty or 0), int(tx_price or 0), ts_bucket, occurrence_idx)
        except Exception:
            signature = None

        now_ts = time.time()

        if signature:
            cutoff = now_ts - self._relist_side_effect_ttl
            self._relist_side_effect_signatures = {
                sig: ts
                for sig, ts in self._relist_side_effect_signatures.items()
                if ts >= cutoff
            }
            if self._relist_side_effect_signatures.get(signature):
                if self.debug:
                    log_debug(f"[RELIST] 🔁 Nebenwirkungen bereits angewendet für {tx_item} (signature={signature})")
                return

        pm = self._preorder_manager
        listed_entry = payload.get('listed_entry')
        placed_entry = payload.get('placed_entry')
        ui_orders_completed = payload.get('ui_orders_completed')

        def _safe_int(val):
            try:
                if val is None:
                    return None
                return int(val)
            except (ValueError, TypeError):
                return None

        if tx_type == 'sell' and listed_entry:
            new_qty = _safe_int(listed_entry.get('qty'))
            new_price = _safe_int(listed_entry.get('price'))

            if new_qty and new_qty > 0 and new_price and new_price > 0:
                old_listing = pm.find_matching_listing(
                    tx_item,
                    tx_qty or 0,
                    tx_price or 0,
                    tx_timestamp or datetime.datetime.now(),
                )
                if old_listing:
                    try:
                        pm.mark_listing_collected(
                            old_listing['id'],
                            tx_timestamp or datetime.datetime.now(),
                            transaction_id=tx.get('id'),
                        )
                        if self.debug:
                            log_debug(f"[RELIST] ✅ Alte Listing ID={old_listing['id']} als collected markiert")
                    except Exception as exc:
                        if self.debug:
                            log_debug(f"[RELIST] ❌ Mark Listing Collect fehlgeschlagen: {exc}")

                try:
                    pm.store_listing(
                        tx_item,
                        new_qty,
                        new_price,
                        tx_timestamp or datetime.datetime.now(),
                    )
                    if self.debug:
                        log_debug(f"[RELIST] ✅ Neue Listing gespeichert: {new_qty}x {tx_item} @ {new_price:,}")
                except Exception as exc:
                    if self.debug:
                        log_debug(f"[RELIST] ❌ Neue Listing speichern fehlgeschlagen: {exc}")

        elif tx_type == 'buy' and placed_entry:
            new_qty = _safe_int(placed_entry.get('qty'))
            new_price = _safe_int(placed_entry.get('price'))

            if new_qty and new_qty > 0 and new_price and new_price > 0:
                old_preorder = pm.find_matching_preorder(
                    tx_item,
                    tx_qty or 0,
                    tx_price or 0,
                    tx_timestamp or datetime.datetime.now(),
                )
                if old_preorder:
                    try:
                        pm.mark_collected(
                            old_preorder['id'],
                            tx_timestamp or datetime.datetime.now(),
                            transaction_id=tx.get('id'),
                        )
                        if ui_orders_completed and ui_orders_completed > 0:
                            pm.update_quantity_filled(
                                preorder_id=old_preorder['id'],
                                filled_quantity=ui_orders_completed
                            )
                        if self.debug:
                            log_debug(f"[RELIST] ✅ Alte Preorder ID={old_preorder['id']} als collected markiert")
                    except Exception as exc:
                        if self.debug:
                            log_debug(f"[RELIST] ❌ Mark Collected fehlgeschlagen: {exc}")
                else:
                    # Keine aktive Preorder gefunden → Legacy-Eintrag erfassen und UI-Fills synchronisieren
                    if ui_orders_completed and ui_orders_completed > 0 and tx_item:
                        try:
                            pm.update_quantity_filled_by_item(tx_item, ui_orders_completed)
                        except Exception as exc:
                            if self.debug:
                                log_debug(f"[RELIST] ⚠️ UI-Fill-Sync fehlgeschlagen: {exc}")
                    legacy_qty = _safe_int(tx_qty)
                    legacy_price = _safe_int(tx_price)
                    if legacy_qty and legacy_qty > 0 and legacy_price and legacy_price > 0:
                        try:
                            pm.record_legacy_preorder(
                                item_name=tx_item,
                                quantity=legacy_qty,
                                price=legacy_price,
                                collected_at=tx_timestamp or datetime.datetime.now(),
                                status='collected',
                            )
                            if self.debug:
                                log_debug(f"[RELIST] ✅ Legacy Preorder erfasst: {legacy_qty}x {tx_item} @ {legacy_price:,}")
                        except Exception as exc:
                            if self.debug:
                                log_debug(f"[RELIST] ❌ Legacy Preorder erfassen fehlgeschlagen: {exc}")

                try:
                    pm.store_preorder(
                        tx_item,
                        new_qty,
                        new_price,
                        tx_timestamp or datetime.datetime.now(),
                    )
                    if self.debug:
                        log_debug(f"[RELIST] ✅ Neue Preorder gespeichert: {new_qty}x {tx_item} @ {new_price:,}")
                except Exception as exc:
                    if self.debug:
                        log_debug(f"[RELIST] ❌ Neue Preorder speichern fehlgeschlagen: {exc}")

                # Cached Detail-Inputs zurücksetzen, damit nachfolgende Detail-Scans aktuelle Werte ziehen
                if ui_orders_completed and ui_orders_completed > 0:
                    self._invalidate_detail_input_cache('refresh')

        if signature:
            self._relist_side_effect_signatures[signature] = now_ts

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

        # CRITICAL: Rapid-Scans for Detail-Window transactions
        # These must execute IMMEDIATELY after baseline capture to catch fast transactions
        while self._request_immediate_rescan > 0 and self.running:
            if self.debug:
                log_debug(f"[RAPID-SCAN] Starting rapid scan #{4 - self._request_immediate_rescan} (remaining={self._request_immediate_rescan})")
            
            time.sleep(0.05)
            
            img2 = self._capture_frame()
            if img2 is None:
                if self.debug:
                    log_debug(f"[RAPID-SCAN] ❌ Capture failed (img=None)")
                break
            
            if not self.running:
                if self.debug:
                    log_debug(f"[RAPID-SCAN] ❌ Stopped (running=False)")
                break
            
            self._process_image(img2, context='quick', allow_debug=False)
            self._request_immediate_rescan -= 1
            
            if self.debug:
                log_debug(f"[RAPID-SCAN] ✅ Completed scan #{3 - self._request_immediate_rescan}, remaining={self._request_immediate_rescan}")

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
                            log_debug("[ASYNC-DROP] Dropped stale frame (queue full - OCR too slow)")
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
            # CRITICAL FIX: Add timeout for responsive stop (max 1s wait)
            try:
                item = await asyncio.wait_for(self.queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                # Check if stop was requested during wait
                if self._stop_requested or not self.tracker.running:
                    break
                continue  # Retry queue.get()
            
            if item is None:
                self.queue.task_done()
                break

            if not self.tracker.running and self._stop_requested:
                self.queue.task_done()
                continue

            try:
                start_process = time.perf_counter()
                await loop.run_in_executor(
                    self.executor,
                    self.tracker._process_image,
                    item['image'],
                    'async',
                    self.tracker.debug,
                )
                # PERFORMANCE METRICS: Always log queue latency (even in non-debug mode)
                captured_at = item.get('captured_at')
                if captured_at is not None:
                    queue_latency_ms = (start_process - captured_at) * 1000
                    process_time_ms = (time.perf_counter() - start_process) * 1000
                    total_latency_ms = (time.perf_counter() - captured_at) * 1000
                    log_debug(f"[ASYNC-PERF] Worker {worker_id}: queue={queue_latency_ms:.1f}ms process={process_time_ms:.1f}ms total={total_latency_ms:.1f}ms")
            except Exception as exc:
                log_debug(f"[ASYNC-ERROR] Worker {worker_id}: {exc}")
            finally:
                self.queue.task_done()

    async def _interruptible_sleep(self, duration: float) -> None:
        if duration <= 0:
            await asyncio.sleep(0)
            return

        elapsed = 0.0
        # CRITICAL FIX: Faster granularity for <100ms stop response (was 0.1s, now 0.05s)
        step = 0.05  # Check every 50ms instead of 100ms
        while elapsed < duration and not self._stop_requested and self.tracker.running:
            slice_len = min(step, duration - elapsed)
            await asyncio.sleep(slice_len)
            elapsed += slice_len

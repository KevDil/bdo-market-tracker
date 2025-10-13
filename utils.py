import re
import datetime
import cv2
import numpy as np
import mss
from PIL import Image
import pytesseract
import csv
import hashlib
import time
import threading
from functools import lru_cache
import os
from typing import Dict, Iterator, Optional, Sequence

# Performance: Import Windows-specific modules at top level (not inside function)
try:
    import ctypes
    from ctypes import wintypes
    _WINDOWS_MODULES_AVAILABLE = True
except (ImportError, AttributeError):
    _WINDOWS_MODULES_AVAILABLE = False

from config import (
    USE_EASYOCR,
    reader,
    LOG_PATH,
    LETTER_TO_DIGIT,
    DIGIT_TO_LETTER,
    ITEM_CATEGORIES_CSV,
    FOCUS_REQUIRED,
    FOCUS_WINDOW_TITLES,
)

from market_json_manager import (
    correct_item_name as mjm_correct_item_name,
    get_all_item_names,
    get_item_id_by_name as mjm_get_item_id_by_name,
    get_item_registry,
)
from bdo_api_client import get_item_price_range

# -----------------------
# Performance: Screenshot-Hash-Caching (50-80% Reduktion bei statischen Screens)
# -----------------------
_screenshot_cache = {}  # {hash: (timestamp, ocr_result, cache_hits)}
_cache_lock = threading.Lock()
# Performance optimization: Increased cache parameters for better hit rate
# Market window changes infrequently, so longer TTL is safe
CACHE_TTL = 5.0  # Sekunden - Cache-Einträge sind 5s gültig (was 2.0s)
MAX_CACHE_SIZE = 20  # Maximal 20 verschiedene Screenshots im Cache (was 10)
# Expected improvement: Cache hit rate from ~50% to >70%

def log_text(text):
    """Logging mit automatischer Rotation bei 10MB Limit (Performance: verhindert unbegrenztes Wachstum)"""
    try:
        # Prüfe Dateigröße vor dem Schreiben
        if os.path.exists(LOG_PATH):
            size = os.path.getsize(LOG_PATH)
            if size > 10 * 1024 * 1024:  # 10 MB Limit
                # Rotate: .txt → .txt.old (überschreibt alte Rotation)
                try:
                    os.rename(LOG_PATH, f"{LOG_PATH}.old")
                except Exception:
                    # Falls rename fehlschlägt, versuche zu löschen
                    try:
                        os.remove(LOG_PATH)
                    except Exception:
                        pass
        
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now().isoformat()}:\n{text}\n\n")
    except Exception:
        pass

def log_debug(message: str):
    """Append a debug line to ocr_log.txt with timestamp (for development diagnostics)."""
    try:
        ts = datetime.datetime.now().isoformat()
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{ts} [DEBUG] {message}\n")
    except Exception:
        pass


def _get_foreground_window_title_windows() -> str:
    """Get foreground window title on Windows. Optimized with module-level imports."""
    if not _WINDOWS_MODULES_AVAILABLE:
        return ""
    
    try:
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [wintypes.HWND, ctypes.c_wchar_p, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int

        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""

        length = user32.GetWindowTextLengthW(hwnd)
        buffer_length = max(0, length) + 2
        buf = ctypes.create_unicode_buffer(buffer_length)
        user32.GetWindowTextW(hwnd, buf, buffer_length)
        return buf.value.strip()
    except Exception:
        return ""


def get_foreground_window_title() -> str:
    if os.name != "nt":
        return ""
    try:
        return _get_foreground_window_title_windows()
    except Exception as exc:
        log_debug(f"[FOCUS] Foreground title lookup failed: {exc}")
        return ""


def is_bdo_window_in_foreground(expected_titles: Optional[Sequence[str]] = None) -> tuple[bool, str]:
    if os.name != "nt":
        return True, ""

    titles = [t for t in (expected_titles or FOCUS_WINDOW_TITLES) if t]
    if not titles:
        return True, ""

    title = get_foreground_window_title()
    if not title:
        return False, ""

    lower_title = title.lower()
    for needle in titles:
        if needle.lower() in lower_title:
            return True, title
    return False, title

def capture_region(region):
    x1,y1,x2,y2 = region
    w,h = x2-x1, y2-y1
    with mss.mss() as sct:
        mon = {"left": x1, "top": y1, "width": w, "height": h}
        sct_img = sct.grab(mon)
        arr = np.array(sct_img)  # BGRA
        img = cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
    return img

def detect_log_roi(img):
    """
    Erkennt die Log-Region (ROI) im Market-Window.
    Gibt (x, y, w, h) zurück oder None bei Fehler.
    Die Log-Region ist typischerweise im unteren Bereich des Fensters.
    """
    try:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        
        # Heuristik: Log ist typischerweise in der unteren Hälfte
        # und hat charakteristische horizontale Linien/Strukturen
        # Für BDO: Die Log-Einträge sind im unteren 60% Bereich
        roi_y_start = int(h * 0.3)  # Skip top 30% (Header/Navigation)
        roi_y_end = h
        roi_x_start = 0
        roi_x_end = w
        
        # Optional: Erkenne Text-Regionen für präzisere ROI
        # (Hier simple Heuristik, kann erweitert werden)
        
        return (roi_x_start, roi_y_start, roi_x_end - roi_x_start, roi_y_end - roi_y_start)
    except Exception:
        return None

def preprocess(img, adaptive=True, denoise=False):
    """
    Verbessertes Preprocessing optimiert für Game-UIs wie BDO.
    
    Args:
        img: Input image (BGR oder Grayscale)
        adaptive: Nutze sanfte CLAHE-Kontrastverstärkung (empfohlen für UIs)
        denoise: Wende Noise-Reduction an (meist nicht nötig bei Game-UIs)
    
    Returns:
        Preprocessed image optimiert für OCR
    """
    # Convert to grayscale
    if img.ndim == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()
    
    # 1. Optional: Noise Reduction (nur bei sehr rauschigen Screenshots)
    if denoise:
        gray = cv2.fastNlMeansDenoising(gray, h=7, templateWindowSize=7, searchWindowSize=21)
    
    # 2. Sanfte Kontrast-Verbesserung mit CLAHE
    # Game UIs haben meist schon guten Kontrast - nur leicht verstärken
    if adaptive:
        clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8,8))
        gray = clahe.apply(gray)
    
    # 3. Sanfte Schärfung (weniger aggressiv als vorher)
    # Für UI-Text reicht ein einfacher Schärfungskernel
    kernel_sharp = np.array([
        [0, -0.5, 0],
        [-0.5, 3, -0.5],
        [0, -0.5, 0]
    ])
    sharpened = cv2.filter2D(gray, -1, kernel_sharp)
    
    # 4. Leichte Helligkeit/Kontrast-Anpassung
    # Alpha=1.2 (Kontrast), Beta=10 (Helligkeit)
    enhanced = cv2.convertScaleAbs(sharpened, alpha=1.2, beta=10)
    
    # 5. KEINE aggressive Binarisierung für Game-UIs!
    # EasyOCR funktioniert besser mit Graustufen-Bildern
    # Nur leichtes Thresholding um sehr dunkle/helle Bereiche zu normalisieren
    # (Optional - auskommentiert, da meist nicht nötig)
    # _, enhanced = cv2.threshold(enhanced, 30, 255, cv2.THRESH_TOZERO)
    
    # 6. Optional: Größen-Normalisierung nur wenn Bild zu klein
    h, w = enhanced.shape
    if h < 500:  # Nur bei sehr kleinen Bildern skalieren
        scale = 500 / h
        new_w = int(w * scale)
        enhanced = cv2.resize(enhanced, (new_w, 500), interpolation=cv2.INTER_CUBIC)
    
    return enhanced

def extract_text(img, use_roi=True, method='easyocr'):
    """
    OCR mit verbesserter Konfiguration.
    
    Args:
        img: Preprocessed image
        use_roi: Nutze ROI-Detection für Log-Region
        method: 'easyocr', 'tesseract', or 'both' (beide versuchen und längeres Ergebnis nehmen)
    
    Returns:
        Extracted text string
    """
    # Optional: ROI-Detection
    target_img = img
    if use_roi and img.ndim >= 2:
        roi = detect_log_roi(img)
        if roi:
            x, y, w, h = roi
            target_img = img[y:y+h, x:x+w]
    
    result_easy = ""
    result_tess = ""
    ocr_confidence = None
    
    # EasyOCR mit balancierten Parametern (optimiert für Game-UIs)
    if method in ['easyocr', 'both']:
        try:
            if USE_EASYOCR and reader is not None:
                # Convert to RGB
                if target_img.ndim == 2:
                    rgb = cv2.cvtColor(target_img, cv2.COLOR_GRAY2RGB)
                elif target_img.shape[2] == 4:
                    rgb = cv2.cvtColor(target_img, cv2.COLOR_BGRA2RGB)
                else:
                    rgb = cv2.cvtColor(target_img, cv2.COLOR_BGR2RGB)
                
                # Balancierte EasyOCR-Parameter (nicht zu aggressiv)
                # Game-UIs haben meist klaren Text - Standard-Parameter funktionieren oft besser
                # detail=1 gibt uns (bbox, text, confidence) zurück
                res_with_conf = reader.readtext(
                    rgb,
                    detail=1,
                    paragraph=True,
                    contrast_ths=0.3,        # Erhöht von 0.1 - weniger False Positives
                    adjust_contrast=0.5,     # Kontrast-Anpassung
                    text_threshold=0.7,      # Standard (war zu niedrig bei 0.6)
                    low_text=0.4,            # Standard (war zu niedrig bei 0.3)
                    link_threshold=0.4,      # Standard (war zu niedrig bei 0.3)
                    canvas_size=2560,        # Gut für Details
                    mag_ratio=1.0            # Kein Zoom (war zu hoch bei 1.5)
                )
                
                # Extrahiere Text und berechne durchschnittliche Confidence
                # ROBUST: EasyOCR gibt manchmal nur 2 Werte zurück statt 3
                texts = []
                confidences = []
                for entry in res_with_conf:
                    try:
                        if len(entry) == 3:
                            # Standard: (bbox, text, confidence)
                            bbox, text, conf = entry
                            texts.append(text)
                            confidences.append(conf)
                        elif len(entry) == 2:
                            # Fallback: (bbox, text) ohne Confidence
                            bbox, text = entry
                            texts.append(text)
                            # Kein Confidence-Wert verfügbar
                        else:
                            # Unerwartetes Format - überspringe
                            log_debug(f"⚠️ Unexpected EasyOCR entry format: {len(entry)} values")
                            continue
                    except Exception as parse_err:
                        log_debug(f"⚠️ Error parsing EasyOCR entry: {parse_err}")
                        continue
                
                result_easy = " ".join(texts)
                if confidences:
                    ocr_confidence = sum(confidences) / len(confidences)
                    # Logge Confidence
                    log_debug(f"EasyOCR confidence: avg={ocr_confidence:.3f}, min={min(confidences):.3f}, max={max(confidences):.3f}, blocks={len(confidences)}")
                    if ocr_confidence < 0.5:
                        log_debug(f"⚠️ LOW CONFIDENCE: {ocr_confidence:.3f} - OCR may be unreliable")
                elif texts:
                    # Texte gefunden, aber keine Confidence-Werte
                    log_debug(f"EasyOCR extracted {len(texts)} text blocks (no confidence data)")
        except Exception as e:
            log_debug(f"EasyOCR error: {e}")
    
    # Tesseract mit Whitelist und PSM
    if method in ['tesseract', 'both']:
        try:
            # Whitelist: Nur erlaubte Zeichen (reduziert Fehler massiv)
            # Erlaubt: Buchstaben, Zahlen, Leerzeichen, und wichtige Sonderzeichen
            whitelist = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ .,':x-()[]/"
            
            # PSM 6 = Uniform block of text (am besten für Log-Einträge)
            # OEM 3 = Default (LSTM + Legacy)
            config = f'--psm 6 --oem 3 -c tessedit_char_whitelist="{whitelist}"'
            
            if target_img.ndim == 2:
                pil = Image.fromarray(target_img)
            else:
                pil = Image.fromarray(cv2.cvtColor(target_img, cv2.COLOR_BGR2RGB))
            
            result_tess = pytesseract.image_to_string(pil, config=config)
        except Exception as e:
            log_debug(f"Tesseract error: {e}")
    
    # Bei 'both': Nimm das längere/bessere Ergebnis
    final_result = ""
    if method == 'both':
        if len(result_easy) > len(result_tess):
            final_result = result_easy
            log_debug(f"Using EasyOCR result (longer: {len(result_easy)} vs {len(result_tess)})")
        else:
            final_result = result_tess if result_tess else result_easy
            log_debug(f"Using Tesseract result (longer: {len(result_tess)} vs {len(result_easy)})")
    elif method == 'easyocr':
        final_result = result_easy
    else:
        final_result = result_tess
    
    # Logge finale OCR-Statistiken
    if final_result:
        log_debug(f"OCR complete: method={method}, length={len(final_result)}, confidence={ocr_confidence if ocr_confidence else 'N/A'}")
    
    return final_result

def ocr_image_cached(img, method='easyocr', use_roi=True, preprocessed=None):
    """Run OCR on a pre-captured image with cache support."""
    global _screenshot_cache

    # Determine hash for cache lookup (ROI-based when available)
    hash_img = img
    if use_roi:
        roi = detect_log_roi(img)
        if roi:
            x, y, w, h = roi
            hash_img = img[y:y+h, x:x+w]

    now = time.time()
    try:
        img_hash = hashlib.md5(hash_img.tobytes()).hexdigest()
    except Exception:
        img_hash = str(now)

    with _cache_lock:
        entry = _screenshot_cache.get(img_hash)
        if entry:
            cached_time, cached_result, cache_hits = entry
            if now - cached_time < CACHE_TTL:
                _screenshot_cache[img_hash] = (cached_time, cached_result, cache_hits + 1)
                cache_stats = {
                    'cache_hit': True,
                    'cache_age': now - cached_time,
                    'cache_hits': cache_hits + 1,
                    'cache_size': len(_screenshot_cache),
                    'hit_rate': 0.0,
                }
                log_debug(f"[CACHE HIT] Hash={img_hash[:8]}... age={cache_stats['cache_age']:.2f}s hits={cache_stats['cache_hits']}")
                return cached_result, True, cache_stats
            # Expired entry → remove to allow refresh
            del _screenshot_cache[img_hash]

    # Cache miss: perform preprocessing/OCR outside of cache lock
    if preprocessed is None:
        preprocessed = preprocess(img)

    result = extract_text(preprocessed, use_roi=use_roi, method=method)

    with _cache_lock:
        _screenshot_cache[img_hash] = (now, result, 0)
        if len(_screenshot_cache) > MAX_CACHE_SIZE:
            oldest_hash = min(_screenshot_cache.items(), key=lambda x: x[1][0])[0]
            del _screenshot_cache[oldest_hash]
            log_debug(f"[CACHE] Evicted oldest entry (cache size: {len(_screenshot_cache)})")
        cache_stats = {
            'cache_hit': False,
            'cache_age': 0,
            'cache_hits': 0,
            'cache_size': len(_screenshot_cache),
            'hit_rate': 0.0,
        }

    log_debug(f"[CACHE MISS] Hash={img_hash[:8]}... cached new result (size={len(result)} chars)")
    return result, False, cache_stats


def capture_and_ocr_cached(region, method='easyocr', use_roi=True):
    """Capture a region and run cached OCR (thread-safe)."""
    img = capture_region(region)
    return ocr_image_cached(img, method=method, use_roi=use_roi)

def get_cache_stats():
    """Gibt Cache-Statistiken zurück für Monitoring/Debugging."""
    global _screenshot_cache
    with _cache_lock:
        if not _screenshot_cache:
            return {'total_entries': 0, 'total_hits': 0, 'hit_rate': 0.0}

        total_entries = len(_screenshot_cache)
        total_hits = sum(hits for _, _, hits in _screenshot_cache.values())
        total_requests = total_hits + total_entries  # Jeder Eintrag = 1 Miss + N Hits
        hit_rate = (total_hits / total_requests * 100) if total_requests > 0 else 0.0

        return {
            'total_entries': total_entries,
            'total_hits': total_hits,
            'total_requests': total_requests,
            'hit_rate': hit_rate
        }

def clear_cache():
    """Leert den Screenshot-Cache (nützlich für Tests/Debugging)."""
    global _screenshot_cache
    with _cache_lock:
        _screenshot_cache.clear()
    log_debug("[CACHE] Cleared all cache entries")

def normalize_numeric_str(s):
    """Ersetze häufige OCR-Fehler und parse int."""
    if not s:
        return None
    # CRITICAL FIX: Remove whitespace FIRST to handle OCR errors like "585, 585, OO0" (spaces between digits)
    s = s.replace(' ', '')
    # map confusables
    mapped = "".join(LETTER_TO_DIGIT.get(ch, ch) for ch in s)
    cleaned = re.sub(r'[^0-9,\.]', '', mapped)
    if cleaned == "":
        return None
    cleaned = cleaned.replace(',', '').replace('.', '')
    try:
        return int(cleaned)
    except:
        return None

def clean_item_name(raw):
    if not raw:
        return ""
    raw = re.sub(r'^(?:transaction\s*of|listed\s*|placed\s*order\s*of|withdrew\s*order\s*of|withdrew|placed)\s*', '', raw, flags=re.I)
    # Keep common punctuation used in item names like colon and parentheses
    raw = re.sub(r"[^A-Za-z0-9\s'\-:\(\)]", ' ', raw)
    if any(ch.isdigit() for ch in raw):
        raw = "".join(DIGIT_TO_LETTER.get(ch, ch) for ch in raw)
    raw = re.sub(r'\s+', ' ', raw).strip()
    # reject trivial garbage like 'ooo' after cleaning
    if not re.search(r'[A-Za-z].*[A-Za-z]', raw):
        return ""
    # make nicer capitalization
    return raw.title()

class MarketDataProxy:
    """Lazy API-backed view that exposes min/max prices per item using market.json."""

    def __init__(self) -> None:
        registry = get_item_registry()
        # Map lowercase name → (canonical name, item_id)
        self._entries: Dict[str, tuple[str, str]] = {
            name.lower(): (name, str(item_id)) for name, item_id in registry.items()
        }
        self._cache: Dict[str, Dict[str, int]] = {}

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, item_name: object) -> bool:
        if not isinstance(item_name, str):
            return False
        return item_name.lower() in self._entries

    def _fetch(self, key: str) -> Dict[str, int]:
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        entry = self._entries.get(key)
        if entry is None:
            raise KeyError(key)

        canonical_name, item_id = entry
        price_data = get_item_price_range(item_id)
        if not price_data:
            raise KeyError(key)

        record = {
            'item_name': canonical_name,
            'item_id': item_id,
            'min_price': price_data['min_price'],
            'max_price': price_data['max_price'],
            'base_price': price_data.get('base_price'),
        }
        self._cache[key] = record
        return record

    def __getitem__(self, item_name: str) -> Dict[str, int]:
        if not isinstance(item_name, str):
            raise KeyError(item_name)
        key = item_name.lower()
        return self._fetch(key)

    def get(self, item_name: str, default: Optional[Dict[str, int]] = None) -> Optional[Dict[str, int]]:
        try:
            return self[item_name]
        except KeyError:
            return default

    def keys(self) -> Iterator[str]:
        for canonical, _ in self._entries.values():
            yield canonical

    def __iter__(self) -> Iterator[str]:
        return self.keys()

    def items(self) -> Iterator[tuple[str, Dict[str, int]]]:
        for canonical, _ in self._entries.values():
            yield canonical, self[canonical]


@lru_cache(maxsize=1)
def _load_market_data() -> MarketDataProxy:
    """Return a lazy proxy that resolves item prices through the BDO API."""
    return MarketDataProxy()


@lru_cache(maxsize=1)
def _load_item_names():
    """Return sorted list of known item names sourced from market.json."""
    try:
        names = get_all_item_names()
        return sorted(names)
    except Exception as exc:
        print(f"Warning: Failed to load item names from market.json: {exc}")
        return []

@lru_cache(maxsize=1)  # File content doesn't change, cache permanently
def _load_item_categories():
    """Lade Item-Kategorien (most_likely_buy/most_likely_sell) aus CSV.
    Returns: dict {item_name: 'buy' oder 'sell'}
    """
    categories = {}
    try:
        with open(ITEM_CATEGORIES_CSV, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader, None)  # Skip header
            for row in reader:
                if len(row) < 2:
                    continue
                item_name = row[0].strip()
                category = row[1].strip().lower()
                if 'buy' in category:
                    categories[item_name] = 'buy'
                elif 'sell' in category:
                    categories[item_name] = 'sell'
    except Exception:
        pass
    return categories

def get_item_likely_type(item_name: str) -> str:
    """Gibt zurück: 'buy', 'sell', oder None (wenn nicht in Liste).
    Nutze dies für historische Transaktionen ohne Kontext-Anker.
    """
    if not item_name:
        return None
    categories = _load_item_categories()
    # Normalize apostrophes (OCR produces different variants: ' vs ' vs `)
    def normalize_apostrophe(s):
        return s.replace("'", "'").replace("`", "'").replace("'", "'") if s else s
    
    item_normalized = normalize_apostrophe(item_name)
    # Exakter Match (mit Apostroph-Normalisierung)
    if item_normalized in categories:
        return categories[item_normalized]
    
    # Case-insensitive Match (mit Apostroph-Normalisierung)
    item_lower = item_normalized.lower()
    for known_item, cat in categories.items():
        if normalize_apostrophe(known_item).lower() == item_lower:
            return cat
    return None

def check_price_plausibility(item_name: str, quantity: int, total_price: int) -> dict:
    """
    Prüft ob der Gesamtpreis für ein Item plausibel ist basierend auf Market-Data.
    
    Args:
        item_name: Name des Items
        quantity: Menge (Stückzahl)
        total_price: Gesamtpreis (für alle Stücke)
    
    Returns:
        dict with keys:
            'plausible': bool - Ist der Preis plausibel?
            'unit_price': int - Berechneter Stückpreis
            'expected_min': int - Erwarteter Min-Gesamtpreis
            'expected_max': int - Erwarteter Max-Gesamtpreis
            'reason': str - Grund (z.B. "too_low", "too_high", "ok", "no_data")
    """
    result = {
        'plausible': True,
        'unit_price': total_price / quantity if quantity > 0 else 0,
        'expected_min': None,
        'expected_max': None,
        'reason': 'no_data'
    }
    
    if not item_name or quantity <= 0 or total_price is None:
        result['plausible'] = False
        result['reason'] = 'invalid_input'
        return result

    item_id = mjm_get_item_id_by_name(item_name, fuzzy=True)
    if not item_id:
        result['plausible'] = False
        result['reason'] = 'no_data'
        return result

    price_data = get_item_price_range(str(item_id))
    if not price_data:
        result['plausible'] = False
        result['reason'] = 'api_error'
        return result

    min_unit_price = price_data['min_price']
    max_unit_price = price_data['max_price']

    expected_min_total = min_unit_price * quantity
    expected_max_total = max_unit_price * quantity

    result['expected_min'] = expected_min_total
    result['expected_max'] = expected_max_total

    unit_price = total_price / quantity
    result['unit_price'] = unit_price

    tolerance = 0.1
    min_with_tolerance = min_unit_price * (1 - tolerance)
    max_with_tolerance = max_unit_price * (1 + tolerance)

    if unit_price < min_with_tolerance:
        result['plausible'] = False
        result['reason'] = 'too_low'
    elif unit_price > max_with_tolerance:
        result['plausible'] = False
        result['reason'] = 'too_high'
    else:
        result['plausible'] = True
        result['reason'] = 'ok'

    return result

@lru_cache(maxsize=500)  # Performance: Cache corrected item names (50-70% faster on repeated items)
def correct_item_name(name: str, min_score: int = 86) -> str:
    """
    Korrigiert einen Itemnamen per Fuzzy-Matching gegen market.json Whitelist.
    
    NEUE IMPLEMENTIERUNG (seit 2025-10-12):
    - Nutzt market.json statt market_data.csv
    - Gleiche Fuzzy-Logik mit RapidFuzz
    - Exakte Matches haben Vorrang
    
    Args:
        name: OCR'd item name
        min_score: Minimum fuzzy match score (0-100)
        
    Returns:
        Corrected item name or original if no good match
    """
    if not name:
        return name
    
    corrected_name, _ = mjm_correct_item_name(name, min_score=min_score)
    return corrected_name

def parse_timestamp_text(ts_text):
    """Parst Strings wie '2025.10.09 10:13' oder '2025-10-09 10:13' (tolerant gegenüber OCR-Fehlern) -> datetime.
    Nutzt nur Spiel-Zeitstempel; kein Fallback auf Systemzeit.
    """
    if not ts_text:
        return None
    s = ts_text.strip()
    # map common OCR confusables to digits
    extra_map = {'C': '0', 'c': '0', 'T': '7'}
    mapping = {**LETTER_TO_DIGIT, **extra_map}
    s = ''.join(mapping.get(ch, ch) for ch in s)
    # keep plausible timestamp chars
    s = re.sub(r'[^0-9\-\.:,/\s]', '', s)
    # normalize only date separators (don't break time like 17.34)
    s = s.replace('/', '-')
    # allow comma as time separator (OCR often misreads : as ,)
    s = s.replace(',', ':')
    # find YYYY[-/./ or space]MM[-/.]DD HH[: or . or -]MM[:SS]
    m = re.search(r'(20\d{2})[\-\./\s](\d{2})[\-\./](\d{2})\s+(\d{2})[\.:,\-](\d{2})(?::(\d{2}))?', s)
    if not m:
        return None
    try:
        y, mo, d, hh, mm, ss = m.groups()
        return datetime.datetime(int(y), int(mo), int(d), int(hh), int(mm), int(ss) if ss else 0)
    except Exception:
        return None

def find_all_timestamps(text):
    """
    Findet alle Timestamp-Vorkommen (Position, text).
    Format erwartet: 20YY.MM.DD hh:mm oder mit - oder /
    """
    pattern = re.compile(r'20\d{2}[.\-/\s]\d{2}[.\-/]\d{2}\s+\d{2}[:\.,\-]\d{2}')
    res = []
    for m in pattern.finditer(text):
        res.append((m.start(), m.group(0)))
    return res

def detect_tab_from_text(text):
    s = text.lower()
    # prefer the last occurrence: if both present, whichever appears later
    sell_pos = [m.start() for m in re.finditer(r'sales\s+completed', s)]
    buy_pos = [m.start() for m in re.finditer(r'orders\s+completed', s)]
    if not sell_pos and not buy_pos:
        return "unknown"
    last_sell = sell_pos[-1] if sell_pos else -1
    last_buy = buy_pos[-1] if buy_pos else -1
    return "sell" if last_sell > last_buy else "buy"

def detect_window_type(ocr_text: str) -> str:
    """Erkennt eines der 4 Marktfenster anhand von OCR-Keywords (tolerant gegenüber Newlines/OCR-Fehlern).
    Rückgabe: 'sell_overview' | 'buy_overview' | 'sell_item' | 'buy_item' | 'unknown'
    Regeln:
    - sell_overview: 'Sales Completed' (Whitespace/Zeilenumbrüche tolerant, Completed/Complete/Completion akzeptiert)
    - buy_overview: 'Orders Completed' (dito)
    - sell_item: BEIDE 'Set Price' UND 'Register Quantity' (Whitespace tolerant)
    - buy_item: BEIDE 'Desired Price' UND 'Desired Amount' (Whitespace tolerant)
    """
    if not ocr_text:
        return "unknown"
    s = ocr_text.lower()
    # normalisiere Whitespace, damit "sales\ncompleted" erkannt wird
    s_norm = re.sub(r"\s+", " ", s)

    def has_all(substrings):
        return all(sub.lower() in s_norm for sub in substrings)

    # Detail-Fenster zuerst prüfen (strengere Regel: beide Keywords nötig)
    if has_all(["set price", "register quantity"]):
        return "sell_item"
    if has_all(["desired price", "desired amount"]):
        return "buy_item"

    # Overview-Fenster (fuzzy Completed-Erkennung)
    # comp(?:l|1|i)et(?:e|ed|ion)s? → completed/complete/completion
    # pl?et(?:e|ed|ion)s? → plet/pleted (OCR-Fehler wenn 'com' verschwindet)
    sell_pat = re.compile(r"sa?les?\s+(?:comp(?:l|1|i)et(?:e|ed|ion)s?|pl?et(?:e|ed|ion)s?)", re.IGNORECASE)
    buy_pat = re.compile(r"orders?\s+(?:comp(?:l|1|i)et(?:e|ed|ion)s?|pl?et(?:e|ed|ion)s?)", re.IGNORECASE)
    
    # WICHTIG: Die Screen-Region erfasst das KOMPLETTE Marktfenster!
    # Es ist IMMER nur EIN Tab sichtbar (entweder Buy ODER Sell, nie beide gleichzeitig)
    # "Sales Completed" sichtbar → 100% sell_overview (Sell-Tab ist aktiv)
    # "Orders Completed" sichtbar → 100% buy_overview (Buy-Tab ist aktiv)
    
    # Straightforward detection: Nur ein Pattern kann matchen
    if sell_pat.search(s_norm):
        return "sell_overview"
    if buy_pat.search(s_norm):
        return "buy_overview"
    
    # Fallback-Heuristik: Header fehlt (cropping), aber Log-Inhalt vorhanden
    # Wenn es Timestamps gibt und typische Log-Keywords, werten wir als Overview
    try:
        has_ts = bool(find_all_timestamps(ocr_text))
    except Exception:
        has_ts = False
    if has_ts:
        # Buy-Anchor zuerst (purchased/bought/order placed)
        if re.search(r"\b(placed\s+order|purchased?|bought|withdrew\s+order)\b", s_norm, re.IGNORECASE):
            return "buy_overview"
        # Sell-Anchor: listed/relisted
        if re.search(r"\b(listed|relisted)\b", s_norm, re.IGNORECASE):
            return "sell_overview"
    return "unknown"
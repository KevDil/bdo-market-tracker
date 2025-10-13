import os
import pytesseract
import easyocr

# -----------------------
# Konfiguration
# -----------------------
TESS_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
pytesseract.pytesseract.tesseract_cmd = TESS_PATH
USE_EASYOCR = True
DB_PATH = "bdo_tracker.db"
LOG_PATH = "ocr_log.txt"
DEFAULT_REGION = (734, 371, 1823, 1070)
POLL_INTERVAL = 0.3  # 0.3s = ~99 scans/min (GPU cached), erfasst >95% der Transaktionen
MARKET_DATA_CSV = "config/market_data.csv"  # DEPRECATED - Jetzt über BDO World Market API
ITEM_CATEGORIES_CSV = "config/item_categories.csv"  # most_likely_buy/sell für Historical Detection

# Window focus guard: prevent OCR when the game window is not active
FOCUS_REQUIRED = True
FOCUS_WINDOW_TITLES = [
    "Black Desert",
    "BLACK DESERT -",
]

# -----------------------
# Async Pipeline Feature Flag
# -----------------------
USE_ASYNC_PIPELINE = True
ASYNC_QUEUE_MAXSIZE = max(1, int(os.getenv('ASYNC_QUEUE_MAXSIZE', '3') or '3'))
ASYNC_WORKER_COUNT = max(1, int(os.getenv('ASYNC_WORKER_COUNT', '1') or '1'))

# -----------------------
# Performance: GPU-Optimierung (Game-Friendly)
# -----------------------
# Aktuelle Config (RTX 4070 SUPER):
#   - GPU_MEMORY_LIMIT = 2048 MB (2GB VRAM für OCR, 10GB für Spiel)
#   - GPU_LOW_PRIORITY = True (Spiel-Rendering hat Vorrang)
#   - Screenshot-Hash-Cache = 50% Hit-Rate → ~1000ms avg OCR
#   - Throughput: ~99 scans/minute (GPU cached) vs ~60 scans/min (CPU)
#   - Memory: Stabil bei ~80MB (deque maxlen=1000)
#   - Log-Rotation: Auto @ 10MB
#
# Empfohlene Werte (POLL_INTERVAL):
#   0.3s = Sehr schnell, ~99 scans/min (aktuell, empfohlen)
#   0.5s = Balanciert, ~83 scans/min
#   1.0s = Langsamer aber sanfter, ~40 scans/min
# 
# Alternative für ältere GPUs: USE_GPU = False + Cache = 0 Ruckler, ~83 scans/min
GAME_FRIENDLY_MODE = False  # True = Längeres Interval (0.8s) bei GPU-Modus

# -----------------------
# OCR-Tuning-Parameter (V2 - Game-UI-Optimiert)
# -----------------------
# Diese Parameter können in utils.py angepasst werden:
#
# EasyOCR-Parameter (balanciert für Game-UIs):
#   - contrast_ths=0.3        # Balanciert (NICHT < 0.3 → Müll!)
#   - text_threshold=0.7      # Standard (NICHT < 0.7 → False Positives!)
#   - low_text=0.4            # Standard
#   - link_threshold=0.4      # Standard
#   - canvas_size=2560        # Gut für Details
#   - mag_ratio=1.0           # Kein Zoom (Original-Größe)
#
# Preprocessing-Parameter (sanft für Game-UIs):
#   - adaptive=True           # CLAHE-Kontrastverstärkung (sanft!)
#   - denoise=False           # Deaktiviert (Game-UIs nicht verrauscht)
#   - CLAHE clipLimit=1.5     # Sanft (NICHT > 2.0)
#   - KEINE Binarisierung!    # Zerstört UI-Text komplett
#
# Tesseract-Whitelist (Fallback-Engine):
#   "0-9a-zA-Z .,':x-()[]/"
#   Bei Bedarf erweitern
#
# ROI-Detection (Log-Region):
#   roi_y_start = int(h * 0.3)  # Log bei 30%-100% der Höhe
#
# ⚠️ WICHTIG: Zu aggressive Parameter (Binarisierung, niedrige Thresholds)
#            zerstören die OCR-Qualität bei Game-UIs komplett!

# Item quantity bounds (configurable)
# Minimum: 1 (no zero/negative quantities)
# Maximum: 5000 (typical max stack sizes in BDO; filters UI noise like collect amounts)
MIN_ITEM_QUANTITY = 1
MAX_ITEM_QUANTITY = 5000

# -----------------------
# Performance: GPU-Acceleration für EasyOCR
# -----------------------
# GPU kann OCR um 60-75% beschleunigen (1.5s → 0.5s pro Scan)
# Erfordert: CUDA-fähige NVIDIA GPU + CUDA Toolkit + cuDNN
# 
# ⚠️ WICHTIG: GPU-Modus kann Game-Performance beeinflussen (Ruckler beim Screenshot)!
# Ursache: Spiel und OCR konkurrieren um GPU-Ressourcen
# Lösungen:
#   1. USE_GPU = False         → CPU-only (langsamer, aber keine Game-Ruckler)
#   2. GPU_MEMORY_LIMIT = 2048 → Limitiert VRAM-Nutzung (MB)
#   3. GPU_LOW_PRIORITY = True → OCR bekommt niedrige GPU-Priorität
USE_GPU = True  # ⚠️ Auf True setzen wenn GPU verfügbar UND Game-Ruckler akzeptabel

# GPU-Memory-Limit (MB) - Reduziert VRAM-Nutzung, verhindert Konkurrenz mit Spiel
# Empfohlen: 2048-4096 MB (2-4 GB) für RTX 4070
# None = kein Limit (nutzt soviel wie nötig)
GPU_MEMORY_LIMIT = 2048  # MB VRAM für OCR

# GPU Low-Priority Mode - OCR bekommt niedrige GPU-Priorität
# True = Spiel hat Vorrang, OCR läuft im Hintergrund
# False = Normale Priorität (kann Spiel beeinflussen)
GPU_LOW_PRIORITY = True

# OCR reader (EasyOCR) mit optimierten Parametern
reader = None
if USE_EASYOCR:
    cpu_retry = False
    
    # Try to free up memory before initialization
    import gc
    gc.collect()
    
    try:
        # Initialisiere EasyOCR mit optimierten Settings
        # Versuche erst GPU, fallback auf CPU
        gpu_available = USE_GPU
        
        # Test ob GPU verfügbar ist
        if USE_GPU:
            try:
                import torch
                gpu_available = torch.cuda.is_available()
                if gpu_available:
                    try:
                        print(f"[GPU] Detected: {torch.cuda.get_device_name(0)}")
                    except UnicodeEncodeError:
                        print(f"GPU detected: {torch.cuda.get_device_name(0)}")
                    
                    # GPU-Memory-Limit setzen (verhindert VRAM-Konkurrenz mit Spiel)
                    if GPU_MEMORY_LIMIT:
                        try:
                            total_mem = torch.cuda.get_device_properties(0).total_memory
                            fraction = min(1.0, max(0.0, (GPU_MEMORY_LIMIT * 1024 * 1024) / float(total_mem)))
                            torch.cuda.set_per_process_memory_fraction(fraction, device=0)
                            try:
                                print(f"   GPU Memory Limit: {GPU_MEMORY_LIMIT} MB")
                            except UnicodeEncodeError:
                                print(f"GPU Memory Limit: {GPU_MEMORY_LIMIT} MB")
                        except Exception as mem_err:
                            try:
                                print(f"   [WARNING] Could not set memory limit: {mem_err}")
                            except UnicodeEncodeError:
                                print(f"Could not set memory limit: {mem_err}")
                    
                    # Low-Priority Mode für OCR (Spiel hat Vorrang)
                    if GPU_LOW_PRIORITY:
                        try:
                            torch.cuda.set_stream(torch.cuda.Stream(priority=-1))
                            try:
                                print(f"   GPU Priority: Low (game has priority)")
                            except UnicodeEncodeError:
                                print(f"GPU Priority: Low (game has priority)")
                        except Exception as prio_err:
                            try:
                                print(f"   [WARNING] Could not set priority: {prio_err}")
                            except UnicodeEncodeError:
                                print(f"Could not set priority: {prio_err}")
                    
                else:
                    try:
                        print("[WARNING] GPU requested but CUDA not available, falling back to CPU")
                    except UnicodeEncodeError:
                        print("GPU requested but CUDA not available, falling back to CPU")
            except Exception:
                try:
                    print("[WARNING] PyTorch/CUDA not found, falling back to CPU")
                except UnicodeEncodeError:
                    print("PyTorch/CUDA not found, falling back to CPU")
                gpu_available = False
        
        # Use download_enabled=False to avoid network issues during init
        # Use model_storage_directory to cache models
        reader = easyocr.Reader(
            ['en'], 
            gpu=gpu_available,
            verbose=False,
            quantize=not gpu_available,  # Quantize nur bei CPU (GPU braucht es nicht)
            cudnn_benchmark=gpu_available,  # cuDNN-Optimierung bei GPU
            download_enabled=True,  # Allow model downloads if needed
            detector=True,
            recognizer=True
        )
        
        mode = "GPU" if gpu_available else "CPU"
        try:
            print(f"[OK] EasyOCR initialized ({mode} mode)")
        except UnicodeEncodeError:
            print(f"EasyOCR initialized ({mode} mode)")
        
    except Exception as e:
        attempted_mode = "GPU" if USE_GPU else "CPU"
        error_msg = str(e)
        try:
            print(f"[ERROR] EasyOCR init error ({attempted_mode} mode): {error_msg}")
        except UnicodeEncodeError:
            print(f"EasyOCR init error ({attempted_mode} mode): {error_msg}")
        
        # Check if it's a memory error
        is_memory_error = 'not enough memory' in error_msg.lower() or 'out of memory' in error_msg.lower()
        
        reader = None
        if USE_GPU and not is_memory_error:
            # Only retry without GPU if it's not a general memory issue
            cpu_retry = True
            USE_GPU = False
            gpu_available = False
            try:
                print("[WARNING] Retrying EasyOCR initialization without GPU ...")
            except UnicodeEncodeError:
                print("Retrying EasyOCR initialization without GPU ...")
        elif is_memory_error:
            try:
                print("[WARNING] Memory error detected - EasyOCR initialization skipped")
                print("[WARNING] Falling back to Tesseract-only mode")
            except UnicodeEncodeError:
                print("Memory error detected - using Tesseract only")
            cpu_retry = False  # Don't retry if memory is the issue
    
    if reader is None and cpu_retry:
        try:
            import torch
        except Exception:
            torch = None
        try:
            reader = easyocr.Reader(
                ['en'],
                gpu=False,
                verbose=False,
                quantize=True,
                cudnn_benchmark=False
            )
            try:
                print("[OK] EasyOCR initialized (CPU fallback)")
            except UnicodeEncodeError:
                print("EasyOCR initialized (CPU fallback)")
        except Exception as cpu_err:
            try:
                print(f"[ERROR] EasyOCR CPU fallback error: {cpu_err}")
            except UnicodeEncodeError:
                print(f"EasyOCR CPU fallback error: {cpu_err}")
            reader = None

LETTER_TO_DIGIT = {'O':'0','o':'0','D':'0','Q':'0','I':'1','l':'1','|':'1','i':'1',
                   'S':'5','s':'5','B':'8','Z':'2','z':'2'}
DIGIT_TO_LETTER = {'0':'o','1':'l','5':'s','3':'e','4':'a','2':'z','8':'b'}
#!/usr/bin/env python3
"""
OCR Engines Module - Multi-Engine OCR Support

Unterstützt mehrere OCR-Engines:
1. PaddleOCR (primär - beste Game-UI-Performance)
2. EasyOCR (fallback)
3. Tesseract (final fallback)

Features:
- Einheitliches Interface für alle Engines
- GPU-Support (optional)
- Automatischer Fallback bei Fehlern
- Performance-Optimiert
"""

import re
import numpy as np
from typing import Optional, List, Tuple
from functools import lru_cache


# -----------------------
# Engine Initialization Status
# -----------------------
_paddle_reader = None
_paddle_available = False
_easyocr_reader = None
_easyocr_available = False


def init_paddle_ocr(use_gpu: bool = False, lang: str = 'en', show_log: bool = False) -> bool:
    """
    Initialisiert PaddleOCR mit optimierten Parametern für Game-UI.
    
    Args:
        use_gpu: GPU-Acceleration nutzen
        lang: Sprache ('en', 'de', etc.)
        show_log: Logging aktivieren
        
    Returns:
        True wenn erfolgreich initialisiert
    """
    global _paddle_reader, _paddle_available
    
    if _paddle_available and _paddle_reader is not None:
        return True
    
    try:
        from paddleocr import PaddleOCR
        
        # Initialize PaddleOCR v3.2+ mit optimierten Parametern
        # Konfiguration speziell für Game-UI (BDO) angepasst
        _paddle_reader = PaddleOCR(
            lang=lang,
            use_angle_cls=False,  # Kein Text-Rotation bei BDO-UI
            # Detection Parameters (für bessere Textblock-Erkennung)
            det_db_thresh=0.3,        # Lower threshold für bessere Detection (default: 0.3)
            det_db_box_thresh=0.5,    # Box confidence threshold (default: 0.6)
            det_db_unclip_ratio=1.6,  # Text region expansion (default: 1.5)
            # Recognition Parameters (für bessere Text-Erkennung)
            rec_batch_num=6,          # Batch processing (default: 6)
        )
        
        _paddle_available = True
        
        mode = "GPU" if use_gpu else "CPU"
        print(f"✅ PaddleOCR initialized ({mode} mode, optimized for Game-UI)")
        return True
        
    except Exception as e:
        _paddle_available = False
        print(f"⚠️  PaddleOCR initialization failed: {e}")
        return False


def init_easyocr(use_gpu: bool = False, lang: List[str] = None) -> bool:
    """
    Initialisiert EasyOCR (fallback).
    
    Args:
        use_gpu: GPU-Acceleration nutzen
        lang: Sprachen-Liste (default: ['en'])
        
    Returns:
        True wenn erfolgreich initialisiert
    """
    global _easyocr_reader, _easyocr_available
    
    if _easyocr_available and _easyocr_reader is not None:
        return True
    
    if lang is None:
        lang = ['en']
    
    try:
        import easyocr
        
        _easyocr_reader = easyocr.Reader(
            lang,
            gpu=use_gpu,
            verbose=False,
            quantize=not use_gpu,
            cudnn_benchmark=use_gpu
        )
        
        _easyocr_available = True
        
        mode = "GPU" if use_gpu else "CPU"
        print(f"✅ EasyOCR initialized ({mode} mode)")
        return True
        
    except Exception as e:
        _easyocr_available = False
        print(f"⚠️  EasyOCR initialization failed: {e}")
        return False


def ocr_with_paddle(img, confidence_threshold: float = 0.5) -> List[Tuple[str, float]]:
    """
    OCR mit PaddleOCR (optimiert für Game-UI).
    
    Args:
        img: Input image (numpy array oder PIL Image)
        confidence_threshold: Minimum confidence score (0-1) - default 0.5 für höhere Qualität
        
    Returns:
        Liste von (text, confidence) Tupeln
    """
    if not _paddle_available or _paddle_reader is None:
        return []
    
    try:
        # PaddleOCR bevorzugt RGB-Bilder (nicht Grayscale)
        # Convert grayscale to RGB if needed
        if hasattr(img, 'shape'):
            if img.ndim == 2:  # Grayscale -> RGB
                import cv2
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
            elif img.ndim == 3 and img.shape[2] == 1:  # Single-channel -> RGB
                import cv2
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
        
        # PaddleOCR expects numpy array
        if not hasattr(img, 'shape'):
            img = np.array(img)
        
        # Run OCR with optimized parameters
        result = _paddle_reader.ocr(img)
        
        if not result or not result[0]:
            return []
        
        # Format: [([[x1,y1],[x2,y2],[x3,y3],[x4,y4]], (text, confidence))]
        parsed = []
        for line in result[0]:
            if len(line) != 2:
                continue
                
            bbox, (text, conf) = line
            
            # Filter by confidence AND text quality
            if conf >= confidence_threshold and len(text.strip()) > 0:
                parsed.append((text, conf))
        
        return parsed
        
    except Exception as e:
        print(f"⚠️  PaddleOCR error: {e}")
        return []


def ocr_with_easyocr(img, confidence_threshold: float = 0.3) -> List[Tuple[str, float]]:
    """
    OCR mit EasyOCR (fallback).
    
    Args:
        img: Input image (numpy array oder PIL Image)
        confidence_threshold: Minimum confidence score (0-1)
        
    Returns:
        Liste von (text, confidence) Tupeln
    """
    if not _easyocr_available or _easyocr_reader is None:
        return []
    
    try:
        # EasyOCR expects numpy array
        if not hasattr(img, 'shape'):
            img = np.array(img)
        
        result = _easyocr_reader.readtext(img)
        
        # Format: [(bbox, text, confidence)]
        parsed = []
        for item in result:
            if len(item) != 3:
                continue
                
            bbox, text, conf = item
            
            # Filter by confidence
            if conf >= confidence_threshold:
                parsed.append((text, conf))
        
        return parsed
        
    except Exception as e:
        print(f"⚠️  EasyOCR error: {e}")
        return []


def ocr_with_tesseract(img, whitelist: Optional[str] = None) -> List[Tuple[str, float]]:
    """
    OCR mit Tesseract (final fallback).
    
    Args:
        img: Input image (numpy array oder PIL Image)
        whitelist: Erlaubte Zeichen (z.B. "0-9a-zA-Z .,':x-()[]/")
        
    Returns:
        Liste von (text, confidence) Tupeln (confidence always 1.0 for tesseract)
    """
    try:
        import pytesseract
        from PIL import Image
        
        # Convert to PIL Image if needed
        if hasattr(img, 'shape'):  # numpy array
            img = Image.fromarray(img)
        
        # Tesseract config
        config = '--psm 6'  # Assume uniform block of text
        if whitelist:
            config += f' -c tessedit_char_whitelist={whitelist}'
        
        text = pytesseract.image_to_string(img, config=config)
        
        if text.strip():
            return [(text.strip(), 1.0)]
        
        return []
        
    except Exception as e:
        print(f"⚠️  Tesseract error: {e}")
        return []


def ocr_auto(img, 
             engine: str = 'paddle',
             fallback_enabled: bool = True,
             confidence_threshold: float = 0.3,
             tesseract_whitelist: Optional[str] = None) -> str:
    """
    Automatische OCR mit Multi-Engine-Fallback.
    
    Args:
        img: Input image (numpy array oder PIL Image)
        engine: Primäre Engine ('paddle', 'easyocr', 'tesseract')
        fallback_enabled: Fallback zu anderen Engines bei Fehler
        confidence_threshold: Minimum confidence score (0-1)
        tesseract_whitelist: Erlaubte Zeichen für Tesseract
        
    Returns:
        Erkannter Text (kombiniert aus allen Zeilen)
    """
    engines = []
    
    # Bestimme Engine-Reihenfolge
    if engine == 'paddle':
        engines = ['paddle', 'easyocr', 'tesseract']
    elif engine == 'easyocr':
        engines = ['easyocr', 'paddle', 'tesseract']
    elif engine == 'tesseract':
        engines = ['tesseract', 'paddle', 'easyocr']
    else:
        engines = ['paddle', 'easyocr', 'tesseract']
    
    if not fallback_enabled:
        engines = [engine]
    
    # Versuche Engines in Reihenfolge
    for eng in engines:
        result = []
        
        if eng == 'paddle' and _paddle_available:
            result = ocr_with_paddle(img, confidence_threshold)
        elif eng == 'easyocr' and _easyocr_available:
            result = ocr_with_easyocr(img, confidence_threshold)
        elif eng == 'tesseract':
            result = ocr_with_tesseract(img, tesseract_whitelist)
        
        if result:
            # Kombiniere alle Textzeilen
            text = '\n'.join([line[0] for line in result])
            return text
    
    # Keine Engine hat Text erkannt
    return ""


def get_available_engines() -> List[str]:
    """
    Gibt Liste der verfügbaren OCR-Engines zurück.
    
    Returns:
        Liste von Engine-Namen
    """
    engines = []
    
    if _paddle_available:
        engines.append('paddle')
    if _easyocr_available:
        engines.append('easyocr')
    
    # Tesseract is always available (system-level)
    engines.append('tesseract')
    
    return engines


def get_engine_info() -> dict:
    """
    Gibt Informationen über verfügbare Engines zurück.
    
    Returns:
        Dict mit Engine-Status
    """
    return {
        'paddle': {
            'available': _paddle_available,
            'initialized': _paddle_reader is not None
        },
        'easyocr': {
            'available': _easyocr_available,
            'initialized': _easyocr_reader is not None
        },
        'tesseract': {
            'available': True,  # System-level installation
            'initialized': True
        }
    }


# -----------------------
# Precompiled Regex Patterns (Performance-Optimierung)
# -----------------------
# Rule: Regex should always be precompiled for performance reasons
_WHITESPACE_NORMALIZE_PATTERN = re.compile(r'\s+')
_NON_ALPHANUMERIC_PATTERN = re.compile(r'[^a-zA-Z0-9\s\.,:\-\(\)\[\]/]')


def normalize_ocr_text(text: str) -> str:
    """
    Normalisiert OCR-Text (Whitespace, Sonderzeichen).
    
    Args:
        text: Roher OCR-Text
        
    Returns:
        Normalisierter Text
    """
    if not text:
        return ""
    
    # Normalize whitespace
    text = _WHITESPACE_NORMALIZE_PATTERN.sub(' ', text)
    
    # Remove weird characters (keep common punctuation)
    text = _NON_ALPHANUMERIC_PATTERN.sub('', text)
    
    return text.strip()

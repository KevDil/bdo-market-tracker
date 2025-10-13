# -*- coding: utf-8 -*-
"""
Unicode-Fix Helper für Windows Tests

Dieses Modul sollte am Anfang jeder Test-Datei importiert werden,
um Unicode/Emoji-Probleme auf Windows zu vermeiden.
"""

import sys
import io

def fix_windows_unicode():
    """
    Fixe Unicode-Encoding für Windows Console (CP1252 → UTF-8)
    
    Windows PowerShell und CMD nutzen standardmäßig CP1252 (Latin-1),
    was keine Emojis und viele Unicode-Zeichen unterstützt.
    Diese Funktion forciert UTF-8 mit error='replace'.
    """
    if sys.platform == 'win32':
        # Fix stdout - use reconfigure to avoid closing the buffer
        if hasattr(sys.stdout, 'reconfigure'):
            try:
                sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            except (AttributeError, ValueError):
                pass
        
        # Fix stderr - use reconfigure to avoid closing the buffer
        if hasattr(sys.stderr, 'reconfigure'):
            try:
                sys.stderr.reconfigure(encoding='utf-8', errors='replace')
            except (AttributeError, ValueError):
                pass

# Auto-apply beim Import
fix_windows_unicode()

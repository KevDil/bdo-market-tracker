# Archived Documentation

Dieses Verzeichnis enthält historische Dokumentation von Fixes und Features, die in den Hauptcode integriert wurden.

## Zweck

Diese Docs werden archiviert statt gelöscht um:
- **Entscheidungskontext** zu bewahren (Warum wurde X so gelöst?)
- **Debugging-Hilfe** für ähnliche Probleme in der Zukunft
- **Projekt-Historie** zu dokumentieren

## Hauptdokumentation (aktiv)

Die aktuelle, relevante Dokumentation befindet sich in:
- `WARP.md` - Hauptreferenz für Entwicklung (Rules, Architecture, Commands)
- `README.md` - Projekt-Übersicht und Quick Start
- `QUICK_REFERENCE.md` - Befehls-Referenz
- `docs/CHANGELOG_DETAILED.md` - Chronologische Änderungshistorie
- `docs/OCR_V2_README.md` - OCR System Dokumentation

## Archivierte Kategorien

### Performance Fixes (2025-10-12/13)
- GPU/CUDA optimization
- Cache improvements
- Regex pre-compilation
- Async OCR queue

### OCR Robustness (2025-10-12/14)
- Price parsing improvements
- Space handling
- Silver keyword normalization
- Truncated numbers

### Transaction Detection (2025-10-13)
- Duplicate handling
- Fresh transaction detection
- Timestamp bugs
- Mixed context detection

### Critical Bugs (2025-10-13)
- Missing purchases
- UI evidence fixes
- Price error handling

## Konsolidierungsregel

**Neue Dokumentation sollte direkt in:**
1. `WARP.md` (für Regeln/Architecture) ODER
2. `CHANGELOG_DETAILED.md` (für Fixes/Features)

**Separate Docs nur wenn:**
- Extrem komplex (>1000 Zeilen)
- Langfristig relevant
- Referenz für externe Nutzer

## Cleanup

Archivierte Docs bleiben dauerhaft erhalten (disk space ist billig).

Löschung nur bei:
- Komplett irrelevanten Technologien
- Fehlerhafter/irreführender Information

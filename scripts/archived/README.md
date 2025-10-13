# Archived Tests

Dieses Verzeichnis enthält Test-Scripts, die ihre Funktion erfüllt haben oder nicht mehr aktiv benötigt werden.

## Warum archivieren statt löschen?

- **Historischer Kontext**: Tests dokumentieren gelöste Probleme
- **Wiederverwendbarkeit**: Code-Snippets für ähnliche Fälle
- **Regression Testing**: Bei Bedarf reaktivierbar

## Archivierungs-Kriterien

Ein Test wird archiviert wenn:
1. ✅ Das Problem gelöst wurde und die Lösung stabil ist
2. 🔄 Der Test durch einen besseren/umfassenderen Test ersetzt wurde
3. 🎯 Das Feature/Problem nicht mehr relevant ist
4. 🐛 Der Test nur für einmaliges Debugging erstellt wurde

## Kategorien

### Debug Scripts (einmalige Nutzung)
- `debug_*.py` - Temporäre Debug-Hilfen
- `smoke_*.py` - Ad-hoc Smoke Tests
- `check_*.py`, `cleanup_*.py` - Einmalige Operationen

### Duplicate/Superseded Tests
- `test_*_missing.py` - Von finalen Lösungen abgelöst
- `test_*_debug.py` - Debug-Varianten von Haupt-Tests
- `test_user_scenario_*.py` - Spezifische User-Cases (nun in test_exact_user_scenario.py)

### Historical Tests (Problem gelöst)
- `test_historical_*.py` - Historical transaction fixes
- `test_ui_fallback_*.py` - UI metric fallback improvements
- `test_price_*.py` - Preis-Parsing-Fixes
- `test_spaces_*.py` - OCR space handling
- `test_quantity_bounds.py` - Quantity validation (nun in config.py)

### API/Performance Tests (nicht im Standard-Run)
- `test_bdo_api.py` - BDO API Tests (manuell bei Bedarf)
- `test_garmoth_api.py` - Garmoth API Tests (optional)
- `benchmark_performance.py` - Performance Benchmarks (bei Bedbedarf)

## Reaktivierung

Falls ein archivierter Test wieder benötigt wird:
```powershell
# Test zurück nach scripts/ verschieben
Move-Item scripts/archived/test_xyz.py scripts/
```

Beachte: Pfade und Imports müssen eventuell angepasst werden.

## Cleanup Policy

Archivierte Tests werden **nicht automatisch gelöscht**.

Manuelle Löschung nur wenn:
- Code ist komplett veraltet (>1 Jahr)
- Problem existiert nicht mehr
- Kein historischer Wert

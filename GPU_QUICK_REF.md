# ⚙️ GPU-Modus Quick Reference
**Last Updated:** 2025-10-12

---

## 🎮 Empfohlene Settings (nach Use-Case)

### ✅ Aktives Spielen (keine Ruckler)
```python
# config.py
USE_GPU = False          # ← CPU-Modus
POLL_INTERVAL = 0.3      # ← Schnelles Tracking
GAME_FRIENDLY_MODE = True
```
**Performance:** ~950ms/scan (mit Cache), keine Game-Ruckler

---

### ⚡ AFK / Background (maximale Speed)
```python
# config.py
USE_GPU = True           # ← GPU-Modus
GPU_MEMORY_LIMIT = 2048  # ← 2GB VRAM-Limit
GPU_LOW_PRIORITY = True  # ← Niedrige GPU-Priorität
GAME_FRIENDLY_MODE = True # ← Längerer Interval
POLL_INTERVAL = 0.8      # ← Sanfter fürs Spiel
```
**Performance:** ~300ms/scan (mit Cache), leichte Ruckler

---

## 📊 Performance-Vergleich

| Setting | OCR-Zeit | Ruckler | Use-Case |
|---------|----------|---------|----------|
| **CPU + Cache** | ~950ms | ❌ Keine | ⭐ Aktives Spielen |
| **GPU + Cache + Game-Friendly** | ~300ms | ⚠️ Leicht | AFK Tracking |
| **GPU + Cache + Frequent** | ~300ms | ⚠️⚠️ Stark | Nicht empfohlen |

---

## 🔧 Config-Flags Erklärt

```python
USE_GPU = False/True
# False = CPU-only (langsamer, keine Ruckler)
# True  = GPU-Modus (schneller, kann Ruckler verursachen)

GPU_MEMORY_LIMIT = 2048  # MB
# Limitiert VRAM-Nutzung (mehr VRAM bleibt für Spiel)
# Empfohlen: 2048-4096 MB für RTX 4070

GPU_LOW_PRIORITY = True
# True  = OCR bekommt niedrige GPU-Priorität (Spiel hat Vorrang)
# False = Normale Priorität (mehr Ruckler)

GAME_FRIENDLY_MODE = True
# True  = Längeres Poll-Interval bei GPU (0.8s statt 0.3s)
# False = Kurzes Interval (mehr Störungen)

POLL_INTERVAL = 0.3  # Sekunden
# Zeit zwischen Scans
# 0.3s = Schnell (empfohlen für CPU)
# 0.8s = Langsamer (empfohlen für GPU)
```

---

## 🎯 Quick-Decision-Tree

```
Habe ich Ruckler im Spiel?
├─ JA → Setze USE_GPU = False
│       └─ Fertig! Cache übernimmt Performance
│
└─ NEIN (oder AFK)
    └─ Willst du maximale Speed?
        ├─ JA → USE_GPU = True
        │       └─ Setze POLL_INTERVAL = 0.8
        │
        └─ NEIN → USE_GPU = False (sicher)
```

---

## 💡 Pro-Tipps

**Tipp 1:** Cache ist der wichtigste Performance-Boost! 
- CPU + Cache ist schneller als GPU ohne Cache in vielen Szenarien

**Tipp 2:** Poll-Interval anpassen je nach Bedarf:
- 0.3s = Fängt alle Events schnell
- 0.8s = Immer noch schnell genug, sanfter fürs Spiel

**Tipp 3:** Single-Scans sind immer OK mit GPU:
- Ruckler sind nur bei Auto-Track ein Problem
- Manual Scans kannst du mit GPU machen

**Tipp 4:** Monitor Cache-Hit-Rate in `ocr_log.txt`:
- Suche nach `[CACHE HIT]` Einträgen
- 40-60% Hit-Rate = Optimal
- <20% = Viele neue Events (normal bei aktivem Trading)

---

## 🚨 Troubleshooting

**Ruckler trotz CPU-Modus?**
- Prüfe: Ist USE_GPU wirklich False?
- Prüfe Terminal-Output: "EasyOCR initialized (CPU mode)"
- Neu starten falls nötig

**GPU-Modus zu langsam?**
- Erste OCR ist immer langsam (Model-Loading)
- Nach 2-3 Scans sollte es schnell sein
- Prüfe: torch.cuda.is_available() = True?

**Cache funktioniert nicht?**
- Cache-Hits nur bei identischen Screenshots
- Bei ständig neuen Events = 0% Hit-Rate (normal)
- Monitor in ocr_log.txt

---

**Details:** Siehe `docs/GPU_GAME_PERFORMANCE.md`

# ML-Integration für BDO Market Tracker (Ohne eigenes Training)

## 🎯 Überblick

Dieses Dokument beschreibt praktische ML-Ansätze für den market_tracker, die **keine eigene Model-Training-Infrastruktur** benötigen und mit minimalem Aufwand spürbare Verbesserungen bringen.

---

## 1. 🔍 OCR-Verbesserung mit PaddleOCR

### Motivation
- Aktuelle Lösung: EasyOCR + Tesseract
- Problem: Game-UI-Text kann herausfordernd sein (spezielle Schriftarten, Transparenz)
- Lösung: PaddleOCR - ein vortrainiertes OCR-Modell mit besserer Game-UI-Performance

### Implementation
```python
# Installation
pip install paddlepaddle paddleocr

# In config.py oder utils.py
from paddleocr import PaddleOCR

# Initialisierung (GPU optional)
paddle_reader = PaddleOCR(
    lang='en',
    use_angle_cls=False,  # Schneller
    use_gpu=USE_GPU,
    show_log=False
)

# In utils.py - Alternative OCR-Engine
def ocr_with_paddle(img):
    """PaddleOCR als Alternative zu EasyOCR."""
    result = paddle_reader.ocr(img, cls=False)
    
    if not result or not result[0]:
        return []
    
    # Format: [([[x1,y1],[x2,y2],[x3,y3],[x4,y4]], (text, confidence))]
    parsed = []
    for line in result[0]:
        bbox, (text, conf) = line
        parsed.append({
            'text': text,
            'confidence': conf,
            'bbox': bbox
        })
    
    return parsed
```

### Vorteile
- ✅ **Vortrainiert** auf großem Multi-Domain-Dataset
- ✅ **Schneller** als EasyOCR (besonders mit GPU)
- ✅ **Bessere Game-UI-Erkennung** (weniger OCR-Fehler)
- ✅ **Minimaler Aufwand**: Drop-in Replacement

### Aufwand
- **Zeit**: 2-3 Stunden
- **Risiko**: Niedrig (Fallback auf EasyOCR möglich)

---

## 2. 🎯 Fuzzy Matching mit RapidFuzz + ML-Embeddings

### Motivation
- Aktuell: `difflib.SequenceMatcher` für Item-Name-Korrektur
- Problem: Langsam bei großer Whitelist (4874 Items)
- Lösung: RapidFuzz (C++ optimiert) + optionale Sentence-Transformers für semantisches Matching

### Implementation (Basis)
```python
# Installation
pip install rapidfuzz

# In utils.py - Ersetze difflib-Logik
from rapidfuzz import process, fuzz

@lru_cache(maxsize=2000)
def correct_item_name_fast(ocr_name, threshold=80):
    """Schnellere Fuzzy-Korrektur mit RapidFuzz."""
    if not ocr_name or not ITEM_WHITELIST:
        return ocr_name
    
    # RapidFuzz ist 10-50x schneller als difflib
    result = process.extractOne(
        ocr_name,
        ITEM_WHITELIST,
        scorer=fuzz.WRatio,  # Weighted Ratio - robust gegen Teilstrings
        score_cutoff=threshold
    )
    
    if result:
        match, score, idx = result
        if score >= threshold:
            return match
    
    return ocr_name
```

### Implementation (Erweitert mit Embeddings)
```python
# Installation
pip install sentence-transformers

from sentence_transformers import SentenceTransformer
import numpy as np

# Einmalig beim Start (in config.py)
embeddings_model = SentenceTransformer('all-MiniLM-L6-v2')  # Leichtes Modell

# Item-Embeddings vorberechnen (beim Start)
ITEM_EMBEDDINGS = None
def precompute_item_embeddings():
    global ITEM_EMBEDDINGS
    if ITEM_WHITELIST:
        ITEM_EMBEDDINGS = embeddings_model.encode(
            ITEM_WHITELIST,
            convert_to_numpy=True,
            show_progress_bar=False
        )

# Semantische Suche
def find_similar_items_semantic(ocr_name, top_k=5):
    """Finde semantisch ähnliche Items (für schwierige OCR-Fälle)."""
    if not ITEM_EMBEDDINGS:
        return []
    
    query_emb = embeddings_model.encode([ocr_name], convert_to_numpy=True)
    
    # Cosine-Similarity
    similarities = np.dot(ITEM_EMBEDDINGS, query_emb.T).flatten()
    top_indices = similarities.argsort()[-top_k:][::-1]
    
    results = [
        (ITEM_WHITELIST[idx], float(similarities[idx]))
        for idx in top_indices
    ]
    
    return results

# Hybrid-Ansatz: RapidFuzz + Embeddings
def correct_item_name_hybrid(ocr_name, threshold=80):
    """Kombiniert String-Matching und semantische Suche."""
    # 1. Versuche exaktes/fuzzy Match (schnell)
    fuzzy_result = correct_item_name_fast(ocr_name, threshold)
    if fuzzy_result != ocr_name:
        return fuzzy_result
    
    # 2. Falls keine gute Fuzzy-Match: Semantische Suche (langsamer, aber robuster)
    semantic_results = find_similar_items_semantic(ocr_name, top_k=3)
    if semantic_results and semantic_results[0][1] > 0.7:  # Confidence > 70%
        return semantic_results[0][0]
    
    return ocr_name
```

### Vorteile
- ✅ **10-50x schneller** (RapidFuzz vs difflib)
- ✅ **Bessere Erkennung** bei stark verrauschtem OCR (Embeddings)
- ✅ **Vortrainiert**: Kein eigenes Training nötig
- ✅ **Cache-freundlich**: Embeddings werden nur einmal berechnet

### Aufwand
- **Basis (RapidFuzz)**: 1-2 Stunden
- **Erweitert (Embeddings)**: 3-4 Stunden
- **Risiko**: Niedrig

---

## 3. 📊 Anomalie-Erkennung für Preis-Plausibilität

### Motivation
- Aktuell: Statische ±10% Toleranz vs BDO API
- Problem: Manche OCR-Fehler bleiben unerkannt (z.B. "1,500" → "15,00")
- Lösung: Isolation Forest für Anomalie-Erkennung (vortrainiertes sklearn-Modell)

### Implementation
```python
# In requirements.txt
scikit-learn>=1.0.0

# In database.py oder utils.py
from sklearn.ensemble import IsolationForest
import numpy as np

class PriceAnomalyDetector:
    """Erkennt unplausible Preise basierend auf historischen Daten."""
    
    def __init__(self):
        self.models = {}  # Pro Item ein Modell
        self.min_samples = 10  # Mindestens 10 Transaktionen nötig
        
    def train_for_item(self, item_name, prices):
        """Trainiert Anomalie-Detektor für ein Item (online, ohne persistentes Training)."""
        if len(prices) < self.min_samples:
            return False
        
        # Log-Transform für bessere Verteilung
        X = np.log1p(np.array(prices).reshape(-1, 1))
        
        # Isolation Forest (unsupervised, kein Label-Training nötig)
        clf = IsolationForest(
            contamination=0.05,  # 5% Ausreißer erwartet
            random_state=42,
            n_estimators=50
        )
        clf.fit(X)
        
        self.models[item_name] = clf
        return True
    
    def is_price_anomaly(self, item_name, price):
        """Prüft ob Preis ein Ausreißer ist."""
        if item_name not in self.models:
            # Lade historische Preise aus DB und trainiere on-the-fly
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT price FROM transactions WHERE item_name = ? AND price > 0 LIMIT 100",
                (item_name,)
            )
            prices = [row[0] for row in cursor.fetchall()]
            
            if not self.train_for_item(item_name, prices):
                return False  # Nicht genug Daten
        
        # Prüfe ob Preis Anomalie ist
        X = np.log1p(np.array([[price]]))
        prediction = self.models[item_name].predict(X)
        
        return prediction[0] == -1  # -1 = Anomalie

# Global Instanz
price_anomaly_detector = PriceAnomalyDetector()

# In tracker.py - Erweitere Validierung
def validate_price_with_ml(item_name, price, unit_price):
    """Kombiniert API-Check mit ML-Anomalie-Erkennung."""
    # 1. API-Check (aktuell)
    api_valid = check_price_plausibility(item_name, unit_price)
    
    # 2. ML-Check (neu)
    is_anomaly = price_anomaly_detector.is_price_anomaly(item_name, price)
    
    if is_anomaly:
        log_debug(f"[ML-ANOMALY] Price {price} for {item_name} detected as outlier")
        return False
    
    return api_valid
```

### Vorteile
- ✅ **Kein Training nötig**: Nutzt historische DB-Daten
- ✅ **Adaptive**: Lernt aus neuen Transaktionen
- ✅ **Erkennt subtile Fehler**: Z.B. verschobene Dezimalstellen
- ✅ **Schnell**: Isolation Forest ist sehr effizient

### Aufwand
- **Zeit**: 3-4 Stunden
- **Risiko**: Niedrig (nur Zusatz-Validierung)

---

## 4. 🧠 Buy/Sell-Klassifikation mit Zero-Shot Learning

### Motivation
- Aktuell: `item_categories.csv` für Historical Detection
- Problem: Manuelle Pflege, unvollständig
- Lösung: Zero-Shot Text-Klassifikation (BART, T5) - vortrainiert!

### Implementation
```python
# Installation
pip install transformers torch

from transformers import pipeline

# In config.py - Beim Start laden
zero_shot_classifier = pipeline(
    "zero-shot-classification",
    model="facebook/bart-large-mnli",  # Vortrainiertes Modell
    device=0 if USE_GPU else -1
)

# In tracker.py oder parsing.py
def predict_transaction_type_ml(item_name, context_text=""):
    """Klassifiziert Buy/Sell ohne manuelle Kategorien."""
    
    # Erstelle Prompt mit Kontext
    input_text = f"{item_name}"
    if context_text:
        input_text = f"{context_text}: {item_name}"
    
    # Zero-Shot Classification
    result = zero_shot_classifier(
        input_text,
        candidate_labels=["buying item", "selling item"],
        multi_label=False
    )
    
    # Beste Klasse
    predicted_type = "buy" if "buying" in result['labels'][0] else "sell"
    confidence = result['scores'][0]
    
    return predicted_type, confidence

# Hybrid-Ansatz: CSV Fallback + ML
def infer_transaction_type_hybrid(item_name, context=""):
    """Kombiniert CSV-Lookup mit ML-Prediction."""
    
    # 1. Versuche CSV-Lookup (schnell)
    csv_type = get_most_likely_type_from_csv(item_name)
    if csv_type:
        return csv_type, 1.0  # High confidence
    
    # 2. Falls nicht in CSV: ML-Prediction
    ml_type, ml_conf = predict_transaction_type_ml(item_name, context)
    
    if ml_conf > 0.75:  # Nur bei hoher Confidence verwenden
        return ml_type, ml_conf
    
    return None, 0.0  # Nicht sicher
```

### Vorteile
- ✅ **Keine manuelle Kategorisierung** mehr nötig
- ✅ **Vortrainiert**: BART/T5 verstehen semantischen Kontext
- ✅ **Adaptive**: Funktioniert mit neuen Items sofort
- ✅ **Confidence-Score**: Weiß, wenn es unsicher ist

### Nachteile
- ⚠️ **Langsamer**: ~200-500ms pro Inference (mit GPU schneller)
- ⚠️ **Größere Dependencies**: Transformers + PyTorch

### Aufwand
- **Zeit**: 4-5 Stunden
- **Risiko**: Mittel (Latenz kann problematisch sein)

---

## 5. 🔮 Time-Series Forecasting für Smart Alerts (Bonus)

### Motivation
- Zukünftige Feature: "Benachrichtige mich bei ungewöhnlichen Preisschwankungen"
- Lösung: Prophet (Facebook) - vortrainiertes Time-Series-Modell

### Implementation (Proof of Concept)
```python
# Installation
pip install prophet

from prophet import Prophet
import pandas as pd

def forecast_item_price(item_name, days_ahead=7):
    """Prognostiziert zukünftige Preise basierend auf Historie."""
    
    # Lade historische Daten
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT timestamp, price FROM transactions WHERE item_name = ? ORDER BY timestamp",
        conn,
        params=(item_name,)
    )
    
    if len(df) < 30:  # Mindestens 30 Datenpunkte
        return None
    
    # Prophet-Format
    df = df.rename(columns={'timestamp': 'ds', 'price': 'y'})
    df['ds'] = pd.to_datetime(df['ds'])
    
    # Trainiere Modell (schnell, kein persistentes Training)
    model = Prophet(
        daily_seasonality=True,
        weekly_seasonality=True,
        changepoint_prior_scale=0.05
    )
    model.fit(df)
    
    # Forecast
    future = model.make_future_dataframe(periods=days_ahead)
    forecast = model.predict(future)
    
    return forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].tail(days_ahead)

# Beispiel-Nutzung
forecast = forecast_item_price("Black Stone (Weapon)", days_ahead=7)
if forecast is not None:
    print(f"Prognose für nächste 7 Tage: {forecast}")
```

### Vorteile
- ✅ **Vortrainiert** auf Time-Series-Patterns
- ✅ **Kein ML-Know-how** nötig
- ✅ **Robuste Prognosen** mit Confidence-Intervallen
- ✅ **Schnell**: Training in Sekunden

### Aufwand
- **Zeit**: 5-6 Stunden (für GUI-Integration)
- **Risiko**: Niedrig (optional Feature)

---

## 📊 Empfohlene Priorität

| Feature | Aufwand | Impact | Priorität |
|---------|---------|--------|-----------|
| **1. RapidFuzz** | 1-2h | Hoch (Performance) | 🟢 **HOCH** |
| **2. PaddleOCR** | 2-3h | Hoch (Accuracy) | 🟢 **HOCH** |
| **3. Anomalie-Erkennung** | 3-4h | Mittel (Qualität) | 🟡 **MITTEL** |
| **4. Zero-Shot Buy/Sell** | 4-5h | Niedrig (Convenience) | 🔴 **NIEDRIG** |
| **5. Prophet Forecasting** | 5-6h | Niedrig (Feature) | 🔴 **NIEDRIG** |

---

## 🚀 Quick Start (Top 2 Features)

### Phase 1: RapidFuzz (1-2 Stunden)
```bash
pip install rapidfuzz

# Ersetze in utils.py die correct_item_name-Funktion
# Test mit: python scripts/test_item_validation.py
```

### Phase 2: PaddleOCR (2-3 Stunden)
```bash
pip install paddlepaddle paddleocr

# Füge zu config.py hinzu (neben EasyOCR)
# Test mit: python scripts/utils/compare_ocr.py
```

**Erwartete Verbesserungen:**
- ⚡ **50-80% schnellere** Item-Korrektur
- 📈 **5-10% bessere** OCR-Accuracy
- 🎯 **Weniger False Positives** bei Item-Namen

---

## 🔧 Integration in Bestehenden Code

Alle vorgeschlagenen ML-Lösungen sind **drop-in kompatibel** und können schrittweise integriert werden:

1. **Kein Breaking Change**: Fallback auf aktuelle Logik möglich
2. **Feature-Flags**: Einfach an/ausschaltbar in `config.py`
3. **Backward-kompatibel**: Keine DB-Schema-Änderungen
4. **Test-abgedeckt**: Bestehende Tests bleiben gültig

---

## 📝 Zusammenfassung

Alle vorgeschlagenen ML-Ansätze nutzen **vortrainierte Modelle** und benötigen **kein eigenes Training**. Die Implementierung ist relativ einfach und bringt spürbare Verbesserungen bei:

- 🔍 **OCR-Qualität** (PaddleOCR)
- ⚡ **Performance** (RapidFuzz)
- 🎯 **Datenqualität** (Anomalie-Erkennung)
- 🧠 **Intelligenz** (Zero-Shot Classification)

**Empfohlener Start:** RapidFuzz + PaddleOCR (3-5 Stunden, hoher ROI)

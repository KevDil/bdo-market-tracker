import re
from utils import normalize_numeric_str, clean_item_name, parse_timestamp_text, find_all_timestamps, correct_item_name

# -----------------------
# Performance: Pre-compiled Regex Patterns (10-15% faster parsing)
# -----------------------
_ANCHOR_PATTERN = re.compile(
    r"("
    r"(?:\btransact[il1]on\b|\bsold\b)"              # transaction/sold
    r"|(?:\bplaced\s+order\b|\border\s+placed\b)"   # placed order
    r"|(?:\bre-?list(?:ed)?\b|\blisted\b)"           # relist/listed variants
    r"|(?:\bwith\s*draw\b|\bwithdrew\b|\bwithdraw(?:n|ed)?\b)"  # withdrew
    r"|(?:\bpurchased\b|\bbought\b)"                 # purchased/bought
    r"|\bcollect\b"                                    # collect indicator
    r")",
    re.IGNORECASE,
)

_ITEM_PATTERN = re.compile(r"(.+?)\s+x([0-9OoIl,\.]+)", re.IGNORECASE)
_PRICE_PATTERN = re.compile(r"(?:for|worth)\s+([0-9,\.]+)\s+Silver", re.IGNORECASE)
_TRANSACTION_PATTERN = re.compile(r"Transaction of (.+?) worth", re.IGNORECASE)
_PLACED_ORDER_PATTERN = re.compile(r"(?:placed\s+order|order\s+placed)\s+of\s+(.+?)\s+(?:for|worth)", re.IGNORECASE)
_PURCHASED_PATTERN = re.compile(r"purchased\s+(.+?)\s+(?:for|worth)", re.IGNORECASE)
_LISTED_PATTERN = re.compile(r"(?:listed|re-?list(?:ed)?)\s+(.+?)\s+for", re.IGNORECASE)
_WITHDREW_PATTERN = re.compile(r"(?:withdrew?|withdraw(?:n|ed)?)\s+(?:order\s+of\s+)?(.+?)\s+(?:for|worth)", re.IGNORECASE)

_MULTIPLIER_SYMBOL = r"(?:(?<=\s)|^)(?:[x×X\*]|[lI\|])(?=\s*[0-9OolI\|SsZzBb,\.]{1,6}(?:\b|$))"
_MULTIPLIER_WITH_QTY_PATTERN = re.compile(fr"{_MULTIPLIER_SYMBOL}\s*([0-9OolI\|SsZzBb,\.]+)", re.IGNORECASE)
_MULTIPLIER_PRESENCE_PATTERN = re.compile(fr"{_MULTIPLIER_SYMBOL}\s*[0-9OolI\|SsZzBb,\.]+", re.IGNORECASE)

_SILVER_PATTERN_RAW = r"s\s*[iIl1]\s*[lIl1]\s*[vV]\s*[eE]\s*[rR]"
_SILVER_PATTERN = re.compile(_SILVER_PATTERN_RAW, re.IGNORECASE)
_WORTH_SILVER_PATTERN = re.compile(fr"\bworth\s+[0-9OolI\|\s,\.]+\s*{_SILVER_PATTERN_RAW}", re.IGNORECASE)
_PRICE_WITH_SILVER_PATTERN = re.compile(fr"([0-9OolI\|SsZzBb\s,\.]{3,})\s*{_SILVER_PATTERN_RAW}", re.IGNORECASE)
_MULTIPLIER_THEN_PRICE_PATTERN = re.compile(fr"{_MULTIPLIER_SYMBOL}[\s\S]*?([0-9OolI\|SsZzBb\s,\.]{3,})\s*{_SILVER_PATTERN_RAW}", re.IGNORECASE)

_UI_DECIMAL_PATTERN = re.compile(r"\b\d{1,2}\.(?:\d{3})\b")

_DETAIL_PATTERNS = {
    "transaction_keyword": re.compile(r"\btransaction\b", re.IGNORECASE),
    "sold_keyword": re.compile(r"\bsold\b", re.IGNORECASE),
    "placed_order": re.compile(r"\bplaced\s+order\b", re.IGNORECASE),
    "order_placed": re.compile(r"\border\s+placed\b", re.IGNORECASE),
    "placed_anchor": re.compile(r"(?:placed\s+order\s+of|order\s+placed\s+for|placed\s+order)\b", re.IGNORECASE),
    "listed": re.compile(r"\blisted\b", re.IGNORECASE),
    "relist": re.compile(r"\bre-?list(?:ed)?\b", re.IGNORECASE),
    "listed_anchor": re.compile(r"\b(?:re-?list(?:ed)?|listed)\b", re.IGNORECASE),
    "withdrew": re.compile(r"\bwith\s*draw\b|\bwithdrew\b|\bwithdraw(?:n|ed)?\b|\bcancel+l?ed\b|\bretract(?:ed)?\b|\bremoved\s+order\b|\bremove\s+order\b|\border\s+removed\b", re.IGNORECASE),
    "withdrew_anchor": re.compile(r"\b(?:with\s*draw|withdrew|withdraw(?:n|ed)?)\b", re.IGNORECASE),
    "purchased": re.compile(r"\bpurchased\b|\bbought\b", re.IGNORECASE),
    "collect": re.compile(r"\bcollect\b", re.IGNORECASE),
    "transaction_anchor": re.compile(r"\btransact[il1]on\b|\bsold\b", re.IGNORECASE),
    "worth": re.compile(r"\bworth\b", re.IGNORECASE),
    "for": re.compile(r"\bfor\b", re.IGNORECASE),
    "non_transaction_keywords": re.compile(r"\blisted\b|\border\s+placed\b|\bplaced\s+order\b|\bpurchased\b|\bbought\b|\bwith\s*draw\b|\bwithdrew\b", re.IGNORECASE),
}

_TRANSACTION_ITEM_PATTERN = re.compile(fr"(?:transact[il1]on\s+of|sold)\s+([\s\S]*?)\s+{_MULTIPLIER_SYMBOL}", re.IGNORECASE)
_TRANSACTION_ITEM_FALLBACK_PATTERN = re.compile(r"(?:transact[il1]on\s+of|sold)\s+([\s\S]*?)(?:\s+worth|\s+for|\s+silver|$)", re.IGNORECASE)
_PURCHASED_ITEM_PATTERN = re.compile(fr"(?:purchased|bought)\s+([\s\S]*?)\s+{_MULTIPLIER_SYMBOL}", re.IGNORECASE)
_PURCHASED_ITEM_FALLBACK_PATTERN = re.compile(r"(?:purchased|bought)\s+([\s\S]*?)(?:\s+worth|\s+for|\s+silver|$)", re.IGNORECASE)
_PLACED_ITEM_PATTERN = re.compile(fr"(?:placed\s+order\s+of|order\s+placed\s+for|placed\s+order)\s+([\s\S]*?)\s+{_MULTIPLIER_SYMBOL}", re.IGNORECASE)
_PLACED_ITEM_FALLBACK_PATTERN = re.compile(r"(?:placed\s+order\s+of|order\s+placed\s+for|placed\s+order)\s+([\s\S]*?)(?:\s+worth|\s+for|\s+silver|$)", re.IGNORECASE)
_LISTED_ITEM_PATTERN = re.compile(fr"(?:re-?list(?:ed)?|listed)\s+([\s\S]*?)\s+{_MULTIPLIER_SYMBOL}", re.IGNORECASE)
_LISTED_ITEM_FALLBACK_PATTERN = re.compile(r"(?:re-?list(?:ed)?|listed)\s+([\s\S]*?)(?:\s+worth|\s+for|\s+silver|$)", re.IGNORECASE)
_WITHDREW_ITEM_PATTERN = re.compile(fr"(?:with\s*draw|withdrew|withdraw(?:n|ed)?)\s+(?:order\s+of\s+)?([\s\S]*?)\s+{_MULTIPLIER_SYMBOL}", re.IGNORECASE)
_WITHDREW_ITEM_FALLBACK_PATTERN = re.compile(r"(?:with\s*draw|withdrew|withdraw(?:n|ed)?)\s+(?:order\s+of\s+)?([\s\S]*?)(?:\s+worth|\s+for|\s+silver|$)", re.IGNORECASE)

_BOUNDARY_PATTERNS = {
    "transaction": [
        re.compile(r"l\s*[i1l]\s*s\s*t\s*e\s*d", re.IGNORECASE),
        re.compile(r"p\s*l\s*a\s*c\s*e\s*d\s+o\s*r\s*d\s*e\s*r", re.IGNORECASE),
        re.compile(r"w\s*i\s*t\s*h\s*d\s*r\s*e\s*w(?:\s+o\s*r\s*d\s*e\s*r)?", re.IGNORECASE),
        re.compile(r"p\s*u\s*r\s*c\s*h\s*a\s*s\s*s\s*e\s*d", re.IGNORECASE),
    ],
    "purchased": [
        re.compile(r"l\s*[i1l]\s*s\s*t\s*e\s*d", re.IGNORECASE),
        re.compile(r"r\s*e\s*l\s*i\s*s\s*t\s*e\s*d", re.IGNORECASE),
        re.compile(r"p\s*l\s*a\s*c\s*e\s*d\s+(?:a\s*n\s+)?o\s*r\s*d\s*e\s*r", re.IGNORECASE),
        re.compile(r"o\s*r\s*d\s*e\s*r\s+placed", re.IGNORECASE),
        re.compile(r"w\s*i\s*t\s*h\s*d\s*r\s*a\s*w(?:n|e\s*d)?(?:\s+o\s*r\s*d\s*e\s*r)?", re.IGNORECASE),
        re.compile(r"c\s*a\s*n\s*c\s*e\s*l+\s*e\s*d", re.IGNORECASE),
        re.compile(r"r\s*e\s*t\s*r\s*a\s*c\s*t\s*e\s*d", re.IGNORECASE),
        re.compile(r"t\s*r\s*a\s*n\s*s\s*a\s*c\s*t\s*i\s*o\s*n\b", re.IGNORECASE),
    ],
    "placed": [
        re.compile(r"l\s*[i1l]\s*s\s*t\s*e\s*d", re.IGNORECASE),
        re.compile(r"r\s*e\s*l\s*i\s*s\s*t\s*e\s*d", re.IGNORECASE),
        re.compile(r"w\s*i\s*t\s*h\s*d\s*r\s*a\s*w(?:n|e\s*d)?(?:\s+o\s*r\s*d\s*e\s*r)?", re.IGNORECASE),
        re.compile(r"c\s*a\s*n\s*c\s*e\s*l+\s*e\s*d", re.IGNORECASE),
        re.compile(r"r\s*e\s*t\s*r\s*a\s*c\s*t\s*e\s*d", re.IGNORECASE),
        re.compile(r"t\s*r\s*a\s*n\s*s\s*a\s*c\s*t\s*i\s*o\s*n\b", re.IGNORECASE),
        re.compile(r"p\s*u\s*r\s*c\s*h\s*a\s*s\s*s\s*e\s*d", re.IGNORECASE),
    ],
    "listed": [
        re.compile(r"p\s*l\s*a\s*c\s*e\s*d\s+(?:a\s*n\s+)?o\s*r\s*d\s*e\s*r", re.IGNORECASE),
        re.compile(r"o\s*r\s*d\s*e\s*r\s+placed", re.IGNORECASE),
        re.compile(r"w\s*i\s*t\s*h\s*d\s*r\s*a\s*w(?:n|e\s*d)?(?:\s+o\s*r\s*d\s*e\s*r)?", re.IGNORECASE),
        re.compile(r"c\s*a\s*n\s*c\s*e\s*l+\s*e\s*d", re.IGNORECASE),
        re.compile(r"r\s*e\s*t\s*r\s*a\s*c\s*t\s*e\s*d", re.IGNORECASE),
        re.compile(r"t\s*r\s*a\s*n\s*s\s*a\s*c\s*t\s*i\s*o\s*n\b", re.IGNORECASE),
        re.compile(r"p\s*u\s*r\s*c\s*h\s*a\s*s\s*s\s*e\s*d", re.IGNORECASE),
    ],
    "withdrew": [
        re.compile(r"l\s*[i1l]\s*s\s*t\s*e\s*d", re.IGNORECASE),
        re.compile(r"r\s*e\s*l\s*i\s*s\s*t\s*e\s*d", re.IGNORECASE),
        re.compile(r"p\s*l\s*a\s*c\s*e\s*d\s+(?:a\s*n\s+)?o\s*r\s*d\s*e\s*r", re.IGNORECASE),
        re.compile(r"o\s*r\s*d\s*e\s*r\s+placed", re.IGNORECASE),
        re.compile(r"c\s*a\s*n\s*c\s*e\s*l+\s*e\s*d", re.IGNORECASE),
        re.compile(r"r\s*e\s*t\s*r\s*a\s*c\s*t\s*e\s*d", re.IGNORECASE),
        re.compile(r"t\s*r\s*a\s*n\s*s\s*a\s*c\s*t\s*i\s*o\s*n\b", re.IGNORECASE),
        re.compile(r"p\s*u\s*r\s*c\s*h\s*a\s*s\s*s\s*e\s*d", re.IGNORECASE),
    ],
}

_PRICE_BOUNDARIES = [_DETAIL_PATTERNS["worth"], _DETAIL_PATTERNS["for"], _SILVER_PATTERN]


def _find_boundary_offset(patterns, text):
    """Return the earliest match start position across compiled patterns."""
    boundary_offset = None
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            pos = match.start()
            if boundary_offset is None or pos < boundary_offset:
                boundary_offset = pos
    return boundary_offset

# -----------------------
# Eintrags-/Block-Parsing
# -----------------------
def split_text_into_log_entries(text):
    """
    Teilt den OCR-Text in Log-Einträge anhand gefundener Timestamps.
    Robust auch dann, wenn die OCR alle Zeilen zu einer einzigen Zeile zusammenfasst.
    
    WICHTIG: Intelligente Zuordnung für Timestamp-Cluster.
    Wenn mehrere Timestamps als Cluster am Anfang stehen (typisch: '11.05 10.56 10.50 10.50'),
    gefolgt von Events, werden Events per Index zugeordnet:
    - 1. Event → 1. Timestamp im Cluster (neuester)
    - 2. Event → 2. Timestamp im Cluster
    - 3. Event → 3. Timestamp im Cluster
    Dies löst das Problem bei umgekehrter chronologischer Reihenfolge.
    """
    ts_positions = find_all_timestamps(text)
    if not ts_positions:
        return []

    entries = []
    # Finde alle Event-Anker im gesamten Text mit Positionen (nutzt pre-compiled pattern)
    all_anchors = [(m.start(), m.end(), m.group()) for m in _ANCHOR_PATTERN.finditer(text)]
    
    if not all_anchors:
        # Keine Events gefunden - alte Logik: Segmente nach Timestamps
        for idx, (pos, ts_text) in enumerate(ts_positions):
            start = pos
            end = ts_positions[idx + 1][0] if idx + 1 < len(ts_positions) else len(text)
            snippet = text[start:end].strip()
            if snippet:
                entries.append((start, ts_text, snippet))
        return entries
    
    # Prüfe ob Timestamps ein Cluster am Anfang bilden (alle vor dem ersten Event)
    first_event_pos = all_anchors[0][0]
    ts_cluster = [ts for ts in ts_positions if ts[0] < first_event_pos]
    
    if len(ts_cluster) >= 2:
        # Timestamp-Cluster erkannt! Verwende Index-basierte Zuordnung
        # Events werden der Reihe nach den Timestamps im Cluster zugeordnet
        for event_idx, (anchor_start, anchor_end, anchor_text) in enumerate(all_anchors):
            # Wähle Timestamp aus Cluster basierend auf Event-Index
            ts_idx = min(event_idx, len(ts_cluster) - 1)  # Clip to cluster size
            best_ts_pos, best_ts_text = ts_cluster[ts_idx]
            
            # Finde Event-Ende (bis zum nächsten Anker oder max 300 Zeichen)
            next_anchor_start = None
            for next_a_start, _, _ in all_anchors:
                if next_a_start > anchor_start:
                    next_anchor_start = next_a_start
                    break
            
            event_end = anchor_end + 300  # Max 300 Zeichen
            if next_anchor_start and next_anchor_start < event_end:
                event_end = next_anchor_start
            
            snippet = text[anchor_start:event_end].strip()
            if snippet:
                entries.append((anchor_start, best_ts_text, snippet))
    else:
        # Kein Cluster - Fallback: Proximity-basierte Zuordnung (alte Logik)
        for anchor_start, anchor_end, anchor_text in all_anchors:
            # Finde alle Timestamps VOR diesem Event
            preceding_ts = [(pos, ts_txt) for pos, ts_txt in ts_positions if pos < anchor_start]
            
            if not preceding_ts:
                # Kein Timestamp vor diesem Event - überspringe
                continue
            
            # Wähle den letzten Timestamp vor dem Event (kleinste Distanz)
            best_ts_pos, best_ts_text = max(preceding_ts, key=lambda x: x[0])
            
            # Finde Event-Ende
            next_anchor_start = None
            for next_a_start, _, _ in all_anchors:
                if next_a_start > anchor_start:
                    next_anchor_start = next_a_start
                    break
            
            event_end = anchor_end + 300
            if next_anchor_start and next_anchor_start < event_end:
                event_end = next_anchor_start
            
            snippet = text[anchor_start:event_end].strip()
            if snippet:
                entries.append((anchor_start, best_ts_text, snippet))
    
    return entries

def extract_details_from_entry(ts_text, entry_text):
    """
    Aus einem Eintrag (der typischerweise mit einem Timestamp beginnt) extrahieren:
    type: transaction / placed / listed / withdrew / other
    item, qty, price
    timestamp: parsed datetime (from ts_text or nearest in entry)
    """
    # OCR robustness: Fix common OCR errors in Silver keyword before processing
    # Common OCR variants:
    #   - 'Silve_' (missing 'r', underscore artifact) → Silver
    #   - 'Silve ' (trailing space) → Silver
    #   - 'Silv:' / 'Silv.' / 'Silv_' (truncated + punctuation) → Silver
    # Match patterns:
    #   1) 'Silve' + non-letter (space, underscore, punctuation)
    #   2) 'Silv' + punctuation (colon, dot, underscore)
    entry_text = re.sub(r'\bSilve[_\s:,\.]+(?![a-z])', 'Silver ', entry_text, flags=re.IGNORECASE)
    entry_text = re.sub(r'\bSilv[:_\.]', 'Silver', entry_text, flags=re.IGNORECASE)
    
    low = entry_text.lower()
    typ = "other"
    # classify line type conservatively using shared, pre-compiled patterns
    if "transaction of" in low or _DETAIL_PATTERNS["transaction_keyword"].search(low) or _DETAIL_PATTERNS["sold_keyword"].search(low):
        typ = "transaction"
    elif "placed order" in low or _DETAIL_PATTERNS["order_placed"].search(low) or _DETAIL_PATTERNS["placed_order"].search(low):
        typ = "placed"
    elif "listed" in low or _DETAIL_PATTERNS["relist"].search(low):
        # CRITICAL: Avoid false "listed" detection from Buy Overview UI buttons
        # Buy Overview UI: "Maple Sap Orders 5000 Orders Completed 2564 Collect 17,295,600 Re-list"
        # This contains "Re-list" but is NOT a listing event - it's a UI button
        # Only mark as "listed" if we have clear transaction log context (not just UI buttons)
        has_transaction_context = (
            "transaction of" in low or 
            "listed" in low.split("re-list")[0] if "re-list" in low else "listed" in low
        )
        # Additional filter: if "orders completed" appears (Buy Overview UI), this is NOT a listing
        has_ui_context = "orders completed" in low or "orders" in low and "collect" in low
        if has_transaction_context and not has_ui_context:
            typ = "listed"
        # If no clear transaction context, leave as "other"
    elif _DETAIL_PATTERNS["withdrew"].search(low):
        typ = "withdrew"
    elif _DETAIL_PATTERNS["purchased"].search(low):
        typ = "purchased"
    else:
        if _WORTH_SILVER_PATTERN.search(entry_text):
            typ = "transaction"
        elif _DETAIL_PATTERNS["collect"].search(low):
            if _PRICE_WITH_SILVER_PATTERN.search(entry_text):
                typ = "transaction"
        else:
            if _MULTIPLIER_THEN_PRICE_PATTERN.search(entry_text) and not _DETAIL_PATTERNS["non_transaction_keywords"].search(low):
                typ = "transaction"
    # Prefer purchased over transaction if both appear in the snippet
    if typ == "transaction" and _DETAIL_PATTERNS["purchased"].search(low):
        typ = "purchased"

    # qty & item: default global search, but scope to transaction/purchased segments when applicable
    qty = None
    item = None
    tx_segment = None
    purch_segment = None
    # helper to find the most reliable quantity match within a text segment: take the last match before 'worth/for/silver'
    def find_qty_in_segment(segment: str):
        boundary_pos = _find_boundary_offset(_PRICE_BOUNDARIES, segment)
        seg = segment if boundary_pos is None else segment[:boundary_pos]
        # remove obvious UI decimals like 31.590 near 'Pearl Item Selling Limit'
        seg = _UI_DECIMAL_PATTERN.sub(' ', seg)
        # choose the last plausible xN before price context; prefer values in [1..100000]
        last = None
        for match in _MULTIPLIER_WITH_QTY_PATTERN.finditer(seg):
            last = match
        if last:
            val = normalize_numeric_str(last.group(1))
            if val and 1 <= val <= 100000:
                return val
        return None

    explicit_qty = False  # tracks whether a multiplier like 'xN' was explicitly found
    placed_segment = None
    listed_segment = None
    withdrew_segment = None
    if typ == "transaction":
        m_anchor = _DETAIL_PATTERNS["transaction_anchor"].search(entry_text)
        anchor = m_anchor.start() if m_anchor else 0
        after_text = entry_text[anchor:]
        boundary_offset = _find_boundary_offset(_BOUNDARY_PATTERNS["transaction"], after_text)
        boundary_pos = anchor + boundary_offset if boundary_offset is not None else None
        tx_segment = entry_text[anchor:boundary_pos] if boundary_pos is not None else entry_text[anchor:]

        qty_local = find_qty_in_segment(tx_segment)
        if qty_local:
            qty = qty_local
            boundary_offset = _find_boundary_offset(_PRICE_BOUNDARIES, tx_segment)
            seg2 = tx_segment if boundary_offset is None else tx_segment[:boundary_offset]
            if _MULTIPLIER_PRESENCE_PATTERN.search(seg2):
                explicit_qty = True

        m_item_local = _TRANSACTION_ITEM_PATTERN.search(tx_segment)
        if m_item_local:
            item = clean_item_name(m_item_local.group(1))
        else:
            m_item_local2 = _TRANSACTION_ITEM_FALLBACK_PATTERN.search(tx_segment)
            if m_item_local2:
                item = clean_item_name(m_item_local2.group(1))
    elif typ == "purchased":
        m_anchor = _DETAIL_PATTERNS["purchased"].search(entry_text)
        anchor = m_anchor.start() if m_anchor else 0
        after_text = entry_text[anchor:]
        boundary_offset = _find_boundary_offset(_BOUNDARY_PATTERNS["purchased"], after_text)
        boundary_pos = anchor + boundary_offset if boundary_offset is not None else None
        purch_segment = entry_text[anchor:boundary_pos] if boundary_pos is not None else entry_text[anchor:]

        qty_local = find_qty_in_segment(purch_segment)
        if qty_local:
            qty = qty_local
            boundary_offset = _find_boundary_offset(_PRICE_BOUNDARIES, purch_segment)
            seg2 = purch_segment if boundary_offset is None else purch_segment[:boundary_offset]
            if _MULTIPLIER_PRESENCE_PATTERN.search(seg2):
                explicit_qty = True

        m_item_local = _PURCHASED_ITEM_PATTERN.search(purch_segment)
        if m_item_local:
            item = clean_item_name(m_item_local.group(1))
        else:
            m_item_local2 = _PURCHASED_ITEM_FALLBACK_PATTERN.search(purch_segment)
            if m_item_local2:
                item = clean_item_name(m_item_local2.group(1))
    elif typ == "placed":
        m_anchor = _DETAIL_PATTERNS["placed_anchor"].search(entry_text)
        anchor = m_anchor.start() if m_anchor else 0
        after_text = entry_text[anchor:]
        boundary_offset = _find_boundary_offset(_BOUNDARY_PATTERNS["placed"], after_text)
        boundary_pos = anchor + boundary_offset if boundary_offset is not None else None
        placed_segment = entry_text[anchor:boundary_pos] if boundary_pos is not None else entry_text[anchor:]

        qty_local = find_qty_in_segment(placed_segment)
        if qty_local:
            qty = qty_local

        m_item_local = _PLACED_ITEM_PATTERN.search(placed_segment)
        if m_item_local:
            item = clean_item_name(m_item_local.group(1))
        else:
            m_item_local2 = _PLACED_ITEM_FALLBACK_PATTERN.search(placed_segment)
            if m_item_local2:
                item = clean_item_name(m_item_local2.group(1))
    elif typ == "listed":
        m_anchor = _DETAIL_PATTERNS["listed_anchor"].search(entry_text)
        anchor = m_anchor.start() if m_anchor else 0
        after_text = entry_text[anchor:]
        boundary_offset = _find_boundary_offset(_BOUNDARY_PATTERNS["listed"], after_text)
        boundary_pos = anchor + boundary_offset if boundary_offset is not None else None
        listed_segment = entry_text[anchor:boundary_pos] if boundary_pos is not None else entry_text[anchor:]

        qty_local = find_qty_in_segment(listed_segment)
        if qty_local:
            qty = qty_local

        m_item_local = _LISTED_ITEM_PATTERN.search(listed_segment)
        if m_item_local:
            item = clean_item_name(m_item_local.group(1))
        else:
            m_item_local2 = _LISTED_ITEM_FALLBACK_PATTERN.search(listed_segment)
            if m_item_local2:
                item = clean_item_name(m_item_local2.group(1))
    elif typ == "withdrew":
        m_anchor = _DETAIL_PATTERNS["withdrew_anchor"].search(entry_text)
        anchor = m_anchor.start() if m_anchor else 0
        after_text = entry_text[anchor:]
        boundary_offset = _find_boundary_offset(_BOUNDARY_PATTERNS["withdrew"], after_text)
        boundary_pos = anchor + boundary_offset if boundary_offset is not None else None
        withdrew_segment = entry_text[anchor:boundary_pos] if boundary_pos is not None else entry_text[anchor:]

        qty_local = find_qty_in_segment(withdrew_segment)
        if qty_local:
            qty = qty_local

        m_item_local = _WITHDREW_ITEM_PATTERN.search(withdrew_segment)
        if m_item_local:
            item = clean_item_name(m_item_local.group(1))
        else:
            m_item_local2 = _WITHDREW_ITEM_FALLBACK_PATTERN.search(withdrew_segment)
            if m_item_local2:
                item = clean_item_name(m_item_local2.group(1))
    # fallback global qty if not found
    if qty is None:
        # global search: still apply the same boundary-aware rule and take the last match
        qty_global = find_qty_in_segment(entry_text)
        if qty_global:
            qty = qty_global

    # price extraction
    price = None
    if typ in ("transaction", "purchased", "listed", "placed", "withdrew"):
        # For transaction lines, prefer 'worth <N> Silver' (net amount)
        if typ == "transaction":
            # allow OCR variants of 'silver' such as 's1lver', 'si1ver', 'siluer'
            # CRITICAL: Use lowercase 'i' not uppercase 'I' for matching lowercase 'i' in 'Silver'
            silver_pat = r's\s*[iIl1]\s*[lIl1]\s*[vV]\s*[eE]\s*[rR]'
            silver_sep = r'(?:\s|[^A-Za-z0-9]{1,3})*'
            # strict 'worth <N> Silver' first (allow small punctuation between number and Silver)
            # detect if a leading digit may be missing (e.g., "worth ,809,990,000 Silver")
            # CRITICAL: Allow spaces within the numeric string to handle OCR errors like "585, 585, OO0" (spaces after commas)
            # IMPORTANT: Added capital 'O' to pattern to match 'OO0' in OCR errors
            m_worth_missing = re.search(fr'worth\s+([^0-9]{{0,2}})[\s]*([0-9OolI\|,\.\s]+){silver_sep}{silver_pat}', entry_text, re.IGNORECASE)
            m_worth = re.search(fr'worth\s+([0-9OolI\|,\.\s]{{3,}}?){silver_sep}{silver_pat}', entry_text, re.IGNORECASE)
            if m_worth:
                price = normalize_numeric_str(m_worth.group(1))
                # if the token right after 'worth' started with a comma/dot (likely missing leading '1'), bump by 1,000,000,000
                try:
                    if price is not None and price < 1_000_000_000 and m_worth_missing:
                        lead = (m_worth_missing.group(1) or '').strip()
                        if lead and (',' in lead or '.' in lead):
                            price = price + 1_000_000_000
                except Exception:
                    pass
            if price is None:
                # relaxed: 'worth <N>' without requiring 'Silver' ONLY if we also see a completion phrase or 'Silver' nearby
                m_worth_relaxed = re.search(r'worth\s+([0-9OolI\|,\.]{3,})', entry_text, re.IGNORECASE)
                if m_worth_relaxed:
                    context_has_silver = re.search(silver_pat, entry_text, re.IGNORECASE) is not None
                    context_has_completed = re.search(r'has\s+been\s+comp(?:let|lct|lec)ed|completed', entry_text, re.IGNORECASE) is not None
                    if context_has_silver or context_has_completed:
                        cand = normalize_numeric_str(m_worth_relaxed.group(1))
                        if cand and cand >= 100000:
                            price = cand
            if price is None:
                # pick '<number> Silver' within the transaction segment only, excluding later 'listed/placed/withdrew/purchased' parts
                m_anchor = re.search(r'\b(transaction|sold)\b', entry_text, re.IGNORECASE)
                anchor = m_anchor.end() if m_anchor else 0
                # determine boundary: first occurrence of one of the other keywords after anchor
                # Use whitespace-tolerant patterns and allow common OCR confusables for 'i/l/1'
                boundary_patterns = [
                    r'l\s*[i1l]\s*s\s*t\s*e\s*d',                  # listed
                    r'r\s*e\s*l\s*i\s*s\s*t\s*e\s*d',             # relisted
                    r'p\s*l\s*a\s*c\s*e\s*d\s+(?:a\s*n\s+)?o\s*r\s*d\s*e\s*r',  # placed (an) order
                    r'o\s*r\s*d\s*e\s*r\s+placed',                  # order placed
                    r'w\s*i\s*t\s*h\s*d\s*r\s*a\s*w(?:n|e\s*d)?(?:\s+o\s*r\s*d\s*e\s*r)?',  # withdraw variants
                    r'c\s*a\s*n\s*c\s*e\s*l+\s*e\s*d',            # canceled/cancelled
                    r'r\s*e\s*t\s*r\s*a\s*c\s*t\s*e\s*d',        # retracted
                    r'p\s*u\s*r\s*c\s*h\s*a\s*s\s*e\s*d'         # purchased
                ]
                boundary_pos = None
                after_text = entry_text[anchor:]
                for pat in boundary_patterns:
                    m_kw = re.search(pat, after_text, re.IGNORECASE)
                    if m_kw:
                        pos = anchor + m_kw.start()
                        if boundary_pos is None or pos < boundary_pos:
                            boundary_pos = pos
                segment = entry_text[anchor:boundary_pos] if boundary_pos is not None else entry_text[anchor:]
                m_silver = re.search(fr'([0-9OolI\|,\.]{3,}){silver_sep}{silver_pat}', segment, re.IGNORECASE)
                if m_silver:
                    price = normalize_numeric_str(m_silver.group(1))
                else:
                    # As a last resort, only scan for a plausible large number if 'Silver' appears anywhere in the entry.
                    if re.search(silver_pat, entry_text, re.IGNORECASE):
                        noise_pat = re.compile(r'(limit|vt|capacity|warehouse|selling\s+limit|items?\s+listed)', re.IGNORECASE)
                        nums = re.finditer(r'([0-9OolI\|,\.]{3,})', segment)
                        best = None
                        for m in nums:
                            v = normalize_numeric_str(m.group(1))
                            if not v or v < 100000:
                                continue
                            start, end = m.start(), m.end()
                            left = segment[max(0, start-15):start]
                            right = segment[end:end+15]
                            if noise_pat.search(left) or noise_pat.search(right):
                                continue
                            if best is None or v > best:
                                best = v
                        price = best
                    if price is None:
                        # Als zusätzlicher Fallback: Preis in der Nähe von 'Collect' im gesamten entry_text suchen
                        around = entry_text
                        m_near_collect = re.search(fr'collect[\s\S]{{0,50}}?([0-9OolI\|,\.]{{3,}}){silver_sep}{silver_pat}', around, re.IGNORECASE)
                        if m_near_collect:
                            price = normalize_numeric_str(m_near_collect.group(1))
        else:
            # purchased/listed: prefer price within their own segment to avoid picking UI numbers
            silver_pat = r's\s*[iIl1]\s*[lIl1]\s*[vV]\s*[eE]\s*[rR]'
            silver_sep = r'(?:\s|[^A-Za-z0-9]{1,3})*'
            listed_segment = None
            withdrew_segment2 = None
            if typ == 'listed':
                # define listed segment [anchor, boundary)
                m_anchor = re.search(r'\b(re-?list(?:ed)?|listed)\b', entry_text, re.IGNORECASE)
                anchor = m_anchor.start() if m_anchor else 0
                boundary_patterns = [
                    r'p\s*l\s*a\s*c\s*e\s*d\s+(?:a\s*n\s+)?o\s*r\s*d\s*e\s*r',
                    r'o\s*r\s*d\s*e\s*r\s+placed',
                    r'w\s*i\s*t\s*h\s*d\s*r\s*a\s*w(?:n|e\s*d)?(?:\s+o\s*r\s*d\s*e\s*r)?',
                    r'c\s*a\s*n\s*c\s*e\s*l+\s*e\s*d',
                    r'r\s*e\s*t\s*r\s*a\s*c\s*t\s*e\s*d',
                    r'p\s*u\s*r\s*c\s*h\s*a\s*s\s*e\s*d',
                    r't\s*r\s*a\s*n\s*s\s*a\s*c\s*t\s*i\s*o\s*n\b'
                ]
                boundary_pos = None
                after_text = entry_text[anchor:]
                for pat in boundary_patterns:
                    m_kw = re.search(pat, after_text, re.IGNORECASE)
                    if m_kw:
                        pos = anchor + m_kw.start()
                        if boundary_pos is None or pos < boundary_pos:
                            boundary_pos = pos
                listed_segment = entry_text[anchor:boundary_pos] if boundary_pos is not None else entry_text[anchor:]
            if typ == 'withdrew':
                m_anchor = re.search(r'\b(with\s*draw|withdrew|withdraw(?:n|ed)?)\b', entry_text, re.IGNORECASE)
                anchor = m_anchor.start() if m_anchor else 0
                boundary_patterns = [
                    r'l\s*[i1l]\s*s\s*t\s*e\s*d',
                    r'r\s*e\s*l\s*i\s*s\s*t\s*e\s*d',
                    r'p\s*l\s*a\s*c\s*e\s*d\s+(?:a\s*n\s+)?o\s*r\s*d\s*e\s*r',
                    r'o\s*r\s*d\s*e\s*r\s+placed',
                    r'c\s*a\s*n\s*c\s*e\s*l+\s*e\s*d',
                    r'r\s*e\s*t\s*r\s*a\s*c\s*t\s*e\s*d',
                    r'p\s*u\s*r\s*c\s*h\s*a\s*s\s*e\s*d',
                    r't\s*r\s*a\s*n\s*s\s*a\s*c\s*t\s*i\s*o\s*n\b'
                ]
                boundary_pos = None
                after_text = entry_text[anchor:]
                for pat in boundary_patterns:
                    m_kw = re.search(pat, after_text, re.IGNORECASE)
                    if m_kw:
                        pos = anchor + m_kw.start()
                        if boundary_pos is None or pos < boundary_pos:
                            boundary_pos = pos
                withdrew_segment2 = entry_text[anchor:boundary_pos] if boundary_pos is not None else entry_text[anchor:]
            segment = purch_segment if (typ == 'purchased' and purch_segment is not None) else (listed_segment if listed_segment is not None else (withdrew_segment2 if withdrew_segment2 is not None else entry_text))
            # prioritize 'for <N> Silver' in the segment
            # CRITICAL: Allow spaces within numeric string to handle OCR errors like "585, 585, OO0"
            m_for_ctx = re.search(fr'\bfor\s+([0-9OolI\|,\.\s]{{3,}}?){silver_sep}{silver_pat}', segment, re.IGNORECASE)
            if m_for_ctx:
                price = normalize_numeric_str(m_for_ctx.group(1))
            if price is None:
                m_silver = re.search(fr'([0-9OolI\|,\.\s]{{3,}}?){silver_sep}{silver_pat}', segment, re.IGNORECASE)
                if m_silver:
                    price = normalize_numeric_str(m_silver.group(1))
            if price is None:
                # fallback: choose plausible large number in segment, skip UI-noise context
                noise_pat = re.compile(r'(limit|vt|capacity|warehouse|selling\s+limit|items?\s+listed)', re.IGNORECASE)
                nums = re.finditer(r'([0-9OolI\|,\.]{3,})', segment)
                best = None
                for m in nums:
                    val = normalize_numeric_str(m.group(1))
                    if not val or val < 100000:
                        continue
                    start, end = m.start(), m.end()
                    left = segment[max(0, start-15):start]
                    right = segment[end:end+15]
                    if noise_pat.search(left) or noise_pat.search(right):
                        continue
                    if best is None or val > best:
                        best = val
                price = best

    # global item fallback if not set yet
    if item is None:
        # patterns: "Transaction of <item> xNN", "Listed <item> xNN for", "Placed order of <item> xNN"
        # Be tolerant to line breaks between words using [\s\S]*? minimal matches
        m_item = re.search(fr"(?:transaction\s+of|placed\s+order\s+of|re-?list(?:ed)?|listed|withdrew\s+order\s+of|withdrew|purchased|sold)\s+([\s\S]*?)\s+{_MULTIPLIER_SYMBOL}", entry_text, re.I)
        if m_item:
            item = clean_item_name(m_item.group(1))
        else:
            # fallback: capture until 'worth' or 'for' or 'silver'
            m_item2 = re.search(r'(?:transaction\s+of|placed\s+order\s+of|re-?list(?:ed)?|listed|withdrew|withdrew\s+order\s+of|purchased|sold)\s+([\s\S]*?)(?:\s+worth|\s+for|\s+silver|$)', entry_text, re.I)
            if m_item2:
                item = clean_item_name(m_item2.group(1))
    # last-resort item inference: take token sequence before the qty marker within the chosen segment
    if item is None and (typ in ('transaction', 'purchased')):
        segment = tx_segment if (typ == 'transaction' and tx_segment is not None) else (purch_segment if (typ == 'purchased' and purch_segment is not None) else entry_text)
        m_local = re.search(fr"([A-Za-z0-9\s'\-:\(\)]{{3,}}?)\s+{_MULTIPLIER_SYMBOL}\s*[0-9OolI\|,\.]+", segment)
        if m_local:
            item = clean_item_name(m_local.group(1))
        elif re.search(r'\bcollect\b', segment, re.IGNORECASE):
            # Sammle Name vor/um den Multiplikator im Collect-Zusammenhang
            m_name = re.search(fr"([A-Za-z0-9\s'\-:\(\)]{{3,}}?)\s+(?:registration\s+count|collect|re-?list)\b", segment, re.IGNORECASE)
            if m_name:
                item = clean_item_name(m_name.group(1))

    # As an additional fallback: infer quantity when missing by looking for a number right before 'worth/for/silver'
    # Example: 'Transaction of Corrupt Oil of Immortality xlO worth 283,000,000 Silver' or
    # 'Transaction of Birch Sap OO0 worth 61,500,000 Silver'
    if typ in ('transaction', 'purchased') and (qty is None or qty == 0):
        silver_pat = r's[il1][lv][ve]r'
        # Prefer to search within the relevant segment to avoid picking numbers from adjacent UI text
        search_scope = tx_segment if (typ == 'transaction' and tx_segment is not None) else (purch_segment if (typ == 'purchased' and purch_segment is not None) else entry_text)
        # Allow optional multiplier symbol and capture the numeric token immediately before worth/for/silver
        m_qty_fallback = re.search(
            fr"(?:transact[il1]on\s+of|sold|purchased|bought)\s+([\s\S]*?)\s+(?:{_MULTIPLIER_SYMBOL}\s*)?([0-9OolI\|,\.]{1,6})\s+(?:worth|for|{silver_pat})\b",
            search_scope,
            re.IGNORECASE,
        )
        if m_qty_fallback:
            qty_cand = normalize_numeric_str(m_qty_fallback.group(2))
            # Only accept plausible quantities (1..100000)
            if qty_cand and 1 <= qty_cand <= 100000:
                qty = qty_cand
                # Use the trimmed item name from the capture group (group 1)
                item = clean_item_name(m_qty_fallback.group(1)) or item

    # If a plausible larger qty was present but earlier parsing yielded qty==1, allow override
    if typ in ('transaction', 'purchased') and (qty == 1 or qty is None):
        # look for explicit multiplier in the main segment (use the last valid before price context)
        segment = tx_segment if (typ == 'transaction' and tx_segment is not None) else (purch_segment if (typ == 'purchased' and purch_segment is not None) else entry_text)
        q2 = find_qty_in_segment(segment)
        if q2 and q2 >= 2:
            qty = q2

    # As a final heuristic, if qty is still missing or 1 but we have a price, infer from common stack sizes
    # This helps with OCR like 'OO0' (lost the '5' in '5,000') appearing without an 'x' multiplier.
    # Apply only to purchased to avoid inflating sell-side (e.g., crystals) when multiplier is missing.
    if typ == 'purchased' and (qty is None or qty <= 1) and price and not explicit_qty:
        # Try common stack sizes in descending order to prefer larger realistic batches
        for qcand in (5000, 1000, 100, 10):
            if price % qcand == 0:
                unit = price // qcand
                # accept reasonable unit prices (avoid absurdly low/high)
                if 100 <= unit <= 5_000_000:
                    qty = qcand
                    break

    # Clean trailing OCR quantity artifacts from item name (e.g., 'Birch Sap OO0' -> 'Birch Sap')
    if item:
        item = re.sub(r"\s+(?:x\s*s?)?\s*[0OoIl\|]{2,}$", "", item.strip(), flags=re.IGNORECASE)
        # additionally strip trailing multiplier artifacts like 'xS'/'x5'/'X5' at the end of the item name
        item = re.sub(r"\s*[x×X\*]\s*[0-9OolI\|Ss]{1,6}$", "", item, flags=re.IGNORECASE)
        # strip common OCR noise where the multiplier + quantity 'x12' was misread and glued to the name as 'Xlz'
        item = re.sub(r"\s*[x×X]\s*[lI1]\s*[zZ2]$", "", item, flags=re.IGNORECASE)
        # Fuzzy-Korrektur gegen Whitelist (sofern verfügbar)
        try:
            fixed = correct_item_name(item)
            if fixed:
                item = fixed
        except Exception:
            pass
    
    # Advanced plausibility check using market data (min/max unit prices)
    # Checks if the total price is plausible for the item based on known market ranges
    if typ in ('transaction', 'purchased') and price is not None and qty is not None and item:
        from utils import check_price_plausibility
        try:
            plausibility = check_price_plausibility(item, qty, price)
            if not plausibility['plausible']:
                reason = plausibility.get('reason', 'unknown')
                unit_price = plausibility.get('unit_price', 0)
                expected_min = plausibility.get('expected_min')
                expected_max = plausibility.get('expected_max')
                
                # Mark price as invalid if significantly outside range
                # This triggers UI fallback in tracker.py
                if reason in ('too_low', 'too_high'):
                    # Strict threshold: invalidate if price is less than 10% of expected minimum
                    # or more than 10x expected maximum (clear OCR error)
                    if reason == 'too_low' and expected_min and price < expected_min * 0.1:
                        # Price is less than 10% of expected minimum → definitely OCR error
                        # Common pattern: lost leading digit(s) e.g., "265M" instead of "1265M"
                        price = None
                    elif reason == 'too_high' and expected_max and price > expected_max * 10:
                        # Price is more than 10x expected maximum → definitely OCR error
                        price = None
                    # Moderate threshold: warn but keep price if within 10-50% of expected range
                    # This allows tracker.py to attempt UI fallback correction
                    elif reason == 'too_low' and expected_min and price < expected_min * 0.5:
                        # Price is 10-50% of expected minimum → possible OCR error
                        # Keep for now but mark for UI validation
                        pass  # Keep price, let tracker.py validate with UI
        except Exception:
            pass  # If plausibility check fails, keep original price
    
    # Fallback: Simple heuristic for very low prices with high quantities
    # (For items not in market_data.csv or if check failed)
    if typ in ('transaction', 'purchased') and price is not None and qty is not None:
        if qty >= 10 and price < 1_000_000:
            # Price too low for high quantity - likely OCR error with missing leading digits
            # Common pattern: lost 4-6 leading digits from a price like "585,585,000"
            # Mark as invalid price to trigger UI fallback in tracker.py
            price = None

    # timestamp: from ts_text if given, else try to find within entry_text
    ts = None
    # Prefer a timestamp found inside this entry snippet if available (more precise per-row attribution)
    m_ts_local = re.search(r'(20\d{2}[.\-/]\d{2}[.\-/]\d{2}\s+\d{2}[:\.,\-]\d{2})', entry_text)
    if m_ts_local:
        ts = parse_timestamp_text(m_ts_local.group(1))
    if not ts and ts_text:
        ts = parse_timestamp_text(ts_text)
    # kein Fallback auf Systemzeit; ohne gültigen Spiel-Zeitstempel wird der Eintrag verworfen

    return {
        'type': typ,
        'item': item,
        'qty': int(qty) if qty else None,
        'price': int(price) if price else None,
        'timestamp': ts,
        'raw': entry_text,
        'ts_text': ts_text
    }
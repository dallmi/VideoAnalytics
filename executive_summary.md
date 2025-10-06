# Video Analytics - Executive Summary

## Problem Statement

Aktuell werden Video-Interaktionen in Azure Log Analytics als einzelne Events (play, pause, resume, etc.) getrackt. Die Herausforderung besteht darin, aus diesen atomaren Events aussagekräftige Metriken wie **Total Watch Time** pro User und Video zu berechnen, um das Video-Engagement zu verstehen.

**Komplexität:** 
- Jede Interaktion = 1 Event-Row
- User Journey muss manuell rekonstruiert werden
- Edge Cases wie Browser-Close, Skips, Multi-Tab-Sessions

---

## Lösung: Multi-Layer Aggregation

### Architektur

```
Raw Events (AppInsights)
    ↓ [Real-time]
├─→ KQL Queries (Ad-hoc Analysis)
    ↓ [Hourly ETL]
├─→ Session Aggregation (Materialized View)
    ↓ [Daily ETL]
├─→ User-Video Metrics (SQL/Cosmos)
    ↓ [Reporting]
└─→ Dashboards & Analytics
```

---

## Implementierungs-Phasen

### Phase 1: Basis Watch Time (2 Wochen)
**Ziel:** Einfache Szenarien abdecken (Play → Pause → End)

**Deliverables:**
- KQL Query für Watch Time Berechnung
- Dashboard mit Top Videos by Watch Time
- Validierung mit bekannten Test-Usern

**Impact:** 80% der Use Cases abgedeckt

---

### Phase 2: Edge Cases (2 Wochen)
**Ziel:** Skip Detection, Session Timeouts, Data Quality

**Deliverables:**
- Jump/Skip Detection Logik
- Session Timeout Handling (Browser Close)
- Data Quality Dashboard
- Alert Rules für Anomalien

**Impact:** Robuste Datenqualität, korrekte Metriken auch bei komplexen Szenarien

---

### Phase 3: Multi-Video & Advanced (2 Wochen)
**Ziel:** Video-Switching, Replays, Multi-Session Tracking

**Deliverables:**
- Video-Switching Detection
- Replay-Erkennung
- User Engagement Scoring
- Retention & Drop-off Analysis

**Impact:** Tiefere Insights in User-Verhalten

---

### Phase 4: Database Layer (2 Wochen)
**Ziel:** Performance-Optimierung durch Aggregation

**Deliverables:**
- Materialized Views in Kusto
- ETL Pipeline (Python/Azure Functions)
- Aggregierte Tabellen: `video_sessions`, `user_video_metrics`
- Scheduled Reports

**Impact:** Sub-second Dashboard-Ladezeiten, Skalierung auf Millionen Events

---

## Key Metriken

### Video-Level Metriken
- **Unique Viewers**: Anzahl eindeutiger User
- **Total Watch Time**: Gesamte angeschaute Zeit
- **Completion Rate**: % der Sessions mit "video_ended" Event
- **Avg Watch Time per Session**: Durchschnittliche Wiedergabezeit
- **Engagement Score**: Gewichtete Metrik aus Watch Time, Completions, Sessions

### User-Level Metriken
- **Total Watch Time**: Summe über alle Videos
- **Videos Watched**: Anzahl gestarteter Videos
- **Videos Completed**: Anzahl fertig geschauter Videos
- **Engagement Tier**: High/Medium/Low/Minimal basierend auf Score

### Session-Level Metriken
- **Watch Time**: Tatsächlich angeschaute Zeit (ohne Skips)
- **Max Position**: Weiteste Stelle im Video
- **Pause Count**: Anzahl Pausen
- **Skip Count**: Anzahl Vor-/Zurücksprünge
- **Completed**: Boolean, ob Video zu Ende geschaut

---

## Szenario-Abdeckung (18 Szenarien identifiziert)

### ✅ Vollständig gelöst:
1. **Straightforward Play → End** (Basis-Szenario)
2. **Play → Pause → Resume → End** (Mit Pausen)
3. **Play → Pause → Browser Close** (Session Timeout)
4. **Skip Forward/Backward** (Jump Detection)
5. **Multiple Sessions (Replay)** (Replay-Erkennung)
6. **Multiple Videos in Session** (Video-Switching)

### ⚠️ Teilweise gelöst (benötigt Client-seitige Änderungen):
7. **Tab-Switch** (Heuristik über Pause-Dauer)
8. **Page Refresh** (Session-Neustart-Erkennung)
9. **Resume from Last Position** (Benötigt Position-Tracking)
10. **Autoplay** (Benötigt Autoplay-Flag im Event)

### 🔴 Nicht lösbar mit Current Events:
11. **Video komplett ignoriert** (Benötigt Page-View Events mit Video-Liste)

---

## Datenqualität & Monitoring

### Validation Checks
- ✅ Watch Time ≤ Video Duration (+10% Toleranz)
- ✅ Keine negative Watch Time
- ✅ Completion nur mit ausreichender Watch Time (>75%)
- ✅ Session-Dauer < 4 Stunden
- ✅ Events-per-Session Ratio: 3-5

### Alerts
- 🚨 Data Freshness > 3 Stunden
- 🚨 Completion Rate Drop > 20%
- 🚨 Zero-Watch-Rate > 15%
- 🚨 Negative Watch Time entdeckt

---

## Performance & Skalierung

### Aktuelle Schätzung (basierend auf Annahmen):
- **10,000 User/Tag** × 5 Videos × 4 Events = **200,000 Events/Tag**
- **6M Events/Monat**, **73M Events/Jahr**
- **Storage**: ~7.3 GB/Jahr (Raw), ~1 GB/Jahr (Aggregiert)

### Query Performance Targets:
- Session Aggregation (1 Tag): **< 5 Sekunden**
- User-Video Metrics (1 Woche): **< 10 Sekunden**
- Dashboard Refresh: **< 15 Sekunden**
- Real-time (letzte Stunde): **< 2 Sekunden**

Mit Materialized Views: **Sub-second queries** für aggregierte Daten

---

## Quick Start: Erste Schritte

### Woche 1: Validierung
1. **Deploy Basis-Query** aus Phase 1
2. **Teste mit 5-10 bekannten Usern**
3. **Vergleiche manuelle Stichproben** mit Query-Resultaten
4. **Dokumentiere Diskrepanzen**

### Woche 2: Dashboard Setup
1. **Setup Power BI / Grafana Dashboard**
2. **Implementiere Top 3 Metriken:**
   - Total Watch Time by Video
   - Completion Rate by Video
   - Active Users over Time

### Woche 3-4: Datenqualität
1. **Implementiere Data Quality Checks**
2. **Setup Alerts für Anomalien**
3. **Dokumentiere Edge Cases**

### Ab Woche 5: Iterative Verbesserung
- Advanced Scenarios nach Priorität
- Performance-Optimierung
- Feature Requests vom Business

---

## Kosten-Nutzen

### Aufwand
- **Phase 1-2**: ~4 Wochen (1 Developer)
- **Phase 3**: ~2 Wochen (Optional, je nach Business-Need)
- **Phase 4**: ~2 Wochen (Bei Performance-Problemen)
- **Gesamt**: 6-8 Wochen

### Nutzen
- ✅ **Datengetriebene Video-Strategie**: Welche Videos funktionieren?
- ✅ **Content-Optimierung**: Wo steigen User aus?
- ✅ **User Engagement Tracking**: Wer sind Power-User?
- ✅ **ROI-Messung**: Lohnt sich Video-Produktion?
- ✅ **A/B Testing Fähigkeit**: Welcher Thumbnail funktioniert besser?

---

## Risiken & Mitigationen

| Risiko | Wahrscheinlichkeit | Impact | Mitigation |
|--------|-------------------|--------|------------|
| Unvollständige Events (Browser Close) | Hoch | Mittel | Session Timeout Heuristik |
| Skip-Verhalten verfälscht Metriken | Mittel | Hoch | Jump Detection implementieren |
| Performance-Probleme bei Skalierung | Mittel | Mittel | Materialized Views, Aggregation |
| Tracking-Lücken (Multi-Tab) | Niedrig | Niedrig | Dokumentieren, nicht blockierend |

---

## Empfehlung

**Start sofort mit Phase 1** (Basis Watch Time Berechnung). Dies liefert bereits 80% des Business Value mit minimalem Aufwand.

**Phase 2 innerhalb von 4 Wochen** für Datenqualität und Robustheit.

**Phase 3+4 nach Bedarf**, basierend auf:
- Anzahl User/Events (Skalierung)
- Komplexität der Business-Fragen
- Performance-Anforderungen

---

## Nächste Schritte

1. ✅ **Review dieser Dokumentation** mit Team
2. 📅 **Sprint Planning** für Phase 1
3. 🧪 **Setup Test-Environment** mit synthetischen Events
4. 🚀 **Deploy Basis-Query** in Production
5. 📊 **Setup erstes Dashboard**
6. 🔄 **Iterative Verbesserung** basierend auf Feedback

---

## Anhänge

Detaillierte Dokumentation:
- `video_analytics_kql.md`: Vollständige KQL Queries für alle Szenarien
- `implementation_roadmap.md`: Schritt-für-Schritt Implementierung
- `video_analytics_etl.py`: Python ETL Pipeline für DB-Layer
- `test_scenarios.md`: Test Cases & Validierungs-Queries


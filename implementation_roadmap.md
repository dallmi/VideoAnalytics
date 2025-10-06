# Video Analytics - Implementierungs-Roadmap

## Phase 1: Quick Wins (Woche 1-2)

### 1.1 Basis Watch Time Berechnung
**Was:** Szenarien 1-3 abdecken (einfaches Play/Pause/End)

**KQL Query:**
```kusto
let videoEvents = customEvents
| where name in ("video_play", "video_pause", "video_resume", "video_ended")
| extend videoId = tostring(customDimensions.videoId)
| extend currentTime = todouble(customDimensions.currentTime)
| extend sessionId = tostring(customDimensions.sessionId)
| extend userId = tostring(customDimensions.userId)
| project timestamp, userId, sessionId, videoId, eventName = name, currentTime
| sort by userId, sessionId, videoId, timestamp asc
| serialize;

videoEvents
| extend prevEvent = prev(eventName)
| extend prevTime = prev(currentTime)
| extend prevSession = prev(sessionId)
| extend prevVideo = prev(videoId)
| extend isSameContext = (sessionId == prevSession) and (videoId == prevVideo)
| extend watchedSeconds = iff(
    isSameContext and 
    prevEvent in ("video_play", "video_resume") and 
    eventName in ("video_pause", "video_ended"),
    currentTime - prevTime,
    0.0
)
| summarize 
    totalWatchTime = sum(watchedSeconds),
    sessions = dcount(sessionId),
    completions = countif(eventName == "video_ended"),
    interactions = count()
    by userId, videoId
| where totalWatchTime > 0
```

**Validation:**
- Teste mit bekannten Usern die 1 komplettes Video angeschaut haben
- Expected: watchTime ≈ Video-Länge
- Expected: completions = 1

---

### 1.2 Quick Dashboard Setup
```kusto
// Top 10 Videos nach Total Watch Time
videoMetrics
| summarize 
    unique_viewers = dcount(userId),
    total_hours = sum(totalWatchTime) / 3600,
    avg_watch_time = avg(totalWatchTime)
    by videoId
| order by total_hours desc
| take 10
```

---

## Phase 2: Datenqualität & Edge Cases (Woche 3-4)

### 2.1 Jump/Skip Detection (Szenario 4)
**Problem:** User skippen vor/zurück, verfälscht Watch Time

**Lösung:**
```kusto
videoEvents
| extend timeDelta = currentTime - prev(currentTime)
| extend prevSession = prev(sessionId)
| extend isSameSession = sessionId == prevSession
| extend jumpType = case(
    not(isSameSession), "new_session",
    timeDelta > 5, "skip_forward",
    timeDelta < -2, "skip_backward", 
    "normal"
)
| extend validWatchTime = iff(
    jumpType == "normal" and 
    prev(eventName) in ("video_play", "video_resume"),
    timeDelta,
    0.0
)
```

**Testing:**
1. Identifiziere User mit vielen Skips: `| where jumpType != "normal" | summarize skips = count() by userId`
2. Vergleiche `sum(watchedSeconds)` mit `sum(validWatchTime)`
3. Expected: validWatchTime < watchedSeconds bei Usern mit Skips

---

### 2.2 Session Timeout Handling (Szenario 5)
**Problem:** Browser geschlossen = keine Events mehr

**Lösung:**
```kusto
let sessionTimeout = 300; // 5 Minuten in Sekunden

videoEvents
| serialize
| extend nextTimestamp = next(timestamp)
| extend nextSession = next(sessionId)
| extend isSameSession = sessionId == nextSession
| extend timeSinceLastEvent = datetime_diff('second', nextTimestamp, timestamp)
| extend sessionTimedOut = timeSinceLastEvent > sessionTimeout or not(isSameSession)
| extend estimatedWatchTime = case(
    // Normal pause/end event
    eventName in ("video_pause", "video_ended"), 
        currentTime - prev(currentTime),
    // Playing aber Session endet ohne pause/end = Timeout
    sessionTimedOut and eventName in ("video_play", "video_resume"),
        min_of(timeSinceLastEvent, sessionTimeout), // Max. Timeout anrechnen
    0.0
)
```

**Validation Approach:**
```kusto
// Finde Sessions ohne "sauberes" Ende
videoEvents
| summarize events = make_list(eventName), lastEvent = any(arg_max(timestamp, eventName)) by sessionId
| where lastEvent != "video_ended" and lastEvent != "video_pause"
| join kind=inner videoEvents on sessionId
| summarize count() // Wie viele Sessions sind betroffen?
```

---

### 2.3 Data Quality Checks
```kusto
// Quality Check Dashboard
let qualityChecks = videoEvents
| summarize 
    totalEvents = count(),
    sessionsWithoutEnd = countif(eventName != "video_ended" and eventName != "video_pause"),
    negativeTimeDelta = countif(currentTime < prev(currentTime)),
    duplicateEvents = count() - dcount(pack(sessionId, timestamp, eventName))
    by bin(timestamp, 1d);

qualityChecks
| extend 
    endEventRate = 1.0 - (todouble(sessionsWithoutEnd) / totalEvents),
    cleanDataRate = 1.0 - (todouble(negativeTimeDelta + duplicateEvents) / totalEvents)
| project timestamp, endEventRate, cleanDataRate, totalEvents
```

---

## Phase 3: Multi-Video & Advanced Scenarios (Woche 5-6)

### 3.1 Video Switching Detection (Szenario 10-11)
```kusto
videoEvents
| serialize
| extend prevVideoId = prev(videoId)
| extend prevTimestamp = prev(timestamp)
| extend isSameSession = sessionId == prev(sessionId)
| extend videoSwitch = isSameSession and (videoId != prevVideoId)
| summarize 
    videosInSession = dcount(videoId),
    switchCount = countif(videoSwitch),
    sessionWatchTime = sum(watchedSeconds)
    by userId, sessionId
| summarize 
    avgVideosPerSession = avg(todouble(videosInSession)),
    avgSwitchesPerSession = avg(todouble(switchCount)),
    sessionsWithMultipleVideos = countif(videosInSession > 1)
    by bin(timestamp, 1d)
```

---

### 3.2 Replay Detection (Szenario 13)
```kusto
// Identifiziere Replays
let videoSessions = videoEvents
| summarize 
    sessions = make_set(sessionId),
    sessionCount = dcount(sessionId),
    firstWatch = min(timestamp),
    lastWatch = max(timestamp)
    by userId, videoId;

videoSessions
| where sessionCount > 1
| extend isReplay = true
| join kind=rightouter (videoEvents) on userId, videoId
| extend isReplay = coalesce(isReplay, false)
| summarize 
    totalWatches = count(),
    uniqueWatchers = dcount(userId),
    replays = countif(isReplay)
    by videoId
| extend replayRate = todouble(replays) / totalWatches
```

---

## Phase 4: Database Layer & Aggregation (Woche 7-8)

### 4.1 Materialized View/Table erstellen

**Option A: Azure Data Explorer Materialized View**
```kusto
.create materialized-view video_sessions_mv on table customEvents
{
    customEvents
    | where name in ("video_play", "video_pause", "video_resume", "video_ended")
    | extend videoId = tostring(customDimensions.videoId)
    | extend currentTime = todouble(customDimensions.currentTime)
    | extend sessionId = tostring(customDimensions.sessionId)
    | extend userId = tostring(customDimensions.userId)
    | summarize 
        watchTime = sum(watchedSeconds),
        maxPosition = max(currentTime),
        completed = countif(name == "video_ended") > 0,
        eventCount = count()
        by userId, videoId, sessionId, bin(timestamp, 1d)
}
```

**Option B: Scheduled Export zu SQL/CosmosDB**
```kusto
// Export Job (läuft täglich)
.export to table session_summary
(
    videoEvents
    | where timestamp > ago(1d)
    | [deine Master Query hier]
)
```

---

### 4.2 Aggregation Pipeline
```
Raw Events (AppInsights) 
    ↓ [Real-time: 1-5 min latency]
Session Aggregation (KQL Materialized View)
    ↓ [Hourly ETL]
User-Video Metrics (SQL Table)
    ↓ [Daily ETL]
Video Performance Dashboard (PowerBI/Grafana)
```

---

## Phase 5: Advanced Analytics (Woche 9+)

### 5.1 Engagement Scoring
```kusto
userVideoMetrics
| extend engagementScore = 
    (totalWatchTime / 60.0) * 1.0 +                    // Base: Minuten geschaut
    (completions * 50.0) +                             // Bonus: Video fertig geschaut
    (sessionCount * 5.0) +                             // Bonus: Mehrere Sessions
    iff(maxPositionReached > 0.9, 20.0, 0.0) -        // Bonus: >90% geschaut
    (avgSkipsPerSession * 2.0)                         // Malus: Viel geskippt
| extend engagementTier = case(
    engagementScore > 100, "High",
    engagementScore > 50, "Medium",
    engagementScore > 10, "Low",
    "Minimal"
)
```

---

### 5.2 Retention & Drop-off Analysis
```kusto
// Wo steigen User aus?
videoEvents
| where eventName in ("video_pause", "video_ended")
| extend positionBucket = floor(currentTime / 30) * 30 // 30-Sekunden Buckets
| summarize 
    exitCount = count(),
    uniqueUsers = dcount(userId)
    by videoId, positionBucket
| order by videoId, positionBucket
```

---

### 5.3 Cohort Analysis
```kusto
// Erste Watch Date als Cohort
let userCohorts = videoEvents
| summarize firstWatch = min(timestamp) by userId
| extend cohort = startofweek(firstWatch);

videoEvents
| join kind=inner userCohorts on userId
| summarize 
    weeklyActiveUsers = dcount(userId),
    avgWatchTime = avg(watchedSeconds)
    by cohort, weeksSinceFirstWatch = datetime_diff('week', timestamp, cohort)
| order by cohort, weeksSinceFirstWatch
```

---

## Testing Strategy

### Testdaten generieren
```kusto
// Finde "saubere" Testfälle für jedes Szenario
let testScenarios = datatable(scenario:string, description:string)
[
    "complete_watch", "User watched entire video without pause",
    "pause_resume", "User paused and resumed multiple times",
    "abandoned", "User started but never finished",
    "skip_forward", "User skipped parts of video",
    "multi_session", "User watched video across multiple sessions"
];

// Für jedes Szenario: Finde 5 Beispiel-User
videoEvents
| where <szenario_bedingung>
| summarize by userId, sessionId
| take 5
```

### Validation Queries
```kusto
// 1. Plausibility Check: Watch Time kann nicht > Video-Länge sein
userVideoMetrics
| join kind=inner videoMetadata on videoId // Annahme: Du hast Video-Längen
| where totalWatchTime > videoDuration * 1.1 // 10% Toleranz
| project userId, videoId, totalWatchTime, videoDuration, deviation = totalWatchTime - videoDuration

// 2. Consistency Check: Completions ohne ausreichende Watch Time
userVideoMetrics
| join kind=inner videoMetadata on videoId
| where completions > 0 and totalWatchTime < videoDuration * 0.8
| project userId, videoId, completions, totalWatchTime, videoDuration

// 3. Anomaly Detection: Extreme Outliers
userVideoMetrics
| summarize avg_watch = avg(totalWatchTime), std_watch = stdev(totalWatchTime) by videoId
| join kind=inner userVideoMetrics on videoId
| where totalWatchTime > (avg_watch + 3 * std_watch) // 3 Sigma
| project userId, videoId, totalWatchTime, avg_watch, deviation = totalWatchTime - avg_watch
```

---

## Metriken für Success Tracking

### KPIs zu monitoren:
1. **Data Completeness**: % der Sessions mit "sauberem" Ende (ended/paused event)
2. **Processing Lag**: Zeit zwischen Event und Aggregation
3. **Query Performance**: P95 Latency der Dashboard-Queries
4. **Data Volume**: Events pro Tag, Storage Growth
5. **Business Metrics**: 
   - Unique Viewers pro Video
   - Avg. Watch Time
   - Completion Rate
   - Engagement Score Distribution

### Alert Rules
```kusto
// Alert: Completion Rate Drop
videoMetrics
| where timestamp > ago(7d)
| summarize currentRate = avg(completionRate) by videoId
| join kind=inner (
    videoMetrics 
    | where timestamp between (ago(14d) .. ago(7d))
    | summarize previousRate = avg(completionRate) by videoId
) on videoId
| where currentRate < previousRate * 0.8 // 20% Drop
| project videoId, currentRate, previousRate, drop = previousRate - currentRate
```

---

## Nächste Schritte

1. **Jetzt sofort:**
   - Starte mit Phase 1 Query
   - Teste mit 5-10 bekannten Usern
   - Validiere Ergebnisse manuell

2. **Diese Woche:**
   - Implementiere Jump Detection
   - Setup Data Quality Dashboard
   - Dokumentiere bekannte Edge Cases

3. **Nächste 2 Wochen:**
   - Session Timeout Handling
   - Multi-Video Tracking
   - Erste Materialized View

4. **Langfristig:**
   - Engagement Scoring
   - Predictive Analytics (wer schaut Video wahrscheinlich zu Ende?)
   - A/B Testing Framework für Video-Features


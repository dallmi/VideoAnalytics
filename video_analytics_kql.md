# Video Analytics - Szenario-basierte KQL Queries

## Übersicht der Szenarien & Lösungsansätze

### **Annahmen für die Queries:**
- Event-Namen: `video_play`, `video_pause`, `video_resume`, `video_ended`
- CustomDimensions enthalten: `videoId`, `currentTime`, `sessionId`, `userId`
- Timestamps sind vorhanden

---

## **1. SINGLE VIDEO INTERACTION SCENARIOS (1-8)**

### Szenario 1-3: Grundlegende Play/Pause/End Logik

```kusto
// Basis-Query: Watch Time pro User & Video berechnen
let videoEvents = customEvents
| where name in ("video_play", "video_pause", "video_resume", "video_ended")
| extend videoId = tostring(customDimensions.videoId)
| extend currentTime = todouble(customDimensions.currentTime)
| extend sessionId = tostring(customDimensions.sessionId)
| extend userId = tostring(customDimensions.userId)
| project timestamp, userId, sessionId, videoId, eventName = name, currentTime
| sort by userId, sessionId, videoId, timestamp asc;

// Watch Time Berechnung mit State Machine Logik
videoEvents
| serialize 
| extend prevEvent = prev(eventName)
| extend prevTime = prev(currentTime)
| extend prevTimestamp = prev(timestamp)
| extend isSameSession = (sessionId == prev(sessionId)) and (videoId == prev(videoId))
// Watchtime = currentTime - prevTime nur wenn von play/resume zu pause/end
| extend watchedSeconds = iff(
    isSameSession and prevEvent in ("video_play", "video_resume") and eventName in ("video_pause", "video_ended"),
    currentTime - prevTime,
    0.0
)
| summarize 
    totalWatchedSeconds = sum(watchedSeconds),
    completedVideo = countif(eventName == "video_ended") > 0,
    pauseCount = countif(eventName == "video_pause"),
    maxPosition = max(currentTime)
    by userId, videoId, sessionId
| summarize 
    totalWatchTime = sum(totalWatchedSeconds),
    sessions = count(),
    completions = countif(completedVideo),
    avgPauses = avg(todouble(pauseCount)),
    maxReached = max(maxPosition)
    by userId, videoId
```

### Szenario 3: Video pausiert aber nie resumed (Browser geschlossen)

```kusto
// Identifiziere "unvollständige" Sessions
let incompleteSessions = videoEvents
| summarize 
    events = make_list(eventName),
    lastEvent = arg_max(timestamp, eventName),
    duration = datetime_diff('second', max(timestamp), min(timestamp))
    by userId, sessionId, videoId
| where lastEvent == "video_pause" // Letzte Aktion war Pause
| where duration > 10 // Session länger als 10 Sekunden
| project userId, sessionId, videoId, sessionType = "incomplete";

// Verwende für diese Sessions die Zeit bis zur letzten Pause
videoEvents
| join kind=leftouter incompleteSession on userId, sessionId, videoId
| extend isIncomplete = isnotnull(sessionType)
// ... weitere Berechnung
```

### Szenario 4: Skip/Seek Forward/Backward

```kusto
// Erkennung von Jumps im Video
let videoEventsWithJumps = videoEvents
| serialize
| extend prevTime = prev(currentTime)
| extend timeDelta = currentTime - prevTime
| extend isSameSession = (sessionId == prev(sessionId)) and (videoId == prev(videoId))
| extend jumpType = case(
    not(isSameSession), "new_session",
    timeDelta > 5, "skip_forward",  // Mehr als 5 Sekunden Sprung vorwärts
    timeDelta < -2, "skip_backward", // Sprung rückwärts
    "normal"
);

// Watch Time NUR für normale Abspielungen (ohne Skips)
videoEventsWithJumps
| where jumpType == "normal"
| extend watchedSeconds = iff(
    prev(eventName) in ("video_play", "video_resume") and eventName in ("video_pause", "video_ended"),
    currentTime - prevTime,
    0.0
)
| summarize 
    totalWatchTime = sum(watchedSeconds),
    forwardSkips = countif(jumpType == "skip_forward"),
    backwardSkips = countif(jumpType == "skip_backward")
    by userId, videoId
```

### Szenario 5: Browser geschlossen ohne Event

```kusto
// Heuristik: Wenn zwischen Events mehr als X Minuten vergehen
let sessionTimeout = 5m; // 5 Minuten Timeout

videoEvents
| serialize
| extend nextTimestamp = next(timestamp)
| extend isSameSession = (sessionId == next(sessionId))
| extend timeSinceLastEvent = datetime_diff('second', nextTimestamp, timestamp)
| extend sessionEnded = not(isSameSession) or timeSinceLastEvent > datetime_diff('second', sessionTimeout, datetime(0))
| extend estimatedWatchTime = case(
    sessionEnded and eventName in ("video_play", "video_resume"), 
        min_of(timeSinceLastEvent, 300), // Max 5 Minuten anrechnen
    eventName in ("video_pause", "video_ended"),
        currentTime - prev(currentTime),
    0.0
)
| summarize totalWatchTime = sum(estimatedWatchTime) by userId, videoId
```

### Szenario 6-7: Tab Switch & Resume

```kusto
// Verwende Page Visibility API Events (falls implementiert)
// Falls nicht: Heuristik über längere Pausen zwischen Events
let suspiciousPauses = videoEvents
| serialize
| extend nextTimestamp = next(timestamp)
| extend isSameSession = (sessionId == next(sessionId))
| extend pauseDuration = datetime_diff('second', nextTimestamp, timestamp)
| where isSameSession
| where eventName in ("video_play", "video_resume")
| where next(eventName) in ("video_play", "video_resume", "video_pause")
| where pauseDuration > 60 // Pause länger als 1 Minute = wahrscheinlich Tab-Switch
| project userId, sessionId, videoId, timestamp, suspectedTabSwitch = true;

// In der Hauptberechnung diese Zeiten ausschließen oder gesondert behandeln
```

### Szenario 8: Page Refresh

```kusto
// Erkennung über Session-Neustart bei gleichem User & Video
let refreshDetection = videoEvents
| summarize 
    minTime = min(timestamp),
    firstEvent = arg_min(timestamp, eventName, currentTime)
    by userId, videoId, sessionId
| where firstEvent_eventName == "video_play" 
| where firstEvent_currentTime > 0 // Video startet nicht bei 0 = wahrscheinlich Refresh
| project userId, videoId, sessionId, isRefresh = true;
```

---

## **2. MULTIPLE VIDEOS SCENARIOS (9-14)**

### Szenario 9: Sequentielles Ansehen mehrerer Videos

```kusto
// Aggregation über mehrere Videos hinweg
videoEvents
| summarize 
    totalWatchTime = sum(watchedSeconds),
    videosStarted = dcount(videoId),
    videosCompleted = dcountif(videoId, eventName == "video_ended")
    by userId, bin(timestamp, 1d) // Pro Tag
```

### Szenario 10-11: Video-Switching

```kusto
// Identifiziere Video-Wechsel innerhalb einer Session
let videoSwitching = videoEvents
| serialize
| extend prevVideoId = prev(videoId)
| extend prevTimestamp = prev(timestamp)
| extend isSameSession = sessionId == prev(sessionId)
| extend videoSwitch = isSameSession and (videoId != prevVideoId)
| extend switchTime = datetime_diff('second', timestamp, prevTimestamp)
| where videoSwitch
| summarize 
    switchCount = count(),
    avgSwitchTime = avg(switchTime),
    videosInSession = dcount(videoId)
    by userId, sessionId;

// Watch Time pro Video auch bei Switching korrekt berechnen
videoEvents
| serialize
| extend prevVideoId = prev(videoId)
| extend watchedSeconds = iff(
    videoId == prevVideoId and prev(eventName) in ("video_play", "video_resume"),
    currentTime - prev(currentTime),
    0.0
)
| summarize totalWatchTime = sum(watchedSeconds) by userId, videoId
```

### Szenario 12: Mehrere Videos gleichzeitig (Multiple Tabs)

```kusto
// Erkennung über überlappende Timestamps
let overlappingVideos = videoEvents
| summarize 
    startTime = min(timestamp),
    endTime = max(timestamp)
    by userId, sessionId, videoId
| join kind=inner (
    videoEvents
    | summarize 
        startTime2 = min(timestamp),
        endTime2 = max(timestamp)
    by userId, sessionId2 = sessionId, videoId2 = videoId
) on userId
| where sessionId != sessionId2
| where videoId != videoId2
| where startTime < endTime2 and endTime > startTime2 // Overlap
| project userId, session1 = sessionId, video1 = videoId, 
          session2 = sessionId2, video2 = videoId2, overlapDetected = true;

// Bei Overlap: Watch Time auf beide Videos aufteilen oder nur das "aktive" zählen
```

### Szenario 13: Video Replay

```kusto
// Replay-Erkennung über mehrere Sessions mit gleichem Video
let replays = videoEvents
| summarize 
    sessions = dcount(sessionId),
    firstWatch = min(timestamp),
    lastWatch = max(timestamp)
    by userId, videoId
| where sessions > 1
| project userId, videoId, replayCount = sessions - 1;

// Separate Metriken für First-Time vs. Replay
videoEvents
| join kind=leftouter replays on userId, videoId
| extend isReplay = isnotnull(replayCount)
| summarize 
    firstTimeWatchers = dcountif(userId, not(isReplay)),
    replayWatchers = dcountif(userId, isReplay),
    totalWatchTime = sum(watchedSeconds)
    by videoId
```

---

## **3. PAGE/WINDOW-LEVEL INTERACTIONS (15-18)**

### Szenario 15: Browser Close & Return

```kusto
// Session-Tracking über User-Agent, IP und zeitliche Nähe
let returningUsers = videoEvents
| summarize 
    sessions = make_list(pack("sessionId", sessionId, "timestamp", timestamp, "videoId", videoId))
    by userId, videoId
| mv-expand sessions
| extend sessionId = tostring(sessions.sessionId)
| extend timestamp = todatetime(sessions.timestamp)
| extend videoId = tostring(sessions.videoId)
| serialize
| extend nextSession = next(sessionId)
| extend nextTimestamp = next(timestamp)
| extend timeBetweenSessions = datetime_diff('minute', nextTimestamp, timestamp)
| where timeBetweenSessions between (1 .. 60) // 1-60 Minuten = wahrscheinlich Return
| summarize returningSessions = count() by userId, videoId;
```

### Szenario 16: Resume from Last Position

```kusto
// Benötigt Tracking der letzten Position beim Verlassen
// Prüfe ob neue Session nahe der letzten Position startet
let lastPositions = videoEvents
| where eventName in ("video_pause", "video_ended")
| summarize lastPosition = arg_max(timestamp, currentTime) by userId, videoId, sessionId;

videoEvents
| where eventName == "video_play"
| join kind=inner lastPositions on userId, videoId
| where sessionId != sessionId1 // Andere Session
| where timestamp > timestamp1 // Späterer Zeitpunkt
| where abs(currentTime - lastPosition_currentTime) < 10 // Innerhalb 10 Sekunden
| project userId, videoId, sessionId, resumedFromPosition = true;
```

### Szenario 17: Autoplay Interaction

```kusto
// Wenn vorhanden: Autoplay-Flag im Event
// Sonst: Heuristik über sehr kurze Zeit zwischen Page Load und Play
let autoplayVideos = videoEvents
| where eventName == "video_play"
| extend isAutoplay = tobool(customDimensions.autoplay) // Falls getrackt
// Oder Heuristik:
| extend timeSincePageLoad = todouble(customDimensions.timeSincePageLoad)
| where timeSincePageLoad < 1000 // Weniger als 1 Sekunde
| project userId, videoId, sessionId, isAutoplay = true;

// Engagement-Metrik: Hat User bei Autoplay interagiert?
videoEvents
| join kind=leftouter autoplayVideos on userId, videoId, sessionId
| summarize 
    wasAutoplay = max(iff(isnotnull(isAutoplay), 1, 0)),
    hadInteraction = countif(eventName in ("video_pause", "video_resume")) > 0
    by userId, videoId, sessionId
| summarize 
    autoplayEngagement = todouble(sumif(hadInteraction, wasAutoplay == 1)) / sumif(1, wasAutoplay == 1)
    by videoId
```

### Szenario 18: Video komplett ignoriert

```kusto
// Videos auf der Seite, aber keine Events
// Benötigt: Page-View Events mit Liste der verfügbaren Videos
let pageViews = customEvents
| where name == "page_view"
| extend videosOnPage = todynamic(customDimensions.videosOnPage)
| mv-expand videoId = videosOnPage
| project userId, pageViewTime = timestamp, videoId = tostring(videoId);

let videoInteractions = videoEvents
| summarize firstInteraction = min(timestamp) by userId, videoId;

pageViews
| join kind=leftanti videoInteractions on userId, videoId
| summarize ignoredViews = count() by videoId
```

---

## **4. MASTER QUERY - Alle Metriken kombiniert**

```kusto
// Schritt 1: Event-Stream vorbereiten
let enrichedEvents = customEvents
| where name in ("video_play", "video_pause", "video_resume", "video_ended")
| extend videoId = tostring(customDimensions.videoId)
| extend currentTime = todouble(customDimensions.currentTime)
| extend sessionId = tostring(customDimensions.sessionId)
| extend userId = tostring(customDimensions.userId)
| project timestamp, userId, sessionId, videoId, eventName = name, currentTime
| sort by userId, sessionId, videoId, timestamp asc
| serialize
| extend prevEvent = prev(eventName, 1)
| extend prevTime = prev(currentTime, 1)
| extend prevTimestamp = prev(timestamp, 1)
| extend prevSessionId = prev(sessionId, 1)
| extend prevVideoId = prev(videoId, 1)
| extend isSameSession = (sessionId == prevSessionId) and (videoId == prevVideoId);

// Schritt 2: Watch Time berechnen (mit Jump Detection)
let watchTimeCalc = enrichedEvents
| extend timeDelta = currentTime - prevTime
| extend isJump = abs(timeDelta) > 5 // Mehr als 5 Sekunden Unterschied
| extend watchedSeconds = case(
    not(isSameSession), 0.0,
    isJump, 0.0, // Keine Watch Time bei Jumps
    prevEvent in ("video_play", "video_resume") and eventName in ("video_pause", "video_ended"), timeDelta,
    0.0
)
| extend segmentType = case(
    not(isSameSession), "new_session",
    isJump and timeDelta > 0, "skip_forward",
    isJump and timeDelta < 0, "skip_backward",
    "normal_playback"
);

// Schritt 3: Session-Level Aggregation
let sessionMetrics = watchTimeCalc
| summarize 
    watchTime = sum(watchedSeconds),
    events = count(),
    completed = countif(eventName == "video_ended") > 0,
    pauses = countif(eventName == "video_pause"),
    forwardSkips = countif(segmentType == "skip_forward"),
    backwardSkips = countif(segmentType == "skip_backward"),
    maxPosition = max(currentTime),
    startTime = min(timestamp),
    endTime = max(timestamp),
    duration = datetime_diff('second', max(timestamp), min(timestamp))
    by userId, videoId, sessionId;

// Schritt 4: User-Video Aggregation
sessionMetrics
| summarize 
    totalWatchTime = sum(watchTime),
    sessions = count(),
    completions = countif(completed),
    avgWatchTimePerSession = avg(watchTime),
    avgPausesPerSession = avg(todouble(pauses)),
    totalForwardSkips = sum(forwardSkips),
    totalBackwardSkips = sum(backwardSkips),
    maxPositionReached = max(maxPosition),
    firstWatch = min(startTime),
    lastWatch = max(endTime),
    avgSessionDuration = avg(duration)
    by userId, videoId
| extend 
    engagementScore = (totalWatchTime / 60.0) * (1.0 + todouble(completions) * 0.5),
    isActiveViewer = completions > 0 or totalWatchTime > 60
| order by totalWatchTime desc
```

---

## **5. AGGREGATION AUF VIDEO-EBENE**

```kusto
// Top-Level Video Performance Metriken
sessionMetrics
| summarize 
    uniqueViewers = dcount(userId),
    totalViews = count(),
    completionRate = todouble(countif(completed)) / count(),
    avgWatchTime = avg(watchTime),
    medianWatchTime = percentile(watchTime, 50),
    totalWatchTime = sum(watchTime),
    avgSessionDuration = avg(duration),
    repeatedViewers = dcountif(userId, count() > 1)
    by videoId
| extend 
    avgWatchPercentage = (avgWatchTime / (maxPositionReached / count())) * 100,
    engagement_tier = case(
        completionRate > 0.7, "High",
        completionRate > 0.4, "Medium",
        "Low"
    )
| order by uniqueViewers desc
```

---

## **6. DATENBANK-LAYER OPTIMIERUNGEN**

### Vorschlag für aggregierte Tabelle:

```sql
CREATE TABLE video_watch_sessions (
    user_id STRING,
    video_id STRING,
    session_id STRING,
    watch_time_seconds FLOAT,
    max_position_reached FLOAT,
    completed BOOLEAN,
    pause_count INT,
    forward_skip_count INT,
    backward_skip_count INT,
    session_start TIMESTAMP,
    session_end TIMESTAMP,
    session_duration_seconds INT,
    PRIMARY KEY (user_id, video_id, session_id)
)

-- Aggregierte User-Video Metriken
CREATE TABLE user_video_metrics (
    user_id STRING,
    video_id STRING,
    total_watch_time_seconds FLOAT,
    session_count INT,
    completion_count INT,
    first_watch_date TIMESTAMP,
    last_watch_date TIMESTAMP,
    avg_watch_time_per_session FLOAT,
    engagement_score FLOAT,
    last_updated TIMESTAMP,
    PRIMARY KEY (user_id, video_id)
)
```

### ETL Job (täglich/stündlich):

```kusto
// Von Raw Events zu aggregierten Sessions
.set-or-append video_watch_sessions <| 
watchTimeCalc
| where timestamp > ago(1d)
| summarize 
    watch_time_seconds = sum(watchedSeconds),
    max_position_reached = max(currentTime),
    completed = countif(eventName == "video_ended") > 0,
    pause_count = countif(eventName == "video_pause"),
    forward_skip_count = countif(segmentType == "skip_forward"),
    backward_skip_count = countif(segmentType == "skip_backward"),
    session_start = min(timestamp),
    session_end = max(timestamp),
    session_duration_seconds = datetime_diff('second', max(timestamp), min(timestamp))
    by user_id = userId, video_id = videoId, session_id = sessionId
```

---

## **7. DASHBOARD QUERIES**

### Top Videos by Engagement
```kusto
user_video_metrics
| summarize 
    unique_viewers = dcount(user_id),
    total_watch_hours = sum(total_watch_time_seconds) / 3600,
    avg_completion_rate = avg(todouble(completion_count) / session_count)
    by video_id
| order by total_watch_hours desc
| take 10
```

### User Engagement Over Time
```kusto
video_watch_sessions
| summarize 
    active_users = dcount(user_id),
    total_watch_hours = sum(watch_time_seconds) / 3600,
    avg_session_length = avg(watch_time_seconds)
    by bin(session_start, 1d)
| render timechart
```

### Completion Funnel
```kusto
video_watch_sessions
| extend completion_bucket = case(
    max_position_reached < 0.25, "0-25%",
    max_position_reached < 0.5, "25-50%",
    max_position_reached < 0.75, "50-75%",
    "75-100%"
)
| summarize sessions = count() by video_id, completion_bucket
| order by video_id, completion_bucket
```


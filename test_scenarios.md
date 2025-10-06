# Video Analytics - Test Scenarios & Validation

## Test Data Generation

### Szenario 1: Complete Watch (Ideal Path)
```kusto
// User watches entire video without interruption
let testUserId = "test_user_001";
let testVideoId = "video_123";
let testSessionId = "session_001";
let videoDuration = 180; // 3 minutes

datatable(timestamp:datetime, eventName:string, currentTime:double)
[
    datetime(2025-01-15 10:00:00), "video_play", 0.0,
    datetime(2025-01-15 10:03:00), "video_ended", 180.0
]
| extend userId = testUserId, videoId = testVideoId, sessionId = testSessionId

// Expected Result:
// - watchTime = 180 seconds
// - completed = true
// - pauseCount = 0
```

### Szenario 2: Pause & Resume
```kusto
datatable(timestamp:datetime, eventName:string, currentTime:double)
[
    datetime(2025-01-15 10:00:00), "video_play", 0.0,
    datetime(2025-01-15 10:01:00), "video_pause", 60.0,      // Watched 60s
    datetime(2025-01-15 10:05:00), "video_resume", 60.0,     // Pause for 4 minutes
    datetime(2025-01-15 10:07:00), "video_ended", 180.0      // Watched another 120s
]
| extend userId = testUserId, videoId = testVideoId, sessionId = testSessionId

// Expected Result:
// - watchTime = 180 seconds (60 + 120)
// - completed = true
// - pauseCount = 1
// - sessionDuration = 420 seconds (7 minutes including pause)
```

### Szenario 3: Abandoned (No Resume)
```kusto
datatable(timestamp:datetime, eventName:string, currentTime:double)
[
    datetime(2025-01-15 10:00:00), "video_play", 0.0,
    datetime(2025-01-15 10:01:30), "video_pause", 90.0
    // No resume or end event = user closed browser
]
| extend userId = testUserId, videoId = testVideoId, sessionId = testSessionId

// Expected Result:
// - watchTime = 90 seconds
// - completed = false
// - sessionEnd detected via timeout heuristic
```

### Szenario 4: Skip Forward
```kusto
datatable(timestamp:datetime, eventName:string, currentTime:double)
[
    datetime(2025-01-15 10:00:00), "video_play", 0.0,
    datetime(2025-01-15 10:00:30), "video_pause", 30.0,      // Watched 30s
    datetime(2025-01-15 10:00:35), "video_resume", 90.0,     // Skipped to 1:30
    datetime(2025-01-15 10:02:05), "video_ended", 180.0      // Watched 90s more
]
| extend userId = testUserId, videoId = testVideoId, sessionId = testSessionId

// Expected Result:
// - watchTime = 120 seconds (30 + 90, skip not counted)
// - skipCount = 1
// - maxPosition = 180
```

### Szenario 5: Skip Backward (Replay Section)
```kusto
datatable(timestamp:datetime, eventName:string, currentTime:double)
[
    datetime(2025-01-15 10:00:00), "video_play", 0.0,
    datetime(2025-01-15 10:01:00), "video_pause", 60.0,
    datetime(2025-01-15 10:01:05), "video_resume", 30.0,     // Jump back 30s
    datetime(2025-01-15 10:02:35), "video_ended", 120.0      // Watched 90s
]
| extend userId = testUserId, videoId = testVideoId, sessionId = testSessionId

// Expected Result:
// - watchTime = 150 seconds (60 + 90)
// - skipCount = 1 (backward skip)
// - Note: User watched seconds 30-60 twice
```

### Szenario 6: Multiple Sessions (Replay)
```kusto
// Session 1: Partial watch
datatable(timestamp:datetime, eventName:string, currentTime:double, sessionId:string)
[
    datetime(2025-01-15 10:00:00), "video_play", 0.0, "session_001",
    datetime(2025-01-15 10:01:00), "video_pause", 60.0, "session_001"
]
| extend userId = testUserId, videoId = testVideoId
| union (
    // Session 2: Complete watch later
    datatable(timestamp:datetime, eventName:string, currentTime:double, sessionId:string)
    [
        datetime(2025-01-15 15:00:00), "video_play", 0.0, "session_002",
        datetime(2025-01-15 15:03:00), "video_ended", 180.0, "session_002"
    ]
    | extend userId = testUserId, videoId = testVideoId
)

// Expected Result:
// - totalWatchTime = 240 seconds (60 + 180)
// - sessionCount = 2
// - completionCount = 1
// - isReplay = true
```

### Szenario 7: Multiple Videos in One Session
```kusto
datatable(timestamp:datetime, eventName:string, videoId:string, currentTime:double)
[
    // Video 1
    datetime(2025-01-15 10:00:00), "video_play", "video_001", 0.0,
    datetime(2025-01-15 10:02:00), "video_ended", "video_001", 120.0,
    // Switch to Video 2
    datetime(2025-01-15 10:02:30), "video_play", "video_002", 0.0,
    datetime(2025-01-15 10:05:30), "video_ended", "video_002", 180.0
]
| extend userId = testUserId, sessionId = testSessionId

// Expected Result:
// - 2 separate video watches in same session
// - video_001: watchTime = 120s, completed
// - video_002: watchTime = 180s, completed
```

---

## Validation Queries

### 1. Watch Time Cannot Exceed Video Duration
```kusto
let videoDurations = datatable(videoId:string, duration:double)
[
    "video_001", 300,
    "video_002", 600,
    "video_003", 180
];

userVideoMetrics
| join kind=inner videoDurations on videoId
| where totalWatchTime > duration * 1.1  // Allow 10% tolerance for errors
| project userId, videoId, totalWatchTime, videoDuration = duration,
          excessTime = totalWatchTime - duration,
          excessPercentage = ((totalWatchTime - duration) / duration) * 100
| order by excessPercentage desc

// Action: Investigate users with >10% excess watch time
```

### 2. Completion Without Sufficient Watch Time
```kusto
userVideoMetrics
| join kind=inner videoDurations on videoId
| where completionCount > 0
| where totalWatchTime < duration * 0.75  // Should watch at least 75%
| project userId, videoId, completionCount, totalWatchTime, 
          videoDuration = duration,
          watchPercentage = (totalWatchTime / duration) * 100
| order by watchPercentage asc

// Action: These might be data quality issues or skip-to-end behaviors
```

### 3. Negative Watch Time Detection
```kusto
// This should NEVER happen
videoSessions
| where watchTime < 0
| project userId, videoId, sessionId, watchTime, 
          sessionStart, sessionEnd, eventCount
| take 100

// Action: Critical data quality issue - investigate immediately
```

### 4. Unrealistic Session Durations
```kusto
videoSessions
| where sessionDuration > 14400  // > 4 hours
| project userId, videoId, sessionId, 
          sessionDuration,
          sessionDurationHours = sessionDuration / 3600,
          watchTime,
          maxPosition
| order by sessionDuration desc

// Action: Likely forgotten tabs or session timeout issues
```

### 5. Sessions Without Any Watch Time
```kusto
videoSessions
| where watchTime == 0
| summarize 
    zeroWatchSessions = count(),
    totalSessions = count()
    by bin(sessionStart, 1d)
| extend zeroWatchRate = todouble(zeroWatchSessions) / totalSessions
| where zeroWatchRate > 0.1  // Alert if >10% have zero watch time
| order by sessionStart desc

// Action: Might indicate tracking issues or users who immediately close
```

### 6. Completion Rate by Video
```kusto
videoSessions
| summarize 
    totalSessions = count(),
    completions = countif(completed),
    uniqueUsers = dcount(userId),
    avgWatchTime = avg(watchTime),
    medianWatchTime = percentile(watchTime, 50)
    by videoId
| extend completionRate = todouble(completions) / totalSessions
| order by completionRate desc

// Compare with expected completion rates (typically 30-60% for educational content)
```

### 7. User Engagement Distribution
```kusto
userVideoMetrics
| summarize 
    users = dcount(userId)
    by engagementTier
| extend percentage = (todouble(users) / toscalar(userVideoMetrics | summarize dcount(userId))) * 100
| order by 
    case(
        engagementTier == "High", 4,
        engagementTier == "Medium", 3,
        engagementTier == "Low", 2,
        1
    ) desc

// Healthy distribution: ~10-15% High, ~25-30% Medium, ~35-40% Low, ~20-25% Minimal
```

### 8. Data Freshness Check
```kusto
videoSessions
| summarize 
    latestEvent = max(sessionEnd),
    oldestEvent = min(sessionStart),
    totalEvents = count()
| extend 
    dataAge = datetime_diff('hour', now(), latestEvent),
    dataSpan = datetime_diff('day', latestEvent, oldestEvent)
| project latestEvent, dataAge, dataSpan, totalEvents

// Alert if dataAge > 2 hours (ETL might be failing)
```

### 9. Session Continuity Check
```kusto
// Check for gaps in user sessions that might indicate tracking issues
videoSessions
| where sessionDuration > 60  // At least 1 minute
| summarize sessions = make_list(pack("start", sessionStart, "end", sessionEnd, "watchTime", watchTime))
    by userId, videoId
| mv-expand sessions
| extend 
    start = todatetime(sessions.start),
    end = todatetime(sessions.end),
    watchTime = todouble(sessions.watchTime)
| serialize
| extend nextStart = next(start)
| extend gapMinutes = datetime_diff('minute', nextStart, end)
| where gapMinutes < 0  // Overlapping sessions!
| project userId, videoId, 
          session1_end = end,
          session2_start = nextStart,
          overlap = abs(gapMinutes)

// Action: Sessions should not overlap unless multiple tabs/devices
```

### 10. Compare Sessions vs Events Ratio
```kusto
let sessionCount = videoSessions | summarize count();
let eventCount = customEvents 
    | where name in ("video_play", "video_pause", "video_resume", "video_ended")
    | summarize count();

print 
    sessions = toscalar(sessionCount),
    events = toscalar(eventCount),
    eventsPerSession = todouble(toscalar(eventCount)) / toscalar(sessionCount)

// Typical ratio: 3-5 events per session
// Much higher: Might indicate excessive pausing
// Much lower: Might indicate missing events
```

---

## A/B Testing Framework

### Compare Two Tracking Implementations
```kusto
// If you're rolling out new tracking logic
let oldLogic = videoSessions | where sessionStart < datetime(2025-01-15);
let newLogic = videoSessions | where sessionStart >= datetime(2025-01-15);

oldLogic
| summarize 
    avgWatchTime = avg(watchTime),
    completionRate = todouble(countif(completed)) / count(),
    avgPauses = avg(pauseCount)
| extend implementation = "Old"
| union (
    newLogic
    | summarize 
        avgWatchTime = avg(watchTime),
        completionRate = todouble(countif(completed)) / count(),
        avgPauses = avg(pauseCount)
    | extend implementation = "New"
)
```

---

## Monitoring Alerts

### Alert Template
```kusto
// Run every hour
let alertThresholds = datatable(metric:string, threshold:double)
[
    "completion_rate_drop", 0.2,      // 20% drop in completion rate
    "zero_watch_rate", 0.15,          // >15% sessions with no watch time
    "data_freshness_hours", 3,        // Data older than 3 hours
    "negative_watch_time_count", 1,   // ANY negative watch time
    "excessive_duration_rate", 0.05   // >5% sessions >4 hours
];

// Check each metric and fire alerts
videoSessions
| where sessionStart > ago(1h)
| summarize 
    zeroWatchRate = todouble(countif(watchTime == 0)) / count(),
    negativeWatchCount = countif(watchTime < 0),
    excessiveDurationRate = todouble(countif(sessionDuration > 14400)) / count(),
    dataFreshness = datetime_diff('hour', now(), max(sessionEnd))
| extend alerts = pack_array(
    iff(zeroWatchRate > 0.15, "HIGH_ZERO_WATCH_RATE", ""),
    iff(negativeWatchCount > 0, "NEGATIVE_WATCH_TIME_DETECTED", ""),
    iff(excessiveDurationRate > 0.05, "HIGH_EXCESSIVE_DURATION_RATE", ""),
    iff(dataFreshness > 3, "STALE_DATA_DETECTED", "")
)
| mv-expand alert = alerts
| where alert != ""
```

---

## Performance Benchmarks

### Query Performance Targets
- Session aggregation query: < 5 seconds for 1 day of data
- User-video metrics: < 10 seconds for 1 week of data
- Dashboard refresh: < 15 seconds
- Real-time query (last hour): < 2 seconds

### Data Volume Estimates
Assuming:
- 10,000 active users/day
- 5 videos watched per user
- 4 events per video (play, pause, resume, end)

Daily volume: 10,000 × 5 × 4 = 200,000 events/day
Monthly volume: ~6M events
Annual volume: ~73M events

Storage: ~100 bytes per event × 73M = ~7.3 GB/year raw events
After aggregation: ~1 GB/year for sessions + metrics


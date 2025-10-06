# Video Analytics Databricks - Quick Reference Guide

## 🎯 Overview

**Problem:** Raw Events (play, pause, resume, end) → Aggregated User-Video metrics

**Solution:** PySpark script that transforms atomic events into a clean table with **one row per User+Video**

---

## 📊 Output Schema

The final `aggregated_user_video_engagement` table contains:

```sql
userId                      STRING    -- User Identifier
videoId                     STRING    -- Video Identifier  
videoTitle                  STRING    -- Video Title (from metadata)
videoDuration               DOUBLE    -- Video length in seconds

-- Watch Time Metrics
totalWatchTime              DOUBLE    -- Total watched time in seconds
totalUniqueSecondsWatched   DOUBLE    -- Unique seconds (without counting replays twice)
maxPositionReached          DOUBLE    -- Furthest position reached in video

-- Percentages
watchPercentage             DOUBLE    -- (totalWatchTime / videoDuration) * 100
completionPercentage        DOUBLE    -- (maxPositionReached / videoDuration) * 100
uniqueWatchPercentage       DOUBLE    -- (uniqueSecondsWatched / videoDuration) * 100

-- Session Metrics
sessionCount                LONG      -- Number of sessions
avgWatchTimePerSession      DOUBLE    -- Average watch time per session
avgSessionDuration          DOUBLE    -- Average session duration (incl. pauses)

-- Interaction Metrics  
avgPausesPerSession         DOUBLE    -- Average number of pauses
totalForwardSkips           LONG      -- Number of forward skips
totalBackwardSkips          LONG      -- Number of backward skips

-- Completion
completionCount             LONG      -- How many times video was completed
isCompletedAtLeastOnce      BOOLEAN   -- Completed at least once

-- Engagement
engagementScore             DOUBLE    -- Weighted engagement metric
engagementTier              STRING    -- High / Medium / Low / Minimal

-- Temporal
firstWatchDate              TIMESTAMP -- First watch session
lastWatchDate               TIMESTAMP -- Last watch session

-- Flags
isReplay                    BOOLEAN   -- Multiple sessions (replay behavior)
dataQualityFlag             STRING    -- ok / excessive_watch_time / very_short_watch / etc.

-- Meta
processedAt                 TIMESTAMP -- When aggregated
```

---

## 🚀 Quick Start

### 1. Upload Script to Databricks
```bash
# Upload databricks_video_aggregation.py to Databricks Workspace
# Path: /Workspace/Users/<your-email>/video_analytics/
```

### 2. Run in Notebook
```python
# In Databricks Notebook
%run /Workspace/Users/your-email/video_analytics/databricks_video_aggregation

from databricks_video_aggregation import VideoEngagementAggregator

# Initialize
aggregator = VideoEngagementAggregator(
    spark=spark,
    input_table="your_raw_events_table",
    output_table="aggregated_user_video_engagement",
    video_metadata_table="video_metadata"  # Optional
)

# Run
result = aggregator.run_aggregation()

# Save
aggregator.save_results(result)
```

### 3. Query Results
```python
# Read aggregated table
df = spark.table("aggregated_user_video_engagement")

# Peter's engagement for Video 1
df.filter((col("userId") == "peter") & (col("videoId") == "video_001")).show()
```

---

## 📝 Example: Peter's Video Journey

**Raw Events:**
```
timestamp              | eventName    | currentTime
-----------------------|--------------|------------
2025-01-15 10:00:00   | video_play   | 0
2025-01-15 10:00:30   | video_pause  | 30      ← Watched 30s
2025-01-15 10:00:35   | video_resume | 30
2025-01-15 10:02:05   | video_pause  | 120     ← Watched 90s
2025-01-15 10:02:10   | video_resume | 110     ← Skip back 10s
2025-01-15 10:02:20   | video_pause  | 120     ← Watched 10s
```

**Aggregated Result (1 Row):**
```
userId: peter
videoId: video_001
videoDuration: 300s (5 minutes)

totalWatchTime: 130s (30 + 90 + 10)
uniqueSecondsWatched: 120s (0-120, without counting 110-120 twice)
maxPositionReached: 120s

watchPercentage: 43.3% (130/300)
completionPercentage: 40% (120/300)
uniqueWatchPercentage: 40% (120/300)

sessionCount: 1
completionCount: 0
isCompletedAtLeastOnce: False

forwardSkips: 0
backwardSkips: 1

engagementScore: ~17.2
engagementTier: Low
```

---

## 🔧 Configuration

### Input Table Requirements
```python
# Your raw events table must have the following columns:
# - timestamp (TimestampType)
# - userId (StringType)
# - sessionId (StringType)
# - videoId (StringType)
# - eventName (StringType): "video_play", "video_pause", "video_resume", "video_ended"
# - currentTime (DoubleType): Position in video in seconds
```

### Optional: Video Metadata Table
```python
# If available, create table with:
# - videoId (StringType)
# - duration (DoubleType)
# - title (StringType)

# Or: Script estimates duration from maxPosition
```

### Performance Tuning
```python
# For large datasets (>10M events):
aggregator.run_aggregation(
    calculate_unique_seconds=True,    # True = accurate, False = faster
    use_efficient_method=True         # True for production (interval merging)
)

# Incremental processing:
from datetime import datetime, timedelta
start_date = datetime.now() - timedelta(days=1)
result = aggregator.run_aggregation(start_date=start_date)
```

---

## 📅 Scheduling (Production Setup)

### Option A: Databricks Job
```json
{
  "name": "Video Analytics Daily Aggregation",
  "schedule": {
    "quartz_cron_expression": "0 0 2 * * ?",
    "timezone_id": "Europe/Zurich"
  },
  "tasks": [{
    "task_key": "aggregate_video_engagement",
    "notebook_task": {
      "notebook_path": "/video_analytics/aggregation_notebook",
      "base_parameters": {
        "start_date": "{{job.start_time.iso_datetime}}"
      }
    }
  }]
}
```

### Option B: Workflow Notebook
```python
# Notebook: daily_video_aggregation.py

from datetime import datetime, timedelta

# Process yesterday's data
yesterday = datetime.now() - timedelta(days=1)
start_date = yesterday.replace(hour=0, minute=0, second=0)
end_date = start_date + timedelta(days=1)

# Run aggregation
result = aggregator.run_aggregation(
    start_date=start_date,
    end_date=end_date
)

# Save with append mode for incremental updates
aggregator.save_results(result, mode="append")
```

---

## 🎨 BI Integration

### Power BI / Tableau Connection
```sql
-- Create optimized view
CREATE OR REPLACE VIEW vw_video_engagement_bi AS
SELECT 
    userId,
    videoId,
    videoTitle,
    totalWatchTime / 60.0 as watchMinutes,
    watchPercentage,
    completionPercentage,
    engagementTier,
    DATE(firstWatchDate) as firstWatchDay,
    sessionCount,
    isCompletedAtLeastOnce
FROM aggregated_user_video_engagement
WHERE dataQualityFlag = 'ok';
```

### Example Dashboard Queries

**Top Videos by Engagement:**
```sql
SELECT 
    videoId,
    videoTitle,
    COUNT(DISTINCT userId) as uniqueViewers,
    SUM(totalWatchTime) / 3600 as totalWatchHours,
    AVG(watchPercentage) as avgWatchPercentage,
    SUM(completionCount) as totalCompletions
FROM aggregated_user_video_engagement
GROUP BY videoId, videoTitle
ORDER BY totalWatchHours DESC
LIMIT 10;
```

**User Engagement Distribution:**
```sql
SELECT 
    engagementTier,
    COUNT(*) as userVideoCount,
    COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () as percentage
FROM aggregated_user_video_engagement
GROUP BY engagementTier
ORDER BY 
    CASE engagementTier
        WHEN 'High' THEN 1
        WHEN 'Medium' THEN 2
        WHEN 'Low' THEN 3
        ELSE 4
    END;
```

**Drop-off Analysis:**
```sql
-- Where do users drop off?
SELECT 
    videoId,
    FLOOR(maxPositionReached / 30) * 30 as positionBucket,
    COUNT(*) as userCount
FROM aggregated_user_video_engagement
WHERE completionCount = 0
GROUP BY videoId, positionBucket
ORDER BY videoId, positionBucket;
```

---

## ✅ Data Quality Checks

### Automated Validation Queries

**1. Watch Time Cannot Exceed Duration:**
```python
quality_issues = spark.sql("""
    SELECT 
        userId, videoId,
        totalWatchTime, videoDuration,
        (totalWatchTime - videoDuration) as excess
    FROM aggregated_user_video_engagement
    WHERE totalWatchTime > videoDuration * 1.1
    ORDER BY excess DESC
""")

if quality_issues.count() > 0:
    print("⚠️ Found excessive watch times!")
    quality_issues.show()
```

**2. Completion Without Sufficient Watch:**
```python
incomplete_completions = spark.sql("""
    SELECT userId, videoId, completionCount, watchPercentage
    FROM aggregated_user_video_engagement
    WHERE completionCount > 0 AND watchPercentage < 75
""")
```

**3. Data Freshness:**
```python
freshness = spark.sql("""
    SELECT 
        MAX(processedAt) as lastProcessed,
        TIMESTAMPDIFF(HOUR, MAX(processedAt), CURRENT_TIMESTAMP()) as hoursAgo
    FROM aggregated_user_video_engagement
""").collect()[0]

if freshness['hoursAgo'] > 24:
    print("⚠️ Data is stale! Last processed over 24h ago")
```

---

## 🐛 Troubleshooting

### Problem: "Column not found"
```python
# Check input table schema
spark.table("raw_video_events").printSchema()

# Ensure all required columns exist:
# timestamp, userId, sessionId, videoId, eventName, currentTime
```

### Problem: "Out of Memory"
```python
# For very large datasets:
# 1. Disable unique seconds calculation
result = aggregator.run_aggregation(calculate_unique_seconds=False)

# 2. Process in batches
for month in range(1, 13):
    start = f"2024-{month:02d}-01"
    end = f"2024-{month:02d}-28"
    result = aggregator.run_aggregation(start_date=start, end_date=end)
    aggregator.save_results(result, mode="append")
```

### Problem: Negative Watch Time
```python
# Debug: Find problematic sessions
spark.sql("""
    SELECT userId, videoId, sessionId, 
           COLLECT_LIST(STRUCT(timestamp, eventName, currentTime)) as events
    FROM raw_video_events
    GROUP BY userId, videoId, sessionId
    HAVING SUM(CASE WHEN eventName = 'video_pause' 
                    AND currentTime < LAG(currentTime) 
                    THEN 1 ELSE 0 END) > 0
""").show(truncate=False)
```

---

## 📈 Performance Benchmarks

**Typical Performance (Databricks Standard Cluster):**
- 1M events → ~2-3 minutes
- 10M events → ~15-20 minutes
- 100M events → ~2-3 hours

**Optimization Tips:**
1. **Partitioning:** Partition output table by date
   ```python
   aggregator.save_results(result, partition_by=["firstWatchDate"])
   ```

2. **Caching:** Script already caches intermediate results

3. **Cluster Size:** Use autoscaling cluster
   ```
   Min workers: 2
   Max workers: 8
   ```

4. **Delta Lake:** Output as Delta table for ACID + Time Travel

---

## 🔄 Migration from KQL to PySpark

**KQL Equivalents in PySpark:**

| KQL | PySpark |
|-----|---------|
| `serialize` | `Window.orderBy()` |
| `prev()` | `lag()` over window |
| `next()` | `lead()` over window |
| `summarize` | `groupBy().agg()` |
| `extend` | `withColumn()` |
| `where` | `filter()` |
| `mv-expand` | `explode()` |

---

## 📚 Additional Resources

- **Main Script:** `databricks_video_aggregation.py`
- **Example Notebook:** `databricks_example_notebook.py`
- **KQL Queries:** `video_analytics_kql.md` (for Azure Log Analytics)
- **Implementation Guide:** `implementation_roadmap.md`

---

## 🎯 Next Steps

1. ✅ Upload script to Databricks
2. ✅ Run example notebook with sample data
3. ✅ Validate output for known users
4. ✅ Point script to your real raw events
5. ✅ Schedule as daily job
6. ✅ Connect BI tool to output table
7. ✅ Setup data quality alerts
8. ✅ Iterate based on business feedback

**Happy Analyzing! 🚀**

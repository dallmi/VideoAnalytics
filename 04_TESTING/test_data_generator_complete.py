# Databricks notebook source
# MAGIC %md
# MAGIC # Complete Test Data Generator - All 25 Scenarios
# MAGIC
# MAGIC ## 🎯 Purpose
# MAGIC This notebook generates **comprehensive test data** for validating the Video Engagement
# MAGIC Aggregation script. It covers 25 test scenarios representing 90%+ of real-world cases
# MAGIC and edge cases you'll encounter in production.
# MAGIC
# MAGIC ## 📋 Test Coverage Summary
# MAGIC
# MAGIC ### Core Scenarios (TC-001 to TC-010) - Common User Behaviors
# MAGIC | ID | Scenario | Purpose | Expected Behavior |
# MAGIC |-------|----------|---------|-------------------|
# MAGIC | TC-001 | Perfect Viewing | User watches start→finish | Watch%=100%, Completion=100% |
# MAGIC | TC-002 | Simple Pause & Resume | User pauses once | Valid watch segments calculated |
# MAGIC | TC-003 | Browser Close | Lost session (no end event) | Partial watch time captured |
# MAGIC | TC-004 | Skip Forward | User jumps ahead | Forward skip counted, gap not counted |
# MAGIC | TC-005 | Skip Backward | User rewinds | Backward skip counted, overlap handled |
# MAGIC | TC-006 | Multiple Sessions | User returns later | Replay flag=true, sessions counted |
# MAGIC | TC-007 | Binge Watching | Multiple videos in one session | Each video tracked separately |
# MAGIC | TC-008 | Abandoned Early | User watches <10s and leaves | Low engagement flag |
# MAGIC | TC-009 | Complex Navigation | Multiple pauses + skips | All segments calculated correctly |
# MAGIC | TC-010 | Gaming Detection | Skip to end to game completion | Data quality flag raised |
# MAGIC
# MAGIC ### Edge Cases (TC-011 to TC-025) - Data Quality & Unusual Patterns
# MAGIC | ID | Scenario | What It Tests | Expected Handling |
# MAGIC |-------|----------|---------------|-------------------|
# MAGIC | TC-011 | Duplicate Events | Same event twice | Deduplication via window functions |
# MAGIC | TC-012 | Out-of-Order Events | Events arrive in wrong order | Sorted by timestamp before processing |
# MAGIC | TC-013 | Null/Missing Values | NULL userId/videoId | Filtered out during load |
# MAGIC | TC-014 | Negative currentTime | Invalid position (-10s) | Filtered out (data quality) |
# MAGIC | TC-015 | Extremely Long Watch | Position=9999s for 5min video | Data quality flag raised |
# MAGIC | TC-016 | Rapid Fire Events | Events <1s apart | All captured, may indicate bot |
# MAGIC | TC-017 | Session Timeout | 5-hour pause | Long pause handled |
# MAGIC | TC-018 | Same Video, Same Day | Multiple sessions same day | Each session counted |
# MAGIC | TC-019 | Midnight Boundary | Session crosses midnight | Time calculation works correctly |
# MAGIC | TC-020 | Position Beyond Duration | currentTime > video duration | Data quality flag raised |
# MAGIC | TC-021 | Zero Duration Segment | Start=end position | Ignored (no watch time) |
# MAGIC | TC-022 | Only Resume Events | Resume without play | Handled gracefully |
# MAGIC | TC-023 | Only Pause Events | Pause without play | Handled gracefully |
# MAGIC | TC-024 | Empty Session | Only play event | No segments calculated |
# MAGIC | TC-025 | Multiple Consecutive Plays | Play→Play→Play | Last valid segment used |
# MAGIC
# MAGIC ## 🎓 How to Use This Notebook
# MAGIC
# MAGIC ### For QA/Testers
# MAGIC 1. Run this notebook to generate test data
# MAGIC 2. Run the aggregation script on the generated data
# MAGIC 3. Compare results against expected outcomes in `TEST_SCENARIOS_COMPLETE.md`
# MAGIC 4. Verify all 25 scenarios pass validation
# MAGIC
# MAGIC ### For Developers
# MAGIC 1. Use this to **understand edge cases** your code must handle
# MAGIC 2. Add new scenarios when bugs are discovered
# MAGIC 3. Use as **regression test suite** before deployments
# MAGIC
# MAGIC ### For Business Analysts
# MAGIC 1. Review scenarios to understand **data quality issues** that may arise
# MAGIC 2. See how different user behaviors are classified
# MAGIC 3. Understand **engagement tiers** and **data quality flags**
# MAGIC
# MAGIC ## ⏱️ Execution Time
# MAGIC - **Generation**: ~30 seconds
# MAGIC - **Aggregation**: ~2 minutes
# MAGIC - **Validation**: ~5 minutes
# MAGIC - **Total**: ~8 minutes
# MAGIC
# MAGIC ---

# COMMAND ----------

# MAGIC %md
# MAGIC ## Setup

# COMMAND ----------

from pyspark.sql import SparkSession
from pyspark.sql.types import *
from datetime import datetime, timedelta
import random

spark = SparkSession.builder.getOrCreate()

# Define schema for raw events
schema = StructType([
    StructField("timestamp", TimestampType(), False),
    StructField("userId", StringType(), True),  # Nullable for TC-013
    StructField("sessionId", StringType(), False),
    StructField("videoId", StringType(), True),  # Nullable for TC-013
    StructField("eventName", StringType(), False),
    StructField("currentTime", DoubleType(), False)
])

# COMMAND ----------

# MAGIC %md
# MAGIC ## CORE SCENARIOS (TC-001 to TC-010)

# COMMAND ----------

# MAGIC %md
# MAGIC ### TC-001: Perfect Viewing (Start to Finish)

# COMMAND ----------

all_events = []
base_time = datetime.now() - timedelta(days=2)

# TC-001: Anna - Perfect viewing
tc001 = [
    (base_time, "anna", "session_tc001", "video_001", "video_play", 0.0),
    (base_time + timedelta(seconds=300), "anna", "session_tc001", "video_001", "video_ended", 300.0),
]
all_events.extend(tc001)

# COMMAND ----------

# MAGIC %md
# MAGIC ### TC-002: Simple Pause & Resume

# COMMAND ----------

base_time = datetime.now() - timedelta(days=2, hours=1)

tc002 = [
    (base_time, "bob", "session_tc002", "video_001", "video_play", 0.0),
    (base_time + timedelta(seconds=60), "bob", "session_tc002", "video_001", "video_pause", 60.0),
    (base_time + timedelta(minutes=5), "bob", "session_tc002", "video_001", "video_resume", 60.0),
    (base_time + timedelta(minutes=9), "bob", "session_tc002", "video_001", "video_ended", 300.0),
]
all_events.extend(tc002)

# COMMAND ----------

# MAGIC %md
# MAGIC ### TC-003: Browser Close (Lost Session)

# COMMAND ----------

base_time = datetime.now() - timedelta(days=2, hours=2)

tc003 = [
    (base_time, "lisa", "session_tc003", "video_001", "video_play", 0.0),
    (base_time + timedelta(seconds=45), "lisa", "session_tc003", "video_001", "video_pause", 45.0),
    (base_time + timedelta(seconds=50), "lisa", "session_tc003", "video_001", "video_resume", 45.0),
    # Browser closed - no more events
]
all_events.extend(tc003)

# COMMAND ----------

# MAGIC %md
# MAGIC ### TC-004: Skip Forward

# COMMAND ----------

base_time = datetime.now() - timedelta(days=2, hours=3)

tc004 = [
    (base_time, "tom", "session_tc004", "video_002", "video_play", 0.0),
    (base_time + timedelta(seconds=30), "tom", "session_tc004", "video_002", "video_pause", 30.0),
    (base_time + timedelta(seconds=32), "tom", "session_tc004", "video_002", "video_resume", 300.0),  # Skip 270s
    (base_time + timedelta(seconds=92), "tom", "session_tc004", "video_002", "video_ended", 360.0),
]
all_events.extend(tc004)

# COMMAND ----------

# MAGIC %md
# MAGIC ### TC-005: Skip Backward (Rewind)

# COMMAND ----------

base_time = datetime.now() - timedelta(days=2, hours=4)

tc005 = [
    (base_time, "peter", "session_tc005", "video_001", "video_play", 0.0),
    (base_time + timedelta(seconds=30), "peter", "session_tc005", "video_001", "video_pause", 30.0),
    (base_time + timedelta(seconds=35), "peter", "session_tc005", "video_001", "video_resume", 30.0),
    (base_time + timedelta(seconds=125), "peter", "session_tc005", "video_001", "video_pause", 120.0),
    (base_time + timedelta(seconds=130), "peter", "session_tc005", "video_001", "video_resume", 110.0),  # Rewind 10s
    (base_time + timedelta(seconds=140), "peter", "session_tc005", "video_001", "video_pause", 120.0),
]
all_events.extend(tc005)

# COMMAND ----------

# MAGIC %md
# MAGIC ### TC-006: Multiple Sessions (Replay)

# COMMAND ----------

# Session 1 - Day 1
base_time_s1 = datetime.now() - timedelta(days=2, hours=5)
tc006_s1 = [
    (base_time_s1, "sarah", "session_tc006_1", "video_003", "video_play", 0.0),
    (base_time_s1 + timedelta(seconds=60), "sarah", "session_tc006_1", "video_003", "video_pause", 60.0),
]
all_events.extend(tc006_s1)

# Session 2 - Day 2
base_time_s2 = datetime.now() - timedelta(days=1, hours=14)
tc006_s2 = [
    (base_time_s2, "sarah", "session_tc006_2", "video_003", "video_play", 0.0),
    (base_time_s2 + timedelta(seconds=180), "sarah", "session_tc006_2", "video_003", "video_ended", 180.0),
]
all_events.extend(tc006_s2)

# COMMAND ----------

# MAGIC %md
# MAGIC ### TC-007: Multi-Video Session (Binge Watching)

# COMMAND ----------

base_time = datetime.now() - timedelta(days=1, hours=20)

tc007 = [
    # Video 1
    (base_time, "max", "session_tc007", "video_001", "video_play", 0.0),
    (base_time + timedelta(seconds=300), "max", "session_tc007", "video_001", "video_ended", 300.0),
    # Video 2
    (base_time + timedelta(seconds=310), "max", "session_tc007", "video_002", "video_play", 0.0),
    (base_time + timedelta(seconds=610), "max", "session_tc007", "video_002", "video_ended", 300.0),
    # Video 3
    (base_time + timedelta(seconds=620), "max", "session_tc007", "video_003", "video_play", 0.0),
    (base_time + timedelta(seconds=800), "max", "session_tc007", "video_003", "video_ended", 180.0),
]
all_events.extend(tc007)

# COMMAND ----------

# MAGIC %md
# MAGIC ### TC-008: Abandoned Early (Low Engagement)

# COMMAND ----------

base_time = datetime.now() - timedelta(days=1, hours=18)

tc008 = [
    (base_time, "john", "session_tc008", "video_001", "video_play", 0.0),
    (base_time + timedelta(seconds=8), "john", "session_tc008", "video_001", "video_pause", 8.0),
]
all_events.extend(tc008)

# COMMAND ----------

# MAGIC %md
# MAGIC ### TC-009: Complex Navigation

# COMMAND ----------

base_time = datetime.now() - timedelta(days=1, hours=16)

tc009 = [
    (base_time, "alex", "session_tc009", "video_002", "video_play", 0.0),
    (base_time + timedelta(seconds=60), "alex", "session_tc009", "video_002", "video_pause", 60.0),
    (base_time + timedelta(seconds=65), "alex", "session_tc009", "video_002", "video_resume", 60.0),
    (base_time + timedelta(seconds=185), "alex", "session_tc009", "video_002", "video_pause", 180.0),
    (base_time + timedelta(seconds=190), "alex", "session_tc009", "video_002", "video_resume", 300.0),  # Skip forward
    (base_time + timedelta(seconds=250), "alex", "session_tc009", "video_002", "video_pause", 360.0),
    (base_time + timedelta(seconds=255), "alex", "session_tc009", "video_002", "video_resume", 200.0),  # Skip back
    (base_time + timedelta(seconds=345), "alex", "session_tc009", "video_002", "video_ended", 600.0),
]
all_events.extend(tc009)

# COMMAND ----------

# MAGIC %md
# MAGIC ### TC-010: Gaming Detection (Skip to End)

# COMMAND ----------

base_time = datetime.now() - timedelta(days=1, hours=14)

tc010 = [
    (base_time, "mike", "session_tc010", "video_001", "video_play", 0.0),
    (base_time + timedelta(seconds=5), "mike", "session_tc010", "video_001", "video_pause", 5.0),
    (base_time + timedelta(seconds=6), "mike", "session_tc010", "video_001", "video_resume", 295.0),  # Skip almost to end
    (base_time + timedelta(seconds=11), "mike", "session_tc010", "video_001", "video_ended", 300.0),
]
all_events.extend(tc010)

# COMMAND ----------

# MAGIC %md
# MAGIC ## EDGE CASE SCENARIOS (TC-011 to TC-025)

# COMMAND ----------

# MAGIC %md
# MAGIC ### TC-011: Duplicate Events

# COMMAND ----------

base_time = datetime.now() - timedelta(days=1, hours=12)

tc011 = [
    (base_time, "user1", "session_tc011", "video_001", "video_play", 0.0),
    (base_time + timedelta(seconds=30), "user1", "session_tc011", "video_001", "video_pause", 30.0),
    (base_time + timedelta(seconds=30), "user1", "session_tc011", "video_001", "video_pause", 30.0),  # DUPLICATE
    (base_time + timedelta(seconds=35), "user1", "session_tc011", "video_001", "video_resume", 30.0),
    (base_time + timedelta(seconds=125), "user1", "session_tc011", "video_001", "video_ended", 120.0),
]
all_events.extend(tc011)

# COMMAND ----------

# MAGIC %md
# MAGIC ### TC-012: Out-of-Order Events

# COMMAND ----------

base_time = datetime.now() - timedelta(days=1, hours=10)

tc012 = [
    (base_time + timedelta(seconds=30), "user2", "session_tc012", "video_001", "video_pause", 30.0),  # Out of order
    (base_time, "user2", "session_tc012", "video_001", "video_play", 0.0),  # Should be first
    (base_time + timedelta(seconds=125), "user2", "session_tc012", "video_001", "video_ended", 120.0),
    (base_time + timedelta(seconds=35), "user2", "session_tc012", "video_001", "video_resume", 30.0),  # Out of order
]
all_events.extend(tc012)

# COMMAND ----------

# MAGIC %md
# MAGIC ### TC-013: Null/Missing Values

# COMMAND ----------

base_time = datetime.now() - timedelta(days=1, hours=8)

tc013 = [
    (base_time, "user3", "session_tc013", "video_001", "video_play", 0.0),
    (base_time + timedelta(seconds=30), None, "session_tc013", "video_001", "video_pause", 30.0),  # NULL userId
    (base_time + timedelta(seconds=35), "user3", "session_tc013", None, "video_resume", 30.0),  # NULL videoId
    (base_time + timedelta(seconds=125), "user3", "session_tc013", "video_001", "video_ended", 120.0),
]
all_events.extend(tc013)

# COMMAND ----------

# MAGIC %md
# MAGIC ### TC-014: Negative or Invalid currentTime

# COMMAND ----------

base_time = datetime.now() - timedelta(days=1, hours=6)

tc014 = [
    (base_time, "user4", "session_tc014", "video_001", "video_play", 0.0),
    (base_time + timedelta(seconds=30), "user4", "session_tc014", "video_001", "video_pause", -10.0),  # INVALID NEGATIVE
    (base_time + timedelta(seconds=35), "user4", "session_tc014", "video_001", "video_resume", 0.0),
    (base_time + timedelta(seconds=95), "user4", "session_tc014", "video_001", "video_ended", 60.0),
]
all_events.extend(tc014)

# COMMAND ----------

# MAGIC %md
# MAGIC ### TC-015: Extremely Long Watch Time

# COMMAND ----------

base_time = datetime.now() - timedelta(days=1, hours=4)

tc015 = [
    (base_time, "user5", "session_tc015", "video_001", "video_play", 0.0),
    (base_time + timedelta(seconds=5), "user5", "session_tc015", "video_001", "video_pause", 9999.0),  # IMPLAUSIBLE
]
all_events.extend(tc015)

# COMMAND ----------

# MAGIC %md
# MAGIC ### TC-016: Rapid Fire Events (< 1 second apart)

# COMMAND ----------

base_time = datetime.now() - timedelta(days=1, hours=2)

tc016 = [
    (base_time, "user6", "session_tc016", "video_001", "video_play", 0.0),
    (base_time + timedelta(milliseconds=100), "user6", "session_tc016", "video_001", "video_pause", 0.1),
    (base_time + timedelta(milliseconds=200), "user6", "session_tc016", "video_001", "video_resume", 0.1),
    (base_time + timedelta(milliseconds=300), "user6", "session_tc016", "video_001", "video_pause", 0.2),
    (base_time + timedelta(milliseconds=400), "user6", "session_tc016", "video_001", "video_resume", 0.2),
    (base_time + timedelta(seconds=60), "user6", "session_tc016", "video_001", "video_ended", 60.0),
]
all_events.extend(tc016)

# COMMAND ----------

# MAGIC %md
# MAGIC ### TC-017: Session Timeout (Long Pause)

# COMMAND ----------

base_time = datetime.now() - timedelta(days=1, hours=0)

tc017 = [
    (base_time, "user7", "session_tc017", "video_001", "video_play", 0.0),
    (base_time + timedelta(seconds=30), "user7", "session_tc017", "video_001", "video_pause", 30.0),
    (base_time + timedelta(hours=5, seconds=30), "user7", "session_tc017", "video_001", "video_resume", 30.0),  # 5 hours later
    (base_time + timedelta(hours=5, seconds=90), "user7", "session_tc017", "video_001", "video_ended", 90.0),
]
all_events.extend(tc017)

# COMMAND ----------

# MAGIC %md
# MAGIC ### TC-018: Same Video, Different Sessions, Same Day

# COMMAND ----------

base_time = datetime.now() - timedelta(hours=20)

tc018_s1 = [
    (base_time, "user8", "session_tc018_1", "video_001", "video_play", 0.0),
    (base_time + timedelta(seconds=60), "user8", "session_tc018_1", "video_001", "video_pause", 60.0),
]
all_events.extend(tc018_s1)

tc018_s2 = [
    (base_time + timedelta(hours=6), "user8", "session_tc018_2", "video_001", "video_play", 0.0),
    (base_time + timedelta(hours=6, seconds=120), "user8", "session_tc018_2", "video_001", "video_ended", 120.0),
]
all_events.extend(tc018_s2)

# COMMAND ----------

# MAGIC %md
# MAGIC ### TC-019: Midnight Boundary Cross

# COMMAND ----------

# Calculate time for 23:58:00 yesterday
yesterday = datetime.now() - timedelta(days=1)
base_time = yesterday.replace(hour=23, minute=58, second=0, microsecond=0)

tc019 = [
    (base_time, "user9", "session_tc019", "video_001", "video_play", 0.0),
    (base_time + timedelta(minutes=4), "user9", "session_tc019", "video_001", "video_ended", 240.0),  # Crosses midnight
]
all_events.extend(tc019)

# COMMAND ----------

# MAGIC %md
# MAGIC ### TC-020: Position Beyond Video Duration

# COMMAND ----------

base_time = datetime.now() - timedelta(hours=18)

tc020 = [
    (base_time, "user10", "session_tc020", "video_001", "video_play", 0.0),
    (base_time + timedelta(seconds=60), "user10", "session_tc020", "video_001", "video_pause", 350.0),  # Video is 300s!
]
all_events.extend(tc020)

# COMMAND ----------

# MAGIC %md
# MAGIC ### TC-021: Zero Duration Segment

# COMMAND ----------

base_time = datetime.now() - timedelta(hours=16)

tc021 = [
    (base_time, "user11", "session_tc021", "video_001", "video_play", 50.0),
    (base_time + timedelta(seconds=5), "user11", "session_tc021", "video_001", "video_pause", 50.0),  # Same position
    (base_time + timedelta(seconds=10), "user11", "session_tc021", "video_001", "video_resume", 50.0),
    (base_time + timedelta(seconds=70), "user11", "session_tc021", "video_001", "video_ended", 110.0),
]
all_events.extend(tc021)

# COMMAND ----------

# MAGIC %md
# MAGIC ### TC-022: Only Resume Events (No Play)

# COMMAND ----------

base_time = datetime.now() - timedelta(hours=14)

tc022 = [
    (base_time, "user12", "session_tc022", "video_001", "video_resume", 50.0),  # No play before
    (base_time + timedelta(seconds=60), "user12", "session_tc022", "video_001", "video_pause", 110.0),
]
all_events.extend(tc022)

# COMMAND ----------

# MAGIC %md
# MAGIC ### TC-023: Only Pause Events (No Play)

# COMMAND ----------

base_time = datetime.now() - timedelta(hours=12)

tc023 = [
    (base_time, "user13", "session_tc023", "video_001", "video_pause", 30.0),  # No play before
    (base_time + timedelta(seconds=5), "user13", "session_tc023", "video_001", "video_resume", 30.0),
    (base_time + timedelta(seconds=65), "user13", "session_tc023", "video_001", "video_ended", 90.0),
]
all_events.extend(tc023)

# COMMAND ----------

# MAGIC %md
# MAGIC ### TC-024: Empty Session (No Valid Segments)

# COMMAND ----------

base_time = datetime.now() - timedelta(hours=10)

tc024 = [
    (base_time, "user14", "session_tc024", "video_001", "video_play", 0.0),
    # No more events - browser closed immediately
]
all_events.extend(tc024)

# COMMAND ----------

# MAGIC %md
# MAGIC ### TC-025: Multiple Consecutive Play Events

# COMMAND ----------

base_time = datetime.now() - timedelta(hours=8)

tc025 = [
    (base_time, "user15", "session_tc025", "video_001", "video_play", 0.0),
    (base_time + timedelta(seconds=5), "user15", "session_tc025", "video_001", "video_play", 5.0),  # Another play
    (base_time + timedelta(seconds=10), "user15", "session_tc025", "video_001", "video_play", 10.0),  # Another play
    (base_time + timedelta(seconds=70), "user15", "session_tc025", "video_001", "video_ended", 70.0),
]
all_events.extend(tc025)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Create DataFrame and Save

# COMMAND ----------

# Create DataFrame
events_df = spark.createDataFrame(all_events, schema)

# Save to table
events_df.write.mode("overwrite").saveAsTable("raw_video_events_test_complete")

print(f"✅ Created {events_df.count()} test events for 25 scenarios")
events_df.show(50, truncate=False)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Create Video Metadata Table

# COMMAND ----------

video_metadata = [
    ("video_001", 300.0, "Introduction to Databricks"),
    ("video_002", 600.0, "Advanced PySpark Techniques"),
    ("video_003", 180.0, "Data Quality Best Practices"),
]

metadata_schema = StructType([
    StructField("videoId", StringType(), False),
    StructField("duration", DoubleType(), False),
    StructField("title", StringType(), False)
])

metadata_df = spark.createDataFrame(video_metadata, metadata_schema)
metadata_df.write.mode("overwrite").saveAsTable("video_metadata_test")

print("✅ Created video metadata")
metadata_df.show()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary of Test Data

# COMMAND ----------

print("="*80)
print("TEST DATA SUMMARY")
print("="*80)

# Count events by scenario (approximate based on userId patterns)
events_df.createOrReplaceTempView("test_events")

spark.sql("""
    SELECT
        CASE
            WHEN userId = 'anna' THEN 'TC-001: Perfect Viewing'
            WHEN userId = 'bob' THEN 'TC-002: Pause & Resume'
            WHEN userId = 'lisa' THEN 'TC-003: Browser Close'
            WHEN userId = 'tom' THEN 'TC-004: Skip Forward'
            WHEN userId = 'peter' THEN 'TC-005: Skip Backward'
            WHEN userId = 'sarah' THEN 'TC-006: Multiple Sessions'
            WHEN userId = 'max' THEN 'TC-007: Multi-Video'
            WHEN userId = 'john' THEN 'TC-008: Abandoned Early'
            WHEN userId = 'alex' THEN 'TC-009: Complex Navigation'
            WHEN userId = 'mike' THEN 'TC-010: Gaming Detection'
            WHEN userId LIKE 'user%' THEN 'TC-011 to TC-025: Edge Cases'
            ELSE 'Unknown'
        END as scenario,
        COUNT(*) as eventCount,
        MIN(timestamp) as firstEvent,
        MAX(timestamp) as lastEvent
    FROM test_events
    GROUP BY
        CASE
            WHEN userId = 'anna' THEN 'TC-001: Perfect Viewing'
            WHEN userId = 'bob' THEN 'TC-002: Pause & Resume'
            WHEN userId = 'lisa' THEN 'TC-003: Browser Close'
            WHEN userId = 'tom' THEN 'TC-004: Skip Forward'
            WHEN userId = 'peter' THEN 'TC-005: Skip Backward'
            WHEN userId = 'sarah' THEN 'TC-006: Multiple Sessions'
            WHEN userId = 'max' THEN 'TC-007: Multi-Video'
            WHEN userId = 'john' THEN 'TC-008: Abandoned Early'
            WHEN userId = 'alex' THEN 'TC-009: Complex Navigation'
            WHEN userId = 'mike' THEN 'TC-010: Gaming Detection'
            WHEN userId LIKE 'user%' THEN 'TC-011 to TC-025: Edge Cases'
            ELSE 'Unknown'
        END
    ORDER BY scenario
""").show(50, truncate=False)

print("\n✅ All 25 test scenarios generated successfully!")
print("   Ready for aggregation testing.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Next Steps
# MAGIC
# MAGIC 1. Run the aggregation script on this test data
# MAGIC 2. Validate each scenario's output against expected results
# MAGIC 3. See `TEST_SCENARIOS_COMPLETE.md` for expected outputs
# MAGIC 4. Run validation queries from the test spec

# COMMAND ----------



# Databricks notebook source
# MAGIC %md
# MAGIC # Video Engagement Aggregation - Example Notebook
# MAGIC 
# MAGIC Dieses Notebook zeigt wie man das Video Aggregation Script verwendet und testet.
# MAGIC 
# MAGIC ## Setup
# MAGIC 1. Upload `databricks_video_aggregation.py` zu Databricks
# MAGIC 2. Run dieses Notebook
# MAGIC 3. Check results in `aggregated_user_video_engagement` table

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Generate Sample Data
# MAGIC 
# MAGIC Erstelle Test-Daten für verschiedene Szenarien

# COMMAND ----------

from pyspark.sql import SparkSession
from pyspark.sql.types import *
from datetime import datetime, timedelta
import random

spark = SparkSession.builder.getOrCreate()

# Define schema für raw events
schema = StructType([
    StructField("timestamp", TimestampType(), False),
    StructField("userId", StringType(), False),
    StructField("sessionId", StringType(), False),
    StructField("videoId", StringType(), False),
    StructField("eventName", StringType(), False),
    StructField("currentTime", DoubleType(), False)
])

# Generate sample events
sample_events = []

# Szenario 1: Peter schaut Video 1 (Dein Beispiel)
# Video duration: 300 seconds (5 minutes)
# Peter schaut: 0-30s (30s), pause, 30-120s (90s), skip back zu 110s, 110-120s (10s)
# Total: 130s watched, Unique: 120s (0-120), Watch%: 43.3%, Completion%: 40%

base_time = datetime.now() - timedelta(hours=2)

peter_video1 = [
    # Play von 0
    (base_time, "peter", "session_001", "video_001", "video_play", 0.0),
    # Pause bei 30s
    (base_time + timedelta(seconds=30), "peter", "session_001", "video_001", "video_pause", 30.0),
    # Resume bei 30s
    (base_time + timedelta(seconds=35), "peter", "session_001", "video_001", "video_resume", 30.0),
    # Pause bei 120s (90s geschaut)
    (base_time + timedelta(seconds=125), "peter", "session_001", "video_001", "video_pause", 120.0),
    # Resume bei 110s (skip backward)
    (base_time + timedelta(seconds=130), "peter", "session_001", "video_001", "video_resume", 110.0),
    # End bei 120s (10s geschaut)
    (base_time + timedelta(seconds=140), "peter", "session_001", "video_001", "video_pause", 120.0),
]

sample_events.extend(peter_video1)

# Szenario 2: Anna schaut Video 1 komplett durch
base_time2 = datetime.now() - timedelta(hours=1)
anna_video1 = [
    (base_time2, "anna", "session_002", "video_001", "video_play", 0.0),
    (base_time2 + timedelta(seconds=300), "anna", "session_002", "video_001", "video_ended", 300.0),
]
sample_events.extend(anna_video1)

# Szenario 3: Max schaut Video 2 mit mehreren Pausen
base_time3 = datetime.now() - timedelta(minutes=30)
max_video2 = [
    (base_time3, "max", "session_003", "video_002", "video_play", 0.0),
    (base_time3 + timedelta(seconds=60), "max", "session_003", "video_002", "video_pause", 60.0),
    (base_time3 + timedelta(minutes=5), "max", "session_003", "video_002", "video_resume", 60.0),
    (base_time3 + timedelta(minutes=7), "max", "session_003", "video_002", "video_pause", 180.0),
    (base_time3 + timedelta(minutes=10), "max", "session_003", "video_002", "video_resume", 180.0),
    (base_time3 + timedelta(minutes=15), "max", "session_003", "video_002", "video_ended", 480.0),
]
sample_events.extend(max_video2)

# Szenario 4: Lisa - abandoned session (kein end event)
base_time4 = datetime.now() - timedelta(minutes=15)
lisa_video1 = [
    (base_time4, "lisa", "session_004", "video_001", "video_play", 0.0),
    (base_time4 + timedelta(seconds=45), "lisa", "session_004", "video_001", "video_pause", 45.0),
    # Kein resume/end = Browser geschlossen
]
sample_events.extend(lisa_video1)

# Szenario 5: Tom - Skip forward (überspringt Teile)
base_time5 = datetime.now() - timedelta(minutes=10)
tom_video2 = [
    (base_time5, "tom", "session_005", "video_002", "video_play", 0.0),
    (base_time5 + timedelta(seconds=30), "tom", "session_005", "video_002", "video_pause", 30.0),
    # Skip zu Minute 5
    (base_time5 + timedelta(seconds=35), "tom", "session_005", "video_002", "video_resume", 300.0),
    (base_time5 + timedelta(seconds=95), "tom", "session_005", "video_002", "video_ended", 360.0),
]
sample_events.extend(tom_video2)

# Szenario 6: Sarah - Replay (schaut Video mehrmals)
base_time6 = datetime.now() - timedelta(days=2)
sarah_video3_session1 = [
    (base_time6, "sarah", "session_006", "video_003", "video_play", 0.0),
    (base_time6 + timedelta(seconds=60), "sarah", "session_006", "video_003", "video_pause", 60.0),
]
sample_events.extend(sarah_video3_session1)

base_time7 = datetime.now() - timedelta(days=1)
sarah_video3_session2 = [
    (base_time7, "sarah", "session_007", "video_003", "video_play", 0.0),
    (base_time7 + timedelta(seconds=180), "sarah", "session_007", "video_003", "video_ended", 180.0),
]
sample_events.extend(sarah_video3_session2)

# Create DataFrame
events_df = spark.createDataFrame(sample_events, schema)

# Save to table
events_df.write.mode("overwrite").saveAsTable("raw_video_events")

print(f"✅ Created {events_df.count()} sample events")
events_df.show(50, truncate=False)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Create Video Metadata Table

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
metadata_df.write.mode("overwrite").saveAsTable("video_metadata")

print("✅ Created video metadata")
metadata_df.show()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Run Aggregation
# MAGIC 
# MAGIC Importiere und führe das Aggregation Script aus

# COMMAND ----------

# Import the aggregator class
# Wenn du das Script als .py File hochgeladen hast:
# %run /path/to/databricks_video_aggregation

# Oder copy-paste die VideoEngagementAggregator class hier

# Für dieses Beispiel: simplified inline version
from pyspark.sql import Window
from pyspark.sql.functions import *

# Initialisiere Aggregator
from databricks_video_aggregation import VideoEngagementAggregator

aggregator = VideoEngagementAggregator(
    spark=spark,
    input_table="raw_video_events",
    output_table="aggregated_user_video_engagement",
    video_metadata_table="video_metadata"
)

# Run aggregation
result_df = aggregator.run_aggregation(
    calculate_unique_seconds=True,
    use_efficient_method=True
)

# Show results
print("\n" + "="*80)
print("AGGREGATED RESULTS")
print("="*80)
result_df.orderBy("userId", "videoId").show(100, truncate=False)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Validate Results
# MAGIC 
# MAGIC Prüfe die Ergebnisse für Peter + Video 1

# COMMAND ----------

# Peter's Video 1 Engagement
peter_result = result_df.filter(
    (col("userId") == "peter") & (col("videoId") == "video_001")
).select(
    "userId", "videoId", "videoTitle",
    "totalWatchTime", "totalUniqueSecondsWatched", 
    "videoDuration", "maxPositionReached",
    "watchPercentage", "completionPercentage", "uniqueWatchPercentage",
    "sessionCount", "pauseCount", "totalForwardSkips", "totalBackwardSkips",
    "engagementScore", "engagementTier"
)

print("\n🔍 Peter's Video 1 Engagement:")
print("="*80)
peter_result.show(truncate=False, vertical=True)

print("\n📊 Expected Results:")
print("- Total Watch Time: ~130 seconds (30 + 90 + 10)")
print("- Unique Seconds Watched: ~120 seconds (0-120, ohne doppelte Sekunden)")
print("- Video Duration: 300 seconds")
print("- Max Position: 120 seconds")
print("- Watch Percentage: ~43.3% (130/300)")
print("- Completion Percentage: 40% (120/300)")
print("- Unique Watch Percentage: 40% (120/300)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Aggregation auf Video-Level

# COMMAND ----------

# Video Performance Metrics
video_performance = result_df.groupBy("videoId", "videoTitle", "videoDuration").agg(
    countDistinct("userId").alias("uniqueViewers"),
    sum("totalWatchTime").alias("totalWatchTime"),
    avg("watchPercentage").alias("avgWatchPercentage"),
    avg("completionPercentage").alias("avgCompletionPercentage"),
    sum("completionCount").alias("totalCompletions"),
    count("*").alias("totalUserVideoRecords"),
    avg("sessionCount").alias("avgSessionsPerUser")
).withColumn(
    "completionRate",
    round((col("totalCompletions") / col("totalUserVideoRecords")) * 100, 2)
).orderBy("totalWatchTime", ascending=False)

print("\n📹 Video Performance Summary:")
print("="*80)
video_performance.show(truncate=False)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. User Engagement Distribution

# COMMAND ----------

# Engagement Tier Distribution
print("\n👥 User Engagement Distribution:")
print("="*80)

engagement_dist = result_df.groupBy("engagementTier").agg(
    count("*").alias("userVideoCount"),
    avg("watchPercentage").alias("avgWatchPercentage"),
    avg("totalWatchTime").alias("avgWatchTime")
).orderBy(
    when(col("engagementTier") == "High", 1)
    .when(col("engagementTier") == "Medium", 2)
    .when(col("engagementTier") == "Low", 3)
    .otherwise(4)
)

engagement_dist.show(truncate=False)

# Visual distribution
display(engagement_dist)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Advanced Queries
# MAGIC 
# MAGIC Beispiel-Queries für verschiedene Business-Fragen

# COMMAND ----------

# Query 1: Welche User haben Video nicht fertig geschaut aber viel Zeit investiert?
high_engagement_incomplete = result_df.filter(
    (col("completionCount") == 0) & 
    (col("watchPercentage") > 50)
).select(
    "userId", "videoId", "videoTitle",
    "watchPercentage", "completionPercentage",
    "sessionCount", "totalWatchTime"
).orderBy("watchPercentage", ascending=False)

print("\n🤔 High Engagement but Not Completed:")
print("="*80)
high_engagement_incomplete.show(10, truncate=False)

# COMMAND ----------

# Query 2: Replay Behavior - User die Videos mehrmals anschauen
replays = result_df.filter(col("isReplay") == True).select(
    "userId", "videoId", "videoTitle",
    "sessionCount", "totalWatchTime", "completionCount",
    "watchPercentage"
).orderBy("sessionCount", ascending=False)

print("\n🔁 Users with Replay Behavior:")
print("="*80)
replays.show(10, truncate=False)

# COMMAND ----------

# Query 3: Data Quality Issues
quality_issues = result_df.filter(col("dataQualityFlag") != "ok").select(
    "userId", "videoId", "dataQualityFlag",
    "totalWatchTime", "videoDuration", "watchPercentage"
).orderBy("dataQualityFlag")

print("\n⚠️ Data Quality Issues:")
print("="*80)
quality_issues.show(20, truncate=False)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8. Export für BI Tools

# COMMAND ----------

# Erstelle optimierte View für Tableau/Power BI
spark.sql("""
    CREATE OR REPLACE VIEW vw_video_engagement_bi AS
    SELECT 
        userId,
        videoId,
        videoTitle,
        videoDuration,
        
        -- Watch metrics
        totalWatchTime,
        totalUniqueSecondsWatched,
        watchPercentage,
        completionPercentage,
        uniqueWatchPercentage,
        
        -- Session metrics
        sessionCount,
        avgWatchTimePerSession,
        avgSessionDuration,
        
        -- Interaction metrics
        avgPausesPerSession,
        totalForwardSkips,
        totalBackwardSkips,
        
        -- Completion
        isCompletedAtLeastOnce,
        completionCount,
        
        -- Engagement
        engagementScore,
        engagementTier,
        
        -- Temporal
        firstWatchDate,
        lastWatchDate,
        
        -- Flags
        isReplay,
        dataQualityFlag,
        
        processedAt
    FROM aggregated_user_video_engagement
""")

print("✅ Created view: vw_video_engagement_bi")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 9. Performance Test mit mehr Daten

# COMMAND ----------

# Optional: Generate larger dataset für Performance Testing
def generate_large_dataset(num_users=1000, num_videos=50, avg_sessions_per_user=3):
    """Generate synthetic large dataset"""
    import random
    from datetime import datetime, timedelta
    
    events = []
    base_time = datetime.now() - timedelta(days=30)
    
    for user_id in range(num_users):
        # Random videos watched by this user
        videos_watched = random.sample(range(num_videos), k=random.randint(1, 10))
        
        for video_id in videos_watched:
            video_duration = random.choice([180, 300, 600, 900])  # 3, 5, 10, 15 min
            
            # Generate sessions for this user-video
            for session in range(random.randint(1, avg_sessions_per_user)):
                session_start = base_time + timedelta(
                    days=random.randint(0, 30),
                    hours=random.randint(0, 23)
                )
                
                session_id = f"session_{user_id}_{video_id}_{session}"
                current_pos = 0.0
                
                # Play event
                events.append((
                    session_start,
                    f"user_{user_id:04d}",
                    session_id,
                    f"video_{video_id:03d}",
                    "video_play",
                    0.0
                ))
                
                # Generate random play/pause sequence
                while current_pos < video_duration:
                    # Watch for random duration
                    watch_duration = random.randint(20, 120)
                    current_pos += watch_duration
                    
                    if current_pos >= video_duration:
                        # Reached end
                        events.append((
                            session_start + timedelta(seconds=current_pos),
                            f"user_{user_id:04d}",
                            session_id,
                            f"video_{video_id:03d}",
                            "video_ended",
                            video_duration
                        ))
                        break
                    
                    # Random: pause, skip, or end
                    action = random.choices(
                        ["pause", "skip_forward", "end"],
                        weights=[0.6, 0.2, 0.2]
                    )[0]
                    
                    if action == "pause":
                        events.append((
                            session_start + timedelta(seconds=current_pos),
                            f"user_{user_id:04d}",
                            session_id,
                            f"video_{video_id:03d}",
                            "video_pause",
                            current_pos
                        ))
                        
                        # Resume after pause
                        pause_duration = random.randint(5, 60)
                        events.append((
                            session_start + timedelta(seconds=current_pos + pause_duration),
                            f"user_{user_id:04d}",
                            session_id,
                            f"video_{video_id:03d}",
                            "video_resume",
                            current_pos
                        ))
                    
                    elif action == "skip_forward":
                        skip_amount = random.randint(10, 60)
                        events.append((
                            session_start + timedelta(seconds=current_pos),
                            f"user_{user_id:04d}",
                            session_id,
                            f"video_{video_id:03d}",
                            "video_pause",
                            current_pos
                        ))
                        current_pos += skip_amount
                        events.append((
                            session_start + timedelta(seconds=current_pos),
                            f"user_{user_id:04d}",
                            session_id,
                            f"video_{video_id:03d}",
                            "video_resume",
                            current_pos
                        ))
                    
                    else:  # end early
                        events.append((
                            session_start + timedelta(seconds=current_pos),
                            f"user_{user_id:04d}",
                            session_id,
                            f"video_{video_id:03d}",
                            "video_pause",
                            current_pos
                        ))
                        break
    
    return spark.createDataFrame(events, schema)

# Uncomment to generate large dataset:
# print("Generating large test dataset...")
# large_df = generate_large_dataset(num_users=100, num_videos=20)
# large_df.write.mode("overwrite").saveAsTable("raw_video_events_large")
# print(f"✅ Generated {large_df.count()} events")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 10. Summary & Next Steps
# MAGIC 
# MAGIC ✅ **Was wir erreicht haben:**
# MAGIC - Raw Events → Aggregierte User-Video Metriken
# MAGIC - Watch Time, Completion %, Engagement Score
# MAGIC - Unique Seconds Watched (ohne Replays doppelt zu zählen)
# MAGIC - Data Quality Checks
# MAGIC 
# MAGIC 📊 **Output Tabelle enthält:**
# MAGIC - Eine Row pro User + Video Kombination
# MAGIC - Alle relevanten Metriken für Analytics
# MAGIC - Ready für BI Tools (Tableau, Power BI, etc.)
# MAGIC 
# MAGIC 🚀 **Next Steps:**
# MAGIC 1. Schedule dieses Notebook als Job (täglich/stündlich)
# MAGIC 2. Connect BI Tool zu `aggregated_user_video_engagement` table
# MAGIC 3. Setup Alerts für Data Quality Issues
# MAGIC 4. Iterative Verbesserung basierend auf Business Feedback

# COMMAND ----------



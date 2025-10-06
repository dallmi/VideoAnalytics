"""
Databricks Video Analytics - Raw Event Aggregation
===================================================

Dieses Script verarbeitet raw video events und erstellt aggregierte User-Video Metriken.

Input: Raw events table mit columns: timestamp, userId, sessionId, videoId, eventName, currentTime
Output: Aggregierte Tabelle mit einer Row pro User+Video Kombination

Beispiel Output für Peter + Video 1:
- totalWatchTime: 130 seconds (30 + 90 + 10)
- videoDuration: 300 seconds
- watchPercentage: 43.3%
- uniqueSecondsWatched: 120 seconds (ohne Replay)
- completionPercentage: 40% (max position reached)
"""

from pyspark.sql import SparkSession, Window
from pyspark.sql.functions import (
    col, lag, lead, when, sum as _sum, count, max as _max, min as _min,
    datediff, unix_timestamp, countDistinct, avg, round as _round,
    explode, sequence, array_distinct, size, lit, coalesce, expr,
    row_number, dense_rank, first, last, collect_list, concat_ws
)
from pyspark.sql.types import *
from datetime import datetime, timedelta
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VideoEngagementAggregator:
    """
    Aggregates raw video events into user-video engagement metrics
    """
    
    def __init__(self, spark, input_table, output_table, video_metadata_table=None):
        """
        Args:
            spark: SparkSession
            input_table: Name of raw events table
            output_table: Name of output aggregated table
            video_metadata_table: Optional table with videoId, duration columns
        """
        self.spark = spark
        self.input_table = input_table
        self.output_table = output_table
        self.video_metadata_table = video_metadata_table
        
    def load_raw_events(self, start_date=None, end_date=None):
        """Load raw events with optional date filtering"""
        
        logger.info(f"Loading raw events from {self.input_table}")
        
        df = self.spark.table(self.input_table)
        
        # Filter by date if provided
        if start_date:
            df = df.filter(col("timestamp") >= start_date)
        if end_date:
            df = df.filter(col("timestamp") < end_date)
        
        # Basic data quality filter
        df = df.filter(
            col("userId").isNotNull() &
            col("videoId").isNotNull() &
            col("sessionId").isNotNull() &
            col("eventName").isin(["video_play", "video_pause", "video_resume", "video_ended"]) &
            col("currentTime").isNotNull() &
            (col("currentTime") >= 0)
        )
        
        logger.info(f"Loaded {df.count()} events")
        return df
    
    def calculate_watch_segments(self, events_df):
        """
        Berechnet Watch-Segmente zwischen Play/Resume und Pause/End Events
        
        Returns DataFrame mit zusätzlichen Columns:
        - prevEvent, prevTime, prevTimestamp
        - timeDelta: Unterschied in Video-Position
        - timestampDelta: Unterschied in realer Zeit
        - isValidSegment: Boolean ob Segment gezählt werden soll
        - watchedSeconds: Tatsächlich geschaute Sekunden
        """
        
        logger.info("Calculating watch segments...")
        
        # Sort events chronologically within each user-video-session
        window_spec = Window.partitionBy("userId", "videoId", "sessionId").orderBy("timestamp")
        
        df = events_df.withColumn("prevEvent", lag("eventName").over(window_spec)) \
                      .withColumn("prevTime", lag("currentTime").over(window_spec)) \
                      .withColumn("prevTimestamp", lag("timestamp").over(window_spec))
        
        # Calculate deltas
        df = df.withColumn(
            "timeDelta", 
            col("currentTime") - col("prevTime")
        ).withColumn(
            "timestampDelta",
            unix_timestamp("timestamp") - unix_timestamp("prevTimestamp")
        )
        
        # Identify valid watch segments
        # Valid = von Play/Resume zu Pause/End, ohne große Sprünge
        df = df.withColumn(
            "isValidSegment",
            (col("prevEvent").isin(["video_play", "video_resume"])) &
            (col("eventName").isin(["video_pause", "video_ended"])) &
            (col("timeDelta") > 0) &
            (col("timeDelta") < 7200) &  # Max 2 Stunden pro Segment
            (col("timeDelta").between(0, col("timestampDelta") + 5))  # Plausibilitäts-Check
        )
        
        # Calculate watched seconds
        df = df.withColumn(
            "watchedSeconds",
            when(col("isValidSegment"), col("timeDelta")).otherwise(0.0)
        )
        
        # Identify jumps/skips
        df = df.withColumn(
            "isJump",
            (col("timeDelta").isNotNull()) & (
                (col("timeDelta") > 5) |  # Forward skip
                (col("timeDelta") < -2)    # Backward skip
            )
        ).withColumn(
            "jumpType",
            when(col("timeDelta") > 5, "forward")
            .when(col("timeDelta") < -2, "backward")
            .otherwise("none")
        )
        
        return df
    
    def calculate_unique_seconds_watched(self, events_df):
        """
        Berechnet UNIQUE Sekunden die geschaut wurden (ohne Replays zu zählen)
        
        Beispiel: User schaut 0-30s, dann zurück zu 20s und schaut bis 40s
        - Total watch time: 30 + 20 = 50 seconds
        - Unique watch time: 40 seconds (0-40s, aber 20-30 doppelt = nicht doppelt zählen)
        """
        
        logger.info("Calculating unique seconds watched...")
        
        # Window für jede User-Video Kombination
        window_spec = Window.partitionBy("userId", "videoId", "sessionId").orderBy("timestamp")
        
        # Erstelle Start und End für jedes Watch-Segment
        segments_df = events_df.filter(col("isValidSegment")) \
            .withColumn("segmentStart", col("prevTime").cast("int")) \
            .withColumn("segmentEnd", col("currentTime").cast("int")) \
            .select("userId", "videoId", "sessionId", "segmentStart", "segmentEnd")
        
        # Erweitere jedes Segment zu einer Liste von Sekunden
        # Achtung: Kann bei langen Videos memory-intensive sein!
        # Alternative unten für Production
        segments_df = segments_df.withColumn(
            "secondsWatched",
            expr("sequence(segmentStart, segmentEnd - 1)")
        )
        
        # Flatten und dedupliziere
        unique_seconds = segments_df.select(
            "userId", "videoId", "sessionId",
            explode("secondsWatched").alias("second")
        ).distinct()
        
        # Zähle unique Sekunden pro User-Video-Session
        unique_count = unique_seconds.groupBy("userId", "videoId", "sessionId") \
            .agg(count("second").alias("uniqueSecondsWatched"))
        
        return unique_count
    
    def calculate_unique_seconds_efficient(self, events_df):
        """
        Effizientere Version für Production: Merge overlapping intervals
        Vermeidet explode() bei langen Videos
        """
        
        logger.info("Calculating unique seconds watched (efficient method)...")
        
        # Erstelle Segmente
        segments = events_df.filter(col("isValidSegment")) \
            .withColumn("segmentStart", col("prevTime").cast("double")) \
            .withColumn("segmentEnd", col("currentTime").cast("double")) \
            .select("userId", "videoId", "sessionId", "segmentStart", "segmentEnd") \
            .orderBy("userId", "videoId", "sessionId", "segmentStart")
        
        # Merge overlapping intervals via SQL
        # Das ist komplexer, daher machen wir es via temp view
        segments.createOrReplaceTempView("segments_temp")
        
        merged = self.spark.sql("""
            WITH ordered_segments AS (
                SELECT 
                    userId, videoId, sessionId,
                    segmentStart, segmentEnd,
                    LAG(segmentEnd) OVER (
                        PARTITION BY userId, videoId, sessionId 
                        ORDER BY segmentStart
                    ) as prevEnd
                FROM segments_temp
            ),
            merged_segments AS (
                SELECT 
                    userId, videoId, sessionId,
                    segmentStart,
                    segmentEnd,
                    CASE 
                        WHEN prevEnd IS NULL OR segmentStart > prevEnd 
                        THEN 1 
                        ELSE 0 
                    END as newGroup
                FROM ordered_segments
            ),
            grouped AS (
                SELECT 
                    userId, videoId, sessionId,
                    segmentStart, segmentEnd,
                    SUM(newGroup) OVER (
                        PARTITION BY userId, videoId, sessionId 
                        ORDER BY segmentStart
                    ) as groupId
                FROM merged_segments
            )
            SELECT 
                userId, videoId, sessionId,
                MIN(segmentStart) as mergedStart,
                MAX(segmentEnd) as mergedEnd
            FROM grouped
            GROUP BY userId, videoId, sessionId, groupId
        """)
        
        # Berechne Summe der merged intervals
        unique_seconds = merged.withColumn(
            "intervalLength",
            col("mergedEnd") - col("mergedStart")
        ).groupBy("userId", "videoId", "sessionId") \
         .agg(_sum("intervalLength").alias("uniqueSecondsWatched"))
        
        return unique_seconds
    
    def aggregate_sessions(self, events_df):
        """Aggregiere auf Session-Level"""
        
        logger.info("Aggregating session metrics...")
        
        session_metrics = events_df.groupBy("userId", "videoId", "sessionId").agg(
            # Watch time
            _sum("watchedSeconds").alias("watchTime"),
            
            # Position tracking
            _max("currentTime").alias("maxPosition"),
            _min("timestamp").alias("sessionStart"),
            _max("timestamp").alias("sessionEnd"),
            
            # Completion
            _max(when(col("eventName") == "video_ended", 1).otherwise(0)).alias("completed"),
            
            # Interaction counts
            _sum(when(col("eventName") == "video_pause", 1).otherwise(0)).alias("pauseCount"),
            _sum(when(col("jumpType") == "forward", 1).otherwise(0)).alias("forwardSkipCount"),
            _sum(when(col("jumpType") == "backward", 1).otherwise(0)).alias("backwardSkipCount"),
            
            # Event count
            count("*").alias("eventCount")
        )
        
        # Session duration in seconds
        session_metrics = session_metrics.withColumn(
            "sessionDurationSeconds",
            unix_timestamp("sessionEnd") - unix_timestamp("sessionStart")
        )
        
        return session_metrics
    
    def aggregate_user_video(self, session_df, unique_seconds_df=None):
        """
        Aggregiere auf User-Video Level (finale Output-Tabelle)
        Eine Row pro User + Video Kombination
        """
        
        logger.info("Aggregating user-video metrics...")
        
        # Join mit unique seconds falls vorhanden
        if unique_seconds_df is not None:
            user_video = session_df.join(
                unique_seconds_df,
                on=["userId", "videoId", "sessionId"],
                how="left"
            )
            # Aggregiere auch unique seconds
            unique_seconds_total = user_video.groupBy("userId", "videoId") \
                .agg(_sum("uniqueSecondsWatched").alias("totalUniqueSecondsWatched"))
        else:
            unique_seconds_total = None
        
        # Haupt-Aggregation
        user_video_metrics = session_df.groupBy("userId", "videoId").agg(
            # Watch time metrics
            _sum("watchTime").alias("totalWatchTime"),
            _max("maxPosition").alias("maxPositionReached"),
            
            # Session counts
            countDistinct("sessionId").alias("sessionCount"),
            _sum("completed").alias("completionCount"),
            
            # Interaction metrics
            avg("pauseCount").alias("avgPausesPerSession"),
            _sum("forwardSkipCount").alias("totalForwardSkips"),
            _sum("backwardSkipCount").alias("totalBackwardSkips"),
            
            # Temporal
            _min("sessionStart").alias("firstWatchDate"),
            _max("sessionEnd").alias("lastWatchDate"),
            
            # Averages
            avg("watchTime").alias("avgWatchTimePerSession"),
            avg("sessionDurationSeconds").alias("avgSessionDuration")
        )
        
        # Join mit unique seconds
        if unique_seconds_total is not None:
            user_video_metrics = user_video_metrics.join(
                unique_seconds_total,
                on=["userId", "videoId"],
                how="left"
            )
        
        # Add calculated columns
        user_video_metrics = user_video_metrics.withColumn(
            "isReplay",
            when(col("sessionCount") > 1, True).otherwise(False)
        ).withColumn(
            "isCompletedAtLeastOnce",
            when(col("completionCount") > 0, True).otherwise(False)
        )
        
        return user_video_metrics
    
    def enrich_with_video_metadata(self, user_video_df):
        """
        Füge Video-Metadaten hinzu (Duration, Title, etc.) und berechne Percentages
        """
        
        if self.video_metadata_table is None:
            logger.warning("No video metadata table provided, using defaults")
            # Erstelle dummy metadata basierend auf maxPosition
            video_durations = user_video_df.groupBy("videoId") \
                .agg(_max("maxPositionReached").alias("estimatedDuration"))
            
            enriched = user_video_df.join(video_durations, on="videoId", how="left")
            enriched = enriched.withColumn("videoDuration", col("estimatedDuration"))
        else:
            logger.info(f"Enriching with metadata from {self.video_metadata_table}")
            metadata = self.spark.table(self.video_metadata_table)
            enriched = user_video_df.join(
                metadata.select("videoId", "duration", "title"),
                on="videoId",
                how="left"
            )
            enriched = enriched.withColumnRenamed("duration", "videoDuration") \
                             .withColumnRenamed("title", "videoTitle")
        
        # Berechne Percentages
        enriched = enriched.withColumn(
            "watchPercentage",
            _round((col("totalWatchTime") / col("videoDuration")) * 100, 2)
        ).withColumn(
            "completionPercentage",
            _round((col("maxPositionReached") / col("videoDuration")) * 100, 2)
        ).withColumn(
            "uniqueWatchPercentage",
            when(
                col("totalUniqueSecondsWatched").isNotNull(),
                _round((col("totalUniqueSecondsWatched") / col("videoDuration")) * 100, 2)
            ).otherwise(None)
        )
        
        # Engagement Score
        # Formula: (watch_time/60) * 1.0 + completions * 50 + sessions * 5 - skips * 2
        enriched = enriched.withColumn(
            "engagementScore",
            _round(
                (col("totalWatchTime") / 60.0) * 1.0 +
                col("completionCount") * 50.0 +
                col("sessionCount") * 5.0 -
                (col("totalForwardSkips") + col("totalBackwardSkips")) * 2.0,
                2
            )
        )
        
        # Engagement Tier
        enriched = enriched.withColumn(
            "engagementTier",
            when(col("engagementScore") > 100, "High")
            .when(col("engagementScore") > 50, "Medium")
            .when(col("engagementScore") > 10, "Low")
            .otherwise("Minimal")
        )
        
        # Data Quality Flags
        enriched = enriched.withColumn(
            "dataQualityFlag",
            when(col("totalWatchTime") > col("videoDuration") * 1.2, "excessive_watch_time")
            .when(col("totalWatchTime") < 5, "very_short_watch")
            .when(col("completionCount") > 0 & (col("watchPercentage") < 75), "completed_without_sufficient_watch")
            .otherwise("ok")
        )
        
        return enriched
    
    def run_aggregation(self, start_date=None, end_date=None, 
                       calculate_unique_seconds=True, use_efficient_method=True):
        """
        Führt die komplette Aggregation durch
        
        Args:
            start_date: Optional filter start date
            end_date: Optional filter end date
            calculate_unique_seconds: Boolean, ob unique seconds berechnet werden sollen
            use_efficient_method: Boolean, nutze efficient interval merging statt explode
        
        Returns:
            Aggregated DataFrame
        """
        
        logger.info("="*80)
        logger.info("Starting Video Engagement Aggregation")
        logger.info("="*80)
        
        # Step 1: Load raw events
        events = self.load_raw_events(start_date, end_date)
        events.cache()  # Cache for reuse
        
        # Step 2: Calculate watch segments
        events_with_segments = self.calculate_watch_segments(events)
        events_with_segments.cache()
        
        # Step 3: Calculate unique seconds (optional)
        unique_seconds = None
        if calculate_unique_seconds:
            if use_efficient_method:
                unique_seconds = self.calculate_unique_seconds_efficient(events_with_segments)
            else:
                unique_seconds = self.calculate_unique_seconds_watched(events_with_segments)
        
        # Step 4: Aggregate sessions
        sessions = self.aggregate_sessions(events_with_segments)
        sessions.cache()
        
        # Step 5: Aggregate user-video
        user_video = self.aggregate_user_video(sessions, unique_seconds)
        
        # Step 6: Enrich with metadata
        final_df = self.enrich_with_video_metadata(user_video)
        
        # Cleanup cache
        events.unpersist()
        events_with_segments.unpersist()
        sessions.unpersist()
        
        logger.info("="*80)
        logger.info("Aggregation Complete")
        logger.info(f"Total user-video combinations: {final_df.count()}")
        logger.info("="*80)
        
        return final_df
    
    def save_results(self, df, mode="overwrite", partition_by=None):
        """
        Speichert Ergebnisse in Output-Tabelle
        
        Args:
            df: DataFrame to save
            mode: "overwrite", "append", or "merge"
            partition_by: Optional list of columns to partition by (e.g. ["firstWatchDate"])
        """
        
        logger.info(f"Saving results to {self.output_table}")
        
        # Add processing metadata
        df = df.withColumn("processedAt", lit(datetime.now()))
        
        writer = df.write.format("delta")  # Nutze Delta Lake für ACID
        
        if partition_by:
            writer = writer.partitionBy(*partition_by)
        
        writer.mode(mode).saveAsTable(self.output_table)
        
        logger.info(f"Successfully saved {df.count()} rows to {self.output_table}")
    
    def generate_summary_stats(self, df):
        """Generiere Summary-Statistiken für Validierung"""
        
        logger.info("\n" + "="*80)
        logger.info("SUMMARY STATISTICS")
        logger.info("="*80)
        
        # Overall stats
        total_users = df.select("userId").distinct().count()
        total_videos = df.select("videoId").distinct().count()
        total_combinations = df.count()
        
        logger.info(f"Total unique users: {total_users:,}")
        logger.info(f"Total unique videos: {total_videos:,}")
        logger.info(f"Total user-video combinations: {total_combinations:,}")
        
        # Engagement distribution
        logger.info("\nEngagement Tier Distribution:")
        tier_dist = df.groupBy("engagementTier").count().orderBy("count", ascending=False)
        tier_dist.show()
        
        # Watch percentage distribution
        logger.info("\nWatch Percentage Distribution:")
        df.select("watchPercentage").describe().show()
        
        # Completion stats
        completion_rate = df.filter(col("isCompletedAtLeastOnce")).count() / total_combinations * 100
        logger.info(f"\nOverall Completion Rate: {completion_rate:.2f}%")
        
        # Data quality
        logger.info("\nData Quality Flags:")
        quality_flags = df.groupBy("dataQualityFlag").count().orderBy("count", ascending=False)
        quality_flags.show()
        
        # Top videos by engagement
        logger.info("\nTop 10 Videos by Total Watch Time:")
        top_videos = df.groupBy("videoId").agg(
            _sum("totalWatchTime").alias("totalWatchTime"),
            countDistinct("userId").alias("uniqueViewers"),
            avg("watchPercentage").alias("avgWatchPercentage")
        ).orderBy("totalWatchTime", ascending=False).limit(10)
        top_videos.show(truncate=False)
        
        logger.info("="*80 + "\n")


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Main execution function"""
    
    # Initialize Spark Session
    spark = SparkSession.builder \
        .appName("VideoEngagementAggregation") \
        .config("spark.sql.adaptive.enabled", "true") \
        .config("spark.sql.adaptive.coalescePartitions.enabled", "true") \
        .getOrCreate()
    
    # Configuration
    INPUT_TABLE = "raw_video_events"  # Deine Raw Events Tabelle
    OUTPUT_TABLE = "aggregated_user_video_engagement"  # Output Tabelle
    VIDEO_METADATA_TABLE = "video_metadata"  # Optional: Tabelle mit Video Metadaten
    
    # Optional: Process nur letzte N Tage
    # start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    start_date = None  # Alle Daten
    end_date = None
    
    # Initialize aggregator
    aggregator = VideoEngagementAggregator(
        spark=spark,
        input_table=INPUT_TABLE,
        output_table=OUTPUT_TABLE,
        video_metadata_table=VIDEO_METADATA_TABLE  # None falls nicht vorhanden
    )
    
    # Run aggregation
    result_df = aggregator.run_aggregation(
        start_date=start_date,
        end_date=end_date,
        calculate_unique_seconds=True,  # True für akkurate unique watch time
        use_efficient_method=True       # True für Production (skaliert besser)
    )
    
    # Generate summary stats
    aggregator.generate_summary_stats(result_df)
    
    # Save results
    aggregator.save_results(
        result_df,
        mode="overwrite",  # Oder "append" für inkrementelle Updates
        partition_by=["firstWatchDate"]  # Optional: Partition nach Datum
    )
    
    # Optional: Erstelle View für BI Tools
    result_df.createOrReplaceTempView("vw_user_video_engagement")
    spark.sql(f"CREATE OR REPLACE VIEW vw_user_video_engagement AS SELECT * FROM {OUTPUT_TABLE}")
    
    logger.info("\n✅ Aggregation completed successfully!")
    
    return result_df


if __name__ == "__main__":
    result = main()

"""
Databricks Video Analytics - Raw Event Aggregation
===================================================

PURPOSE:
--------
This script processes raw video tracking events and aggregates them into meaningful
user engagement metrics at the User-Video level. It handles complex scenarios like
rewinding, skipping, multiple sessions, and data quality issues.

BUSINESS VALUE:
--------------
- Understand which videos engage users most effectively
- Identify drop-off points and completion rates
- Detect unusual viewing patterns (gaming, very short views)
- Provide clean data for BI dashboards and ML models

INPUT DATA STRUCTURE:
--------------------
Raw events table with the following columns:
  - timestamp (TimestampType): When the event occurred (server time)
  - userId (String): Unique identifier for the user
  - sessionId (String): Unique identifier for the viewing session
  - videoId (String): Unique identifier for the video
  - eventName (String): Type of event - one of:
      * "video_play": User started playing the video
      * "video_pause": User paused the video
      * "video_resume": User resumed after pausing
      * "video_ended": User reached the end of the video
  - currentTime (Double): Position in the video in seconds (e.g., 30.5 = 30.5 seconds into video)

Example raw events for a user watching a 5-minute (300s) video:
  timestamp                userId  sessionId    videoId    eventName      currentTime
  2024-01-01 10:00:00     peter   session_001  video_001  video_play     0.0
  2024-01-01 10:00:30     peter   session_001  video_001  video_pause    30.0
  2024-01-01 10:00:35     peter   session_001  video_001  video_resume   30.0
  2024-01-01 10:02:05     peter   session_001  video_001  video_pause    120.0

OUTPUT DATA STRUCTURE:
---------------------
Aggregated table with ONE ROW per User-Video combination containing:
  - Watch time metrics (total, unique, percentages)
  - Session counts and averages
  - Interaction metrics (pauses, skips)
  - Completion tracking
  - Engagement scores and tiers
  - Data quality flags

EXAMPLE OUTPUT:
--------------
For Peter watching Video 1 (300s long):
  Raw events: Play 0s → Pause 30s → Resume 30s → Pause 120s → Resume 110s → Pause 120s

  Calculated metrics:
  - totalWatchTime: 130 seconds
    Explanation: 3 watch segments: (0→30s = 30s) + (30→120s = 90s) + (110→120s = 10s) = 130s

  - uniqueSecondsWatched: 120 seconds
    Explanation: User watched seconds 0-120, but 110-120 was watched twice (rewind).
                 Unique coverage = 0 to 120 = 120 seconds (don't count the overlap twice)

  - watchPercentage: 43.3%
    Calculation: (130 / 300) * 100 = 43.3%
    Meaning: User spent 43.3% of the video duration watching (includes rewatched parts)

  - completionPercentage: 40%
    Calculation: (120 / 300) * 100 = 40%
    Meaning: User reached 40% of the way through the video

  - uniqueWatchPercentage: 40%
    Calculation: (120 / 300) * 100 = 40%
    Meaning: User saw unique content covering 40% of the video

KEY CONCEPTS:
------------
1. WATCH SEGMENT: A continuous period from Play/Resume to Pause/End
   - Valid segment: prevEvent=play/resume AND currentEvent=pause/ended AND timeDelta>0
   - watchedSeconds = currentTime - prevTime

2. UNIQUE SECONDS: The actual video content seen (without counting replays)
   - Uses interval merging to handle overlapping segments
   - Example: Watched 0-30s then 20-40s = 40 unique seconds (not 50)

3. SESSION: A continuous viewing period with the same sessionId
   - Multiple sessions = user came back to the video later
   - isReplay flag = sessionCount > 1

4. ENGAGEMENT SCORE: Composite metric combining multiple factors
   - Formula: (watchTime/60)*1.0 + completions*50 + sessions*5 - skips*2
   - Higher score = more engaged user

TYPICAL USAGE:
-------------
# Initialize the aggregator
aggregator = VideoEngagementAggregator(
    spark=spark,
    input_table="raw_video_events",
    output_table="aggregated_user_video_engagement",
    video_metadata_table="video_metadata"
)

# Run the full aggregation pipeline
result_df = aggregator.run_aggregation(
    calculate_unique_seconds=True,  # Include unique watch time calculation
    use_efficient_method=True        # Use optimized interval merging (recommended)
)

# Save to Delta table
aggregator.save_results(result_df, mode="overwrite")

PERFORMANCE CONSIDERATIONS:
--------------------------
- For large datasets (millions of events), use use_efficient_method=True
- Consider partitioning output by date for faster queries
- Cache intermediate DataFrames when doing exploratory analysis
- Use Delta Lake format for ACID transactions and time travel

DATA QUALITY HANDLING:
---------------------
The script automatically handles:
- Null/missing values: Filtered out during load
- Negative currentTime: Filtered out
- Duplicate events: Naturally handled by window functions
- Out-of-order events: Sorted by timestamp before processing
- Implausible values: Flagged in dataQualityFlag column

See individual method documentation for detailed explanations.
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
    Aggregates raw video events into user-video engagement metrics.

    This class orchestrates the entire aggregation pipeline from raw events
    to actionable user-video metrics. It handles all the complex logic including:
    - Watch segment calculation (handling play/pause/resume/end events)
    - Unique seconds watched (de-duplicating overlapping time ranges)
    - Session aggregation (grouping related events)
    - User-video aggregation (final output metrics)
    - Data quality checks and flagging

    DESIGN PHILOSOPHY:
    -----------------
    The aggregation follows a multi-step pipeline approach:
    1. Load & Filter → 2. Calculate Segments → 3. Calculate Unique Seconds →
    4. Aggregate Sessions → 5. Aggregate User-Video → 6. Enrich with Metadata

    Each step produces a DataFrame that feeds into the next, allowing for
    intermediate inspection and debugging.

    EXAMPLE:
    -------
    >>> aggregator = VideoEngagementAggregator(
    ...     spark=spark,
    ...     input_table="raw_video_events",
    ...     output_table="aggregated_metrics",
    ...     video_metadata_table="video_catalog"
    ... )
    >>> results = aggregator.run_aggregation()
    >>> aggregator.save_results(results)
    """

    def __init__(self, spark, input_table, output_table, video_metadata_table=None):
        """
        Initialize the Video Engagement Aggregator.

        Args:
            spark (SparkSession): Active Spark session for DataFrame operations

            input_table (str): Name of the input table containing raw video events.
                Must have columns: timestamp, userId, sessionId, videoId, eventName, currentTime
                Example: "raw_video_events" or "bronze.video_tracking"

            output_table (str): Name of the table where aggregated results will be saved.
                Will be created if it doesn't exist.
                Example: "aggregated_user_video_engagement" or "gold.user_video_metrics"

            video_metadata_table (str, optional): Name of table containing video metadata.
                Expected columns: videoId, duration (seconds), title (optional)
                If None, video duration will be estimated from max position reached.
                Example: "video_metadata" or "dim_videos"

        Example:
            >>> spark = SparkSession.builder.getOrCreate()
            >>> agg = VideoEngagementAggregator(
            ...     spark=spark,
            ...     input_table="raw_video_events",
            ...     output_table="user_video_metrics",
            ...     video_metadata_table="video_catalog"
            ... )
        """
        self.spark = spark
        self.input_table = input_table
        self.output_table = output_table
        self.video_metadata_table = video_metadata_table
        
    def load_raw_events(self, start_date=None, end_date=None):
        """
        Load and filter raw video tracking events.

        This method performs initial data quality filtering to ensure we only
        process valid, well-formed events. Invalid events are silently dropped.

        DATA QUALITY FILTERS APPLIED:
        -----------------------------
        1. userId, videoId, sessionId must not be null
        2. eventName must be one of: video_play, video_pause, video_resume, video_ended
        3. currentTime must not be null and must be >= 0 (negative positions are invalid)

        Args:
            start_date (str or datetime, optional): Filter events on or after this date.
                Format: "YYYY-MM-DD" or datetime object
                Example: "2024-01-01" or datetime(2024, 1, 1)

            end_date (str or datetime, optional): Filter events before this date (exclusive).
                Format: "YYYY-MM-DD" or datetime object
                Example: "2024-02-01"

        Returns:
            DataFrame: Filtered events with columns:
                - timestamp: Event time
                - userId: User identifier
                - videoId: Video identifier
                - sessionId: Session identifier
                - eventName: Event type (play/pause/resume/ended)
                - currentTime: Video position in seconds

        Example:
            >>> # Load last 30 days of events
            >>> from datetime import datetime, timedelta
            >>> start = datetime.now() - timedelta(days=30)
            >>> events = aggregator.load_raw_events(start_date=start)

            >>> # Load events for January 2024
            >>> events = aggregator.load_raw_events(
            ...     start_date="2024-01-01",
            ...     end_date="2024-02-01"
            ... )

        PERFORMANCE NOTE:
        ----------------
        If your raw events table is partitioned by date, providing start_date
        and end_date will significantly improve performance by pruning partitions.
        """

        logger.info(f"Loading raw events from {self.input_table}")

        # Load the raw events table
        df = self.spark.table(self.input_table)

        # Apply date filters if provided (helps with partition pruning)
        if start_date:
            df = df.filter(col("timestamp") >= start_date)
            logger.info(f"Filtering events on or after {start_date}")
        if end_date:
            df = df.filter(col("timestamp") < end_date)
            logger.info(f"Filtering events before {end_date}")

        # Basic data quality filters - remove invalid events
        # These filters ensure we only process well-formed events
        df = df.filter(
            col("userId").isNotNull() &           # Must have a user
            col("videoId").isNotNull() &          # Must have a video
            col("sessionId").isNotNull() &        # Must have a session
            col("eventName").isin([               # Must be a known event type
                "video_play",
                "video_pause",
                "video_resume",
                "video_ended"
            ]) &
            col("currentTime").isNotNull() &      # Must have a position
            (col("currentTime") >= 0)             # Position can't be negative
        )

        event_count = df.count()
        logger.info(f"Loaded {event_count:,} valid events after filtering")

        return df
    
    def calculate_watch_segments(self, events_df):
        """
        Calculate watch segments and identify valid viewing periods.

        A "watch segment" is a continuous period where the user is actively watching.
        It starts with a Play or Resume event and ends with a Pause or Ended event.

        ALGORITHM EXPLANATION:
        ---------------------
        1. Sort events by timestamp within each (userId, videoId, sessionId) group
        2. Use window functions to look at previous event (lag function)
        3. Calculate time differences between consecutive events:
           - timeDelta: Difference in VIDEO position (currentTime - prevTime)
           - timestampDelta: Difference in REAL WORLD time (server timestamp difference)
        4. Identify valid segments based on event transitions and plausibility checks
        5. Calculate watched seconds for each valid segment

        WHAT IS A VALID SEGMENT?
        ------------------------
        A segment is valid if ALL of these conditions are met:
        - Previous event was "video_play" OR "video_resume" (segment started)
        - Current event is "video_pause" OR "video_ended" (segment ended)
        - timeDelta > 0 (video position moved forward)
        - timeDelta < 7200 seconds (2 hours - prevents data errors)
        - timeDelta is plausible given timestampDelta (can't watch 100s of video in 10s of real time)

        EXAMPLE:
        -------
        Input events for one session:
        timestamp            eventName      currentTime
        2024-01-01 10:00:00  video_play     0.0
        2024-01-01 10:00:30  video_pause    30.0
        2024-01-01 10:00:35  video_resume   30.0
        2024-01-01 10:02:05  video_pause    120.0

        Output segments:
        Row 2: prevEvent=play, event=pause, prevTime=0, currentTime=30
               → timeDelta=30, isValidSegment=True, watchedSeconds=30

        Row 3: prevEvent=pause, event=resume, prevTime=30, currentTime=30
               → timeDelta=0, isValidSegment=False (pause→resume not a watch segment)

        Row 4: prevEvent=resume, event=pause, prevTime=30, currentTime=120
               → timeDelta=90, isValidSegment=True, watchedSeconds=90

        SKIP DETECTION:
        --------------
        We also identify "jumps" (skips) in the video:
        - Forward skip: timeDelta > 5 seconds (user skipped ahead)
        - Backward skip: timeDelta < -2 seconds (user rewound)

        Args:
            events_df (DataFrame): Raw events from load_raw_events()

        Returns:
            DataFrame: Events with additional columns:
                - prevEvent (str): Previous event name
                - prevTime (float): Previous video position
                - prevTimestamp (timestamp): Previous event timestamp
                - timeDelta (float): Change in video position (seconds)
                - timestampDelta (float): Change in real time (seconds)
                - isValidSegment (bool): True if this represents actual watch time
                - watchedSeconds (float): Seconds watched in this segment (0 if invalid)
                - isJump (bool): True if user skipped forward/backward
                - jumpType (str): "forward", "backward", or "none"

        DEBUGGING TIPS:
        --------------
        To inspect segments for a specific user/video:
        >>> segments = aggregator.calculate_watch_segments(events)
        >>> segments.filter(
        ...     (col("userId") == "peter") &
        ...     (col("videoId") == "video_001")
        ... ).orderBy("timestamp").show(truncate=False)
        """

        logger.info("Calculating watch segments...")

        # Create window spec: partition by user-video-session, order by time
        # This allows us to look at previous events within the same viewing session
        window_spec = Window.partitionBy("userId", "videoId", "sessionId").orderBy("timestamp")

        # Add previous event information using lag() window function
        # lag() looks at the previous row within the partition
        df = events_df.withColumn("prevEvent", lag("eventName").over(window_spec)) \
                      .withColumn("prevTime", lag("currentTime").over(window_spec)) \
                      .withColumn("prevTimestamp", lag("timestamp").over(window_spec))

        # Calculate time differences
        # timeDelta: How far the video position moved (can be negative if user rewound)
        # timestampDelta: How much real-world time elapsed
        df = df.withColumn(
            "timeDelta",
            col("currentTime") - col("prevTime")
        ).withColumn(
            "timestampDelta",
            unix_timestamp("timestamp") - unix_timestamp("prevTimestamp")
        )

        # Identify valid watch segments
        # A segment is valid when:
        # 1. It starts with play/resume
        # 2. It ends with pause/ended
        # 3. Time moved forward (timeDelta > 0)
        # 4. The duration is reasonable (< 2 hours to catch data errors)
        # 5. Plausibility: can't watch 100s of video in 1s of real time
        #    (we allow +5s tolerance for network latency)
        df = df.withColumn(
            "isValidSegment",
            (col("prevEvent").isin(["video_play", "video_resume"])) &  # Segment start
            (col("eventName").isin(["video_pause", "video_ended"])) &  # Segment end
            (col("timeDelta") > 0) &                                    # Forward progress
            (col("timeDelta") < 7200) &                                 # Max 2 hours (data quality)
            (col("timeDelta").between(0, col("timestampDelta") + 5))   # Plausibility check
        )

        # Calculate watched seconds: only count valid segments
        df = df.withColumn(
            "watchedSeconds",
            when(col("isValidSegment"), col("timeDelta")).otherwise(0.0)
        )

        # Identify skips/jumps in the video
        # Forward skip: jumped ahead more than 5 seconds
        # Backward skip: rewound more than 2 seconds
        df = df.withColumn(
            "isJump",
            (col("timeDelta").isNotNull()) & (
                (col("timeDelta") > 5) |   # Forward skip (user jumped ahead)
                (col("timeDelta") < -2)    # Backward skip (user rewound)
            )
        ).withColumn(
            "jumpType",
            when(col("timeDelta") > 5, "forward")
            .when(col("timeDelta") < -2, "backward")
            .otherwise("none")
        )

        logger.info("Watch segments calculated successfully")
        return df
    
    def calculate_unique_seconds_watched(self, events_df):
        """
        Calculate UNIQUE seconds watched (without counting replays twice)
        
        Example: User watches 0-30s, then back to 20s and watches until 40s
        - Total watch time: 30 + 20 = 50 seconds
        - Unique watch time: 40 seconds (0-40s, but 20-30 is duplicate = don't count twice)
        """
        
        logger.info("Calculating unique seconds watched...")
        
        # Window for each User-Video combination
        window_spec = Window.partitionBy("userId", "videoId", "sessionId").orderBy("timestamp")
        
        # Create start and end for each watch segment
        segments_df = events_df.filter(col("isValidSegment")) \
            .withColumn("segmentStart", col("prevTime").cast("int")) \
            .withColumn("segmentEnd", col("currentTime").cast("int")) \
            .select("userId", "videoId", "sessionId", "segmentStart", "segmentEnd")
        
        # Expand each segment to a list of seconds
        # Warning: Can be memory-intensive for long videos!
        # Alternative below for production
        segments_df = segments_df.withColumn(
            "secondsWatched",
            expr("sequence(segmentStart, segmentEnd - 1)")
        )
        
        # Flatten and deduplicate
        unique_seconds = segments_df.select(
            "userId", "videoId", "sessionId",
            explode("secondsWatched").alias("second")
        ).distinct()
        
        # Count unique seconds per User-Video-Session
        unique_count = unique_seconds.groupBy("userId", "videoId", "sessionId") \
            .agg(count("second").alias("uniqueSecondsWatched"))
        
        return unique_count
    
    def calculate_unique_seconds_efficient(self, events_df):
        """
        More efficient version for production: Merge overlapping intervals
        Avoids explode() for long videos
        """
        
        logger.info("Calculating unique seconds watched (efficient method)...")
        
        # Create segments
        segments = events_df.filter(col("isValidSegment")) \
            .withColumn("segmentStart", col("prevTime").cast("double")) \
            .withColumn("segmentEnd", col("currentTime").cast("double")) \
            .select("userId", "videoId", "sessionId", "segmentStart", "segmentEnd") \
            .orderBy("userId", "videoId", "sessionId", "segmentStart")
        
        # Merge overlapping intervals via SQL
        # This algorithm solves the interval merging problem:
        # - User watches 0-30s, then rewinds to 20s and watches 20-50s
        # - Segments: [0-30] and [20-50] overlap at 20-30s
        # - Goal: Merge into [0-50] to count 50 unique seconds (not 60)
        #
        # Algorithm in 4 steps:
        # 1. ordered_segments: Add prevEnd (when previous segment ended)
        # 2. merged_segments: Check if current overlaps previous (segmentStart <= prevEnd)
        # 3. grouped: Assign group IDs (overlapping segments get same group)
        # 4. Final: MIN(start), MAX(end) for each group = merged interval

        segments.createOrReplaceTempView("segments_temp")

        merged = self.spark.sql("""
            -- STEP 1: Add previous segment's end time using window function
            -- This lets us check if current segment overlaps with previous
            WITH ordered_segments AS (
                SELECT
                    userId, videoId, sessionId,
                    segmentStart, segmentEnd,
                    LAG(segmentEnd) OVER (
                        PARTITION BY userId, videoId, sessionId
                        ORDER BY segmentStart
                    ) as prevEnd
                    -- Example: If segments are [0-30] then [20-50]
                    --   Row 1: start=0,  end=30, prevEnd=NULL
                    --   Row 2: start=20, end=50, prevEnd=30
                FROM segments_temp
            ),

            -- STEP 2: Detect if segment starts a new group or continues previous
            -- New group = there's a gap (segmentStart > prevEnd)
            -- Same group = there's overlap (segmentStart <= prevEnd)
            merged_segments AS (
                SELECT
                    userId, videoId, sessionId,
                    segmentStart,
                    segmentEnd,
                    CASE
                        WHEN prevEnd IS NULL OR segmentStart > prevEnd
                        THEN 1  -- Start new group (first segment or gap exists)
                        ELSE 0  -- Continue group (overlaps with previous)
                    END as newGroup
                    -- Example continued:
                    --   Row 1: prevEnd=NULL → newGroup=1 (start first group)
                    --   Row 2: 20 <= 30 → newGroup=0 (overlaps, same group)
                FROM ordered_segments
            ),

            -- STEP 3: Assign group IDs by cumulative sum of newGroup
            -- All overlapping segments get the same groupId
            grouped AS (
                SELECT
                    userId, videoId, sessionId,
                    segmentStart, segmentEnd,
                    SUM(newGroup) OVER (
                        PARTITION BY userId, videoId, sessionId
                        ORDER BY segmentStart
                    ) as groupId
                    -- Example continued:
                    --   Row 1: newGroup=1 → groupId=1 (running sum: 1)
                    --   Row 2: newGroup=0 → groupId=1 (running sum: 1+0=1)
                    -- If there was a 3rd segment [60-90] with gap:
                    --   Row 3: newGroup=1 → groupId=2 (running sum: 1+0+1=2)
                FROM merged_segments
            )

            -- STEP 4: Merge intervals by taking MIN(start) and MAX(end) per group
            -- This collapses overlapping segments into single intervals
            SELECT
                userId, videoId, sessionId,
                MIN(segmentStart) as mergedStart,
                MAX(segmentEnd) as mergedEnd
                -- Example result:
                --   groupId=1: MIN(0,20)=0, MAX(30,50)=50 → [0-50] (merged!)
                --   groupId=2: MIN(60)=60, MAX(90)=90 → [60-90]
                -- Total unique seconds: (50-0) + (90-60) = 50 + 30 = 80 seconds
            FROM grouped
            GROUP BY userId, videoId, sessionId, groupId
        """)
        
        # Calculate sum of merged intervals
        unique_seconds = merged.withColumn(
            "intervalLength",
            col("mergedEnd") - col("mergedStart")
        ).groupBy("userId", "videoId", "sessionId") \
         .agg(_sum("intervalLength").alias("uniqueSecondsWatched"))
        
        return unique_seconds
    
    def aggregate_sessions(self, events_df):
        """Aggregate to session-level"""
        
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
        Aggregate to User-Video level (final output table)
        One row per User + Video combination
        """
        
        logger.info("Aggregating user-video metrics...")
        
        # Join with unique seconds if available
        if unique_seconds_df is not None:
            user_video = session_df.join(
                unique_seconds_df,
                on=["userId", "videoId", "sessionId"],
                how="left"
            )
            # Also aggregate unique seconds
            unique_seconds_total = user_video.groupBy("userId", "videoId") \
                .agg(_sum("uniqueSecondsWatched").alias("totalUniqueSecondsWatched"))
        else:
            unique_seconds_total = None
        
        # Main aggregation
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
        
        # Join with unique seconds
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
        Add video metadata (Duration, Title, etc.) and calculate percentages
        """
        
        if self.video_metadata_table is None:
            logger.warning("No video metadata table provided, using defaults")
            # Create dummy metadata based on maxPosition
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
        
        # Calculate percentages
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
        
        # Engagement score
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
        
        # Engagement tier
        enriched = enriched.withColumn(
            "engagementTier",
            when(col("engagementScore") > 100, "High")
            .when(col("engagementScore") > 50, "Medium")
            .when(col("engagementScore") > 10, "Low")
            .otherwise("Minimal")
        )
        
        # Data quality flags
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
        Run the complete aggregation pipeline
        
        Args:
            start_date: Optional filter start date
            end_date: Optional filter end date
            calculate_unique_seconds: Boolean, whether to calculate unique seconds
            use_efficient_method: Boolean, use efficient interval merging instead of explode
        
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
        Save results to output table
        
        Args:
            df: DataFrame to save
            mode: "overwrite", "append", or "merge"
            partition_by: Optional list of columns to partition by (e.g. ["firstWatchDate"])
        """
        
        logger.info(f"Saving results to {self.output_table}")
        
        # Add processing metadata
        df = df.withColumn("processedAt", lit(datetime.now()))
        
        writer = df.write.format("delta")  # Use Delta Lake for ACID
        
        if partition_by:
            writer = writer.partitionBy(*partition_by)
        
        writer.mode(mode).saveAsTable(self.output_table)
        
        logger.info(f"Successfully saved {df.count()} rows to {self.output_table}")
    
    def generate_summary_stats(self, df):
        """Generate summary statistics for validation"""
        
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
    INPUT_TABLE = "raw_video_events"  # Your raw events table
    OUTPUT_TABLE = "aggregated_user_video_engagement"  # Output table
    VIDEO_METADATA_TABLE = "video_metadata"  # Optional: Table with video metadata
    
    # Optional: Process only last N days
    # start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    start_date = None  # All data
    end_date = None
    
    # Initialize aggregator
    aggregator = VideoEngagementAggregator(
        spark=spark,
        input_table=INPUT_TABLE,
        output_table=OUTPUT_TABLE,
        video_metadata_table=VIDEO_METADATA_TABLE  # None if not available
    )
    
    # Run aggregation
    result_df = aggregator.run_aggregation(
        start_date=start_date,
        end_date=end_date,
        calculate_unique_seconds=True,  # True for accurate unique watch time
        use_efficient_method=True       # True for production (scales better)
    )
    
    # Generate summary stats
    aggregator.generate_summary_stats(result_df)
    
    # Save results
    aggregator.save_results(
        result_df,
        mode="overwrite",  # Or "append" for incremental updates
        partition_by=["firstWatchDate"]  # Optional: Partition by date
    )
    
    # Optional: Create view for BI tools
    result_df.createOrReplaceTempView("vw_user_video_engagement")
    spark.sql(f"CREATE OR REPLACE VIEW vw_user_video_engagement AS SELECT * FROM {OUTPUT_TABLE}")
    
    logger.info("\n✅ Aggregation completed successfully!")
    
    return result_df


if __name__ == "__main__":
    result = main()

# Video Analytics - Executive Summary

## Problem Statement

Currently, video interactions are tracked in the Databricks storage layer as individual events (play, pause, resume, etc.). The challenge is to calculate meaningful metrics like **Total Watch Time** per user and video from these atomic events to understand video engagement.

**Complexity:** 
- Each interaction = 1 event row
- User journey must be reconstructed manually
- Edge cases like browser close, skips, multi-tab sessions

---

## Solution: Multi-Layer Aggregation

### Architecture

```
Raw Events (Databricks)
    ↓ [Real-time]
├─→ PySpark Aggregation Script
    ↓ [Batch Processing]
├─→ Aggregated User-Video Table (One row per User+Video)
    ↓ [BI Connection]
└─→ Dashboards & Analytics
```

---

## Implementation Phases

### Phase 1: Basic Watch Time (2 weeks)
**Goal:** Cover simple scenarios (Play → Pause → End)

**Deliverables:**
- PySpark script for watch time calculation
- Dashboard with top videos by watch time
- Validation with known test users

**Impact:** 80% of use cases covered

---

### Phase 2: Edge Cases (2 weeks)
**Goal:** Skip detection, session timeouts, data quality

**Deliverables:**
- Jump/skip detection logic
- Session timeout handling (browser close)
- Data quality dashboard
- Alert rules for anomalies

**Impact:** Robust data quality, correct metrics even for complex scenarios

---

### Phase 3: Multi-Video & Advanced (2 weeks)
**Goal:** Video switching, replays, multi-session tracking

**Deliverables:**
- Video switching detection
- Replay recognition
- User engagement scoring
- Retention & drop-off analysis

**Impact:** Deeper insights into user behavior

---

### Phase 4: Performance Optimization (2 weeks)
**Goal:** Optimize performance through aggregation

**Deliverables:**
- Optimized PySpark script
- Delta Lake tables for ACID compliance
- Scheduled batch processing
- Automated reports

**Impact:** Sub-second dashboard load times, scales to millions of events

---

## Key Metrics

### Video-Level Metrics
- **Unique Viewers**: Number of unique users
- **Total Watch Time**: Total time watched
- **Completion Rate**: % of sessions with "video_ended" event
- **Avg Watch Time per Session**: Average playback time
- **Engagement Score**: Weighted metric from watch time, completions, sessions

### User-Level Metrics
- **Total Watch Time**: Sum across all videos
- **Videos Watched**: Number of videos started
- **Videos Completed**: Number of videos finished
- **Engagement Tier**: High/Medium/Low/Minimal based on score

### Session-Level Metrics
- **Watch Time**: Actually watched time (without skips)
- **Max Position**: Furthest point in video
- **Pause Count**: Number of pauses
- **Skip Count**: Number of forward/backward jumps
- **Completed**: Boolean, whether video was watched to end

---

## Scenario Coverage (18 scenarios identified)

### ✅ Fully solved:
1. **Straightforward Play → End** (Basic scenario)
2. **Play → Pause → Resume → End** (With pauses)
3. **Play → Pause → Browser Close** (Session timeout)
4. **Skip Forward/Backward** (Jump detection)
5. **Multiple Sessions (Replay)** (Replay recognition)
6. **Multiple Videos in Session** (Video switching)

### ⚠️ Partially solved (requires client-side changes):
7. **Tab Switch** (Heuristic via pause duration)
8. **Page Refresh** (Session restart detection)
9. **Resume from Last Position** (Requires position tracking)
10. **Autoplay** (Requires autoplay flag in event)

### 🔴 Not solvable with current events:
11. **Video completely ignored** (Requires page-view events with video list)

---

## Data Quality & Monitoring

### Validation Checks
- ✅ Watch Time ≤ Video Duration (+10% tolerance)
- ✅ No negative watch time
- ✅ Completion only with sufficient watch time (>75%)
- ✅ Session duration < 4 hours
- ✅ Events-per-session ratio: 3-5

### Alerts
- 🚨 Data freshness > 3 hours
- 🚨 Completion rate drop > 20%
- 🚨 Zero-watch-rate > 15%
- 🚨 Negative watch time detected

---

## Performance & Scaling

### Current Estimate (based on assumptions):
- **10,000 Users/Day** × 5 Videos × 4 Events = **200,000 Events/Day**
- **6M Events/Month**, **73M Events/Year**
- **Storage**: ~7.3 GB/year (Raw), ~1 GB/year (Aggregated)

### Query Performance Targets:
- Session aggregation (1 day): **< 5 seconds**
- User-video metrics (1 week): **< 10 seconds**
- Dashboard refresh: **< 15 seconds**
- Real-time (last hour): **< 2 seconds**

With optimized processing: **Sub-second queries** for aggregated data

---

## Quick Start: First Steps

### Week 1: Validation
1. **Deploy basic script** from Phase 1
2. **Test with 5-10 known users**
3. **Compare manual samples** with query results
4. **Document discrepancies**

### Week 2: Dashboard Setup
1. **Setup Power BI / Tableau dashboard**
2. **Implement top 3 metrics:**
   - Total watch time by video
   - Completion rate by video
   - Active users over time

### Week 3-4: Data Quality
1. **Implement data quality checks**
2. **Setup alerts for anomalies**
3. **Document edge cases**

### From Week 5: Iterative Improvement
- Advanced scenarios by priority
- Performance optimization
- Feature requests from business

---

## Cost-Benefit

### Effort
- **Phase 1-2**: ~4 weeks (1 Developer)
- **Phase 3**: ~2 weeks (Optional, depending on business need)
- **Phase 4**: ~2 weeks (If performance issues)
- **Total**: 6-8 weeks

### Benefit
- ✅ **Data-driven video strategy**: Which videos work?
- ✅ **Content optimization**: Where do users drop off?
- ✅ **User engagement tracking**: Who are power users?
- ✅ **ROI measurement**: Is video production worth it?
- ✅ **A/B testing capability**: Which thumbnail works better?

---

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Incomplete events (browser close) | High | Medium | Session timeout heuristic |
| Skip behavior distorts metrics | Medium | High | Implement jump detection |
| Performance issues at scale | Medium | Medium | Optimized processing, partitioning |
| Tracking gaps (multi-tab) | Low | Low | Document, not blocking |

---

## Recommendation

**Start immediately with Phase 1** (Basic watch time calculation). This delivers 80% of business value with minimal effort.

**Phase 2 within 4 weeks** for data quality and robustness.

**Phase 3+4 as needed**, based on:
- Number of users/events (scaling)
- Complexity of business questions
- Performance requirements

---

## Next Steps

1. ✅ **Review this documentation** with team
2. 📅 **Sprint planning** for Phase 1
3. 🧪 **Setup test environment** with synthetic events
4. 🚀 **Deploy basic script** in production
5. 📊 **Setup first dashboard**
6. 🔄 **Iterative improvement** based on feedback

---

## Appendices

Detailed documentation:
- `databricks_video_aggregation.py`: Complete PySpark script
- `databricks_example_notebook.py`: Example notebook with sample data
- `quick_reference_guide.md`: Quick reference for developers
- `implementation_roadmap.md`: Step-by-step implementation
- `test_scenarios.md`: Test cases & validation queries


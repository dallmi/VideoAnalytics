# 🧪 Testing Documentation

## Test Specification

### **📋 Complete Test Coverage: 25 Scenarios (~90% Coverage)**

→ **[TEST_SCENARIOS_COMPLETE.md](TEST_SCENARIOS_COMPLETE.md)** ⭐ Main test specification

This includes:
- **10 Core Scenarios** (common patterns from Business Analysis)
- **15 Edge Cases** (data quality, timing, boundaries)
- **Total: 25 test cases** covering 90%+ of real-world scenarios

---

## 📋 Test Cases Overview

### **Core Scenarios (TC-001 to TC-010)**

| Test Case | Scenario | Priority | Coverage |
|-----------|----------|----------|----------|
| TC-001 | Perfect Viewing | P0 | Happy path |
| TC-002 | Pause & Resume | P0 | Common pattern |
| TC-003 | Browser Close | P0 | Data loss |
| TC-004 | Skip Forward | P1 | Navigation |
| TC-005 | Skip Backward (Rewind) | P1 | Navigation |
| TC-006 | Multiple Sessions | P1 | Replay |
| TC-007 | Multi-Video Session | P1 | Binge watching |
| TC-008 | Abandoned Early | P2 | Low engagement |
| TC-009 | Complex Navigation | P2 | Multiple interactions |
| TC-010 | Gaming Detection | P1 | Data quality |

### **Edge Cases (TC-011 to TC-025)**

| Test Case | Scenario | Priority | Category |
|-----------|----------|----------|----------|
| TC-011 | Duplicate Events | P1 | Data Quality |
| TC-012 | Out-of-Order Events | P1 | Data Quality |
| TC-013 | Null/Missing Values | P0 | Data Quality |
| TC-014 | Negative currentTime | P1 | Data Quality |
| TC-015 | Extremely Long Watch | P1 | Data Quality |
| TC-016 | Rapid Fire Events | P2 | Timing |
| TC-017 | Session Timeout | P2 | Timing |
| TC-018 | Same Day Multiple Sessions | P2 | Timing |
| TC-019 | Midnight Boundary | P2 | Timing |
| TC-020 | Position Beyond Duration | P1 | Boundary |
| TC-021 | Zero Duration Segment | P2 | Boundary |
| TC-022 | Only Resume Events | P2 | Boundary |
| TC-023 | Only Pause Events | P2 | Boundary |
| TC-024 | Empty Session | P2 | Boundary |
| TC-025 | Multiple Play Events | P2 | Data Quality |

---

## 🎯 For Testers

### 1. Read the Complete Test Specification
**→ [TEST_SCENARIOS_COMPLETE.md](TEST_SCENARIOS_COMPLETE.md)** (2 hours)

All 25 scenarios with:
- ✅ Description of behavior
- ✅ Raw input events (test data)
- ✅ Expected output metrics
- ✅ Validation criteria
- ✅ Priority levels (P0/P1/P2)

**Also reference:**
**→ [Video Tracking Scenarios Guide](../02_BUSINESS_ANALYSIS/VIDEO_TRACKING_SCENARIOS_GUIDE.md)** - Business context for core scenarios

### 2. Generate Test Data
**→ [test_data_generator_complete.py](test_data_generator_complete.py)** ⭐ NEW

Complete test data generator for ALL 25 scenarios in one notebook.

### 3. Run Validation Queries
Use the validation queries in the Scenarios Guide (see "Testing Scenarios" section).

### 4. Create Test Report
Template:
```
Test Report - Video Analytics Aggregation

Date: [Date]
Tester: [Name]
Environment: [Dev/Test/Prod]

Test Results:
- TC-001: ✅ PASS
- TC-002: ✅ PASS
- TC-003: ✅ PASS
- TC-004: ✅ PASS
- TC-005: ✅ PASS
- TC-006: ✅ PASS
- TC-007: ✅ PASS
- TC-008: ✅ PASS
- TC-009: ✅ PASS
- TC-010: ✅ PASS

Overall: 10/10 PASS

Issues Found: [None / List issues]
Sign-off: [Name, Date]
```

---

## 🔍 Sample Validation Queries

### Test 1: Verify No Negative Watch Time
```sql
SELECT * FROM aggregated_user_video_engagement
WHERE totalWatchTime < 0;
-- Expected: 0 rows
```

### Test 2: Watch Percentage in Valid Range
```sql
SELECT * FROM aggregated_user_video_engagement
WHERE watchPercentage > 200;
-- Expected: 0 or very few rows (over 200% is suspicious)
```

### Test 3: Completion Requires Sufficient Watch
```sql
SELECT * FROM aggregated_user_video_engagement
WHERE completed = true
  AND watchPercentage < 50
  AND dataQualityFlag = 'ok';
-- Expected: 0 rows (all should be flagged)
```

### Test 4: Max Position ≤ Video Duration
```sql
SELECT * FROM aggregated_user_video_engagement
WHERE maxPositionReached > videoDuration;
-- Expected: 0 rows
```

### Test 5: Session Count ≥ 1
```sql
SELECT * FROM aggregated_user_video_engagement
WHERE sessionCount < 1;
-- Expected: 0 rows
```

---

## ✅ Test Checklist

### Pre-Testing:
- [ ] Read Video Tracking Scenarios Guide (all 10 scenarios)
- [ ] Understand expected behavior for each scenario
- [ ] Setup test environment
- [ ] Generate test data using example notebook

### During Testing:
- [ ] Run aggregation script
- [ ] Execute validation queries
- [ ] Compare output with expected results from guide
- [ ] Document any discrepancies
- [ ] Test edge cases

### Post-Testing:
- [ ] All 10 scenarios pass
- [ ] Data quality checks pass
- [ ] Performance acceptable (see benchmarks)
- [ ] Create test report
- [ ] Get BA sign-off

---

## 🐛 Common Issues & How to Test

### Issue 1: Browser Close Data Loss
**Test:** Scenario 3 (Browser Close)
**Expected:** Only counts completed segments
**Validation:** Check that totalWatchTime is less than actual time if browser closed

### Issue 2: Skip Detection
**Test:** Scenario 4 (Skip Forward) & Scenario 5 (Rewind)
**Expected:** forwardSkipCount or backwardSkipCount > 0
**Validation:** Check skip counts match expected jumps

### Issue 3: Multiple Session Aggregation
**Test:** Scenario 6 (Multiple Sessions)
**Expected:** sessionCount > 1, aggregates across sessions
**Validation:** Sum of session watch times = totalWatchTime

### Issue 4: Gaming Detection
**Test:** Scenario 10 (Skip to End)
**Expected:** dataQualityFlag = 'completed_without_sufficient_watch'
**Validation:** Flag raised when completed but watchPercentage < 75%

---

## 📊 Test Metrics

Track these metrics during testing:

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Test Coverage | 10/10 scenarios | Count passing test cases |
| Data Quality | >95% "ok" flag | Count quality flags |
| Performance | <5 sec for 1M events | Time aggregation run |
| Accuracy | 100% match expected output | Compare with scenarios |

---

## 🆘 Need Help?

1. **For test specification:** See [Video Tracking Scenarios Guide](../02_BUSINESS_ANALYSIS/VIDEO_TRACKING_SCENARIOS_GUIDE.md)
2. **For test data:** See [Example Notebook](../03_DEVELOPMENT/databricks_example_notebook.py)
3. **For expected behavior:** Each scenario in the guide shows expected output
4. **For technical issues:** See [Quick Reference Guide](../05_REFERENCE/quick_reference_guide.md)

---

## 🎯 Success Criteria

Testing is complete when:

✅ All 10 scenarios pass with expected output
✅ Data quality validation queries return 0 problematic rows
✅ Performance meets benchmarks (see Executive Summary)
✅ Business Analyst validates business logic
✅ Test report created and signed off
✅ No critical bugs found

---

*For detailed test cases, see [Video Tracking Scenarios Guide](../02_BUSINESS_ANALYSIS/VIDEO_TRACKING_SCENARIOS_GUIDE.md)*

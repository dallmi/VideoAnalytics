# 🧪 Testing Documentation

## Test Specification

All test cases are documented in the **Business Analysis** section:

→ **[Video Tracking Scenarios Guide](../02_BUSINESS_ANALYSIS/VIDEO_TRACKING_SCENARIOS_GUIDE.md)**

---

## 📋 Test Cases

The Scenarios Guide contains **10 complete test cases** with:

| Test Case | Scenario | Input Data | Expected Output | Location |
|-----------|----------|------------|-----------------|----------|
| TC-001 | Perfect Viewing | Raw events provided | 100% completion | Scenario 1 |
| TC-002 | Pause & Resume | Raw events provided | Correct segments | Scenario 2 |
| TC-003 | Browser Close | Raw events provided | Lost data handling | Scenario 3 |
| TC-004 | Skip Forward | Raw events provided | Jump detection | Scenario 4 |
| TC-005 | Rewind | Raw events provided | Replay handling | Scenario 5 |
| TC-006 | Multiple Sessions | Raw events provided | Session aggregation | Scenario 6 |
| TC-007 | Multi-Video | Raw events provided | Separate rows | Scenario 7 |
| TC-008 | Early Abandonment | Raw events provided | Low engagement flag | Scenario 8 |
| TC-009 | Complex Navigation | Raw events provided | All interactions tracked | Scenario 9 |
| TC-010 | Gaming Detection | Raw events provided | Quality flag raised | Scenario 10 |

---

## 🎯 For Testers

### 1. Read the Test Specification
**→ [Video Tracking Scenarios Guide](../02_BUSINESS_ANALYSIS/VIDEO_TRACKING_SCENARIOS_GUIDE.md)** (90 minutes)

Each scenario provides:
- ✅ Description of behavior
- ✅ Raw input events (test data)
- ✅ Visual timeline
- ✅ Expected output metrics
- ✅ Business validation criteria

### 2. Generate Test Data
**→ [Example Notebook](../03_DEVELOPMENT/databricks_example_notebook.py)**

Contains test data generation code for all scenarios.

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

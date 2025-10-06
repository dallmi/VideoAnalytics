# 📋 Quick Reference Card: Event Pairs & Max Position

## The Two Golden Rules

### Rule #1: Event Pairs Required
```
✅ COUNTED                    ❌ NOT COUNTED
play → pause                  play → [close]
play → ended                  resume → [close]
resume → pause                pause → resume (not watching)
resume → ended                [any single event]
```

### Rule #2: Max Position = Highest
```
maxPosition = MAX(all currentTime values)

Example:
  play(0) → pause(30) → resume(20) → [close]
  maxPosition = MAX(0, 30, 20) = 30s  ← Not 20!
```

---

## Peter's Example at a Glance

### Events
```
10:00:00  ▶️ play(0s)
10:00:30  ⏸️ pause(30s)
10:00:35  ▶️ resume(20s)  ← rewound 10s
10:01:05  ❌ [close]
```

### Calculation
```
Segment 1: play(0) → pause(30)   = 30s ✅
Segment 2: resume(20) → [close]  = 0s  ❌

totalWatchTime = 30s
maxPosition = 30s (not 20s!)
watchPercentage = 10%
```

---

## Common Scenarios

| Scenario | Events | Watch Time | Max Pos |
|----------|--------|------------|---------|
| Normal | play(0) → pause(30) | 30s | 30s |
| Browser close | play(0) → pause(30) → resume(30) → [close] | 30s | 30s |
| With rewind | play(0) → pause(30) → resume(20) → [close] | 30s | 30s |
| Fixed version | play(0) → pause(30) → resume(20) → pause(50) | 60s | 50s |

---

## Why Max Position Uses 30s (Not 20s)

```
Event: pause(30s)    → maxPosition = 30s
Event: resume(20s)   → maxPosition = MAX(30, 20) = 30s ✅

The MAX() function always keeps the highest value!
```

---

## The Fix: Add Closing Events

**Problem:**
```
resume(20s) → [close] = ❌ Not counted
```

**Solution:**
```
resume(20s) → pause(50s) = ✅ 30s counted!
```

Implement: Heartbeat events or beforeunload handler

---

## Quick Questions

**Q: Why isn't the segment after resume counted?**
A: No closing event (pause/ended). We don't know when they stopped.

**Q: Why maxPosition = 30s when they rewound to 20s?**
A: MAX function keeps highest value (30 > 20).

**Q: How much did Peter actually watch?**
A: Probably 60s, but only 30s can be confirmed.

**Q: Is the session in the data?**
A: Yes! It shows up with 30s watch time and flags.

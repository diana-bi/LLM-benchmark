# Test Plan Updates Summary

## Changes Made

### 1. ✅ Updated TEST_PLAN.md
Complete test roadmap with 14 functional tests + 2 bug checks, now includes:

**Key Updates:**
- Test 5 now includes `--plots` and `--live` flags with documentation
- Added new section: "Important: Visualization Flags (Not Stored in Metadata)"
- Clarified that `--plots` and `--live` are UI-only and don't appear in header
- All test commands, expected outputs, and checks are current and executable

**Coverage:**
- Tests 1-8: CLI functionality (baseline, candidate, list)
- Tests 9-11: Observability system (sequential + concurrent analysis)
- Tests 12-14: Promotion flow and error handling
- Bug Checks 1-2: Metadata integrity (no nulls, required fields)

### 2. ✅ Fixed benchmark.py Metadata Bug
Added missing fields to both metadata paths:

**Files modified:** `benchmark.py` (2 locations)

**Changes:**
- **Line 337-342** (validity gate failure path): Added `timestamp`, `rps_override`, `requests_override`
- **Line 528-535** (success path): Added `rps_override`, `requests_override`

**Before:**
```python
metadata = {
    "endpoint": results.get("endpoint", ""),
    "fast_mode": fast_mode,
    "scenario_configs": scenario_configs,
    "include_sweep": include_sweep,
}
```

**After:**
```python
metadata = {
    "endpoint": results.get("endpoint", ""),
    "timestamp": results.get("timestamp", ""),
    "fast_mode": fast_mode,
    "scenario_configs": scenario_configs,
    "include_sweep": include_sweep,
    "rps_override": rps_override,
    "requests_override": requests_override,
}
```

## Test Plan Organization

### Core CLI Tests (Tests 1–8)
| Test | Command | Focus |
|------|---------|-------|
| 1 | `list` (empty) | List functionality when no baselines exist |
| 2 | `baseline` (default) | Production mode, no flags in header |
| 3 | `baseline --fast` | Flag tracking: FAST MODE |
| 4 | `baseline --rps 8` | Flag tracking: RPS override |
| 5 | `baseline --fast --rps 4 --requests 50 --sweep --plots --live` | All flags, visualization modes |
| 6 | `list --stack-id test_cpu` | List filtering and sorting |
| 7 | `candidate` | Auto-load baseline, comparison report |
| 8 | `candidate --sweep` | Concurrency sweep results |

### Observability Tests (Tests 9–11)
| Test | Focus |
|------|-------|
| 9 | Observability analysis visible in report (drift, spikes, distribution, bimodal) |
| 10 | Observability data correctly structured in JSON baseline |
| 11 | Raw latencies (sequential + concurrent) stored in baseline |

### Promotion & Error Handling (Tests 12–14)
| Test | Focus |
|------|-------|
| 12 | Promote candidate to baseline workflow |
| 13 | Error handling: missing baseline |
| 14 | Error handling: unreachable endpoint |

### Data Integrity (Bug Checks)
| Check | Focus |
|-------|-------|
| 1 | No NULL values in metadata |
| 2 | All required metadata keys present (endpoint, timestamp, fast_mode, scenario_configs, include_sweep, rps_override, requests_override) |

## Visualization Flags Clarification

The two new flags `--plots` and `--live` are **display-only** and do not appear in the metadata:

- **`--plots`**: Shows ASCII time-series and histogram plots in terminal
- **`--live`**: Shows Rich dashboard during concurrent phase

They differ from `--fast`, `--rps`, `--requests`, `--sweep` which **do** change benchmark behavior and are tracked in metadata.

## Running the Tests

All tests are executable. Use TEST_PLAN.md as your reference for:
- Exact command syntax
- Expected outputs
- Validation checks
- Python inspection scripts for JSON verification

### 3. ✅ Added Comprehensive Metadata Consistency Validation
Prevents invalid comparisons when baseline and candidate use different benchmark parameters:

**File modified:** `benchmark.py` (lines 195-233)

**What Gets Validated:**
1. **`fast_mode`** - Changes runs (50→25) and warmup (20→5)
2. **`rps_override`** - Changes request rate (affects P95 latency)
3. **`requests_override`** - Changes load per scenario (affects P95 latency)
4. **`include_sweep`** - Adds/removes sweep phase (different phases/metrics)

**Behavior:**
- **All match**: Silent, proceed with comparison ✓
- **Any mismatch**: Show detailed warning listing which parameters differ:
  ```
  [WARNING] Baseline and candidate have different parameters:
    • test mode (PRODUCTION → FAST MODE)
    • RPS override (baseline=None, candidate=8)
  [WARNING] Comparison metrics may not be valid
  ```

**Key Points:**
- Candidate still runs and produces comparison (user decides if valid)
- Multiple mismatches reported simultaneously if any exist
- Warning is clear but non-blocking (allows user override if intentional)

**Why This Matters:**
These parameters directly affect latency metrics. Comparing results from different parameter sets is meaningless for optimization decisions.

### 4. ✅ Expanded Test 8 → Test 8b with 4 Sub-Tests
**File modified:** `TEST_PLAN.md` (Test 8b section)

**Covers all 4 critical parameters:**
- Test 8b-1: Fast mode mismatch
- Test 8b-2: RPS override mismatch
- Test 8b-3: Requests override mismatch
- Test 8b-4: Sweep setting mismatch

Each sub-test shows exact command, expected warning format, and validation checklist.

## Files Updated
- ✅ `TEST_PLAN.md` - Expanded from 14 to 18 tests (Test 8b now has 4 sub-tests) + 2 bug checks = **20 total**
- ✅ `benchmark.py` - Comprehensive metadata validation (lines 195-233)
- ✅ `TEST_UPDATES_SUMMARY.md` - This file

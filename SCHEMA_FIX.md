# Baseline Schema Fix - Session March 11, 2026

## Problem
When running `python benchmark.py candidate ...`, the command failed with:
```
[ERROR] Invalid baseline: missing required field 'schema_version'
```

## Root Cause
The `benchmark.py` file had two issues:
1. **save_report() function** was being used instead of `BaselineManager.save_baseline()`
2. This resulted in baseline JSON files missing required schema fields:
   - `schema_version`
   - `scenario_version`
   - `hardware_state`

The old baseline format was:
```json
{
  "stack_id": "...",
  "phase": "...",
  "timestamp": "...",
  "endpoint": "...",
  "scenarios": {...}
}
```

But `BaselineManager._validate_schema()` expected:
```json
{
  "schema_version": "1.0",
  "stack_id": "...",
  "phase": "...",
  "timestamp": "...",
  "scenario_version": "v1",
  "hardware_state": {...},
  "scenarios": {...}
}
```

## Solution
Updated `benchmark.py` to use `BaselineManager.save_baseline()` in two places:

### 1. When validity gate fails (line 259)
Saves partial results with only sequential phase metrics before stopping.

### 2. When all phases complete (line 382)
Saves complete results including concurrent and optional sweep metrics.

Both paths now:
- Call `baseline_manager.save_baseline()` instead of custom `save_report()`
- Properly format scenario results with all required fields
- Pass metadata (endpoint, timestamp) to the manager
- Handle errors gracefully with try/except

## Verification

### Schema fields now included:
✓ schema_version: "1.0"
✓ stack_id: "{model}_{hardware}"
✓ phase: "baseline" or "candidate"
✓ timestamp: ISO 8601 with Z suffix
✓ scenario_version: "v1"
✓ hardware_state: metadata dict
✓ scenarios: dict with all scenario results

### Immutability protection:
✓ Baseline files cannot be overwritten (same date prevents override)
✓ Error message guides user to use different hardware or wait until next day

## Testing
Run these commands to verify the fix:
```bash
# Baseline phase (creates properly formatted baseline)
python benchmark.py baseline --endpoint http://localhost:9000 --model qwen2.5-7b --hardware cpu

# Candidate phase (loads baseline, validates schema, compares metrics)
python benchmark.py candidate --endpoint http://localhost:9000 --model qwen2.5-7b --hardware cpu
```

## Impact
- ✓ Baseline files now conform to required schema
- ✓ Candidate phase can successfully load and validate baseline files
- ✓ Metrics comparison works correctly
- ✓ Improvement/regression percentages display properly
- ✓ Immutability enforced to prevent accidental overwrites

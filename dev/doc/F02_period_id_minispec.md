# F02 Mini-Spec — Explicit `period_id` and 24-hour mapping (parser/config only)

Per `OpenDTA_Incremental_Development_Rules.md` §15. Branch:
`feature/time-period-contract`.

## Feature ID
F02

## Feature
Explicit integer `period_id` on demand periods + strict time-period parsing.
No DNL kernel change.

## Existing behavior (verified in code at 32a3bbf)

- `settings.yml` `demand_period:` entries carry `period` (label, e.g. `AM`) and
  `time_period` (string `"0700-0800"`, HHMM-HHMM). Parsed in
  `NetworkHandle::read_settings()` ([utils.cpp:1065](../../src/utils.cpp)).
- `DemandPeriod` ([demand.h:321](../../include/demand.h)) stores a sequential
  `uint8_t no` assigned in file order (`j++` at utils.cpp:1106) — the label
  never carries an explicit computational key.
- `DemandPeriod::setup_time()` ([elements.cpp:51](../../src/elements.cpp))
  parses `time_period`; **on any parse failure it silently swallows the
  exception and keeps defaults `start_time=420, dur=60` (07:00–08:00)** —
  a malformed period silently becomes a wrong period (defect F-7 evidence).
- `validate_demand_periods()` ([utils.cpp:104](../../src/utils.cpp)) sorts by
  start time and rejects overlap only. Periods are effectively half-open
  (`end > next_start` is the only failure), but this is nowhere documented.
- Internal time unit: minutes from midnight (`unsigned short`); outputs print
  the label via `get_period()`.

## Requested behavior (only this)

1. Each `demand_period` entry in `settings.yml` MAY carry `period_id: <int≥1>`.
   Stored on `DemandPeriod`, exposed by a getter. When absent, fall back to the
   current sequential numbering (order of appearance, starting at 1) so every
   existing dataset runs unchanged.
2. `validate_demand_periods()` additionally rejects duplicate `period_id`.
3. `setup_time()` failure becomes a **hard error** naming the offending
   `time_period` string, replacing the silent catch. (Behavior change only for
   inputs that are already malformed and silently mis-parsed today.)
4. Half-open convention `[start_time, end_time)` documented at the parse site
   comment. No change to the overlap check logic itself.

## Explicitly out of scope (later features / defects)
- `period_id` columns in output files (F07 owns output schema).
- Consuming gold `demand_period.csv` (the C++ engine still reads settings.yml;
  the CSV is the cross-tool contract consumed by gold tools until F05+).
- Integer-seconds time plumbing (defect F-8), >24:00 wrap times, contiguity
  requirement (legal gaps exist: a single AM period has no successor).

## Files to modify
| File | Change |
| --- | --- |
| `include/demand.h` | `DemandPeriod`: add `period_id` member + getter; extend the 5-arg constructor |
| `src/elements.cpp` | `setup_time()`: throw `std::runtime_error` with the bad string instead of silent catch |
| `src/utils.cpp` | `read_settings()`: read optional `period_id`, default sequential; `validate_demand_periods()`: duplicate-id check |

## Files that must NOT be modified
`src/simulation.cpp`, `src/ue.cpp`, all output functions in `utils.cpp`
(`output_*`), `include/supply.h`, `include/handles.h` simulation members,
CMakeLists.txt, any `data/` input.

## Data-contract change
Additive only: optional YAML key `demand_period[i].period_id` (integer ≥ 1,
unique). No field renamed, no unit changed, no output format touched.

## Mathematical requirement
- `period_id` values form an injective map period → ℤ≥1.
- Periods pairwise non-overlapping on half-open intervals:
  sorted by start, `end_i ≤ start_{i+1}`.
- Absent `period_id` ⇒ assigned id equals 1-based position after file order —
  deterministic and reproducible.

## Gold dataset
- Positive: `data/Two_Corridor` (unmodified, no period_id — exercises fallback)
  and a new fixture `dev/test/f02/settings_period_id.yml` (two periods with
  explicit ids) run through the engine.
- Negative: `dev/test/f02/settings_bad_time.yml` (`time_period: "07x0-0800"`)
  must terminate with the named error, and
  `dev/test/f02/settings_dup_id.yml` (duplicate `period_id: 1`) must terminate.

## Gate
G1 Schema Gate (id/type/mapping validation) + G10 Regression.

## Regression requirement
All F01 baselines byte-identical (valid inputs take the same code path;
per-baseline-README rule for `link_performance_dta.csv` volume==0 rows).
`python dev/test/gold/tools/check_gold.py` unaffected (161/161).

## Expected diff size
Small (~50–70 lines across 3 files).

## Risk
Low. No kernel component touched. The only behavior change for previously
"valid" runs is that silently mis-parsed `time_period` strings now fail loudly
— which is the point.

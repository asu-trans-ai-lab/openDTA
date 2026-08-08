# F03 Mini-Spec — Departure-time profile reading + G5 Time Loading validation

Per `OpenDTA_Incremental_Development_Rules.md` §15. Branch:
`feature/departure-profile`.

## Feature ID
F03

## Feature
Read `departure_profile.csv`, validate it (G5 rules), bind profiles to demand
periods via `settings.yml`. **Storage and validation only — nothing consumes
the profiles yet.** Vehicle generation keeps its current uniform behavior
until F04.

## Existing behavior (verified at b3e6842)
- No departure-profile input exists anywhere in the C++ engine.
- `setup_agents()` ([simulation.cpp:141](../../src/simulation.cpp)) creates
  `ceil(volume)` agents per column and spreads them uniformly
  (`i / volume * dp_dur`) — defects F-2/F-3. **Untouched by F03.**
- CSV reading uses the vendored MIOCSV reader (pattern: `read_links()` in
  utils.cpp).

## Requested behavior (only this)
1. Optional `settings.yml` block:
   ```yaml
   departure_time_profiles:
     source: departure_profile.csv     # default file name
   ```
   and per demand period an optional binding:
   ```yaml
   demand_period:
     - period: AM
       period_id: 1
       departure_profile: AM_PEAK      # profile_id in the CSV
   ```
2. CSV contract (long format, engine consumes these four columns, extra
   columns like `profile_source`/`weight_raw` are ignored):
   ```csv
   profile_id,period_id,departure_time,bin_width_sec,weight
   AM_PEAK,1,07:00:00,1200,0.25
   ```
   `period_id` in the CSV is accepted as `1` or `P1` (leading `P` stripped);
   canonical form is the integer, matching F02's `period_id`.
   `departure_time` is `HH:MM:SS` clock time.
3. G5 validation, per (profile_id, period_id), at load:
   - every `weight ≥ 0`, every `bin_width_sec > 0`;
   - every bin lies inside the bound period's half-open window:
     `start ≤ departure_time` and `departure_time + bin_width ≤ end`;
   - Σweights three-tier tolerance (consensus §5):
     `|Σ−1| ≤ 1e-4` → PASS; `≤ 2e-2` → normalize, print the factor to stderr
     (REPAIRED, never silent); otherwise → hard error naming profile and Σ.
4. A `demand_period` that names a `departure_profile` not present in the CSV
   (or a missing CSV when a binding exists) is a hard error. No bindings at
   all → engine behaves exactly as today (backward compatible).
5. Storage: new small `DepartureProfile` class (demand.h) holding sorted bins
   (minute offsets within the period + normalized weights); `NetworkHandle`
   gains a `profiles` container; `DemandPeriod` gains an optional profile
   reference. Exposed by getters for F04.

## Explicitly out of scope
- Consuming profiles in `setup_agents()` / vehicle generation (F04).
- scope_type hierarchy (od_pair/corridor fallback) — schema tolerates the
  column; V1 implements the period binding only (consensus: "schema
  extensible; implementation honest").
- `departure_profile_binding.csv` (gold's binding file stays a gold-tools
  contract until F04/F05).

## Files to modify
| File | Change |
| --- | --- |
| `include/demand.h` | new `DepartureProfile` class; `DemandPeriod`: optional profile name + pointer |
| `include/handles.h` | `NetworkHandle`: profile container + `read_departure_profiles()` declaration |
| `src/utils.cpp` | read the settings block + binding; `read_departure_profiles()` (MIOCSV) + G5 validation |
| `src/main.cpp` | call `read_departure_profiles()` after `read_network()` |

## Files that must NOT be modified
`src/simulation.cpp`, `src/ue.cpp`, `include/supply.h`, all `output_*`
functions, existing CSV readers' behavior.

## Data-contract change
Additive only: optional YAML keys (`departure_time_profiles`,
`demand_period[i].departure_profile`), optional input file
`departure_profile.csv`. Nothing renamed; absent inputs → behavior unchanged.

## Mathematical requirement
Σ_τ p_τ = 1 (within tolerance tiers) per bound profile; bins within
`[t_start, t_end)`; normalization factor recorded, never silent.

## Gold dataset
- Positive: Two_Corridor + 2-bin AM profile (0.4/0.6) — loads, prints nothing.
- Repaired: Σ = 0.999 profile — loads with recorded factor on stderr.
- Negative: Σ = 0.9 (hard fail); bin at 08:30 for a 07:00–08:00 period
  (hard fail); binding to a nonexistent profile_id (hard fail).
- Cross-check: gold `cases/G1_single_link_two_period/input/departure_profile.csv`
  (P1/P2 form) parses and passes G5 against G1's `demand_period.csv` windows
  (validated in the fixture by binding P1_STEP/P2_STEP to periods 1/2).

## Gate
G5 Time Loading Gate + G10 Regression.

## Regression requirement
All F01 baselines byte-identical (no baseline dataset has profiles → identical
code path); gold suite 161/161; F02 fixtures unchanged.

## Expected diff size
Medium (~150–200 lines, dominated by the CSV reader + validation).

## Risk
Low-medium. No kernel/simulation change; risk is confined to input parsing.

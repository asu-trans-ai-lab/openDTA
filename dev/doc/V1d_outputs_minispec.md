# V1-d Mini-Spec — required outputs: run_summary, link/queue time series, conservation

Per OPENDTA_V1_MVP_SPEC.md section 6 + build-order bullet V1-d.
Branch `feature/v1d-outputs` (stacked on V1-c).

## What is new
Four new artifacts. **No existing output file changes** — the frozen
baselines (link_performance_dta.csv, trajectories.csv, columns.csv)
stay byte-identical; the added columns live in the NEW link_time_series.csv
exactly as section 6 names it.

### 1. `run_summary.json`
```
run_mode, validation_eligible, used_default_mu, used_default_profile,
vehicles: {generated, entered, not_entered, exited, remaining,
           conservation_ok},
network:  {VMT, VHT, avg_speed_mph, P_max_minutes, P_max_link_id,
           v_T2_mph, queued_link_count, spillback_link_count},
runtime_seconds, all_gate_status: {the nine V1-b READYs}
```
**PT-6 N-accounting** (the spec's "currently unreported" gap) is the
identity `generated == not_entered + exited + remaining`, asserted and
stamped `conservation_ok`. `not_entered` counts vehicles that were
generated but never reached the network — no path, or a departure
interval past the simulation horizon; silently losing these is the
leak PT-6 names.

**Metric definitions (frozen here so later work cannot drift):**
- `VMT = sum_l CD_l(T) * length_l` — CD_l(T) is the count of vehicles
  that traversed link l.
- `VHT = sum_l sum_t occupancy_l(t) * dt` — the exact N-curve area
  (time in system), not a speed-derived estimate. When `remaining == 0`
  this must equal the sum of agent travel times; conservation_report
  asserts that cross-source identity.
- `P` (queue duration) per link = total minutes with queue > 0.
  `P_max_minutes` is the worst link's, with `P_max_link_id` naming it.
- `v_T2` = the MINIMUM speed inside the P_max link's longest congestion
  episode (QVDF's speed at the congestion peak). Reported for the link
  that owns P_max, so P and v_T2 always describe the same bottleneck.
- `peak_memory_mb` is deliberately ABSENT: a portable probe is a
  platform decision, not a physics one. Open item for Simon.

### 2. `link_time_series.csv` (per link per minute)
existing per-minute columns + `inflow`, `outflow` (CA/CD minute diffs),
`mu_vph`, `spillback_flag`.
- `mu_vph` = the REALIZED service capacity: the discretizer's integer
  outflow_cap summed over the minute's intervals, x60. Under V1-c this
  echoes link_supply.csv exactly on aligned windows (the gate asserts
  1800/600/3600 on sp01) — the user can verify the mu the engine used
  against the mu they supplied.
- `spillback_flag` = 1 when occupancy reaches the link's spatial
  capacity, using the SAME model-dependent occupancy the engine's own
  acceptance test uses (simulation.cpp merge/transfer gate), so the flag
  cannot disagree with the physics that produced it.

### 3. `queue_time_series.csv` (per congestion episode)
`link_id, episode_id, start_minute, end_minute, duration_minutes,
max_queue, v_T2_mph, total_delay_veh_min`. Contiguous minutes with
queue > 0. This is where P and v_T2 come from — a per-episode table
rather than a duplicate of the per-minute queue column.

### 4. `conservation_report.csv`
`check, scope, expected, actual, abs_diff, tolerance, status`:
1. PT-6 vehicle accounting identity (network);
2. VHT from link N-curves == sum of agent travel times (network, only
   when remaining == 0; otherwise SKIPPED with the reason stamped);
3. VMT recomputed per link from CD(T) x length vs the summary total;
4. CD monotone non-decreasing (per link);
5. CA(T) >= CD(T), i.e. non-negative terminal occupancy (per link).
Any FAIL is reported, not thrown — this is a diagnostic artifact; the
gate is what fails the build.

### 5. `gate_report.json` (tools side)
run_all_gates.py additionally emits the battery record as JSON
(gate name, class, status, duration) next to the existing .md record.

## Deferred with reason
`path_loading_summary.csv` (section 6) needs the path->agent grouping
that V1-e's Test 1 assertion `x_l = sum_k A_lk f_k` builds anyway;
writing it twice would fork the mapping. It lands in V1-e.

## Two defects this work surfaced (NOT fixed here — both move frozen files)

**D-1: `completes_trip()` reports every stranded vehicle as arrived.**
`Agent::initialize_intervals()` fills `dep_intvls` with `size_type::max()`,
and `completes_trip()` tests `front() > 0` — the sentinel passes. So the
`trip_completed` column in trajectories.csv reads `c` for vehicles that
never finished. This is precisely the PT-6 leak the spec names
("REMAINING — currently unreported"): the engine had no way to report
remaining because its completion predicate could not return false.
A second, subtler case sits behind the same accessor:
`increment_dep_interval()` schedules `arrival + waiting`, which can land
PAST the last simulated interval, so even a set value is not a completion
unless it falls inside the horizon.
V1-d therefore counts exits with the new `Agent::get_final_dep_interval()`
range-checked against the horizon, and leaves `completes_trip()` untouched
so trajectories.csv stays byte-identical. **Repairing it is its own
change** — it moves the trip_completed column and its baselines.

Visible consequence, worth stating plainly: **ST00 cannot ever land all 60
vehicles.** It departs one per minute across a 60-minute horizon with a
1-minute free-flow time and no buffer, so the last vehicle is still on the
link when the clock stops — 59 traverse, 1 remains, VMT 59 not 60. The
gate asserts that, because it is the truth about the fixture.

**D-2: `output_link_performance_dta()` stamps every link after the first
with the LAST demand period.** `dp_no` and `ub` are declared OUTSIDE the
link loop, so once the first link has walked the whole horizon `ub` sits at
the end and no later link ever advances a period. Demonstrated on
ST03_tandem_gold (4 periods, 2 links): link 1 correctly reports
P1A=30 / P1B=30 / P2=60 / CLEAR=60 minutes, while link 2 reports
CLEAR=180. `dp_no` also indexes the per-period free-flow travel time used
by `get_travel_time` / `get_speed` / `get_queue`, so this is not only a
label: on any network whose periods carry different per-link fftt, the
travel_time, speed and queue columns for every link after the first are
computed against the wrong period. On the current gold cases the periods
share an fftt, so the numbers happen to match (verified: 0 of 180 minutes
differ on ST03) and only the label is wrong — which is exactly why it has
gone unnoticed. link_time_series.csv resets `dp_no` per link and is
correct. **Fixing link_performance_dta.csv moves a frozen baseline** and so
is deliberately left to its own change.

## Gate (red-first) — tools/check_outputs.py (19th)
- ST00 free-flow (60 veh, 1 mi, 60 mph): generated == entered == 60,
  exited == 59, remaining == 1 (the horizon-edge vehicle, D-1 above),
  VMT == 59, VHT ~ 1.0 veh-h, avg speed at free flow, P == 0, no spillback.
- ST02a step gold (bottleneck): P > 0, v_T2 < free speed, the episode
  table non-empty, PT-6 identity holds.
- sp01_step_mu (V1-c): mu_vph column == 1800 / 600 / 3600 per window.
- Cross-file: the gate INDEPENDENTLY recomputes VMT and the N-accounting
  from link_performance_dta.csv and trajectories.csv and compares to
  run_summary.json — the summary must not be self-certifying.
- conservation_report.csv: every check PASS (or SKIPPED with reason).

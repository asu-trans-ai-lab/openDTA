# S2a/S2b Mini-Spec — Conserved integer vehicleization + 6-sec deterministic staggering

Per rules §15. Branch: `feature/vehicleization` → PR #5. **Touches the
protected kernel (`setup_agents()`) — second approved kernel change after
S0c. Justification: the analytical bank charges the +18 family and the F-2
ceil inflation to exactly these two lines; every gate that measures them is
already in place and red.**

## Feature IDs
S2a (ceil → conserved integers), S2b (minute batches → 6-sec staggering).
One branch, two commits, gated together.

## Existing behavior ([simulation.cpp:156](../../src/simulation.cpp))

```cpp
for (size_type i = 0, vol = std::ceil(col.get_volume()); i != vol; ++i)   // S2a target
{
    ...
    auto delta = static_cast<unsigned short>(i / col.get_volume() * dp_dur);  // S2b target
    auto intvl = this->cast_minute_to_interval(delta) + beg_intvl;
```

- **F-2 (S2a):** `ceil` per column inflates counts (ST02b loads 2604 of
  2602 — UE float noise × 30 columns).
- **Minute batching (S2b):** `delta` truncates to whole minutes → the whole
  minute's demand arrives in one burst (ST02a/ST04a/ST05 CD/Q offsets of
  ~18 veh; phantom T0; Qmax +18; delay +40 veh·h).

## Requested behavior

**S2a — largest-remainder integerization per ColumnVec.** For each
(OD, period, agent) column vector: target N = round(Σ column volumes);
apportion N across columns by floor + largest remainder (ties by column
order — deterministic, no RNG). Single integer-volume column ⇒ N = volume
exactly. Σ agents over the run == Σ round(cv volumes), always.

**S2b — departure realization at simulation-interval resolution.** Replace
the minute-truncated offset with direct interval placement, uniform over the
period:

```cpp
auto dp_intvls = <period duration in intervals>;                   // dur*60/res
auto intvl = beg_intvl + i * dp_intvls / n;                        // integer math,
                                                                   // deterministic
auto dep_time = dp_st + static_cast<double>(i) * dp_dur / n;       // minutes, for output
```

`i·dp_intvls/n` in integer arithmetic is the exact largest-remainder-uniform
staggering (300 veh / 300 intervals → 1 per interval; 1800/600 → 3 per
interval; ST00c's 3 veh / 10 intervals → intervals 0, 3, 6). `dep_time`
becomes fractional minutes (double member already).

Explicitly out of scope: profile-consuming vehicleization (next feature,
turns ST01's final_CA gate live); PCE; any queue/service logic.

## Files to modify
`src/simulation.cpp` — `setup_agents()` only (~10 lines).
Gate tooling: `tools/validate_case.py` (activate strict tolerances),
`tools/check_two_link.py` (`BATCH_TOL 35 → 2`),
`tools/check_agent_timestamps.py` + ST00c gold regeneration (below).

## Files that must NOT be modified
`run_simulation()` loop, `supply.h`, `ue.cpp`, all readers/outputs.

## ST00c gold regeneration (documented, not silent)

ST00c's per-agent gold (TT 1.0/1.1/1.2) **relied on the minute batch**
co-locating 3 vehicles in interval 0. Under S2b they stagger to intervals
0/3/6 with no queue (TT = 1.0 each) — the case would stop testing FIFO
ordering. Redesign: demand 30 veh in the 1-min period, capacity 600/h
(1 veh/interval): arrivals 3 per interval (0,0,0,1,1,1,…), service
1/interval ⇒ vehicle i: TA = i/3, TD = 10 + i (intervals), per-agent
TT = (10 + i − i/3) intervals, total delay Σ = hand-computable. The gate
stays agent-level and gains a genuine staggering assertion (arrival pattern
3/interval). Old gold retired with this justification in the case README.

## Acceptance gates (all pre-existing, currently red)

| Gate | Expected after S2a/b |
| --- | --- |
| ST02b conservation | N = 2602 **exact** (was 2604) |
| ST02a | CD/Q dev ≤ 2 veh; T0 = 32 ± 1; Qmax 600 ± 1%; delay 600 ± 1% — the +18 family **gone** |
| ST04a | Qmax 40 ± 1; same family gone |
| ST05a/b | `BATCH_TOL` tightened to 2 and still green (oracle already models the intended 6-sec contract; CA dev stays 0) |
| ST00c (regenerated) | per-agent TA/TD exact |
| ST00 | 9/9 unchanged (60 veh / 600 intervals → 1 per 10 intervals; free flow) |
| Baselines | UE byte-identical; sim trajectories + dta legitimately change (loading realization corrected) → re-freeze with justification, determinism 3× |
| gold suite | 161/161 unaffected |

## Mathematical requirement
Conservation: Σ agents = Σ round(V_cv) exactly. Staggering: per period,
|A_engine(t) − A_uniform(t)| ≤ 1 vehicle at every interval (largest-remainder
bound). Determinism: byte-identical reruns.

## Classical cross-validation (DTALite-main 2024, added after review)

`consensus_datasets/DTALite-main` confirms both directions from the donor
codebase itself:

- **S2a:** 2024 classical uses `VehicleSize = (path_volume + 0.5)` — ROUND,
  not ceil (simulation.cpp:407). openDTA's `ceil` was a regression, not
  classical behavior. Our largest-remainder is strictly stronger (conserves
  the ColumnVec sum; per-column rounding can drift ±1 per column).
- **S2b:** classical departure times are CONTINUOUS fractional minutes via
  deterministic quantile sampling — `r = v/N` for N ≥ 10, inverse-CDF walk
  with within-slot linear interpolation (`DTA.h get_deparure_time_in_min`),
  plus a deterministic 3-cycle 0.05-min anti-synchronization dither
  (simulation.cpp:447-449). Minute truncation never existed in classical.
  Two deliberate deviations, with reasons: (1) the 3-cycle dither is NOT
  ported — interval-uniform placement already de-synchronizes and keeps the
  oracle exact; (2) classical draws WELL-RNG quantiles when N < 10 — we stay
  deterministic at every N (gold requirement; seeded randomness belongs to
  S4 Mode B).
- **S2c preview (next feature):** classical `compute_cumulative_profile`
  normalizes ratios within the [start, end] window — independently
  confirming the F03b clip-and-renormalize conditional — and the
  quantile → inverse-CDF → within-bin interpolation chain is exactly the
  profile-consuming vehicleization our S2c will implement over the F03c
  conditional bins.

## Expected diff size / risk
Kernel diff ~10 lines; tooling ~40. Risk: medium (first change to loading
since F01) — mitigated by the widest gate coverage any step has had:
five analytical cases + two-link pair + micro case + baselines, all
pre-armed.

# OpenDTA Gold Dataset v2 — `GOLD-DTA-GATES-v2`

Canonical gold datasets for the ASU DTA-Lite / OpenDTA tandem point-queue DNL.
v2 restructures the single composite case of v1 into the **sequential, blocking
gate discipline**: each gate is the last point at which the answer is known
independently of the model, and every gate carries hand-computable (or
machine-frozen) numeric assertions in `assertions.json`.

Gates are sequential. If an engine fails G1, do not debug it on G3.

## Cases

| Case | Gate | What it proves | Key frozen numbers |
|---|---|---|---|
| `cases/G1_single_link_two_period` | Gate 1 / Test 01b | Pure point-queue integrator, μ 1000→1200 at 08:00 | Q(08:00)=266.667 continuous (**I3**), peak 333.333 @08:20 (not a period midpoint), clears exactly 09:00, CA=CD=2133.333; delay drops 16.00→13.33 min discontinuously — **correct physics, not a bug** |
| `cases/G2_two_link_tandem` | Gate 2 / Test 02 | Tandem propagation, CD₁(t)==CQ₂(t+τ⁰₂) to 1e-9 | Q₁ 150 @07:31 clears 07:46; Q₂ 225 @07:48 clears 08:33 — peaks **17 min apart**, clearances **47 min apart**. Distinct onsets are the mechanism behind "why do all links congest simultaneously" |
| `cases/G2b_tandem_period_boundary` | Gate 2b | μ₂ steps 900→750 **mid-queue**; continuity AND conservation asserted **simultaneously** (a reset bug breaks both; separate tests can let both pass) | Q₂(07:45)=210 continuous, slope flips to +450/h, peak 232.5, clears 08:42:36; delay jumps **up** 14.0→16.8 min |
| `cases/G3_network_multiclass` | Gate 3 / Test 03 | v1 network (2 routes, shared L5 bottleneck, auto/truck PCE, period allowed-uses) upgraded to the full contract **plus the vehicle layer**: largest-remainder vehicleization, FIFO vehicle DNL, `vehicle_link_trajectory` audit trail, reconciliation | 2000 vehicles exact per column (no ceil inflation); exit(i)==entry(i+1) every vehicle; 55 trajectory rows with `demand_period ≠ supply_period` — living **I4** evidence; fluid↔vehicle max deviation 3.24 PCE (discretization, bound 5.0) |
| `cases/G4_corridor_ramp` | Gate 4 | Corridor as a first-class object **with declared ramps** | CA_{i+1}=CD_i+R^on−R^off residual ≤1e-9 per junction per interval; M3 queue spans **both** period boundaries; onset dispersion across links |

## Tools (all deterministic, RNG-free — invariant I9)

```bash
python tools/gold_solver.py  cases/<case>    # fluid gold: link×time state, episodes,
                                             # period summaries, boundary audit,
                                             # corridor performance + conservation
python tools/vehicle_gold.py cases/<case>    # vehicle gold: VehiclePool, vehicle-link
                                             # trajectory, trip table, reconciliation
python tools/check_gold.py                   # contract audit + every frozen assertion,
                                             # all cases; exit 0 == all PASS
```

Reruns are byte-identical. Departure allocation is largest-remainder
apportionment (never `ceil`, never RNG); fractional capacity is a
work-conserving deterministic accumulator, never a stochastic draw.

## Recorded semantics (so the numbers can be hand-checked)

* State rows equal **continuous-time values at t** (recorded before the tick).
* Periods are half-open `[s,e)`; the row at a boundary reports the new period's
  μ; the boundary audit reports the t⁻ and t⁺ delays from the same continuous Q.
* Simulation resolution and record resolution are **independent** (I11): G3/G4
  simulate at 6 s so fftt values of 66 s and 72 s land exactly on ticks; state
  is recorded on the minute grid, deliverables on the 5-minute grid.
* `CA` counts arrivals at the link **entrance** (== upstream `CD` at 1:1 nodes);
  `CQ` counts arrivals at the **exit queue** (`CA` shifted by fftt) — the tandem
  identity is asserted on `CQ`.
* `exit_time = t + TT(t)` is stored, not derived (I10). μ per row makes the
  physics auditable in the file itself.
* `link_time_performance.csv` carries `experienced_tt_sec` (flow-weighted, what
  vehicles departing the link in that bin actually experienced) alongside
  `instantaneous_travel_time_sec`; `corridor_time_performance_gold.csv` carries
  the experienced corridor TT (composed through `E_a`) **and** the naive
  instantaneous sum, clearly labelled — compare the experienced one to INRIX.

## Contract deltas vs v1

`link_period.csv` now carries `capacity_unit`, `reference_tt_sec`,
`capacity_ratio`, and both provenance columns; `departure_profile_binding.csv`
declares the profile fallback hierarchy (route → OD → corridor → class →
period → uniform); ramps carry `role`/`merge_node_id`/`diverge_node_id` in
`corridor.csv` and are **mandatory** for the conservation identity; all files
are LF-terminated; every gold table is long format (one entity × one interval
× one row).

## Negative cases (`cases/G3_network_multiclass/negative_cases/`)

* `columns_illegal_truck.csv` — static infeasibility, must fail at load.
* `vehicle_truck_boundary_entry.csv` — the **I4 trap**: a truck departing
  07:59:30 on R1 is legal in its demand period but reaches L2 at 08:00:36,
  where the P2 supply period is auto-only. Verified against the reference
  loader: rejected at entry with `route_infeasible_allowed_uses`,
  `blocked_link=L2`, after legally completing L1. An engine that checks
  allowed-uses only at path generation loads it silently — that is the bug.

## How to test an engine

1. Load `cases/G1_.../input/` without changing the contract. Compare to
   `gold_expected/` and run the assertions. Only then proceed to G2, G2b, G3, G4.
2. Do **not** tune OD, μ, or profiles to improve a match — a mismatch here is
   an engine/interface error by construction.
3. G3's vehicle gold defines the audit-trail format
   (`vehicle_link_trajectory`): both period ids on every row, no deduplication.

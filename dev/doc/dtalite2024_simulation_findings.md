# DTALite-main (2024) Simulation Core — Findings for OpenDTA

Source: `consensus_datasets/DTALite-main` (2024 modernized DTALite:
yaml settings, Tucson planning network, FOCUSING use-case docs).
Complements `F03d_determinism_rng_audit.md` (legacy RNG/service) and the
M-1 resolution (Zhou & Taylor 2014 §3.7 node models). Findings numbered
M-14…M-20, continuing the notes series.

## M-14 — Classical vehicleization is ROUND + continuous-time quantile (S2 cross-validation)

- `VehicleSize = (path_volume + 0.5)` (simulation.cpp:407): **round, not
  ceil**. openDTA's `ceil` (defect F-2) was a regression against classical.
- Departure times: deterministic quantile `r = v/N` (N ≥ 10) → inverse-CDF
  walk over the cumulative profile → **within-slot linear interpolation to
  continuous fractional minutes** (`DTA.h::get_deparure_time_in_min`).
  Minute truncation never existed in classical — openDTA's integer-minute
  batching (the +18 family) is also a regression. S2a/S2b restore classical
  fidelity; deviations (no 3-cycle dither, deterministic at every N) are
  documented in the S2ab mini-spec.
- Small-sample rule: N < 10 draws the quantile from WELL512a (seed chain in
  `m_RandomSeed{101}`) — classical injects randomness for tiny volumes. We
  stay deterministic (gold requirement).

## M-15 — `compute_cumulative_profile` independently confirms the F03b conditional

Classical normalizes profile ratios **within the [start_slot, end_slot]
window** before building the CDF — precisely the clip-and-renormalize
conditional distribution frozen in F03b Layer 4. The time contract now has
three independent confirmations: the F03b design review, the TRANSIMS audit,
and the classical implementation itself.

## M-16 — S2c specification found (profile-consuming vehicleization)

The full classical chain for the NEXT feature after S2a/b:
`quantile v/N → inverse CDF over conditional profile → within-bin linear
interpolation → continuous departure minute → simulation interval`.
Implement over the F03c conditional bins; ST01's `final_CA` gate goes live;
the time-contract equivalence gate (period-pieces ≡ profile representation)
becomes testable.

## M-17 — μ(t) mechanism for F07: sparse per-second capacity override

`m_link_pedefined_capacity_map_in_sec` — a sparse time-indexed map that
zeroes `m_LinkOutFlowCapacity[l][t]` during closures (work zone / incident /
signal red), plus a separate `discharge_rate_after_loading`. Classical
validates the per-interval capacity ARRAY as the runtime representation —
openDTA already has `outflow_cap[t]`; F07 = fill it from the
`link_time_profile.csv` contract through the S4 ServiceDiscretizer instead
of a constant. (Blocked-link `RT_waiting_time = 99` is a rerouting signal —
Ring 3, do not port.)

## M-18 — Ring-2 per-mode behavioral parameters exist in classical

Per mode: `time_headway_in_sec` (feeds the reaction-time release headway
`time_to_be_released`) and `desired_speed_ratio` →
`desired_free_travel_time_ratio` (per-class FFTT scaling). Map to openDTA's
`AgentType` (ffs / use_link_ffs) at F06; the headway becomes the capacity-
per-mode refinement. And for the third codebase in a row:
`p_agent->PCE_unit_size = 1` hard-coded with the real conversion commented
out — PCE remains rebuild-with-own-gold, never "already validated".

## M-19 — The regional release output family (F08 scope, from output.h)

Classical emits 21 output files; the release-relevant set beyond openDTA's
current four:

| Output | Release relevance |
| --- | --- |
| `link_performance_summary.csv`, `td_link_performance.csv` | period + time-dependent link reporting |
| `od_performance_summary.csv` | OD travel-time/distance skims — MPO deliverable |
| `route_assignment.csv` | path flows (TAPLite round-trip check) |
| `system_performance_summary.csv` | network VMT/VHT/delay/throughput |
| `district_performance.csv`, `subarea_link_performance.csv` | district/subarea aggregation — MPO reporting granularity |
| `dynamic_link_waiting_time_profile.csv` | the corridor waiting-profile layer (F08 heatmaps) |
| `internal_model_link/node.csv`, `internal_zone_mapping.csv` | internal-vs-external ID audit — the consensus "stable external IDs" rule made inspectable |
| `trajectory.csv`, `agent.csv` | agent layer (ours is already stronger post-S0d) |

F08's mini-spec should enumerate which of these the regional deployment actually needs
(proposal: od_performance_summary, system_performance_summary, district +
subarea, td_link_performance) rather than porting all 21.

## M-20 — Ready-made benchmark assets in the same package

- `data/02_Sioux_Falls/standard_solution_link_performance_comparison.xlsx`
  — a UE standard solution: a drop-in L1-style gold for the assignment side.
- `data/05_Tucson_planning_network` — planning-scale (G9 scale-up
  rehearsal between Chicago Sketch and the regional network).
- `data/04_ODME_node_link_demand` — minimal ODME fixture for the Phase-2
  observation-layer work; `src/ODME.h` (15 KB) is a compact path-flow
  gradient ODME matching paper §4 — portable later as an application-layer
  module per the boundary rule (never into the DNL core).
- `data/FOCUSING_use-cases-*.docx/xlsx` — use-case master list; mine for
  regional acceptance scenarios before the F08/F07 mini-specs.

## Sequence impact

No reordering needed. S2a/b (cross-validated) → S2c (M-16 spec) → S3/S4 →
S5a-d → S6 → F05 (Daganzo-mid merge per M-1) → F06 (M-18) → F07 (M-17) →
F08 (M-19 scope) → P01-03. M-20 assets slot into gold/benchmark work as
they become relevant.

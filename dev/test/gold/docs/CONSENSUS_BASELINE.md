# OpenDTA Consensus Baseline — Data Contract, Gold Datasets, Gates

Discussion baseline for the OpenDTA / ASU DTA-Lite kernel work (Simon ↔ Peiheng).
This reconciles the proposed "Gold Dataset + Data Contract + 10 Gates +
Time-Dependent DNL" plan with the already-built and verified
`OpenDTA_Gold_Dataset_v2` (5 cases, 161 frozen numeric assertions, all passing,
byte-identical across processes). Nothing here is aspirational: every gate row
below points at a check that runs today.

## 1. The spine (agreed, unchanged)

OD demand → x_p (column) → p_τ (departure profile) → λ_a(t) → [λ_a(t), μ_a(t)]
→ Q_a(t) → D_a(t) → {v,s,q}_{a,t} — ending in the link × time × metric tensor.
v2 implements exactly this spine at two resolutions: fluid (`gold_solver.py`,
Newell cumulative-curve semantics) and vehicle (`vehicle_gold.py`, FIFO with a
full `vehicle_link_trajectory` audit trail). The single-link Gold Test asserts
the cumulative curves A(t), D(t), Q(t) = A − D directly — G1's
Q(08:00)=266.667, peak 333.333@08:20, clearance at exactly 09:00 are frozen
values, not "the program finished".

## 2. Proposed 10 gates ↔ what already runs

| Proposed gate | Status in v2 | Where |
|---|---|---|
| G1 Schema | ✅ running | `check_gold.py` layer A0/G0: required columns, PKs, period grid half-open & contiguous |
| G2 Network | ✅ running | route continuity + corridor mainline continuity checks |
| G3 Static physics | ✅ running | μ>0, fftt≥0, `capacity_unit` declared per row, provenance columns present |
| G4 Demand conservation | ✅ running | demand↔column conservation to 1e-9, per (OD, period, class) |
| G5 Time loading | ✅ running — and it already caught a real bug | profile Σ=1 check; period→clock mapping; **fails on the repo's actual Chicago Sketch profiles** (§5) |
| G6 Vehicle generation | ✅ running | largest-remainder apportionment, Σ_t N == round(V_p) exact, no ceil, no RNG |
| G7 Single-link physics | ✅ frozen case | `cases/G1_single_link_two_period` (μ step at boundary; delay discontinuity asserted as correct physics) |
| G8 Tandem / corridor | ✅ frozen cases | `cases/G2_two_link_tandem` (CD₁==CQ₂ to 1e-9), `G2b` (μ step mid-queue), `G4_corridor_ramp` (CA₁₊ᵢ=CDᵢ+R^on−R^off ≤1e-9) |
| G9 Network DNL | ✅ frozen case | `cases/G3_network_multiclass` (2 routes, shared bottleneck, PCE, period allowed-uses, 2000 vehicles) — Chicago Sketch becomes the scale-up target, not the first network test |
| G10 Regression | ✅ running | 161 frozen assertions + cross-hash-seed byte-identical reruns |
| (proposed §15) Sensitivity | ✅ new tool | `tools/sensitivity_gate.py`: 0.5/0.8/1.0/1.2/1.5×D, monotone delay / peak queue / congested duration / throughput; overload measured via `leftover_pce`, not fatal |

Recommendation: keep the sequential-blocking discipline — an engine that fails
the single-link case is not debugged on Chicago Sketch.

## 3. Contract reconciliation (the only genuine deltas)

| Proposal | v2 today | Resolution |
|---|---|---|
| `agent_type` | `vehicle_class_id` | Adopt **`agent_type`** as canonical (DTALite lineage); `vehicle_class_id` accepted as read-time alias for one release |
| `period_id` numeric + `demand_period` label | `period_id` string (P1/P2) doing both jobs | Adopt the split: integer `period_id` computational key, `demand_period` human label, times only in `demand_period.csv`/`settings.yml`. **AM/PM never implies clock time.** |
| `link_time_profile.csv` (15-min μ, `profile_type` enum) | `link_period.csv` (period-piecewise-constant μ) | Both, layered: `link.csv` holds static reference capacity C_a; `link_period.csv` holds the period contract (what the gold gates consume); `link_time_profile.csv` optionally refines μ within a period, `discharge_rate` the only type V1 truly consumes. Fallback chain: profile → period → C_a. **Schema extensible; implementation honest.** |
| `capacity` vs `discharge_rate` as separate concepts | Already separate (`capacity_pce_per_hour` = μ in the period table; `capacity_unit` declared) | Rename in docs: link.csv `capacity` = C_a nominal; period/profile value = μ_a(t). No silent conflation |
| `vehicle_loading.csv` intermediate | `vehicle_gold.csv` + trajectory files | Same object. Align columns to the proposal (`vehicle_id, agent_type, period_id, departure_time, o_zone_id, d_zone_id, path_id`) with `route_id`→`path_id` mapping. CSV is the contract, pickle is cache — never the reverse |
| `settings.yml` holds interpretation, CSV holds values | v2 uses per-case `config.json` + CSVs | Agreed principle; adopt settings.yml at repo level. Departure profile *bindings* (which profile applies where) in config; weights always in CSV |
| Profile scope hierarchy OD > agent > period default > uniform | `departure_profile_binding.csv` with route/period scopes + uniform fallback | Same idea; add `scope_type ∈ {global, agent_type, od_pair, corridor}` to the binding file. V1 lookup exactly the proposed priority |
| Deterministic capacity only | Hard invariant (I9): no RNG anywhere, byte-identical reruns proven under different PYTHONHASHSEED | Agreed. `capacity_model: deterministic` in settings.yml; stochastic mode is post-baseline |
| No dynamic OD / 5-min column updating / en-route rerouting | Not implemented; interfaces don't preclude it | Agreed scope freeze |

## 4. Two additions the proposal should absorb from v2

1. **The vehicle layer is part of the contract, not an implementation detail.**
   `vehicle_link_trajectory` rows carry BOTH `demand_period_id` and
   `supply_period_id`; the rows where they differ (55 in G3, 617 in G4) are the
   living proof that supply is resolved by arrival clock time. The dynamic
   negative case (truck departing 07:59:30, statically legal, rejected at L2
   entry at 08:00:36 with `route_infeasible_allowed_uses`) must stay in the
   suite — an engine that checks allowed-uses only at path generation passes
   every static test and is still wrong.
2. **Boundary physics is asserted, not narrated.** Queue continuity across
   period boundaries (I3) and the *correct* delay discontinuities
   (16.00→13.33 down at a μ increase; 14.0→16.8 up at a mid-queue μ decrease)
   are frozen numbers with a physically-bounded reset detector. G2b asserts
   continuity and CD→CQ conservation **simultaneously** because a reset bug
   breaks both while separate tests can let both pass.

## 5. Finding: the repo's Chicago Sketch profiles fail the Time Loading Gate today

Audit of `data/Chicago_Sketch/settings.yml` departure profiles
(`reports/chicago/profile_audit.csv`):

| profile | bins | Σ raw | gap to 1 |
|---|---|---|---|
| HBW_SOV_PA | 93 (3 missing: 4h15–4h45) | 0.98948 | **+0.01052** |
| HBW_SOV_AP | 93 | 0.99927 | +0.00073 |
| HBO_SOV_AP | 93 | 0.99816 | +0.00184 |
| HBO_SOV_PA | 93 | 0.99724 | +0.00276 |
| NHB_SOV_AP | 93 | 0.99916 | +0.00084 |
| NHB_SOV_PA | 93 | 0.99916 | +0.00084 (byte-copy of AP — likely placeholder) |
| Trucks | 93 | 0.99958 | +0.00042 |

Consequences without the gate: ~1% of HBW_SOV_PA demand silently vanishes at
loading, the missing 4h15–4h45 bins make period→24h mapping ill-defined for
any period touching 4–5 AM, and the 5:00→28:00 wrap must be an explicit
convention (v2 already uses the monotone >24h clock, e.g. 25:30:00).

`tools/profile_convert.py` converts the wide format to the long contract with
an explicit, reversible repair: raw weight and normalized weight both stored,
normalization factor per profile in the audit file — never a silent fix.
Proposed gate tolerance: |Σ−1| ≤ 1e-4 PASS; ≤ 2e-2 REPAIRED-with-warning
(factor recorded); beyond that FAIL.

## 6. Suggested repo layout mapping

The proposed `OpenDTA-Gold/` layout maps 1:1 onto v2's
`cases/<case>/{input,gold_expected,assertions.json}` plus shared
`tools/` and `schema/`. Suggested adoption path:
`feature/gold-dataset-v2` → `asu-dta-lite`; `tests/` become thin pytest
wrappers around `check_gold.py` per case so CI reads the same
`assertions.json` the humans do; `GOLD_TEST_MANIFEST.yml` is generated from
`dataset_manifest.json` (sha256 per file already included).

## 7. One-line agreements to open the Peiheng discussion

1. OpenDTA first needs a reproducible time-dependent DNL contract, not more
   assignment features.
2. Gold cases are frozen and sequential-blocking; every kernel change reruns
   them; a mismatch is an engine/interface error by construction — inputs are
   never tuned to fit.
3. period_id / demand_period / agent_type / profile → 24h-clock mapping are
   explicit and machine-checked (and the Chicago audit shows why).
4. The column is never loaded directly: column → profile → vehicle_loading
   (CSV contract, pickle cache) → DNL, every stage inspectable.
5. C_a stays static in link.csv; μ_a(t) comes from the period table, optionally
   refined by link_time_profile.csv; deterministic fallback μ=C_a.
6. Link×time outputs are standard, and corridor space–time speed/queue
   heatmaps (plus the conservation table with declared ramps) are baseline
   outputs, not features.
7. No stochastic capacity, no ODME, no 5-minute column evolution until the
   deterministic gates are stable in CI.

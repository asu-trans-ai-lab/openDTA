# F03c Mini-Spec — Migrate the engine reader to the frozen F03b time contract

Per rules §15. Branch: `feature/time-contract-reader`. **Still no
`setup_agents()` / `simulation.cpp` / vehicle-generation changes — F04 stays
blocked until this lands and its audit output is re-reviewed.**

## Feature ID
F03c

## Feature
Replace the transitional F03 profile contract in the C++ reader with the
approved four-layer contract: 24h profile library + binding table +
clip-and-renormalize conditionals + the official G5 Time Contract Audit
printed at load.

## Existing behavior (at d8af353)
- `departure_profile.csv` rows must carry `period_id`; weights inside each
  period must sum to 1 (three-tier tolerance applied per window).
- Binding is a `departure_profile:` key inside each `demand_period` settings
  entry (transitional; F03 was never released outside asu-dta-lite).
- All demand periods are implicitly active.

## Requested behavior
1. **Layer 2 (library):** `departure_profile.csv` needs only
   `profile_id, departure_time, bin_width_sec, weight`. A `period_id` column,
   if present, is ignored with a one-line notice (transitional files keep
   parsing). The three-tier |Σ−1| tolerance (1e-4 / 2e-2 / fail) now applies
   to the **full-day sum per profile_id** — never per window.
2. **Layer 3 (binding):** new settings block replaces the per-period key:
   ```yaml
   departure_profile_binding:
     - period_id: 1        # or P1
       agent_type: auto    # optional; absent = all agent types of the period
       profile_id: HBW_SOV_PA
   ```
   Lookup fallback: (period, agent_type) → (period, any) → unbound (uniform,
   i.e., pre-F03 behavior). The old `demand_period[i].departure_profile` key
   becomes a hard error naming the new block (asu-dta-lite internal; no
   released dataset uses it — fixtures are migrated in this feature).
3. **Layer 1 (active switch):** optional `active: true|false` per
   `demand_period` entry (default true). Inactive periods stay in the
   registry (validated, printed in the audit) but their demand files are not
   loaded and they produce no columns/agents.
4. **Layer 4 (conditionals):** for each binding, clip the 24h profile to the
   period's half-open window by folded bin start time, require
   `S_r ≥ 1e-3` (hard error below), renormalize, store the conditional bins
   on `DepartureProfile` (per binding), and keep the normalization factor.
5. **G5 audit (official):** at load, print exactly the approved audit block
   per period — window, active flag, per-binding S_r, conditional sum,
   demand, allocated demand, earliest/latest bin — plus per-profile full-day
   sum and uncovered mass. This output is the G5 gate record.

## Files to modify
`include/demand.h` (DepartureProfile: conditional bins + S_r + binding key),
`include/handles.h` (binding container), `src/utils.cpp` (settings block,
library reader, conditional computation, audit print), `dev/test/f03/*`
(fixtures re-expressed against the new contract). Nothing else.

## Files that must NOT be modified
`src/simulation.cpp`, `src/ue.cpp` (except: skipping demand files for
inactive periods happens in `read_demands()` in utils.cpp, not in ue.cpp),
`include/supply.h`, all `output_*` functions, `dev/test/gold/**`.

## Data-contract change
- `departure_profile.csv`: `period_id` no longer required (ignored).
- settings.yml: new `departure_profile_binding` block; new optional
  `demand_period[i].active`; removal of transitional
  `demand_period[i].departure_profile` (hard error with migration message).

## Mathematical requirement
S_r = Σ_{k∈W_r} p_k; p̃ = p_k/S_r with Σ p̃ = 1 by construction;
Σ_k D_r·p̃_k = D_r; full-day Σ_k p_k = 1 within tolerance; S_r ≥ 1e-3;
uncovered mass reported.

## Gold dataset / fixtures
- `f03/pos|repaired|bad_sum` re-expressed: 24h two-bin profiles, full-day
  sums 1.0 / 0.999 / 0.9.
- `f03/bad_window` becomes `f03/low_mass`: profile with S_r < 1e-3 in the
  bound window → hard error (window containment is no longer an error — mass
  outside the window is simply clipped; the audit reports it).
- `f03/transims` becomes the **four-period audit fixture**: AM/MD/PM/NT
  registry, car/truck bindings, TRANSIMS library — output must reproduce the
  approved audit numbers (S_r 0.738655 / 0.139320 / 0.305659 / 0.445500 /
  0.682813 / 0.301650 / 0.100012 / 0.108340).
- `f03/dangling` unchanged in spirit (binding to a missing profile_id fails).
- `f03/g1_cross` re-expressed: G1 profiles as 24h library + bindings.
- New `f03/inactive`: P2 inactive → no demand loaded for it, audit still
  prints its registry row.

## Gate
G5 (official audit) + G10 Regression.

## Regression requirement
All F01 baselines byte-identical (no baseline dataset uses profiles or
`active`); gold 161/161; F02 fixtures unchanged.

## Expected diff size
Medium (~250 lines, mostly utils.cpp reader + audit + fixture rework).

## Risk
Low-medium. Parsing/validation layer only. The one behavior change beyond
profiles is `active: false` demand skipping — new opt-in field, absent in all
existing datasets.

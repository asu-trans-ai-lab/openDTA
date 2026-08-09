# S2c Mini-Spec — Profile-consuming vehicleization (quantile inverse-CDF)

Per rules §15. Branch: `feature/profile-vehicleization` → PR #6. Third
approved kernel touch (continues the S2 family in `setup_agents()`).
Authoritative algorithm: finding M-16 (`dtalite2024_simulation_findings.md`)
— classical DTALite's `get_deparure_time_in_min`: quantile → inverse CDF →
within-bin linear interpolation → continuous departure time.

## Existing behavior (at 81f827c)
F03c loads conditional distributions (`dep_profiles`: per binding, folded
bin starts/widths/weights summing to 1). S1 projects them to
`departure_bin_demand.csv`. `setup_agents()` ignores them entirely — every
period loads uniformly (S2b staggering).

## Requested behavior
For each (period, agent) **with a bound profile**, vehicle i of n departs at
the profile's inverse CDF:

```
r          = i / n                       (deterministic at every n — frozen
                                          deviation from classical's RNG
                                          small-sample rule)
find bin s :  F(s-1) <= r < F(s)
offset_min = bin_start(s) + (r - F(s-1)) / w(s) * bin_width(s) - period_start
intvl      = beg_intvl + floor(offset_min * intervals_per_min)
dep_time   = period_start + offset_min
```

Unbound (period, agent) → S2b uniform staggering, **byte-identical** to
today. Largest-remainder counts (S2a) unchanged — the profile shapes timing
only, never counts.

## Files to modify
`src/simulation.cpp` `setup_agents()` (~35 lines: binding lookup + CDF
sample). No header/reader/output changes.

## Gates (tools/check_profile_loading.py, RED before / GREEN after)
1. **ST01 goes live** (case gains `simulation: enable`): D = 1000 ×
   AM_PEAK 0.4/0.6 → CA at the 30-min midpoint = 400 ± 1, final CA = 1000
   exact; per-minute CA matches 1000·F(t) ≤ 1 veh.
2. **Time-contract equivalence gate** (new case `ST01b_equivalence_profile`):
   the ST02a λ(t) expressed as ONE period (07:00–09:30, D = 2700) + a 3-bin
   profile (300/1800/600 over 30/60/60 min) must reproduce the
   period-pieces representation: engine CA vs the ST02a expected A_entry
   ≤ 1 veh at every minute — Representation A ≡ Representation B.
3. Regression: unbound datasets byte-identical (Two_Corridor baselines,
   ST02 bank, ST05, ST00/ST00c); gold 161/161; S1/bin file unchanged.

## Risk
Low-medium: additive branch in `setup_agents()`; unbound path untouched.

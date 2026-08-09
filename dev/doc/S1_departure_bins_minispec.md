# S1 Mini-Spec — Conditional profile → departure-bin demand (no vehicles)

Per rules §15. Branch: `feature/departure-bins` → PR #3 (base `asu-dta-lite`).
Pure arithmetic + audit output on already-loaded objects. **No simulation
change; no vehicle is generated; `setup_agents()` untouched.**

## Feature ID
S1 (F04a in the migration strategy)

## Existing behavior (at ea0e527)
F03c loads and validates conditional departure distributions
(`NetworkHandle::dep_profiles`, one per binding, weights sum to 1) and the
loaded demand per DemandPeriod (`demand_totals`). Nothing consumes either:
vehicle generation still ignores profiles entirely (S2's job).

## Requested behavior (only this)
When at least one profile binding exists, after demand loading emit

```
departure_bin_demand.csv
period_id, agent_type, profile_id, bin_start_clock, bin_width_sec,
conditional_weight, demand
```

one row per conditional bin, where `demand = D_(period,agent) × weight`:

```
D_k = D · p̃_k          Σ_k D_k = D   (exactly)
```

- `D_(period,agent)` sums `demand_totals` over the DemandPeriod rows matching
  the binding (same matching rule the G5 audit already uses);
- bins/weights are taken verbatim from the stored `DepartureProfile`
  conditionals — recomputing nothing keeps this a pure projection of the G5
  audit onto rows;
- unbound periods/agents produce no rows (they stay on the legacy uniform
  path until S2);
- no bindings anywhere → file not written, behavior byte-identical to today.

This table is the exact input contract S2's vehicleization will consume
(largest remainder over these `demand` values).

## Files to modify
| File | Change |
| --- | --- |
| `include/handles.h` | declaration + `m_dep_bin_filename = "departure_bin_demand.csv"` |
| `src/utils.cpp` | `output_departure_bin_demand()` (~40 lines, MIOCSV writer) |
| `src/main.cpp` | one call after the demand-load block, guarded by `enables_output()` |

## Files that must NOT be modified
`src/simulation.cpp`, `src/ue.cpp`, `include/supply.h`, `include/demand.h`,
all existing `output_*` functions.

## Mathematical requirement
Per (period, agent, profile): `|Σ_k D_k − D| ≤ 1e-9`; weights identical to
the G5 audit's conditional weights bit-for-bit; every bin inside its period
window (guaranteed by F03c, re-asserted by the gate).

## Gold cases & gate
- **ST01 case A** (new tiny fixture `cases/ST01_profile_bins`): 1 link,
  D = 1000, AM_PEAK bins 0.4/0.6 → rows exactly 400.000000000 / 600.000000000.
- **Case B** (existing `dev/test/f03/transims` four-period fixture): per
  (period, agent) Σ_k D_k = 1000 exactly, 96 rows per binding, TRANSIMS
  conditional weights.
- Gate script `tools/check_bin_demand.py`: runs the engine on both, parses
  the CSV, asserts conservation to 1e-9 and the case-A bin values exactly.
- `simulation_self_test.yml`: ST01 flips `enabled: false → partial`
  (bin_counts gate live; `final_CA` stays for S2).

## Regression requirement
All baselines byte-identical (no baseline dataset has bindings → the new
code path never executes there); gold 161/161; ST00/ST00c stay green;
analytical bank counts unchanged.

## Expected diff size / risk
Small (~60 lines). Risk: low — output-only, guarded by bindings.

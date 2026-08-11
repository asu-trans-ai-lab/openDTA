# V1-c Mini-Spec — SupplyProvider: link_supply.csv as THE explicit mu(t) input

Per OPENDTA_V1_MVP_SPEC.md section 2 (mu(t) single-source decision, Simon
2026-08-09). Branch `feature/v1c-supply-provider` (stacked on V1-b).

## Requested behavior
Optional input `link_supply.csv` becomes the PRIMARY supply source:

```
link_id, window_start, window_end, mu_value, mu_unit,
per_lane_or_all_lanes, lanes_open, source, quality_flag
```

- windows are absolute clock HHMM spans (e.g. 0730-0800); any length — a
  30-second signal green, a work-zone hour and a whole period are the same
  row type; a link may have many rows; overlaps on one link are an input
  error;
- `mu_unit` MUST be veh/h (`vph`/`veh/h`); anything else aborts with
  `BLOCKED-SUPPLY_UNIT_UNDEFINED` (Phase-2 code). Same for an invalid
  `per_lane_or_all_lanes` (per_lane multiplies by lane count);
- `lanes_open` is parsed and stored (schema frozen) but only the mu
  dimension acts in v1 (spatial-capacity time variation = F07 follow-up);
- unknown link_id aborts (typo protection);
- intervals not covered by any window fall back to the capacity-derived
  constant (the previous behavior), per the spec's priority chain
  explicit -> SLC -> period_capacity -> default.

Engine: LinkQueue's outflow_cap fill consumes a per-link piecewise rate.
The S4 ServiceDiscretizer gains a variable-rate `next(rate)` using the
SAME legacy LCG sequence; with no supply file every link takes the
existing constant path verbatim -> full battery byte-identical.

Readiness (V1-b integration): SUPPLY_MU_READY becomes
- table absent: PASS_WITH_DEFAULT (smoke) / BLOCKED-MU_T_NOT_VALIDATED
  (validation) — unchanged;
- table present, full link coverage: PASS ("N links from link_supply.csv")
  in both modes — validation unblocks;
- partial coverage: PASS_WITH_DEFAULT (smoke, counts disclosed) /
  BLOCKED-MU_T_NOT_VALIDATED (validation, uncovered count named).
readiness_report.json gains links_from_supply / links_from_default.
mu provenance per run: source column values echoed in the report.

## Gate (red-first) — tools/check_supply_provider.py (18th)
Fixtures on the ST00 1-mile link (dev/test/v1c/):
1. **sp01_step_mu**: demand 1200/h 1 h; supply 0700-0730 mu=1800,
   0730-0800 mu=600; CLEAR hour uncovered (falls back to 3600).
   Fluid oracle: no queue in w1; queue grows at 600/h in w2 (peak ~300);
   CD(0730)=600, CD(0800)=900 (+-2 veh); all vehicles out by horizon.
2. **sp02_signal**: demand 900/h 1 h; supply = 30 s green mu=3600 /
   30 s red mu=0 cycles across two hours (240 rows — the signal-timing
   use case). Asserts: CD increments ONLY in green windows; CD(0800)
   = 900 (+-2); avg discharge while queued ~1800/h.
3. **sp03_unit_undefined**: one row mu_unit=veh/min -> exit nonzero,
   BLOCKED-SUPPLY_UNIT_UNDEFINED on stdout.
4. **sp04_validation_supply**: run_mode validation + full-coverage supply
   -> stdout shows SUPPLY_MU_READY: PASS (validation unblocked on supply;
   still blocked overall on the unbound profile — asserted).
Full battery green + baselines byte-identical (no-file default path).

## Files
include/handles.h (SupplyWindow, member map, read_link_supply decl,
readiness fields), include/supply.h (ServiceDiscretizer::next(rate),
LinkQueue ctor optional windows param), src/utils.cpp (parser + readiness
integration), src/simulation.cpp (setup_link_queues passes windows - the
ONLY kernel-file touch, additive), fixtures + gate + runner registration.

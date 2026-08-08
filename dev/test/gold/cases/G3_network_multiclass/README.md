# G3_network_multiclass

One OD pair, two routes/corridors sharing downstream bottleneck L5, three supply periods, auto/truck PCE, period-dependent mu and allowed_uses. v2 adds: full link_period contract (capacity_unit, reference_tt, capacity_ratio, provenance), departure_profile_binding fallback table, vehicle-level gold (largest-remainder vehicleization + deterministic vehicle DNL + vehicle_link_trajectory audit trail), reconciliation, corridor experienced-vs-instantaneous TT, and period-boundary audit.

Numeric truth lives in `assertions.json`; regenerate gold with `python ../../tools/gold_solver.py .` (and `vehicle_gold.py` where vehicle gold exists); verify with `python ../../tools/check_gold.py cases/G3_network_multiclass/` from the dataset root.

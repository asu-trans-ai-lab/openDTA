# G4_corridor_ramp

Four mainline links with an on-ramp merging at n1 and an off-ramp diverging at n3, three routes sharing the mainline. Exercises the corridor conservation identity CA_{i+1}(t) = CD_i(t) + R_on(t) - R_off(t) per node per interval (tolerance 1e-9) - which fails LEGITIMATELY if ramps are not declared in corridor.csv, and that failure is indistinguishable from a DNL bug. M3 bottleneck queue forms in P1, persists across the 08:00 boundary (I3 with ramp flows present), grows in P2, clears in P3. Route-specific departure profiles (peaked mainline, flat on-ramp, late-shifted off-ramp traffic) - deliberately NOT one shared diurnal template.

Numeric truth lives in `assertions.json`; regenerate gold with `python ../../tools/gold_solver.py .` (and `vehicle_gold.py` where vehicle gold exists); verify with `python ../../tools/check_gold.py cases/G4_corridor_ramp/` from the dataset root.

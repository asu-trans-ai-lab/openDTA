# G1_single_link_two_period

Pure point-queue integrator test. tau0=0 isolates queue dynamics so every gold value equals the hand-computed table: Q(08:00)=266.667 continuous across the mu 1000->1200 boundary (I3), peak Q=333.333 at 08:20, clearance exactly 09:00:00, CA(09:00)=CD(09:00)=2133.333, and the correct-physics delay discontinuity w(08:00-)=16.00 min vs w(08:00+)=13.333 min.

Numeric truth lives in `assertions.json`; regenerate gold with `python ../../tools/gold_solver.py .` (and `vehicle_gold.py` where vehicle gold exists); verify with `python ../../tools/check_gold.py cases/G1_single_link_two_period/` from the dataset root.

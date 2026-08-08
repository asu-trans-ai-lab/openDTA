# G2b_tandem_period_boundary

Same topology as G2; mu2 steps 900->750 at 07:45 while Q2 is standing. Asserts Q2 continuity AND CD1->CQ2 conservation SIMULTANEOUSLY - a boundary bug that resets Q2 also silently breaks conservation, and testing them separately can let both pass. Analytic gold: Q2(07:45)=210 continuous; peak 232.5 @07:48; Q2(08:33)=120; Q2(08:42)=7.5; clears between 08:42 and 08:43 (analytic 08:42:36).

Numeric truth lives in `assertions.json`; regenerate gold with `python ../../tools/gold_solver.py .` (and `vehicle_gold.py` where vehicle gold exists); verify with `python ../../tools/check_gold.py cases/G2b_tandem_period_boundary/` from the dataset root.

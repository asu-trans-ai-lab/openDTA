# G2_two_link_tandem

Tandem propagation test. tau01=1min mu1=1200; tau02=2min mu2=900, constant. lambda=1500 (07:00-07:30) then 600. Gold: Q1 onset 07:01, peak 150 @07:31, clears 07:46; Q2 onset 07:03, peak 225 @07:48 (17 min after peak Q1), clears 08:33 (47 min after L1). Identity CD1(t)==CQ2(t+tau02) every interval. Distinct onset/clearance across links is the physical mechanism behind 'why do all links congest simultaneously'.

Numeric truth lives in `assertions.json`; regenerate gold with `python ../../tools/gold_solver.py .` (and `vehicle_gold.py` where vehicle gold exists); verify with `python ../../tools/check_gold.py cases/G2_two_link_tandem/` from the dataset root.

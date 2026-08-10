# ST07 -- FIFO diverge throttling gate (ACTIVE since F05-b; tools/check_node_models.py)

**F05-b measurement (frozen):** spatial queue, plateau minutes 20-50: main
600, ramp 1200, shared discharge 1800 -- the Knoop FIFO values EXACTLY (the
off-ramp storage of 200 veh fills ~minute 10, then the shared exit queue
FIFO-blocks behind ramp-bound heads; single-incoming fast path, no merge
allocation involved). Gate bands +-5%.


Topology: shared 2-lane approach (C = 3600) splits at node 2 into main exit
(C = 3600) and a 1-lane off-ramp (C = 1200). Demand 3600 veh/h on the shared
link, exit fractions f_main = 1/3 (1200), f_ramp = 2/3 (2400).

## F05 gate (frozen truth -- Knoop sec. 11.1.2, FIFO/CTF)
phi_ramp = S_ramp/(f_ramp*d) = 1200/2400 = 0.5; Phi = min(1, phi) = 0.5 ->
**q_main = 600, q_ramp = 1200, total = 1800**. One blocked exit throttles the
through movement too. An engine with independent per-link caps wrongly passes
the full 1200 on the main movement -- the sharpest diverge red test.

## Point-queue tier (today, characterization)
No receiving constraint: shared link discharges 3600; ramp vehicles stack in
the off-ramp's entrance queue (served at 1200); main vehicles pass 1200
unthrottled. Expected observed plateau: main 1200, ramp 1200, shared 3600 --
the DOCUMENTED point-queue limitation (Knoop sec. 2.3: vertical queues ignore
spillback). Spatial queue: once off-ramp storage fills, the shared link's
FIFO exit queue blocks behind ramp vehicles and the main flow collapses
toward the FIFO value -- how closely it approaches 600 is an F05 acceptance
measurement.

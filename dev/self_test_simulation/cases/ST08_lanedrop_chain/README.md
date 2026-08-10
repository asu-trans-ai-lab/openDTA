# ST08 -- lane-drop chain: queue-front trajectory gate (ACTIVE since F05-b)

**F05-b fixture correction:** the demand.csv volume column is the PERIOD
TOTAL, not an hourly rate. The original files encoded 3000 veh over 30 min
(= 6000/h, oversaturating segment 1 itself at the origin) and 1200 over
90 min (= 800/h). Corrected to the rates this README freezes: demand.csv
volume = 1500 (3000/h x 0.5 h), demand_low.csv = 1800 (1200/h x 1.5 h).

**F05-b measurement (frozen, tools/check_node_models.py):** bottleneck
discharge == 30 veh/min EXACTLY on all 89 queued minutes; chain conservation
CD_i == CA_{i+1} holds with 0 deviation on every row; queue onsets (first
minute with >= 5 veh -- the origin link shows a 1-2 veh loading transient at
minute 1 that is not spillback) march strictly upstream:
seg8@3, seg7@4, seg6@5, seg5@7, seg4@10, seg3@12, seg2@14, seg1@16
(~2 min per 0.25-mi segment; the full front-speed numeric oracle lands with
the per-link FD contract follow-up, now unlocked by F05-pre).


Eight 0.25-mi segments; segment 8 drops 2 lanes -> 1 (C: 3600 -> 1800).
Demand 3000 veh/h for 30 min, then 1200 (< 1800, queue must clear).

## Oracle method (freeze the numbers at F05 after the FD contract lands)
With a declared triangular FD (v_f, k_j per lane) the front speeds are chord
slopes w = dq/dk (Knoop Eq. 4.9): the congestion front recedes upstream
through the chain and its trajectory is read from the QUEUE-ONSET TIME OF
EACH SEGMENT (per-link CA/CD/queue outputs) - segment i's onset minus
segment i+1's onset gives the front's traversal time of a 0.25-mi segment.
Invariants that hold regardless of the exact k_j (Treiber 8.17-8.20):
  - only two interior wave speeds exist (v_f forward, w backward);
  - bottleneck discharge == 1800 exactly while any queue exists
    (jam outflow = Q_max; no capacity drop in a first-order model);
  - after demand falls to 1200, recovery front returns DOWNSTREAM at w;
  - vehicle conservation across the chain (CD_i == CA_{i+1} per interval).

## Point-queue tier (today, characterization)
All queueing collapses onto segment 8's vertical queue; segments 1-7 stay
free-flow (onset times undefined) - the documented spillback blind spot.
The bottleneck-discharge and conservation invariants are testable TODAY.

Cross-reference for a full numeric oracle at F05: Treiber & Kesting
Problem 8.5 solution (pp. 443-447) and Knoop sec. 4.2 Tables 4.1-4.2.

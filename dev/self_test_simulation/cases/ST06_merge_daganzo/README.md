# ST06 -- Daganzo merge gate (ACTIVE since F05-a; tools/check_node_models.py)

**F05-a result (frozen):** under the pre-F05 rotation the plateau measured
1680/720 -- the 7:3 service-capacity ratio, priority-blind, and q_B stayed 720
when d_B rose to 2000 (invariance violated). With Daganzo-mid allocation the
plateau is exactly **1920 / 480** at downstream inflow 2400, and d_B
1500 -> 2000 leaves q_B at 480. Gate tolerance +-2%.


Topology: A(4 lanes, C=4200) and B(1 lane, C=1800) merge into a 2-lane
downstream link with **R = 2400 veh/h**. Demands d_A = 3500, d_B = 1500.
Priority from infrastructure (lane counts): p = 4:1.

## F05 gate (frozen truth -- Knoop sec. 11.1.1, Daganzo)
d_A + d_B = 5000 > R, and neither p_i*R covers d_i
(p_A*R = 1920 < 3500; p_B*R = 480 < 1500) -> **q_A = 1920, q_B = 480**.
Assert on the flow plateau of the downstream link and per-approach discharge.
Invariance principle (Lebacque / Tampere): once both approaches are congested
the split is fixed by p (capacities), independent of demands -- raising d_B
must NOT raise q_B.

## Point-queue tier (today, characterization -- NOT the gate)
Point queue has no receiving constraint: both approaches discharge at their
own capacities into the downstream entrance queue; the downstream link alone
serves R = 2400. Total outflow min(D, R) is respected but the SPLIT is
unconstrained upstream (measured: approaches discharge d_A and d_B fully).
Spatial queue engages storage, and the node rotation (t+i)%m then acts as an
implicit ~alternating merge rule (finding M-1) -- expected to deviate from the
4:1 Daganzo split. That deviation is the F05 design decision, not a bug to
patch silently.

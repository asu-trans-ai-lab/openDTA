"""Network-topology and future-tier self-test cases (built now, gated later).

Sources: Knoop Ch. 11 (Daganzo merge, FIFO diverge), Knoop Ch. 4 (lane-drop
shockwave), May Sec. 12.2.3 (incident closed forms), Elefteriadou Ex. 9.2 /
May 12.2.1 (signal). See dev/doc/traffic_flow_testing_notes.md.

Every case dir gets a README.md with the tiered expected behavior:
  - "point-queue tier (today)": what the current engine is EXPECTED to do,
    including its documented limitations (characterization, not endorsement);
  - "F05/F07 tier (gate)": the frozen book-based truth the future feature
    must reproduce.
All capacities are multiples of 600/h (exact integer vehicles per 6-s
interval - no fractional-service RNG pre-S4). Deterministic; no RNG.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

SETTINGS_HEAD = """---
user_equilibrium:
  load_columns: false
  column_gen_num: 20
  column_opd_num: 20

simulation:
  enable: true
  resolution: 6
  traffic_flow_model: {model}

agent_type:
  - type: a
    name: auto
    flow_type: 0
    pce: 1
    vot: 10
    free_speed: 60
    use_link_ffs: true

demand_period:
"""


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        f.write(text)


def periods(entries):
    """entries: list of (period, time_period, demand_file) -> settings block"""
    out = []
    for i, (name, tp, dem) in enumerate(entries, start=1):
        out.append(f"  - period: {name}\n    period_id: {i}\n"
                   f"    time_period: {tp}\n    demand:\n"
                   f"      - file_name: {dem}\n        agent_type: auto\n")

    return "".join(out)


# ---------------------------------------------------------------- ST06 merge
def st06():
    c = os.path.join(ROOT, "cases", "ST06_merge_daganzo")
    # nodes: 1 (origin A), 2 (origin B), 3 (merge), 4 (destination)
    write(os.path.join(c, "node.csv"),
          "node_id,name,x_coord,y_coord,node_type,ctrl_type,zone_id,geometry\n"
          "1,,0.0,0.5,,,1,POINT (0.0 0.5)\n"
          "2,,0.0,-0.5,,,2,POINT (0.0 -0.5)\n"
          "3,,1.0,0.0,,,,POINT (1.0 0.0)\n"
          "4,,2.0,0.0,,,3,POINT (2.0 0.0)\n")
    # approach A: 4 lanes cap 4200; approach B: 1 lane cap 1800;
    # downstream: cap 2400 (R). Priority by lanes p = 4:1.
    write(os.path.join(c, "link.csv"),
          "link_id,name,from_node_id,to_node_id,facility_type,link_type,dir_flag,"
          "length,lanes,free_speed,capacity,geometry\n"
          "1,A_approach,1,3,Freeway,1,1,1,4,60,1050,\"LINESTRING (0.0 0.5, 1.0 0.0)\"\n"
          "2,B_ramp,2,3,Ramp,1,1,1,1,60,1800,\"LINESTRING (0.0 -0.5, 1.0 0.0)\"\n"
          "3,downstream,3,4,Freeway,1,1,1,2,60,1200,\"LINESTRING (1.0 0.0, 2.0 0.0)\"\n")
    # both OD pairs in ONE demand file and ONE period: the merge competition
    # requires the two approach flows to share the same hour
    write(os.path.join(c, "demand.csv"),
          "o_zone_id,d_zone_id,volume\n1,3,3500\n2,3,1500\n")
    write(os.path.join(c, "settings.yml"),
          "---\n# ST06: Daganzo merge gate (Knoop sec. 11.1.1). Spatial queue so the\n"
          "# downstream storage can actually constrain the approaches.\n"
          + SETTINGS_HEAD.format(model="spatial_queue").split("---\n", 1)[1]
          + periods([("PEAK", "0700-0800", "demand.csv")]))
    write(os.path.join(c, "README.md"), MERGE_README)


MERGE_README = """# ST06 -- Daganzo merge gate (prepared for F05)

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
"""


# --------------------------------------------------------------- ST07 diverge
def st07():
    c = os.path.join(ROOT, "cases", "ST07_diverge_fifo")
    write(os.path.join(c, "node.csv"),
          "node_id,name,x_coord,y_coord,node_type,ctrl_type,zone_id,geometry\n"
          "1,,0.0,0.0,,,1,POINT (0.0 0.0)\n"
          "2,,1.0,0.0,,,,POINT (1.0 0.0)\n"
          "3,,2.0,0.5,,,2,POINT (2.0 0.5)\n"
          "4,,2.0,-0.5,,,3,POINT (2.0 -0.5)\n")
    # shared approach cap 3600; main exit cap 3600; ramp exit cap 1200
    write(os.path.join(c, "link.csv"),
          "link_id,name,from_node_id,to_node_id,facility_type,link_type,dir_flag,"
          "length,lanes,free_speed,capacity,geometry\n"
          "1,shared,1,2,Freeway,1,1,1,2,60,1800,\"LINESTRING (0.0 0.0, 1.0 0.0)\"\n"
          "2,main_exit,2,3,Freeway,1,1,1,2,60,1800,\"LINESTRING (1.0 0.0, 2.0 0.5)\"\n"
          "3,off_ramp,2,4,Ramp,1,1,1,1,60,1200,\"LINESTRING (1.0 0.0, 2.0 -0.5)\"\n")
    write(os.path.join(c, "demand.csv"),
          "o_zone_id,d_zone_id,volume\n1,2,1200\n1,3,2400\n")
    write(os.path.join(c, "settings.yml"),
          "---\n# ST07: FIFO diverge throttling gate (Knoop sec. 11.1.2). Spatial\n"
          "# queue so off-ramp storage can spill back into the shared link.\n"
          + SETTINGS_HEAD.format(model="spatial_queue").split("---\n", 1)[1]
          + periods([("PEAK", "0700-0800", "demand.csv")]))
    write(os.path.join(c, "README.md"), DIVERGE_README)


DIVERGE_README = """# ST07 -- FIFO diverge throttling gate (prepared for F05)

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
"""


# ------------------------------------------------------- ST08 lane-drop chain
def st08():
    c = os.path.join(ROOT, "cases", "ST08_lanedrop_chain")
    n_seg = 8
    nodes = ["node_id,name,x_coord,y_coord,node_type,ctrl_type,zone_id,geometry"]
    for i in range(1, n_seg + 2):
        zone = "1" if i == 1 else ("2" if i == n_seg + 1 else "")
        x = (i - 1) * 0.25
        nodes.append(f"{i},,{x:.2f},0.0,,,{zone},POINT ({x:.2f} 0.0)")

    write(os.path.join(c, "node.csv"), "\n".join(nodes) + "\n")
    links = ["link_id,name,from_node_id,to_node_id,facility_type,link_type,dir_flag,"
             "length,lanes,free_speed,capacity,geometry"]
    for i in range(1, n_seg + 1):
        lanes, cap = (2, 1800) if i < n_seg else (1, 1800)   # drop on last segment
        links.append(f"{i},seg{i},{i},{i+1},Freeway,1,1,0.25,{lanes},60,{cap},"
                     f"\"LINESTRING ({(i-1)*0.25:.2f} 0.0, {i*0.25:.2f} 0.0)\"")

    write(os.path.join(c, "link.csv"), "\n".join(links) + "\n")
    write(os.path.join(c, "demand.csv"), "o_zone_id,d_zone_id,volume\n1,2,3000\n")
    write(os.path.join(c, "demand_low.csv"), "o_zone_id,d_zone_id,volume\n1,2,1200\n")
    write(os.path.join(c, "settings.yml"),
          "---\n# ST08: lane-drop chain for queue-front (shockwave) tracking. Eight\n"
          "# 0.25-mi segments; the last drops to 1 lane (C 3600 -> 1800). Demand\n"
          "# 3000 veh/h for 30 min then 1200. Kinematic-wave model so upstream\n"
          "# storage/backwave participates.\n"
          + SETTINGS_HEAD.format(model="kinematic_wave").split("---\n", 1)[1]
          + periods([("PEAK", "0700-0730", "demand.csv"),
                     ("OFF", "0730-0900", "demand_low.csv")]))
    write(os.path.join(c, "README.md"), CHAIN_README)


CHAIN_README = """# ST08 -- lane-drop chain: queue-front trajectory gate (prepared for F05)

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
"""


# -------------------------------------------- ST02e incident (needs mu(t)/F07)
def st02e():
    c = os.path.join(ROOT, "cases", "ST02e_incident_f07")
    write(os.path.join(c, "node.csv"),
          "node_id,name,x_coord,y_coord,node_type,ctrl_type,zone_id,geometry\n"
          "1,,0.0,0.0,,,1,POINT (0.0 0.0)\n2,,1.0,0.0,,,2,POINT (1.0 0.0)\n")
    write(os.path.join(c, "link.csv"),
          "link_id,name,from_node_id,to_node_id,facility_type,link_type,dir_flag,"
          "length,lanes,free_speed,capacity,geometry\n"
          "1,mainline,1,2,Freeway,1,1,1,3,60,2000,\"LINESTRING (0.0 0.0, 1.0 0.0)\"\n")
    write(os.path.join(c, "demand.csv"), "o_zone_id,d_zone_id,volume\n1,2,4800\n")
    # F07 contract preview - consumed by nothing yet:
    write(os.path.join(c, "capacity_profile.csv"),
          "link_id,time_start,time_end,discharge_rate\n"
          "1,07:30,08:15,4200\n")
    write(os.path.join(c, "settings.yml"),
          "---\n# ST02e: May sec. 12.2.3 incident case - REQUIRES mu(t) (feature F07).\n"
          "# enabled: false until then; capacity_profile.csv is the contract preview.\n"
          + SETTINGS_HEAD.format(model="point_queue").split("---\n", 1)[1]
          + periods([("PEAK", "0700-0900", "demand.csv")]))
    write(os.path.join(c, "README.md"), INCIDENT_README)


INCIDENT_README = """# ST02e -- incident capacity-reduction case (REQUIRES F07 mu(t))

May sec. 12.2.3 closed forms, adapted to 600-multiples: lambda = 4800,
mu = 6000 dropping to mu_R = 4200 during the incident window t_R
(07:30-08:15 in the shipped profile, t_R = 0.75 h), then back.

Closed-form gold (May Table 12.1 with these numbers):
  t_Q  = t_R (mu - mu_R)/(mu - lambda) = 1.5 t_R
  Q_M  = t_R (lambda - mu_R)           = 600 t_R   veh
  d_M  = 60 t_R (lambda - mu_R)/lambda = 7.5 t_R   min
  TD   = t_R t_Q (lambda - mu_R)/2     = 450 t_R^2 veh-h
Sweep gate at F07: run t_R = 0.25/0.5/0.75/1.0 h -> TD = 28.1/112.5/253.1/450
veh-h; fitting log TD vs log t_R must give exponent 2.00 +/- 0.02 (the
quadratic incident-delay law). Book original (mu_R = 4000): TD = 666.67 t_R^2.

Status: enabled false. The engine has no time-dependent discharge yet;
capacity_profile.csv is the F07 input-contract preview (link_time_profile
layer of the F03b supply stack).
"""


# ------------------------------------------------- ST10 signal (needs F07)
def st10():
    c = os.path.join(ROOT, "cases", "ST10_signal_webster_f07")
    write(os.path.join(c, "node.csv"),
          "node_id,name,x_coord,y_coord,node_type,ctrl_type,zone_id,geometry\n"
          "1,,0.0,0.0,,,1,POINT (0.0 0.0)\n2,,0.5,0.0,,,2,POINT (0.5 0.0)\n")
    write(os.path.join(c, "link.csv"),
          "link_id,name,from_node_id,to_node_id,facility_type,link_type,dir_flag,"
          "length,lanes,free_speed,capacity,geometry\n"
          "1,approach,1,2,arterial,2,1,0.5,1,30,1800,\"LINESTRING (0.0 0.0, 0.5 0.0)\"\n")
    write(os.path.join(c, "demand.csv"), "o_zone_id,d_zone_id,volume\n1,2,800\n")
    write(os.path.join(c, "capacity_profile.csv"),
          "link_id,time_start,time_end,discharge_rate\n"
          "# 60-s cycle, g/C = 0.5: repeat red (0) / green (1800) blocks - the\n"
          "# F07 signal representation (Treiber Eq. 8.31: DQ = Q_max in red)\n"
          "1,07:00:00,07:00:30,0\n1,07:00:30,07:01:00,1800\n"
          "# ... generated for the full hour by the F07 tooling\n")
    write(os.path.join(c, "settings.yml"),
          "---\n# ST10: Webster uniform-delay signal case - REQUIRES mu(t)/F07.\n"
          + SETTINGS_HEAD.format(model="point_queue").split("---\n", 1)[1]
          + periods([("PEAK", "0700-0800", "demand.csv")]))
    write(os.path.join(c, "README.md"), SIGNAL_README)


SIGNAL_README = """# ST10 -- Webster signal delay case (REQUIRES F07 mu(t))

Elefteriadou Ex. 9.2 / May 12.2.1 / Treiber 8.5.9.1: V = 800 veh/h,
saturation flow S = 1800, C = 60 s, g/C = 0.5 -> capacity 900 veh/h,
v/c = 0.89.

Gold (frozen):
  uniform delay d1 = 0.5 C (1-g/C)^2 / (1 - V/S) = 13.5 s/veh
  per-cycle: Q_M = lambda r = 6.67 veh; t_Q = s r /(s-lambda) = 54 s < g (OK)
  total delay per red grows with r^2 (Treiber Problem 8.4) - a red-duration
  sweep (r = 20/30/40 s at fixed lambda) must fit exponent 2.
  Non-oversaturation condition: V <= C_link * g/C (Treiber 8.49).

Status: enabled false until F07; capacity_profile.csv sketches the red/green
discharge representation.
"""


if __name__ == "__main__":
    st06()
    st07()
    st08()
    st02e()
    st10()
    print("wrote ST06, ST07, ST08, ST02e(F07), ST10(F07) case dirs")

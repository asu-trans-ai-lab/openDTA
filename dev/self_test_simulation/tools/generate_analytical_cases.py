"""Analytical self-test case generator (ST02 family).

Learned from consensus_datasets/QVDF-main (Zhou et al. 2022, polynomial
arrival queue): lambda(t) profiles with constant mu admit exact fluid-queue
solutions. This generator:

1. builds lambda(t) as PIECEWISE-CONSTANT pieces (native shapes: gold_a step,
   quadratic PAQ-style pulse, cubic skewed pulse, twin peaks). Smooth
   polynomials are discretized to 5-min pieces with INTEGER piece volumes, and
   the oracle is computed on the discretized profile itself - so the expected
   truth is exact for what the engine is actually fed, not an approximation;
2. expresses each piece as one OpenDTA demand period (the current engine
   spreads a period's demand uniformly -> exactly piecewise-constant lambda),
   so these cases run on the S0 engine TODAY, before S1/S2 land;
3. solves the point-queue fluid oracle on a minute grid:
       A_entry(t)   cumulative entrance arrivals
       A_service(t) = A_entry(t - fftt)      (Newell shift - see ST02 note)
       D(t)         = point-queue discharge at mu on A_service
       Q(t)         = A_service(t) - D(t)    (matches the engine's queue col)
   and freezes T0 / Tpeak / T3 / Qmax / total delay / total vehicles;
4. writes cases/<id>/ (node, link, per-period demand csvs, settings.yml) and
   expected/<id>_expected.csv.

Deterministic; no RNG. Link: 1 mile, 60 mph (fftt = 1 min), capacity mu chosen
so mu * 6 / 3600 is an integer (integer service path, no fractional rounding).
"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

MU_VPH = 1200          # 2 veh per 6-s interval: integer service path
FFTT_MIN = 1.0         # 1 mile at 60 mph
START_HHMM = 7 * 60    # 07:00, minute 0 of the simulation clock
PIECE_MIN = 5          # discretization of smooth profiles


def pieces_gold_a():
    # the S5 hand table: 600/1800/600 over 30/60/60 min
    return [(30, 300), (60, 1800), (60, 600)]  # (duration_min, piece_volume)


def _discretize(rate_fn, total_min):
    """5-min pieces; piece volume rounded to integer, largest-remainder to a
    round total so conservation is a clean integer."""
    n = total_min // PIECE_MIN
    raw = []
    for i in range(n):
        mid = (i + 0.5) * PIECE_MIN
        raw.append(max(0.0, rate_fn(mid)) * PIECE_MIN / 60.0)

    floors = [int(v) for v in raw]
    target = int(round(sum(raw)))
    remainders = sorted(range(n), key=lambda i: raw[i] - floors[i], reverse=True)
    vols = floors[:]
    for i in remainders[: target - sum(floors)]:
        vols[i] += 1

    return [(PIECE_MIN, v) for v in vols]


def pieces_quadratic():
    # PAQ-style quadratic pulse: base 400, peak 2000 at t=60, half-width 45;
    # oversaturated (lambda > mu = 1200) roughly t in [24, 96]
    def rate(t):
        s = (t - 60.0) / 45.0
        return 400.0 + 1600.0 * max(0.0, 1.0 - s * s)

    return _discretize(rate, 150)


def pieces_cubic():
    # skewed cubic pulse: fast onset, slow recovery (classic PM peak shape)
    def rate(t):
        s = t / 150.0
        return 300.0 + 12000.0 * s * s * (1.0 - s) * 1.9

    return _discretize(rate, 150)


def pieces_twin_peaks():
    def rate(t):
        s1 = (t - 40.0) / 25.0
        s2 = (t - 110.0) / 25.0
        return 500.0 + 1300.0 * max(0.0, 1.0 - s1 * s1) + 1100.0 * max(0.0, 1.0 - s2 * s2)

    return _discretize(rate, 150)


def pieces_sqm_paper():
    # ST04a: the paper-exact SQM case (see TEST_CATALOG.md #ST04a).
    # lambda = 600 / 1500 / 900 veh/h over 10 / 8 / 8 min, mu = 1200:
    # Qmax = 40 veh at t=18, tw_max = 2 min, T3 = 26 min exactly.
    # SQM layer (S5d, constant-mu triangular FD w=12 mph, kj=180/mi/lane):
    # vQ = mu/(kj - mu/w) = 15 mph; tQ_max = 2*60/45 = 2.6667 min;
    # tF_max = 1 - 2*15/45 = 0.3333 min; TT_max = 3.0 min; v_bar_min = 20 mph;
    # physical queue segment dQ = 0.6667 mi. Chosen so the SQM applicability
    # condition holds (tF > 0), unlike ST02a where tw = 30 min violates it.
    return [(10, 100), (8, 200), (8, 120)]


CASES = {
    "ST02a_step_gold": pieces_gold_a,
    "ST02b_quadratic": pieces_quadratic,
    "ST02c_cubic": pieces_cubic,
    "ST02d_twin_peaks": pieces_twin_peaks,
    "ST04a_sqm_paper": pieces_sqm_paper,
}


def solve_oracle(pieces):
    """Exact fluid point-queue on a 1-min grid (piecewise-linear cumulatives).
    Returns per-minute rows and summary events."""
    total_min = sum(d for d, _ in pieces)
    # entrance arrival rate per minute
    lam = []
    for dur, vol in pieces:
        lam += [vol / dur] * dur

    horizon = total_min + 180  # drain buffer
    lam += [0.0] * (horizon - total_min)

    a_entry = [0.0]
    for r in lam:
        a_entry.append(a_entry[-1] + r)

    shift = int(round(FFTT_MIN))
    a_service = [a_entry[max(0, t - shift)] for t in range(horizon + 1)]

    mu_min = MU_VPH / 60.0
    d = [0.0]
    for t in range(1, horizon + 1):
        d.append(min(a_service[t], d[-1] + mu_min))

    q = [a_service[t] - d[t] for t in range(horizon + 1)]

    t0 = next((t for t in range(horizon + 1) if q[t] > 1e-9), None)
    t3 = None
    tpeak = 0
    qmax = 0.0
    if t0 is not None:
        for t in range(t0, horizon + 1):
            if q[t] > qmax:
                qmax, tpeak = q[t], t

        t3 = next((t for t in range(tpeak, horizon + 1) if q[t] < 1e-9), None)

    delay_veh_min = sum((q[t - 1] + q[t]) / 2 for t in range(1, horizon + 1))
    return {
        "horizon": horizon,
        "lam": lam,
        "a_entry": a_entry,
        "a_service": a_service,
        "d": d,
        "q": q,
        "total_vehicles": a_entry[-1],
        "t0": t0,
        "tpeak": tpeak if t0 is not None else None,
        "t3": t3,
        "qmax": qmax,
        "delay_veh_h": delay_veh_min / 60.0,
    }


def hhmm(minute_of_day):
    return f"{minute_of_day // 60:02d}{minute_of_day % 60:02d}"


def write_case(case_id, pieces, oracle):
    cdir = os.path.join(ROOT, "cases", case_id)
    os.makedirs(cdir, exist_ok=True)

    with open(os.path.join(cdir, "node.csv"), "w", newline="") as f:
        f.write("node_id,name,x_coord,y_coord,node_type,ctrl_type,zone_id,geometry\n"
                "1,,0.0,0.0,,,1,POINT (0.0 0.0)\n"
                "2,,1.0,0.0,,,2,POINT (1.0 0.0)\n")

    with open(os.path.join(cdir, "link.csv"), "w", newline="") as f:
        f.write("link_id,name,from_node_id,to_node_id,facility_type,link_type,dir_flag,"
                "length,lanes,free_speed,capacity,geometry\n"
                f"1,(null),1,2,Freeway,1,1,1,1,60,{MU_VPH},\"LINESTRING (0.0 0.0, 1.0 0.0)\"\n")

    lines = ["---",
             f"# {case_id}: analytical point-queue case (generated by",
             "# tools/generate_analytical_cases.py - do not hand-edit).",
             f"# lambda(t) as {len(pieces)} piecewise-constant demand periods, "
             f"mu = {MU_VPH}/h constant,",
             "# expected truth in expected/ from the exact fluid oracle.",
             "user_equilibrium:",
             "  load_columns: false",
             "  column_gen_num: 20",
             "  column_opd_num: 20",
             "",
             "simulation:",
             "  enable: true",
             "  resolution: 6",
             "  traffic_flow_model: point_queue",
             "",
             "agent_type:",
             "  - type: a",
             "    name: auto",
             "    flow_type: 0",
             "    pce: 1",
             "    vot: 10",
             "    free_speed: 60",
             "    use_link_ffs: true",
             "",
             "demand_period:"]

    clock = START_HHMM
    for i, (dur, vol) in enumerate(pieces, start=1):
        dem = f"demand_p{i:02d}.csv"
        with open(os.path.join(cdir, dem), "w", newline="") as f:
            f.write(f"o_zone_id,d_zone_id,volume\n1,2,{vol}\n")

        lines += [f"  - period: P{i:02d}",
                  f"    period_id: {i}",
                  f"    time_period: {hhmm(clock)}-{hhmm(clock + dur)}",
                  "    demand:",
                  f"      - file_name: {dem}",
                  "        agent_type: auto"]
        clock += dur

    with open(os.path.join(cdir, "settings.yml"), "w", newline="") as f:
        f.write("\n".join(lines) + "\n")

    edir = os.path.join(ROOT, "expected")
    os.makedirs(edir, exist_ok=True)
    with open(os.path.join(edir, f"{case_id}_expected.csv"), "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["minute", "lambda_vph", "A_entry", "A_service", "D", "Q"])
        for t in range(oracle["horizon"] + 1):
            lam = oracle["lam"][t] * 60 if t < len(oracle["lam"]) else 0
            w.writerow([t, f"{lam:.6f}", f"{oracle['a_entry'][t]:.6f}",
                        f"{oracle['a_service'][t]:.6f}", f"{oracle['d'][t]:.6f}",
                        f"{oracle['q'][t]:.6f}"])

        w.writerow([])
        w.writerow(["summary", "total_vehicles", f"{oracle['total_vehicles']:.6f}"])
        w.writerow(["summary", "T0_min", oracle["t0"]])
        w.writerow(["summary", "Tpeak_min", oracle["tpeak"]])
        w.writerow(["summary", "T3_min", oracle["t3"]])
        w.writerow(["summary", "Qmax_veh", f"{oracle['qmax']:.6f}"])
        w.writerow(["summary", "total_delay_veh_h", f"{oracle['delay_veh_h']:.6f}"])
        w.writerow(["summary", "mu_vph", MU_VPH])
        w.writerow(["summary", "fftt_min", FFTT_MIN])


if __name__ == "__main__":
    for case_id, fn in CASES.items():
        pieces = fn()
        oracle = solve_oracle(pieces)

        # the engine simulates only through the last demand period: append
        # zero-volume drain periods so the queue clears inside the horizon
        demand_min = sum(d for d, _ in pieces)
        need = (oracle["t3"] or demand_min) + 10
        while demand_min < need:
            pieces.append((60, 0))
            demand_min += 60

        write_case(case_id, pieces, oracle)
        print(f"{case_id}: {len(pieces)} pieces (incl. drain), N={oracle['total_vehicles']:.0f}, "
              f"T0={oracle['t0']} Tpeak={oracle['tpeak']} T3={oracle['t3']} "
              f"Qmax={oracle['qmax']:.1f} delay={oracle['delay_veh_h']:.2f} veh-h")

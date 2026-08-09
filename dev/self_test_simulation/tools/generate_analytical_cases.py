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
SECONDS_IN_MIN_GRID = 10   # 6-s intervals per minute


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


def pieces_knoop_step():
    # ST02f: Knoop 3rd ed. section 2.6 worked example, uniformly rescaled by
    # 0.9 so the service capacity is an exact integer per 6-s interval
    # (book C = 4000/h is not a multiple of 600). Book: lambda =
    # 3600/5000/2000 veh/h for 1h/0.5h/1h, C = 4000 -> Qmax 500 veh,
    # TD 187.5 veh-h, clears at 1:45h. Rescaled (x0.9, mu = 3600):
    # lambda = 3240/4500/1800, Qmax = 450 veh, TD = 168.75 veh-h (delay
    # scales linearly with the flow scale), same event structure.
    return [(60, 3240), (30, 2250), (60, 1800)]


def pieces_may_keller_trapezoid():
    # ST02g: May section 12.2.4 (May-Keller) demand shape - trapezoidal
    # lambda vs constant mu: base, linear ramp up, sustained peak, linear
    # ramp down, base. Book structure with mu adjusted to 5400/h (exact
    # 9 veh/interval; book mu = 5500 is not a multiple of 600). The defining
    # prediction is that the queue persists well past the demand peak
    # (book analog: TQ_N = 2.53 h); the frozen expected values come from
    # the exact discretized oracle below.
    def rate(t):
        if t < 30:
            return 3000.0
        if t < 90:
            return 3000.0 + (6600.0 - 3000.0) * (t - 30.0) / 60.0
        if t < 150:
            return 6600.0
        if t < 210:
            return 6600.0 - (6600.0 - 3000.0) * (t - 150.0) / 60.0
        return 3000.0

    return _discretize(rate, 240)


# case_id -> (pieces_fn, mu_vph); mu must be a multiple of 600 so the 6-s
# per-interval service is an exact integer (no fractional-service RNG pre-S4)
CASES = {
    "ST02a_step_gold": (pieces_gold_a, 1200),
    "ST02b_quadratic": (pieces_quadratic, 1200),
    "ST02c_cubic": (pieces_cubic, 1200),
    "ST02d_twin_peaks": (pieces_twin_peaks, 1200),
    "ST02f_knoop_step": (pieces_knoop_step, 3600),
    "ST02g_trapezoid": (pieces_may_keller_trapezoid, 5400),
    "ST04a_sqm_paper": (pieces_sqm_paper, 1200),
}


def solve_oracle(pieces, mu_vph=MU_VPH):
    """Exact integer point-queue oracle on the 6-s grid, mirroring the
    engine's S2b loading and recording conventions:

    - arrivals reproduce setup_agents() exactly: vehicle i of a period with
      n vehicles over m intervals enters at interval i*m//n (integer math);
    - cumulative arrays are inclusive of the tick (the engine records state
      AFTER processing the interval);
    - service: cap = mu*6/3600 vehicles per interval (integer path);
    - queue = A_service - D at the same interval (the engine's queue column).

    Expected minute rows sample the interval grid at j = 10*minute, so the
    validator compares sim row k to expected row k with no clock shift.
    Everything is integer arithmetic: the oracle is EXACT for the S2b
    engine, and any deviation is an engine defect by construction.
    """
    ipm = SECONDS_IN_MIN_GRID  # intervals per minute (10 at 6-s resolution)
    total_min = sum(d for d, _ in pieces)
    horizon_min = total_min + 180  # drain buffer
    H = horizon_min * ipm

    arr = [0] * (H + 1)
    beg = 0
    for dur, vol in pieces:
        m = dur * ipm
        for i in range(int(vol)):
            arr[beg + i * m // int(vol)] += 1 if vol else 0

        beg += m

    fftt_i = int(round(FFTT_MIN * ipm))
    cap = mu_vph * 6 // 3600
    assert mu_vph * 6 % 3600 == 0, "mu must be an integer per 6-s interval"

    ca = [0] * (H + 1)      # inclusive cumulative entrance arrivals
    cq = [0] * (H + 1)      # inclusive cumulative exit-queue (service point)
    d = [0] * (H + 1)       # inclusive cumulative departures
    run = 0
    for j in range(H + 1):
        run += arr[j]
        ca[j] = run
        cq[j] = ca[j - fftt_i] if j >= fftt_i else 0
        prev = d[j - 1] if j else 0
        d[j] = min(cq[j], prev + cap)

    q = [cq[j] - d[j] for j in range(H + 1)]

    # minute-sampled series (row k == engine output row k at interval 10k)
    lam = []
    for dur, vol in pieces:
        lam += [vol / dur * 60.0] * dur

    lam += [0.0] * (horizon_min - total_min)
    s = {
        "a_entry": [ca[m * ipm] for m in range(horizon_min + 1)],
        "a_service": [cq[m * ipm] for m in range(horizon_min + 1)],
        "d": [d[m * ipm] for m in range(horizon_min + 1)],
        "q": [q[m * ipm] for m in range(horizon_min + 1)],
    }

    qs = s["q"]
    t0 = next((m for m in range(len(qs)) if qs[m] > 1e-9), None)
    t3 = None
    tpeak = 0
    qmax = 0.0
    if t0 is not None:
        for m in range(t0, len(qs)):
            if qs[m] > qmax:
                qmax, tpeak = qs[m], m

        t3 = next((m for m in range(tpeak, len(qs)) if qs[m] < 1e-9), None)

    delay_veh_min = sum(q) / ipm  # rectangle rule on the 6-s grid
    return {
        "horizon": horizon_min,
        "lam": lam,
        "a_entry": s["a_entry"],
        "a_service": s["a_service"],
        "d": s["d"],
        "q": s["q"],
        "total_vehicles": ca[-1],
        "t0": t0,
        "tpeak": tpeak if t0 is not None else None,
        "t3": t3,
        "qmax": qmax,
        "delay_veh_h": delay_veh_min / 60.0,
        "mu_vph": mu_vph,
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

    mu = oracle["mu_vph"]
    with open(os.path.join(cdir, "link.csv"), "w", newline="") as f:
        f.write("link_id,name,from_node_id,to_node_id,facility_type,link_type,dir_flag,"
                "length,lanes,free_speed,capacity,geometry\n"
                f"1,(null),1,2,Freeway,1,1,1,1,60,{mu},\"LINESTRING (0.0 0.0, 1.0 0.0)\"\n")

    lines = ["---",
             f"# {case_id}: analytical point-queue case (generated by",
             "# tools/generate_analytical_cases.py - do not hand-edit).",
             f"# lambda(t) as {len(pieces)} piecewise-constant demand periods, "
             f"mu = {oracle['mu_vph']}/h constant,",
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
        w.writerow(["summary", "mu_vph", oracle["mu_vph"]])
        w.writerow(["summary", "fftt_min", FFTT_MIN])


if __name__ == "__main__":
    for case_id, (fn, mu) in CASES.items():
        pieces = fn()
        oracle = solve_oracle(pieces, mu)

        # the engine simulates only through the last demand period: append
        # zero-volume drain periods so (a) the queue clears inside the
        # horizon AND (b) the last minute's arrivals traverse the FFTT and
        # discharge before the final sampled row (without (b), vehicles
        # entering in the final intervals sit past the last sample and read
        # as a phantom conservation loss - found via ST02d/ST02f)
        demand_min = sum(d for d, _ in pieces)
        need = max((oracle["t3"] or 0) + 10, demand_min + int(FFTT_MIN) + 5)
        while demand_min < need:
            pieces.append((60, 0))
            demand_min += 60

        write_case(case_id, pieces, oracle)
        print(f"{case_id}: {len(pieces)} pieces (incl. drain), N={oracle['total_vehicles']:.0f}, "
              f"T0={oracle['t0']} Tpeak={oracle['tpeak']} T3={oracle['t3']} "
              f"Qmax={oracle['qmax']:.1f} delay={oracle['delay_veh_h']:.2f} veh-h")

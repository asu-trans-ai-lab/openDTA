"""ST05a/ST05b gate: spatial-queue spillback and kinematic-wave backwave.

Two-link corridor: feeder L1 (1 mi, 6 veh/interval, storage 200) into
bottleneck L2 (0.2 mi, 2 veh/interval, storage 40, fftt 2 intervals,
BWTT 10 intervals). Demand 1800/h (3 veh/interval) for 30 min = 900 veh.

Independent per-interval fluid oracle mirroring the ENGINE'S receiving rules
(verified against supply.h / simulation.cpp semantics; all flows integer so
the oracle is exact for the intended 6-sec uniform loading contract):

  SQ  (ST05a): transfers into L2 blocked at t when CA2[t-1] - CD2[t-1] > 40
  KW  (ST05b): blocked when CA2[t-1] - CD2[max(0, t-1-10)] > 40
               (the completed form of the classical DTALite commented-out
               sketch; equals the LTM receiving A <= D(t-BWTT) + storage)

Gates that hold REGARDLESS of the pre-S2b minute-batched loading:
  conservation (CD2 final = 900), bottleneck rate cap, storage-cap bound
  (occ2 <= 40 + 6 one-interval overshoot), spillback occurs on L1, and
  KW blocks no later than SQ. Curve-level closeness to the oracle is
  reported with a one-minute-batch tolerance (35 veh) until S2b; the
  strict <= 2 veh assertion activates after S2b.

Exit 0 = PASS, 1 = FAIL.
"""
import csv
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REPO = os.path.abspath(os.path.join(ROOT, "..", ".."))
EXE = os.path.join(REPO, "build", "Release", "OpenDTA.exe")

N_INTERVALS = 1500          # 150 min horizon at 6 s
ARR = [3 if t < 300 else 0 for t in range(N_INTERVALS)]   # 1800/h for 30 min
CAP1, CAP2 = 6, 2
FFTT1, FFTT2 = 10, 2
STORAGE2 = 40
BWTT2 = 10
TOTAL = 900
BATCH_TOL = 35              # one minute-batch at 1800/h + margin (pre-S2b)


def oracle(kw):
    ca1 = [0] * (N_INTERVALS + 1)
    cd1 = [0] * (N_INTERVALS + 1)
    ca2 = [0] * (N_INTERVALS + 1)
    cd2 = [0] * (N_INTERVALS + 1)
    first_block = None
    for t in range(1, N_INTERVALS + 1):
        ca1[t] = ca1[t - 1] + (ARR[t - 1] if t - 1 < len(ARR) else 0)

        # receiving gate uses the t-1 snapshot (engine semantics)
        lag = max(0, t - 1 - BWTT2) if kw else t - 1
        gate_blocked = (ca2[t - 1] - cd2[lag]) > STORAGE2
        if gate_blocked and first_block is None:
            first_block = t

        ready1 = ca1[max(0, t - FFTT1)] - cd1[t - 1]
        move1 = 0 if gate_blocked else min(ready1, CAP1)
        cd1[t] = cd1[t - 1] + move1
        ca2[t] = ca2[t - 1] + move1

        ready2 = ca2[max(0, t - FFTT2)] - cd2[t - 1]
        cd2[t] = cd2[t - 1] + min(ready2, CAP2)

    return {"ca1": ca1, "cd1": cd1, "ca2": ca2, "cd2": cd2,
            "first_block": first_block,
            "occ1_max": max(ca1[t] - cd1[t] for t in range(N_INTERVALS + 1)),
            "occ2_max": max(ca2[t] - cd2[t] for t in range(N_INTERVALS + 1))}


failed = 0


def check(ok, what):
    global failed
    if not ok:
        failed += 1

    print(("  ok    " if ok else "  FAIL  ") + what)


def read_sim(out_dir):
    sim = {"1": {"CA": [], "CD": [], "Q": []}, "2": {"CA": [], "CD": [], "Q": []}}
    with open(os.path.join(out_dir, "link_performance_dta.csv"), newline="") as f:
        rd = csv.reader(f)
        next(rd)
        for row in rd:
            if row and row[0] in sim:
                sim[row[0]]["CA"].append(float(row[8]))
                sim[row[0]]["CD"].append(float(row[9]))
                sim[row[0]]["Q"].append(float(row[11]))

    return sim


def run_case(case_id, kw):
    print(f"case {case_id} ({'KW' if kw else 'SQ'})")
    out = os.path.join(ROOT, "output", case_id)
    os.makedirs(out, exist_ok=True)
    r = subprocess.run([EXE, os.path.join(ROOT, "cases", case_id) + os.sep, out + os.sep],
                       capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        check(False, f"engine exit {r.returncode}: {r.stderr[:200]}")
        return None

    sim = read_sim(out)
    orc = oracle(kw)
    n = len(sim["1"]["CA"])

    check(abs(sim["1"]["CA"][-1] - TOTAL) < 1e-9, f"L1 loads all {TOTAL}")
    check(abs(sim["2"]["CD"][-1] - TOTAL) < 1e-9, f"L2 discharges all {TOTAL}")

    occ2 = [sim["2"]["CA"][t] - sim["2"]["CD"][t] for t in range(n)]
    check(max(occ2) <= STORAGE2 + CAP1,
          f"L2 occupancy bounded by storage+overshoot ({max(occ2):.0f} <= {STORAGE2 + CAP1})")

    rate2 = max(sim["2"]["CD"][t] - sim["2"]["CD"][t - 1] for t in range(1, n))
    check(rate2 <= CAP2 * 10 + 1e-9,
          f"L2 per-minute discharge <= bottleneck rate ({rate2:.0f} <= {CAP2 * 10})")

    occ1 = [sim["1"]["CA"][t] - sim["1"]["CD"][t] for t in range(n)]
    check(max(occ1) > 60, f"spillback formed on L1 (max occupancy {max(occ1):.0f} veh)")

    # curve-level closeness vs the oracle (minute grid: oracle interval 10t)
    devs = []
    for series, olist in (("1CA", orc["ca1"]), ("1CD", orc["cd1"]),
                          ("2CA", orc["ca2"]), ("2CD", orc["cd2"])):
        link, kind = series[0], series[1:]
        d = max(abs(sim[link][kind][t] - olist[min((t + 1) * 10, N_INTERVALS)])
                for t in range(n))
        devs.append((series, d))

    worst = max(d for _, d in devs)
    check(worst <= BATCH_TOL,
          "curves within one-minute-batch tolerance of the oracle (pre-S2b): "
          + ", ".join(f"{s} {d:.0f}" for s, d in devs))

    print(f"  info  oracle first blocked interval: {orc['first_block']}, "
          f"oracle occ1_max {orc['occ1_max']}, occ2_max {orc['occ2_max']}")
    return {"sim": sim, "orc": orc}


def main():
    a = run_case("ST05a_spatial_spillback", kw=False)
    b = run_case("ST05b_kw_backwave", kw=True)

    if a and b:
        # the backwave reservation must not block later than pure occupancy
        check(b["orc"]["first_block"] <= a["orc"]["first_block"],
              f"oracle: KW blocks no later than SQ "
              f"({b['orc']['first_block']} <= {a['orc']['first_block']})")
        # engine cross-check: KW upstream spillback at least as large as SQ
        occ1a = max(a["sim"]["1"]["CA"][t] - a["sim"]["1"]["CD"][t]
                    for t in range(len(a["sim"]["1"]["CA"])))
        occ1b = max(b["sim"]["1"]["CA"][t] - b["sim"]["1"]["CD"][t]
                    for t in range(len(b["sim"]["1"]["CA"])))
        check(occ1b >= occ1a - 1,
              f"engine: KW spillback >= SQ spillback ({occ1b:.0f} vs {occ1a:.0f})")

    print(f"{'PASS' if failed == 0 else 'FAIL'} ({failed} failing checks)")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

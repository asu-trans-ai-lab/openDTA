"""S6 gate: two-link tandem against the gold G2 case (ST03).

L1 (1 mi, mu 1200/h, fftt 1 min) -> L2 (2 mi, mu 900/h, fftt 2 min),
lambda = 1500/600/600 veh/h. Resolution 12 s: both capacities integer per
interval, so the gold fluid numbers apply exactly.

Gates:
  1. tandem identity: CD1(t) == CA2(t) at every row (the node transfer
     increments both in the same interval);
  2. queue-column semantics on L2: Q2(t) == CA2(t - fftt2) - CD2(t)
     (the virtual-arrival definition, from the output columns themselves);
  3. gold events (sampled clock, +-1 min / +-2 veh):
     Q1 peak 150 @ 07:31, clears 07:46; Q2 peak 225 @ 07:48, clears 08:33;
  4. conservation: 1650 loaded, 1650 discharged from L2;
  5. exact-interval two-link fluid oracle cross-check (<= 2 veh curves).

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

IPM = 5                      # 12-s intervals per minute
CAP1, CAP2 = 4, 3            # veh per interval
FFTT1, FFTT2 = 5, 10         # intervals
TOTAL = 1650
failed = 0


def check(ok, what):
    global failed
    if not ok:
        failed += 1

    print(("  ok    " if ok else "  FAIL  ") + what)


def oracle():
    """Exact 12-s fluid tandem (point queue, no receiving constraint),
    mirroring S2b staggering and inclusive recording."""
    pieces = [(30, 750), (30, 300), (60, 600), (60, 0)]
    H = 180 * IPM
    arr = [0] * (H + 1)
    beg = 0
    for dur, vol in pieces:
        m = dur * IPM
        for i in range(vol):
            arr[beg + i * m // vol] += 1

        beg += m

    ca1 = [0] * (H + 1)
    cd1 = [0] * (H + 1)
    ca2 = [0] * (H + 1)
    cd2 = [0] * (H + 1)
    run = 0
    for j in range(H + 1):
        run += arr[j]
        ca1[j] = run
        cq1 = ca1[j - FFTT1] if j >= FFTT1 else 0
        cd1[j] = min(cq1, (cd1[j - 1] if j else 0) + CAP1)
        ca2[j] = cd1[j]
        cq2 = ca2[j - FFTT2] if j >= FFTT2 else 0
        cd2[j] = min(cq2, (cd2[j - 1] if j else 0) + CAP2)

    return ca1, cd1, ca2, cd2


def main():
    print("S6 gate: two-link tandem (gold G2)")
    out = os.path.join(ROOT, "output", "ST03_tandem_gold")
    os.makedirs(out, exist_ok=True)
    r = subprocess.run([EXE, os.path.join(ROOT, "cases", "ST03_tandem_gold") + os.sep,
                        out + os.sep], capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        check(False, f"engine exit {r.returncode}: {r.stderr[:200]}")
        return 1

    sim = {"1": {"CA": [], "CD": [], "Q": []}, "2": {"CA": [], "CD": [], "Q": []}}
    with open(os.path.join(out, "link_performance_dta.csv"), newline="") as f:
        rd = csv.reader(f)
        next(rd)
        for row in rd:
            if row and row[0] in sim:
                sim[row[0]]["CA"].append(float(row[8]))
                sim[row[0]]["CD"].append(float(row[9]))
                sim[row[0]]["Q"].append(float(row[11]))

    n = len(sim["1"]["CA"])

    # 1. tandem identity
    dev = max(abs(sim["1"]["CD"][t] - sim["2"]["CA"][t]) for t in range(n))
    check(dev == 0, f"tandem identity CD1 == CA2 at every row (max dev {dev:.0f})")

    # 2. L2 queue-column semantics (virtual arrival, fftt2 = 2 min)
    bad = 0
    for t in range(2, n):
        expect = sim["2"]["CA"][t - 2] - sim["2"]["CD"][t]
        if abs(sim["2"]["Q"][t] - expect) > 1e-9:
            bad += 1

    check(bad == 0, f"Q2 == CA2(t-2min) - CD2(t) on every row ({bad} violations)")

    # 3. gold events (row k = minute k, sampled clock)
    q1, q2 = sim["1"]["Q"], sim["2"]["Q"]
    q1_peak = max(q1)
    q1_tpeak = q1.index(q1_peak)
    q1_clear = next(t for t in range(q1_tpeak, n) if q1[t] < 0.5)
    q2_peak = max(q2)
    q2_tpeak = q2.index(q2_peak)
    q2_clear = next(t for t in range(q2_tpeak, n) if q2[t] < 0.5)

    check(abs(q1_peak - 150) <= 2 and abs(q1_tpeak - 31) <= 1,
          f"gold: Q1 peak 150 @ 07:31 (sim {q1_peak:.0f} @ 07:{q1_tpeak:02d})")
    check(abs(q1_clear - 46) <= 1, f"gold: Q1 clears 07:46 (sim 07:{q1_clear:02d})")
    check(abs(q2_peak - 225) <= 2 and abs(q2_tpeak - 48) <= 1,
          f"gold: Q2 peak 225 @ 07:48 (sim {q2_peak:.0f} @ 07:{q2_tpeak:02d})")
    check(abs(q2_clear - 93) <= 1,
          f"gold: Q2 clears 08:33 (sim 0{7 + q2_clear // 60}:{q2_clear % 60:02d})")

    # 4. conservation
    check(abs(sim["1"]["CA"][-1] - TOTAL) < 1e-9
          and abs(sim["2"]["CD"][-1] - TOTAL) < 1e-9,
          f"conservation: {sim['1']['CA'][-1]:.0f} loaded, "
          f"{sim['2']['CD'][-1]:.0f} discharged of {TOTAL}")

    # 5. exact fluid oracle cross-check. Both sides are inclusive-of-the-
    # tick cumulatives, so engine row k (recorded after interval 5k)
    # compares to oracle index 5k directly.
    ca1, cd1, ca2, cd2 = oracle()
    devs = []
    for series, olist in (("1CA", ca1), ("1CD", cd1), ("2CA", ca2), ("2CD", cd2)):
        link, kind = series[0], series[1:]
        d = max(abs(sim[link][kind][t] - olist[min(t * IPM, len(olist) - 1)])
                for t in range(n))
        devs.append((series, d))

    worst = max(d for _, d in devs)
    check(worst <= 2.0, "curves vs exact fluid oracle <= 2 veh ("
          + ", ".join(f"{s} {d:.0f}" for s, d in devs) + ")")

    print(f"{'PASS' if failed == 0 else 'FAIL'} ({failed} failing checks)")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

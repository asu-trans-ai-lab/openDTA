"""ST00c agent-level TA/TD gate (defects S0c-1/S0c-2/S0d; gold regenerated
at S2b - see the case settings.yml for the justification).

Primary truth for time-dependent travel time is the per-agent trajectory:
TT_f = TD_f - TA_f, asserted directly - never via the aggregate waiting
table.

Gold (1-mile 60-mph link, FFTT = 1.0 min = 10 intervals; mu = 600/h =
exactly 1 veh per 6-s interval; 30 vehicles uniformly staggered over the
1-minute period by S2b => arrivals 3 per interval, TA_i = i // 3):

    TD_i = 10 + i  (FIFO, 1/interval from interval 10)
    TT_i = (10 + i - i // 3) / 10 minutes     (TT_0 = 1.0 ... TT_29 = 3.0)

The gate asserts: all 30 vehicles present (S0d), the full sorted TT list
(S0c-1/S0c-2 + S2b staggering), and total delay = sum(TT) - 30.0 min.

Exit 0 = PASS, 1 = FAIL.
"""
import csv
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXE = os.path.join(ROOT, "..", "..", "build", "Release", "OpenDTA.exe")
CASE = os.path.join(ROOT, "cases", "ST00c_terminal_three_vehicles")
OUT = os.path.join(ROOT, "output", "ST00c")

N = 30
GOLD_TT_MIN = sorted((10 + i - i // 3) / 10.0 for i in range(N))
GOLD_TOTAL_DELAY = sum(GOLD_TT_MIN) - 1.0 * N
TOL_MIN = 0.01


def main():
    os.makedirs(OUT, exist_ok=True)
    r = subprocess.run([EXE, CASE + os.sep, OUT + os.sep],
                       capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        print(f"FAIL engine exit {r.returncode}: {r.stderr[:300]}")
        return 1

    rows = []
    with open(os.path.join(OUT, "trajectories.csv"), newline="") as f:
        for row in csv.DictReader(f):
            rows.append(row)

    failed = 0

    def check(ok, what):
        nonlocal failed
        if not ok:
            failed += 1

        print(("  ok    " if ok else "  FAIL  ") + what)

    print("ST00c agent-level TA/TD gate (S2b gold)")
    check(len(rows) == N,
          f"all {N} vehicles present in trajectories.csv "
          f"(found {len(rows)}; fewer means the S0d dedup returned)")

    tts = sorted(float(r["travel_time"]) for r in rows)
    bad = sum(1 for a, b in zip(tts, GOLD_TT_MIN[: len(tts)])
              if abs(a - b) > TOL_MIN)
    check(bad == 0,
          f"per-agent TT matches gold ladder 1.0..3.0 min ({bad} mismatches; "
          f"flat-at-FFTT means S0c-1, wrong ladder means S2b staggering)")

    if len(tts) == N:
        total_delay = sum(tts) - 1.0 * N
        check(abs(total_delay - GOLD_TOTAL_DELAY) <= N * TOL_MIN,
              f"total delay {total_delay:.2f} min vs gold {GOLD_TOTAL_DELAY:.2f}")

    print(f"{'PASS' if failed == 0 else 'FAIL'} ({failed} failing checks)")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

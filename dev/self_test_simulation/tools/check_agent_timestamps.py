"""ST00c agent-level TA/TD gate (defects S0c-1/S0c-2/S0d).

The primary truth for time-dependent travel time is the per-agent trajectory:
TT_f = TD_f - TA_f. This gate asserts it directly on the three-vehicle micro
case - never through the aggregate waiting_time[] table.

Gold (1-mile 60-mph link, FFTT = 1.0 min; mu = 600/h = exactly 1 veh per
6-s interval; three vehicles all entering in interval 0):

    agent 1: TT = 1.0 min      agent 2: TT = 1.1 min      agent 3: TT = 1.2 min

Expected RED on the pre-S0c engine, on two independent counts:
  1. S0d: output_trajectories() dedups agents by (dep_time, OD)
     (utils.cpp ~1759) -> only 1 of 3 vehicles appears at all;
  2. S0c-1: the reaches_last_link branch never calls set_dep_interval(t),
     so the reported TT stays at FFTT regardless of queueing.

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

GOLD_TT_MIN = [1.0, 1.1, 1.2]
TOL_MIN = 0.1  # one 6-s simulation interval


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

    print("ST00c agent-level TA/TD gate")
    check(len(rows) == 3,
          f"all 3 vehicles present in trajectories.csv "
          f"(found {len(rows)}; fewer means the (dep_time, OD) dedup - S0d)")

    tts = sorted(float(r["travel_time"]) for r in rows)
    for i, gold in enumerate(GOLD_TT_MIN[: len(tts)]):
        check(abs(tts[i] - gold) <= TOL_MIN,
              f"agent {i + 1} TT {tts[i]:.2f} min vs gold {gold:.1f} "
              f"(equal-to-FFTT across the board means S0c-1)")

    if len(tts) == 3:
        total_delay = sum(tts) - 3.0
        check(abs(total_delay - 0.3) <= 2 * TOL_MIN,
              f"total delay {total_delay:.2f} min vs gold 0.30")

    print(f"{'PASS' if failed == 0 else 'FAIL'} ({failed} failing checks)")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

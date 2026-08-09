"""S2c gate: profile-consuming vehicleization (quantile inverse-CDF).

Gate 1 (ST01_profile_bins, simulation now enabled): D = 1000 with bins
0.4 / 0.6 over the two half-hours -> engine CA must follow 1000 * F(t)
(the conditional CDF) to <= 1 vehicle at every minute; final CA = 1000.

Gate 2 (ST01b_equivalence_profile): the ST02a lambda(t) expressed as one
period + a 3-bin profile must reproduce the period-pieces representation -
engine CA vs the ST02a expected A_entry <= 1 veh at every minute.
Representation A (period pieces) == Representation B (departure profile).

Expected RED before S2c (profiles ignored -> uniform loading).
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

failed = 0


def check(ok, what):
    global failed
    if not ok:
        failed += 1

    print(("  ok    " if ok else "  FAIL  ") + what)


def run(case_id):
    out = os.path.join(ROOT, "output", case_id)
    os.makedirs(out, exist_ok=True)
    r = subprocess.run([EXE, os.path.join(ROOT, "cases", case_id) + os.sep, out + os.sep],
                       capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"engine exit {r.returncode}: {r.stderr[:200]}")

    ca = []
    with open(os.path.join(out, "link_performance_dta.csv"), newline="") as f:
        rd = csv.reader(f)
        next(rd)
        for row in rd:
            if row and row[0] == "1":
                ca.append(float(row[8]))

    return ca


def main():
    print("S2c gate: profile-consuming vehicleization")

    # Gate 1: ST01 bins 0.4/0.6, D = 1000, window 07:00-08:00
    ca = run("ST01_profile_bins")
    n = len(ca)
    check(abs(ca[-1] - 1000) < 1e-9, f"ST01 final CA = 1000 (sim {ca[-1]:.0f})")
    # CDF: F(t) = 0.4*t/30 for t<=30, 0.4 + 0.6*(t-30)/30 for t<=60
    # sim row k records through interval 10k inclusive -> t = k + 0.1 min
    dev = 0.0
    for k in range(min(n, 60)):
        t = k + 0.1
        f = 0.4 * t / 30 if t <= 30 else 0.4 + 0.6 * (t - 30) / 30
        dev = max(dev, abs(ca[k] - 1000 * min(f, 1.0)))

    check(dev <= 1.0, f"ST01 CA follows 1000*F(t) (max dev {dev:.2f} veh; "
                      "uniform loading means S2c not consuming the profile)")
    # row k records through interval 10k (minute k + 0.1): row 30 = minute
    # 30.1, F = 0.4 + 0.6*0.1/30 -> expected 402
    mid = ca[30]
    check(abs(mid - 402) <= 2, f"ST01 CA at bin boundary = 402 +- 2 (sim {mid:.0f})")

    # Gate 2: equivalence vs the ST02a period-pieces expected A_entry
    ca_b = run("ST01b_equivalence_profile")
    a_entry = []
    with open(os.path.join(ROOT, "expected", "ST02a_step_gold_expected.csv"), newline="") as f:
        for row in csv.reader(f):
            if row and row[0].isdigit():
                a_entry.append(float(row[2]))

    m = min(len(ca_b), len(a_entry))
    dev = max(abs(ca_b[k] - a_entry[k]) for k in range(m))
    check(dev <= 1.0,
          f"equivalence: profile representation reproduces period pieces "
          f"(max |CA_B - A_entry_A| = {dev:.2f} veh over {m} minutes)")
    check(abs(ca_b[m - 1] - 2700) < 1e-9 or abs(ca_b[-1] - 2700) < 1e-9,
          f"equivalence: all 2700 vehicles loaded (sim {ca_b[-1]:.0f})")

    print(f"{'PASS' if failed == 0 else 'FAIL'} ({failed} failing checks)")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

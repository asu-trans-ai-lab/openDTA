"""S1 gate: conditional profile -> departure-bin demand conservation.

Case A (cases/ST01_profile_bins): D = 1000, bins 0.4/0.6 ->
departure_bin_demand.csv rows exactly 400 / 600.
Case B (dev/test/f03/transims): four periods x {car, truck}, D = 1000 each,
96 TRANSIMS bins per binding -> per (period, agent) sum == 1000 to 1e-9.

Expected RED before S1 lands (the engine does not emit the file yet).
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


def run(case_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    r = subprocess.run([EXE, case_dir + os.sep, out_dir + os.sep],
                       capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"engine exit {r.returncode}: {r.stderr[:300]}")

    path = os.path.join(out_dir, "departure_bin_demand.csv")
    if not os.path.exists(path):
        return None

    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def main():
    print("S1 gate: departure-bin demand")

    # Case A
    rows = run(os.path.join(ROOT, "cases", "ST01_profile_bins"),
               os.path.join(ROOT, "output", "ST01"))
    check(rows is not None, "case A: departure_bin_demand.csv produced")
    if rows is not None:
        check(len(rows) == 2, f"case A: 2 bin rows (found {len(rows)})")
        demands = sorted(float(r["demand"]) for r in rows)
        check(abs(demands[0] - 400) <= 1e-9 and abs(demands[1] - 600) <= 1e-9,
              f"case A: bin demands exactly 400/600 (found {demands})")
        check(abs(sum(demands) - 1000) <= 1e-9, "case A: conservation 1000")

    # Case B
    rows = run(os.path.join(REPO, "dev", "test", "f03", "transims"),
               os.path.join(ROOT, "output", "ST01_transims"))
    check(rows is not None, "case B: departure_bin_demand.csv produced")
    if rows is not None:
        groups = {}
        for r in rows:
            key = (r["period_id"], r["agent_type"])
            groups.setdefault(key, []).append(float(r["demand"]))

        check(len(groups) == 8, f"case B: 8 (period, agent) bindings (found {len(groups)})")
        # conditional bins are CLIPPED to the period window (15-min bins):
        # AM 06-10 -> 16, MD 10-15 -> 20, PM 15-19 -> 16, NT 19-24 -> 20
        expected_bins = {"1": 16, "2": 20, "3": 16, "4": 20}
        bad = [(k, len(v), sum(v)) for k, v in groups.items()
               if len(v) != expected_bins[k[0]] or abs(sum(v) - 1000) > 1e-9]
        check(not bad,
              "case B: every binding has its window's bin count and sums exactly to 1000"
              + ("" if not bad else f" (violations: {bad[:2]})"))

    print(f"{'PASS' if failed == 0 else 'FAIL'} ({failed} failing checks)")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

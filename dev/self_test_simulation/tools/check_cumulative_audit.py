"""S3 gate: the engine's own cumulative-departure audit output.

S3 makes the loading contract a PERMANENT engine artifact: after simulation
the engine emits cumulative_departure_audit.csv with, per (period, agent)
cohort and per clock minute, the realized cumulative departures A_sim and
the contract value A_theory = n * F(t) (bound profile CDF, or uniform for
unbound periods). This guards the whole S2a/b/c vehicleization chain as a
standing gate, independent of any link output.

Gate: for ST02a (uniform periods) and ST01b (profile-bound): every cohort
has max |A_sim - A_theory| <= 1 vehicle and final A_sim == cohort size.

Expected RED before S3 (file not emitted). Exit 0 = PASS, 1 = FAIL.
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

    path = os.path.join(out, "cumulative_departure_audit.csv")
    if not os.path.exists(path):
        return None

    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def main():
    print("S3 gate: cumulative-departure audit")
    for case_id in ("ST02a_step_gold", "ST01b_equivalence_profile"):
        rows = run(case_id)
        check(rows is not None, f"{case_id}: audit file emitted")
        if rows is None:
            continue

        cohorts = {}
        for r in rows:
            key = (r["period_id"], r["agent_type"])
            cohorts.setdefault(key, []).append(r)

        worst = 0.0
        exact = True
        for key, rs in cohorts.items():
            dev = max(abs(float(r["A_sim"]) - float(r["A_theory"])) for r in rs)
            worst = max(worst, dev)
            last = rs[-1]
            if abs(float(last["A_sim"]) - float(last["cohort_size"])) > 1e-9:
                exact = False

        check(worst <= 1.0,
              f"{case_id}: max |A_sim - A_theory| = {worst:.2f} veh over "
              f"{len(cohorts)} cohorts")
        check(exact, f"{case_id}: every cohort's final A_sim == cohort size")

    print(f"{'PASS' if failed == 0 else 'FAIL'} ({failed} failing checks)")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

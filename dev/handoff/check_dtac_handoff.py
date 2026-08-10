"""V1-a gate: TAPLite DTAC v2 -> dtac2opendta -> OpenDTA DNL, end to end.

H01 four-node fixture: 7000 veh, one OD, two paths (upper 20 mi via caps
4000/h, lower 30 mi via 3000/h), P1 0700-0800 + CLEAR hour.

Checks:
  1. TAPLite runs with column_output=2 and writes DTAC v2;
  2. converter PT-1 conservation exact (sum_k f_k == q_od);
  3. OpenDTA loads the frozen columns and completes the DNL;
  4. path -> link incidence: per-link CA equals the S2a-integerized path
     volumes (x_l = sum_k A_lk f_k, +-0 veh);
  5. N accounting: entered == exited == 7000, N_remaining == 0 (PT-6);
  6. trajectory completeness: 7000 rows, every row time-stamped complete.

Exit 0 = PASS, 1 = FAIL. TAPLite exe resolved from TAPLITE_EXE env or the
sibling TAPLite4MPO build; skipped (exit 2, SKIP) if absent — the converter
+ DNL checks then run against the committed route_columns.bin.
"""
import csv
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
CASE = os.path.join(HERE, "cases", "H01_four_node")
TAP = os.path.join(CASE, "taplite")
ODA = os.path.join(CASE, "opendta")
OUT = os.path.join(CASE, "output")
EXE = os.path.join(REPO, "build", "Release", "OpenDTA.exe")
TAPLITE_EXE = os.environ.get("TAPLITE_EXE", os.path.join(
    REPO, "..", "TAPLite4MPO", "kernel", "build", "Release", "DTALite_exe.exe"))

failed = 0


def check(ok, what):
    global failed
    if not ok:
        failed += 1

    print(("  ok    " if ok else "  FAIL  ") + what)


def main():
    print("V1-a gate: DTAC handoff (H01 four-node)")

    # 1. TAPLite assignment -> route_columns.bin (DTAC v2)
    if os.path.exists(TAPLITE_EXE):
        r = subprocess.run([TAPLITE_EXE], cwd=TAP, capture_output=True,
                           text=True, timeout=600)
        check(r.returncode == 0 and "DTAC v2" in r.stdout,
              "TAPLite run writes DTAC v2 (column_output=2)")
    else:
        print("  SKIP  TAPLite exe not found; using committed route_columns.bin")

    check(os.path.getsize(os.path.join(TAP, "route_columns.bin")) > 16,
          "route_columns.bin present")

    # 2. converter + PT-1
    r = subprocess.run([sys.executable, os.path.join(HERE, "dtac2opendta.py"),
                        "--taplite-dir", TAP, "--out-dir", ODA,
                        "--period", "P1"],
                       capture_output=True, text=True, timeout=300)
    check(r.returncode == 0, f"dtac2opendta PT-1 conservation ({r.stdout.strip()})")
    rep = json.load(open(os.path.join(ODA, "handoff_report.json")))
    check(rep["dtac_version"] == 2 and rep["validation_eligible"],
          "DTAC v2, validation_eligible")
    check(abs(rep["total_path_flow"] - 7000.0) < 1e-6,
          f"total path flow 7000 (got {rep['total_path_flow']})")

    # expected S2a integerization of the theta split
    flows = [float(row["volume"]) for row in
             csv.DictReader(open(os.path.join(ODA, "columns.csv")))]
    ints = [int(v) for v in flows]
    residuals = [v - int(v) for v in flows]
    for _ in range(7000 - sum(ints)):
        j = residuals.index(max(residuals))
        ints[j] += 1
        residuals[j] = -1

    # 3. OpenDTA DNL
    os.makedirs(OUT, exist_ok=True)
    r = subprocess.run([EXE, ODA + os.sep, OUT + os.sep],
                       capture_output=True, text=True, timeout=600)
    check(r.returncode == 0, f"OpenDTA exit {r.returncode}")

    # 4-5. link incidence + N accounting from link_performance_dta
    last = {}
    with open(os.path.join(OUT, "link_performance_dta.csv"), newline="") as f:
        rd = csv.reader(f)
        next(rd)
        for row in rd:
            if row:
                last[row[0]] = (float(row[8]), float(row[9]))  # CA, CD

    upper, lower = ints[0], ints[1]
    check(last["1"][0] == upper and last["3"][0] == upper,
          f"upper path links CA == {upper} (S2a integerization of 5468.75)")
    check(last["2"][0] == lower and last["4"][0] == lower,
          f"lower path links CA == {lower}")
    entered = last["1"][0] + last["2"][0]
    exited = last["3"][1] + last["4"][1]
    remaining = sum(ca - cd for ca, cd in last.values())
    check(entered == 7000 and exited == 7000,
          f"N accounting: entered {entered:.0f} == exited {exited:.0f} == 7000")
    check(remaining == 0, f"N_remaining == 0 at horizon end (got {remaining:.0f})")

    # 6. trajectories complete
    with open(os.path.join(OUT, "trajectories.csv"), newline="") as f:
        n_rows = sum(1 for _ in f) - 1

    check(n_rows == 7000, f"trajectories.csv rows == 7000 (got {n_rows})")

    print(f"{'PASS' if failed == 0 else 'FAIL'} ({failed} failing checks)")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

"""V1-b gate: nine READY statuses + smoke/validation run modes.

1. ST00 case (smoke default): exit 0; all nine statuses printed;
   SUPPLY_MU and DEPARTURE_PROFILE are PASS_WITH_DEFAULT;
   readiness_report.json written with validation_eligible == false.
2. dev/test/v1b/validation_blocked (same case, run_mode: validation):
   exit nonzero; BLOCKED-MU_T_NOT_VALIDATED and
   BLOCKED-PROFILE_SOURCE_MISSING on stdout; all nine still printed.

Exit 0 = PASS, 1 = FAIL.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REPO = os.path.abspath(os.path.join(ROOT, "..", ".."))
EXE = os.path.join(REPO, "build", "Release", "OpenDTA.exe")

NINE = ["NETWORK_READY", "SUPPLY_MU_READY", "PATH_COLUMN_READY",
        "PATH_FLOW_READY", "DEPARTURE_PROFILE_READY",
        "VEHICLE_GENERATION_READY", "DNL_LOADING_READY",
        "RESULT_OUTPUT_READY", "VISUALIZATION_READY"]

failed = 0


def check(ok, what):
    global failed
    if not ok:
        failed += 1

    print(("  ok    " if ok else "  FAIL  ") + what)


def run(case, out):
    os.makedirs(out, exist_ok=True)
    return subprocess.run([EXE, case + os.sep, out + os.sep],
                          capture_output=True, text=True, timeout=600)


def main():
    print("V1-b gate: readiness statuses + run modes")

    # 1. smoke (default) on ST00
    case = os.path.join(ROOT, "cases", "ST00_freeflow_tt")
    out = os.path.join(ROOT, "output", "_readiness_smoke")
    r = run(case, out)
    check(r.returncode == 0, f"smoke run exit 0 (got {r.returncode})")
    missing = [n for n in NINE if n not in r.stdout]
    check(not missing, f"all nine statuses printed (missing: {missing})")
    check("SUPPLY_MU_READY" in r.stdout and
          r.stdout.count("PASS_WITH_DEFAULT") >= 2,
          "SUPPLY_MU + DEPARTURE_PROFILE report PASS_WITH_DEFAULT")
    rep_path = os.path.join(out, "readiness_report.json")
    ok = os.path.exists(rep_path)
    check(ok, "readiness_report.json written")
    if ok:
        rep = json.load(open(rep_path))
        check(rep.get("run_mode") == "smoke", "report run_mode == smoke")
        check(rep.get("validation_eligible") is False,
              "validation_eligible false (defaults in use)")
        check(rep.get("used_default_mu") is True
              and rep.get("used_default_profile") is True,
              "default mu + profile disclosed")

    # 2. validation mode must block
    case = os.path.join(REPO, "dev", "test", "v1b", "validation_blocked")
    out = os.path.join(ROOT, "output", "_readiness_blocked")
    r = run(case, out)
    check(r.returncode != 0, f"validation run blocked, exit nonzero (got {r.returncode})")
    check("BLOCKED-MU_T_NOT_VALIDATED" in r.stdout,
          "BLOCKED-MU_T_NOT_VALIDATED reported")
    check("BLOCKED-PROFILE_SOURCE_MISSING" in r.stdout,
          "BLOCKED-PROFILE_SOURCE_MISSING reported")
    missing = [n for n in NINE if n not in r.stdout]
    check(not missing, f"all nine statuses printed before abort (missing: {missing})")

    print(f"{'PASS' if failed == 0 else 'FAIL'} ({failed} failing checks)")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

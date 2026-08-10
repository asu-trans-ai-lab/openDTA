"""V1-c gate: SupplyProvider -- link_supply.csv as the explicit mu(t) input.

sp01 step mu:   1-mi link, demand 1200/h for 1 h; mu = 1800 (0700-0730),
                600 (0730-0800); CLEAR hour uncovered -> capacity 3600.
                Fluid truth: w1 free (CD(0730)=600), w2 bottleneck
                (CD(0800)=900, queue peak ~300), all out by horizon.
sp02 signal:    demand 900/h; 30 s green mu=3600 / 30 s red mu=0 cycles
                (HHMMSS windows). CD moves ONLY in green; CD(0800)=900.
sp03 unit:      mu_unit=veh/min -> nonzero exit, BLOCKED-SUPPLY_UNIT_UNDEFINED.
sp04 validation: full-coverage supply + run_mode validation ->
                SUPPLY_MU_READY: PASS printed (still blocked on profile).

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
V1C = os.path.join(REPO, "dev", "test", "v1c")

failed = 0


def check(ok, what):
    global failed
    if not ok:
        failed += 1

    print(("  ok    " if ok else "  FAIL  ") + what)


def run(name):
    case = os.path.join(V1C, name)
    out = os.path.join(ROOT, "output", "_v1c_" + name)
    os.makedirs(out, exist_ok=True)
    r = subprocess.run([EXE, case + os.sep, out + os.sep],
                       capture_output=True, text=True, timeout=600)
    return r, out


def link1_series(out):
    ca, cd, q = [], [], []
    with open(os.path.join(out, "link_performance_dta.csv"), newline="") as f:
        rd = csv.reader(f)
        next(rd)
        for row in rd:
            if row and row[0] == "1":
                ca.append(float(row[8]))
                cd.append(float(row[9]))
                q.append(float(row[11]))

    return ca, cd, q


def main():
    print("V1-c gate: SupplyProvider mu(t)")

    # sp01 step mu
    r, out = run("sp01_step_mu")
    check(r.returncode == 0, f"sp01 exit 0 (got {r.returncode})")
    if r.returncode == 0:
        ca, cd, q = link1_series(out)
        # fluid oracle with fftt = 1 min: w1 free -> CD(0730) = 20*29 = 580;
        # w2 mu = 10/min vs virtual arrivals 20/min -> queue 300 at 0800,
        # CD(0800) = 580 + 300 = 880
        check(abs(cd[30] - 580) <= 2, f"sp01 CD(0730) == 580 +-2 (sim {cd[30]:.0f})")
        # row k records AFTER interval k*ipm (inclusive convention), so the
        # 0800 row already contains one CLEAR-fallback interval; assert the
        # w2 discharge rate away from both boundaries instead: 20 min at
        # mu = 600/h is exactly 200 veh
        check(abs((cd[55] - cd[35]) - 200) <= 2,
              f"sp01 w2 discharge 200 veh over minutes 35-55 (sim {cd[55] - cd[35]:.0f})")
        peak = max(q)
        check(abs(peak - 300) <= 5, f"sp01 queue peak ~300 (sim {peak:.0f})")
        check(cd[-1] == 1200 and q[-1] == 0,
              f"sp01 all 1200 discharged, queue 0 at horizon (CD {cd[-1]:.0f})")
        check("links_from_supply" in open(os.path.join(out, "readiness_report.json")).read(),
              "sp01 readiness report carries supply provenance")

    # sp02 signal
    r, out = run("sp02_signal")
    check(r.returncode == 0, f"sp02 exit 0 (got {r.returncode})")
    if r.returncode == 0:
        ca, cd, q = link1_series(out)
        check(880 <= cd[60] <= 900, f"sp02 CD(0800) in [880, 900] (sim {cd[60]:.0f})")
        check(cd[-1] == 900, f"sp02 all 900 discharged (CD {cd[-1]:.0f})")
        # per-minute discharge never exceeds the green share (30 s at 3600/h)
        per_min = [cd[t] - cd[t - 1] for t in range(1, len(cd))]
        check(max(per_min) <= 30 + 1e-9,
              f"sp02 per-minute discharge <= 30 (green share; max {max(per_min):.0f})")
        # the signal discriminator: red arrivals wait up to 30 s, so mean TT
        # exceeds fftt (1.0 min exactly under free flow) by a real delay
        tts = [float(row["travel_time"]) for row in
               csv.DictReader(open(os.path.join(out, "trajectories.csv")))]
        mean_tt = sum(tts) / len(tts)
        check(1.03 <= mean_tt <= 1.6,
              f"sp02 mean TT shows signal delay in (1.03, 1.6) min (sim {mean_tt:.3f})")

    # sp03 undefined unit
    r, _ = run("sp03_unit_undefined")
    check(r.returncode != 0, f"sp03 blocked, exit nonzero (got {r.returncode})")
    check("BLOCKED-SUPPLY_UNIT_UNDEFINED" in (r.stdout + r.stderr),
          "sp03 BLOCKED-SUPPLY_UNIT_UNDEFINED reported")

    # sp04 validation mode with full coverage
    r, _ = run("sp04_validation_supply")
    check("SUPPLY_MU_READY: PASS" in r.stdout,
          "sp04 SUPPLY_MU_READY unblocked by full-coverage supply (validation)")
    check(r.returncode != 0 and "BLOCKED-PROFILE_SOURCE_MISSING" in r.stdout,
          "sp04 still blocked overall on the unbound profile")

    print(f"{'PASS' if failed == 0 else 'FAIL'} ({failed} failing checks)")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

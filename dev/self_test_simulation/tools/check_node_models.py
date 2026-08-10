"""F05 gate: node models (merge / diverge / lane-drop chain).

ST06 (Knoop 11.1.1, Daganzo-mid merge, spatial queue):
  A_approach 4 ln @ 1050 (= 4200/h) + B_ramp 1 ln (1800/h) -> downstream
  2 ln @ 1200 (R = 2400/h). Demand 3500 / 1500 veh/h, both oversaturating
  R jointly. Frozen truth: q_i = mid{d_i, R - d_j, p_i R} with p = 4:1
  gives q_A = 1920/h, q_B = 480/h (README). Gates:
    1. approach discharge plateau 1920 / 480 (+-2%);
    2. downstream throughput plateau 2400/h (+-2%);
    3. invariance: raising d_B 1500 -> 2000 must leave q_B at 480 (+-2%)
       (the priority share, not the demand, sets the allocation).

ST07 (Knoop 11.1.2, FIFO diverge, spatial queue):
  shared 2 ln (3600/h) -> {main_exit 3600/h, off_ramp 1 ln 1200/h}.
  Demand 1200 main / 2400 ramp. Ramp storage (200 veh) fills ~ minute 10;
  then the shared exit queue is FIFO-blocked by ramp-bound heads: shared
  discharge = 1200 / (2/3) = 1800/h, main throughput = 600/h. Frozen
  truth (README): q_main = 600, q_ramp = 1200. Bands +-5%.

ST08 (lane-drop chain, kinematic wave):
  8 x 0.25 mi segments, last drops to 1 lane (1800/h = 3 per 6 s,
  integer). Demand 3000/h for 30 min, then 1200/h. Gates:
    1. bottleneck (seg8) discharge == 30 veh/min EXACTLY while queued;
    2. chain conservation CD_i(row) == CA_{i+1}(row) on every row;
    3. queue-onset monotonicity: segments congest strictly upstream in
       sequence (onset_8 <= onset_7 <= ...) for every segment that ever
       queues (front-trajectory numeric freeze deferred to the
       FD-contract follow-up, per mini-spec).

Exit 0 = PASS, 1 = FAIL.
"""
import csv
import os
import shutil
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


def run_case(case_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    r = subprocess.run([EXE, case_dir + os.sep, out_dir + os.sep],
                       capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        check(False, f"engine exit {r.returncode} on {os.path.basename(case_dir)}: "
              + r.stderr[:200])
        return None

    series = {}
    with open(os.path.join(out_dir, "link_performance_dta.csv"), newline="") as f:
        rd = csv.reader(f)
        next(rd)
        for row in rd:
            if not row:
                continue

            s = series.setdefault(row[0], {"CA": [], "CD": [], "Q": []})
            s["CA"].append(float(row[8]))
            s["CD"].append(float(row[9]))
            s["Q"].append(float(row[11]))

    return series


def rate_per_hour(cd, m0, m1):
    """Mean discharge over minutes [m0, m1), veh/h, from cumulative CD."""
    return (cd[m1] - cd[m0]) / (m1 - m0) * 60


def st06():
    print("ST06 merge (Daganzo-mid, 4:1 priorities)")
    case = os.path.join(ROOT, "cases", "ST06_merge_daganzo")
    sim = run_case(case, os.path.join(ROOT, "output", "ST06_merge_daganzo"))
    if sim is None:
        return

    # plateau window: both approaches queued well before minute 20 under
    # any candidate node model; horizon ends at minute 60
    q_a = rate_per_hour(sim["1"]["CD"], 20, 50)
    q_b = rate_per_hour(sim["2"]["CD"], 20, 50)
    q_d = rate_per_hour(sim["3"]["CA"], 20, 50)
    check(abs(q_a - 1920) <= 0.02 * 1920,
          f"A_approach plateau 1920/h +-2% (sim {q_a:.0f})")
    check(abs(q_b - 480) <= 0.02 * 480,
          f"B_ramp plateau 480/h +-2% (sim {q_b:.0f})")
    check(abs(q_d - 2400) <= 0.02 * 2400,
          f"downstream inflow plateau 2400/h +-2% (sim {q_d:.0f})")

    # invariance: d_B 1500 -> 2000 with both approaches congested leaves
    # the allocation at the priority shares
    variant = os.path.join(ROOT, "output", "_st06_invariance_case")
    if os.path.isdir(variant):
        shutil.rmtree(variant)

    shutil.copytree(case, variant)
    with open(os.path.join(variant, "demand.csv"), "w", newline="") as f:
        f.write("o_zone_id,d_zone_id,volume\n1,3,3500\n2,3,2000\n")

    sim2 = run_case(variant, os.path.join(ROOT, "output", "_st06_invariance_out"))
    if sim2 is None:
        return

    q_a2 = rate_per_hour(sim2["1"]["CD"], 20, 50)
    q_b2 = rate_per_hour(sim2["2"]["CD"], 20, 50)
    check(abs(q_b2 - 480) <= 0.02 * 480,
          f"invariance: d_B 1500->2000 leaves q_B at 480/h (sim {q_b2:.0f})")
    check(abs(q_a2 - 1920) <= 0.02 * 1920,
          f"invariance: q_A stays 1920/h (sim {q_a2:.0f})")


def st07():
    print("ST07 diverge (FIFO throttling via shared exit queue)")
    sim = run_case(os.path.join(ROOT, "cases", "ST07_diverge_fifo"),
                   os.path.join(ROOT, "output", "ST07_diverge_fifo"))
    if sim is None:
        return

    # ramp storage full ~ minute 10; plateau window 20-50
    q_main = rate_per_hour(sim["2"]["CA"], 20, 50)
    q_ramp = rate_per_hour(sim["3"]["CA"], 20, 50)
    check(abs(q_main - 600) <= 0.05 * 600,
          f"main throughput plateau 600/h +-5% (sim {q_main:.0f})")
    check(abs(q_ramp - 1200) <= 0.05 * 1200,
          f"ramp inflow plateau 1200/h +-5% (sim {q_ramp:.0f})")
    # no independent-caps bypass: shared-link discharge collapses to
    # 1800/h, far under its 3600/h service
    q_shared = rate_per_hour(sim["1"]["CD"], 20, 50)
    check(abs(q_shared - 1800) <= 0.05 * 1800,
          f"shared-link discharge throttled to 1800/h +-5% (sim {q_shared:.0f})")


def st08():
    print("ST08 lane-drop chain (kinematic wave)")
    sim = run_case(os.path.join(ROOT, "cases", "ST08_lanedrop_chain"),
                   os.path.join(ROOT, "output", "ST08_lanedrop_chain"))
    if sim is None:
        return

    ids = [str(i) for i in range(1, 9)]
    n = len(sim["8"]["CD"])

    # 1. bottleneck discharge 1800/h EXACT (30/min) while queued
    q8 = sim["8"]["Q"]
    queued = [t for t in range(1, n - 1) if q8[t] > 0 and q8[t - 1] > 0]
    bad = sum(1 for t in queued
              if abs(sim["8"]["CD"][t] - sim["8"]["CD"][t - 1] - 30) > 1e-9)
    check(len(queued) > 10 and bad == 0,
          f"bottleneck discharge == 30/min exactly on {len(queued)} queued minutes "
          f"({bad} violations)")

    # 2. chain conservation CD_i == CA_{i+1} on every row
    worst = 0
    for i in range(len(ids) - 1):
        d = max(abs(sim[ids[i]]["CD"][t] - sim[ids[i + 1]]["CA"][t])
                for t in range(n))
        worst = max(worst, d)

    check(worst == 0, f"chain conservation CD_i == CA_(i+1) every row (max dev {worst:.0f})")

    # 3. queue-onset monotonic upstream. Onset = first minute with a
    # substantive queue (>= 5 veh): the origin link's queue column shows a
    # 1-2 veh loading transient at minute 1 that is not spillback.
    onsets = []
    for i in ids:
        q = sim[i]["Q"]
        onset = next((t for t in range(n) if q[t] >= 5), None)
        onsets.append(onset)

    seq = [(i, o) for i, o in zip(ids, onsets) if o is not None]
    mono = all(seq[k][1] >= seq[k + 1][1] for k in range(len(seq) - 1))
    check(len(seq) >= 2 and mono,
          "queue onsets march upstream: "
          + ", ".join(f"seg{i}@{o}" for i, o in seq))


def main():
    print("F05 gate: node models (ST06 merge / ST07 diverge / ST08 chain)")
    st06()
    st07()
    st08()
    print(f"{'PASS' if failed == 0 else 'FAIL'} ({failed} failing checks)")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

"""S5a-S5d gate: the time-dependent TT -> speed -> SQM trajectory chain.

S5a  TT^curve(t) = D^-1(A(t)) - t        (FIFO inversion of the oracle
                                          cumulative curves - the general
                                          oracle, valid for any mu(t))
S5b  TT^agent(t) = mean(TD - TA) by entry minute from trajectories.csv
     (the PRIMARY truth) - dual-path consistency |agent - curve| <= 0.2 min
     (one 6-s interval + minute-grid rounding), and the engine-reported TT
     column must match the agent truth on minutes with entrants.
S5c  experienced average speed v_bar(t) = 60 L / TT(t); the engine-reported
     speed strip must match the agent-reconstructed strip (mismatch = FAIL).
S5d  (ST04a only) constant-mu SQM split per paper Eq. (8)-(10):
         t_Q = t_w vF/(vF-vQ),  t_F = FFTT - t_w vQ/(vF-vQ),  d_Q = vQ t_Q
     with vF = 60, vQ = mu/(kj - mu/w) = 15 mph (w = 12, kj = 180).
     Paper-exact assertions: t_w max 2.0, TT max 3.0, t_Q max 2.6667,
     t_F min 0.3333, d_Q max 0.6667 mi, v_bar min 20 mph, t_F > 0 for all.
     Emits reports/tt_sqm_ST04a.html: dual speed strips + the x-t
     trajectory fan (paper Fig. 2(d), two-segment vF/vQ paths).

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

VF, VQ, L, FFTT = 60.0, 15.0, 1.0, 1.0
failed = 0


def check(ok, what):
    global failed
    if not ok:
        failed += 1

    print(("  ok    " if ok else "  FAIL  ") + what)


def hhmmss_to_min(s):
    h, m, sec = (s.split(":") + ["0", "0"])[:3]
    return int(h) * 60 + int(m) + float(sec) / 60


def run(case_id):
    out = os.path.join(ROOT, "output", case_id)
    os.makedirs(out, exist_ok=True)
    r = subprocess.run([EXE, os.path.join(ROOT, "cases", case_id) + os.sep, out + os.sep],
                       capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"engine exit {r.returncode}")

    agents = []
    with open(os.path.join(out, "trajectories.csv"), newline="") as f:
        for row in csv.DictReader(f):
            dep = hhmmss_to_min(row["dep_time"]) - 7 * 60   # clock 07:00 = 0
            agents.append((dep, float(row["travel_time"])))

    perf = {"TT": [], "speed": []}
    with open(os.path.join(out, "link_performance_dta.csv"), newline="") as f:
        rd = csv.reader(f)
        next(rd)
        for row in rd:
            if row and row[0] == "1":
                perf["TT"].append(float(row[5]))
                perf["speed"].append(float(row[7]) if row[7] != "inf" else 0.0)

    return agents, perf


def interval_oracle(case_id):
    """S5a support: the exact 6-s-grid oracle, recomputed from the generator
    (interval-resolution FIFO inversion needs interval-resolution curves)."""
    import generate_analytical_cases as g
    fn, mu = g.CASES[case_id]
    pieces = fn()
    ipm = g.SECONDS_IN_MIN_GRID
    total = sum(dd for dd, _ in pieces)
    H = (total + 180) * ipm
    arr = [0] * (H + 1)
    beg = 0
    for dur, vol in pieces:
        m = dur * ipm
        for i in range(int(vol)):
            arr[beg + i * m // int(vol)] += 1

        beg += m

    fftt_i = int(round(g.FFTT_MIN * ipm))
    cap = mu * 6 // 3600
    ca = [0] * (H + 1)
    cq = [0] * (H + 1)
    d = [0] * (H + 1)
    run = 0
    for j in range(H + 1):
        run += arr[j]
        ca[j] = run
        cq[j] = ca[j - fftt_i] if j >= fftt_i else 0
        d[j] = min(cq[j], (d[j - 1] if j else 0) + cap)

    return ca, d


def tt_curve_cohort(ca, d, minute):
    """S5a: mean FIFO-inversion TT (minutes) for vehicles entering in the
    given minute, on the exact interval grid."""
    j0, j1 = minute * 10, minute * 10 + 10
    tts = []
    dep_j = j0
    for rank in range(ca[j0 - 1] if j0 else 0, ca[j1 - 1]):
        # entry interval of this rank
        ej = j0
        while ca[ej] < rank + 1:
            ej += 1

        while dep_j < len(d) and d[dep_j] < rank + 1:
            dep_j += 1

        if dep_j < len(d):
            tts.append((dep_j - ej) / 10.0)

    return sum(tts) / len(tts) if tts else None


def analyze(case_id, sqm=False):
    print(f"case {case_id}")
    agents, perf = run(case_id)
    ca_o, d_o = interval_oracle(case_id)

    # cohorts by entry minute
    cohorts = {}
    for dep, tt in agents:
        cohorts.setdefault(int(dep), []).append(tt)

    tt_agent = {m: sum(v) / len(v) for m, v in cohorts.items()}

    # S5b: dual-path consistency (agent timestamps vs exact-interval FIFO
    # inversion of the oracle curves) - <= 0.2 min = one interval + rounding
    devs = []
    for m, tta in sorted(tt_agent.items()):
        ttc = tt_curve_cohort(ca_o, d_o, m)
        if ttc is not None:
            devs.append(abs(tta - ttc))

    check(max(devs) <= 0.2 if devs else False,
          f"S5b dual-path |TT_agent - TT_curve| <= 0.2 min "
          f"(max {max(devs):.3f} over {len(devs)} entrant minutes)")

    # S5b: engine-reported TT column vs agent truth
    dev_rep = [abs(perf["TT"][m] - tta) for m, tta in tt_agent.items()
               if m < len(perf["TT"])]
    check(max(dev_rep) <= 0.2,
          f"S5b engine-reported TT matches agent truth <= 0.2 min "
          f"(max {max(dev_rep):.3f})")

    # S5c: reported speed strip vs agent-reconstructed strip. The reported
    # TT is truncated to 0.1-min steps, which propagates into speed as
    # ~60*L*0.06/TT^2 - the tolerance follows that bound (tightest at
    # congested minutes, wide only where speed is near free-flow anyway).
    worst = 0.0
    ok_all = True
    for m, tta in tt_agent.items():
        if m < len(perf["speed"]) and tta > 0:
            dev = abs(perf["speed"][m] - 60.0 * L / tta)
            tol = 0.5 + 60.0 * L * 0.11 / (tta * tta)
            worst = max(worst, dev)
            if dev > tol:
                ok_all = False

    check(ok_all,
          f"S5c reported vs reconstructed speed within the truncation bound "
          f"(worst {worst:.2f} mph)")

    if not sqm:
        return agents, tt_agent, perf

    # ---- S5d: SQM split (constant mu, paper Eq. 8-10), paper-exact numbers.
    # Maxima are PER VEHICLE (the paper's worst vehicle), not per-cohort
    # means - minute averaging dilutes the peak.
    tt_all = [tt for _, tt in agents]
    tw_max = max(tt_all) - FFTT
    tt_max = max(tt_all)
    tws = {m: tta - FFTT for m, tta in tt_agent.items()}
    tq_max = tw_max * VF / (VF - VQ)
    tf_min = FFTT - tw_max * VQ / (VF - VQ)
    tq = {m: tw * VF / (VF - VQ) for m, tw in tws.items()}
    tf = {m: FFTT - tw * VQ / (VF - VQ) for m, tw in tws.items()}
    dq_max = VQ * tq_max / 60.0
    vbar_min = 60.0 * L / tt_max

    check(abs(tw_max - 2.0) <= 0.1, f"S5d t_w max = 2.0 min (sim {tw_max:.3f})")
    check(abs(tt_max - 3.0) <= 0.1, f"S5d TT max = 3.0 min (sim {tt_max:.3f})")
    check(abs(tq_max - 2.6667) <= 0.15,
          f"S5d t_Q max = 2.6667 min (sim {tq_max:.4f})")
    check(abs(tf_min - 0.3333) <= 0.05,
          f"S5d t_F min = 0.3333 min (sim {tf_min:.4f})")
    check(abs(dq_max - 0.6667) <= 0.04,
          f"S5d d_Q max = 0.6667 mi (sim {dq_max:.4f})")
    check(abs(vbar_min - 20.0) <= 0.7,
          f"S5d v_bar min = 20 mph (sim {vbar_min:.2f})")
    check(tf_min > 0,
          "S5d SQM applicability: t_F > 0 for every vehicle")

    write_sqm_html(case_id, agents, tt_agent, perf, tws)
    return agents, tt_agent, perf


def write_sqm_html(case_id, agents, tt_agent, perf, tws):
    """Dual speed strips + the x-t trajectory fan (paper Fig. 2(d))."""
    W, H, PAD = 900, 360, 50
    n_min = max(int(d) for d, _ in agents) + 5

    def strip(values, y0, label):
        cells = []
        cw = (W - 2 * PAD) / n_min
        for m in range(n_min):
            v = values.get(m, VF) if isinstance(values, dict) else (
                values[m] if m < len(values) else VF)
            r = max(0.0, min(1.0, v / VF))
            cells.append(f'<rect x="{PAD + m*cw:.1f}" y="{y0}" width="{cw+0.5:.1f}" '
                         f'height="26" fill="rgb({int(220*(1-r)+30)},{int(180*r+40)},60)"/>')

        return (f'<text x="{PAD}" y="{y0-5}" font-size="12">{label}</text>'
                + "".join(cells))

    rec_speed = {m: 60.0 * L / tt for m, tt in tt_agent.items()}
    strips = (f"<h3>Dual speed strips (green = free flow) — mismatch = FAIL</h3>"
              f"<svg viewBox='0 0 {W} 110' width='100%' style='background:#fff;"
              f"border:1px solid #ddd'>{strip(perf['speed'], 22, 'engine-reported')}"
              f"{strip(rec_speed, 78, 'reconstructed from agent TD - TA')}</svg>")

    # x-t fan: every 15th vehicle, two-segment SQM path
    lines = []
    xmax = n_min
    for dep, tt in sorted(agents)[::15]:
        tw = max(0.0, tt - FFTT)
        tf = FFTT - tw * VQ / (VF - VQ)
        x2 = tf * VF / 60.0                     # miles at the queue tail
        px = lambda t: PAD + t / xmax * (W - 2 * PAD)
        py = lambda x: H - PAD - x / L * (H - 2 * PAD)
        lines.append(f'<polyline fill="none" stroke="#1f77b4" stroke-width="1.2" '
                     f'points="{px(dep):.1f},{py(0):.1f} '
                     f'{px(dep+tf):.1f},{py(x2):.1f} '
                     f'{px(dep+tt):.1f},{py(L):.1f}"/>')

    fan = (f"<h3>Space–time trajectory fan (every 15th vehicle; slope break = "
           f"v_F 60 → v_Q 15 mph, paper Fig. 2(d))</h3>"
           f"<svg viewBox='0 0 {W} {H}' width='100%' style='background:#fff;"
           f"border:1px solid #ddd'>"
           f"<line x1='{PAD}' y1='{H-PAD}' x2='{W-PAD}' y2='{H-PAD}' stroke='#888'/>"
           f"<line x1='{PAD}' y1='{PAD}' x2='{PAD}' y2='{H-PAD}' stroke='#888'/>"
           f"<text x='{W//2}' y='{H-10}' font-size='12' text-anchor='middle'>"
           f"minutes from 07:00</text>"
           f"<text x='16' y='{H//2}' font-size='12' transform='rotate(-90 16 {H//2})' "
           f"text-anchor='middle'>miles</text>" + "".join(lines) + "</svg>")

    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    with open(os.path.join(ROOT, "reports", f"tt_sqm_{case_id}.html"), "w",
              encoding="utf-8") as f:
        f.write(f"<!doctype html><html><head><meta charset='utf-8'>"
                f"<title>{case_id} TT/SQM chain</title>"
                f"<style>body{{font-family:Segoe UI,Arial;margin:24px}}</style>"
                f"</head><body><h1>{case_id} — S5 TT/speed/SQM chain</h1>"
                f"<p>v_F = 60 mph, v_Q = 15 mph (mu/(kj - mu/w), w = 12, "
                f"kj = 180); TT = t_F + t_Q per paper Eq. (8)-(10).</p>"
                + strips + fan + "</body></html>")


def main():
    print("S5 gate: TT -> speed -> SQM chain")
    analyze("ST02a_step_gold", sqm=False)
    analyze("ST04a_sqm_paper", sqm=True)
    print(f"{'PASS' if failed == 0 else 'FAIL'} ({failed} failing checks)")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

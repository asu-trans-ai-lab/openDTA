"""Run an analytical self-test case through the OpenDTA engine, compare with
the fluid-oracle expected truth, and emit a self-contained HTML validation
report (inline SVG, zero external dependencies) so a human can eyeball the
cumulative curves, queue profile, flow rates, and speed strip - in the spirit
of the QVDF space-time visualization tools.

Usage:
    python validate_case.py <case_id> [exe_path]
    python validate_case.py --all [exe_path]

Exit 0 = all validated cases PASS, 1 = any FAIL.
"""
import csv
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_EXE = os.path.join(ROOT, "..", "..", "build", "Release", "OpenDTA.exe")

TOL_CONSERVATION = 1e-9   # vehicles, on totals (integer inputs)
TOL_CUMULATIVE = 1.0      # vehicles, at checkpoints
TOL_EVENT_MIN = 1.0       # minutes
TOL_AGGREGATE = 0.01      # relative, Qmax / delay


def read_expected(case_id):
    path = os.path.join(ROOT, "expected", f"{case_id}_expected.csv")
    series = {"minute": [], "lambda_vph": [], "A_entry": [], "A_service": [], "D": [], "Q": []}
    summary = {}
    with open(path, newline="") as f:
        for row in csv.reader(f):
            if not row or not row[0]:
                continue

            if row[0] == "minute":
                continue

            if row[0] == "summary":
                summary[row[1]] = None if row[2] == "" or row[2] == "None" else float(row[2])
                continue

            series["minute"].append(int(row[0]))
            series["lambda_vph"].append(float(row[1]))
            series["A_entry"].append(float(row[2]))
            series["A_service"].append(float(row[3]))
            series["D"].append(float(row[4]))
            series["Q"].append(float(row[5]))

    return series, summary


def run_engine(case_id, exe):
    cdir = os.path.join(ROOT, "cases", case_id)
    out = os.path.join(ROOT, "output", case_id)
    os.makedirs(out, exist_ok=True)
    r = subprocess.run([exe, cdir + os.sep, out + os.sep],
                       capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"engine exit {r.returncode}: {r.stderr.strip()[:500]}")

    return out


def read_sim(out_dir):
    """link_performance_dta.csv rows for link 1 are one per minute in order.

    Clock convention (verified empirically: sim row t == oracle minute t+1
    with zero deviation): the engine records state AFTER processing the
    minute, while the oracle (gold v2 convention) records the continuous
    value AT t. The comparison below therefore aligns sim row t with oracle
    minute t+1 - a documented recording convention, not a tolerance."""
    sim = {"CA": [], "CD": [], "Q": [], "TT": [], "speed": []}
    with open(os.path.join(out_dir, "link_performance_dta.csv"), newline="") as f:
        rd = csv.reader(f)
        next(rd)
        for row in rd:
            if not row or row[0] != "1":
                continue

            sim["TT"].append(float(row[5]))
            sim["speed"].append(float(row[7]) if row[7] != "inf" else float("inf"))
            sim["CA"].append(float(row[8]))
            sim["CD"].append(float(row[9]))
            sim["Q"].append(float(row[11]))

    return sim


def first_crossing(vals, up=True, thresh=0.5):
    if up:
        return next((i for i, v in enumerate(vals) if v > thresh), None)

    peak = max(range(len(vals)), key=lambda i: vals[i]) if vals else None
    if peak is None:
        return None

    return next((i for i in range(peak, len(vals)) if vals[i] < thresh), None)


def validate(case_id, exe):
    series, summary = read_expected(case_id)
    out = run_engine(case_id, exe)
    sim = read_sim(out)

    # align to the engine's after-the-tick recording: drop oracle minute 0 so
    # oracle index t corresponds to sim row t (see read_sim docstring)
    for key in ("lambda_vph", "A_entry", "A_service", "D", "Q"):
        series[key] = series[key][1:]

    n = min(len(sim["CA"]), len(series["A_entry"]) - 1)
    checks = []

    def check(name, ok, detail):
        checks.append((name, bool(ok), detail))

    # conservation
    n_total = summary["total_vehicles"]
    check("total vehicles loaded (CA final == N)",
          abs(sim["CA"][n - 1] - n_total) <= TOL_CONSERVATION,
          f"sim {sim['CA'][n-1]:.0f} vs N {n_total:.0f}")
    check("all vehicles discharged (CD final == N)",
          abs(sim["CD"][n - 1] - n_total) <= TOL_CONSERVATION,
          f"sim {sim['CD'][n-1]:.0f} vs N {n_total:.0f}")

    # checkpoint deviations (sim row t reports state at minute t)
    dev_ca = max(abs(sim["CA"][t] - series["A_entry"][t]) for t in range(n))
    dev_cd = max(abs(sim["CD"][t] - series["D"][t]) for t in range(n))
    dev_q = max(abs(sim["Q"][t] - series["Q"][t]) for t in range(n))
    check(f"max |CA - A_entry| <= {TOL_CUMULATIVE} veh", dev_ca <= TOL_CUMULATIVE, f"{dev_ca:.2f}")
    check(f"max |CD - D| <= {TOL_CUMULATIVE} veh", dev_cd <= TOL_CUMULATIVE, f"{dev_cd:.2f}")
    check(f"max |Q - Q*| <= {TOL_CUMULATIVE} veh", dev_q <= TOL_CUMULATIVE, f"{dev_q:.2f}")

    # events
    for name, gold_key, sim_t in (
            ("queue onset T0", "T0_min", first_crossing(sim["Q"], up=True)),
            ("queue clearance T3", "T3_min", first_crossing(sim["Q"], up=False))):
        gold_t = summary[gold_key]
        if gold_t is None:
            continue

        # sim row t is oracle minute t+1 (after-the-tick recording)
        sim_min = sim_t + 1 if sim_t is not None else None
        ok = sim_min is not None and abs(sim_min - gold_t) <= TOL_EVENT_MIN
        check(f"{name} within {TOL_EVENT_MIN:.0f} min", ok, f"sim {sim_min} vs gold {gold_t:.0f}")

    qmax_sim = max(sim["Q"][:n]) if n else 0
    qmax_gold = summary["Qmax_veh"]
    ok = abs(qmax_sim - qmax_gold) <= max(TOL_AGGREGATE * qmax_gold, 1.0)
    check("Qmax within 1%", ok, f"sim {qmax_sim:.1f} vs gold {qmax_gold:.1f}")

    delay_sim = sum((sim["Q"][t - 1] + sim["Q"][t]) / 2 for t in range(1, n)) / 60.0
    delay_gold = summary["total_delay_veh_h"]
    ok = abs(delay_sim - delay_gold) <= max(TOL_AGGREGATE * delay_gold, 1.0)
    check("total delay within 1%", ok, f"sim {delay_sim:.1f} vs gold {delay_gold:.1f} veh-h")

    passed = all(ok for _, ok, _ in checks)
    write_html(case_id, series, summary, sim, n, checks, passed)
    return passed, checks


# ---------------- HTML report (inline SVG, self-contained) ----------------

W, H, PAD = 900, 300, 45


def polyline(xs, ys, xmax, ymax, color, width=2, dash=""):
    if not xs or ymax <= 0:
        return ""

    pts = " ".join(f"{PAD + x / xmax * (W - 2 * PAD):.1f},"
                   f"{H - PAD - y / ymax * (H - 2 * PAD):.1f}" for x, y in zip(xs, ys))
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<polyline fill="none" stroke="{color}" stroke-width="{width}"{d} '
            f'points="{pts}"/>')


def axes(xmax, ymax, xlab, ylab, xstep):
    s = [f'<line x1="{PAD}" y1="{H-PAD}" x2="{W-PAD}" y2="{H-PAD}" stroke="#888"/>',
         f'<line x1="{PAD}" y1="{PAD}" x2="{PAD}" y2="{H-PAD}" stroke="#888"/>']
    x = 0
    while x <= xmax:
        px = PAD + x / xmax * (W - 2 * PAD)
        s.append(f'<line x1="{px:.0f}" y1="{H-PAD}" x2="{px:.0f}" y2="{H-PAD+4}" stroke="#888"/>')
        s.append(f'<text x="{px:.0f}" y="{H-PAD+16}" font-size="10" text-anchor="middle">{x}</text>')
        x += xstep

    for i in range(5):
        v = ymax * i / 4
        py = H - PAD - v / ymax * (H - 2 * PAD)
        s.append(f'<text x="{PAD-6}" y="{py:.0f}" font-size="10" text-anchor="end">{v:.0f}</text>')

    s.append(f'<text x="{W//2}" y="{H-6}" font-size="11" text-anchor="middle">{xlab}</text>')
    s.append(f'<text x="14" y="{H//2}" font-size="11" text-anchor="middle" '
             f'transform="rotate(-90 14 {H//2})">{ylab}</text>')
    return "".join(s)


def svg_chart(title, curves, xmax, xlab, ylab):
    ymax = max((max(ys) if ys else 0) for _, ys, _, _ in curves) * 1.08 + 1e-9
    body = axes(xmax, ymax, xlab, ylab, max(10, int(xmax // 10 // 10 * 10) or 10))
    legend = []
    for i, (name, ys, color, dash) in enumerate(curves):
        body += polyline(list(range(len(ys))), ys, xmax, ymax, color, 2, dash)
        lx = PAD + 8 + i * 170
        legend.append(f'<line x1="{lx}" y1="16" x2="{lx+22}" y2="16" stroke="{color}" '
                      f'stroke-width="3" {"stroke-dasharray=" + chr(34) + dash + chr(34) if dash else ""}/>'
                      f'<text x="{lx+27}" y="20" font-size="11">{name}</text>')

    return (f"<h3>{title}</h3><svg viewBox='0 0 {W} {H}' width='100%' "
            f"style='max-width:{W}px;background:#fff;border:1px solid #ddd'>"
            + "".join(legend) + body + "</svg>")


def speed_strip(sim, n, ffs=60.0):
    cells = []
    cw = (W - 2 * PAD) / max(1, n)
    for t in range(n):
        v = sim["speed"][t]
        r = max(0.0, min(1.0, (v if v == v and v != float("inf") else ffs) / ffs))
        # green (free flow) -> red (stopped)
        red, green = int(220 * (1 - r) + 30), int(180 * r + 40)
        cells.append(f'<rect x="{PAD + t*cw:.1f}" y="28" width="{cw+0.5:.1f}" height="36" '
                     f'fill="rgb({red},{green},60)"/>')

    ticks = "".join(f'<text x="{PAD + t/max(1,n)*(W-2*PAD):.0f}" y="80" font-size="10" '
                    f'text-anchor="middle">{t}</text>' for t in range(0, n + 1, max(10, n // 10)))
    return ("<h3>Space–time speed strip (single link; green = free flow, red = queued)</h3>"
            f"<svg viewBox='0 0 {W} 90' width='100%' style='max-width:{W}px;background:#fff;"
            f"border:1px solid #ddd'>{''.join(cells)}{ticks}</svg>")


def write_html(case_id, series, summary, sim, n, checks, passed):
    lam_sim = [0.0] + [(sim["CA"][t] - sim["CA"][t - 1]) * 60 for t in range(1, n)]
    out_rate = [0.0] + [(sim["CD"][t] - sim["CD"][t - 1]) * 60 for t in range(1, n)]

    rows = "".join(
        f"<tr class='{ 'ok' if ok else 'bad'}'><td>{'PASS' if ok else 'FAIL'}</td>"
        f"<td>{name}</td><td>{detail}</td></tr>" for name, ok, detail in checks)

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>{case_id} — OpenDTA self-test validation</title>
<style>
 body {{ font-family: Segoe UI, Arial, sans-serif; margin: 24px; color: #222; }}
 h1 span.badge {{ padding: 3px 12px; border-radius: 6px; color: #fff;
                  background: {'#2e8b57' if passed else '#c0392b'}; font-size: 60%; }}
 table {{ border-collapse: collapse; margin: 12px 0; }}
 td, th {{ border: 1px solid #ccc; padding: 4px 10px; font-size: 13px; }}
 tr.ok td:first-child {{ background: #2e8b57; color: #fff; font-weight: bold; }}
 tr.bad td:first-child {{ background: #c0392b; color: #fff; font-weight: bold; }}
 .meta {{ color: #666; font-size: 13px; }}
</style></head><body>
<h1>{case_id} <span class="badge">{'PASS' if passed else 'FAIL'}</span></h1>
<p class="meta">OpenDTA point-queue engine vs exact fluid oracle
(lambda(t) piecewise-constant, mu = {summary['mu_vph']:.0f}/h, fftt =
{summary['fftt_min']:.0f} min). Oracle: A_service(t) = A_entry(t − fftt);
Q = A_service − D (matches the engine's queue definition). Generated by
tools/validate_case.py — self-contained, no external assets.</p>
<table><tr><th>result</th><th>check</th><th>detail</th></tr>{rows}</table>
{svg_chart("Cumulative curves — sim (solid) vs oracle (dashed)",
           [("sim CA", sim["CA"][:n], "#1f77b4", ""),
            ("sim CD", sim["CD"][:n], "#d62728", ""),
            ("oracle A_entry", series["A_entry"][:n], "#1f77b4", "6,4"),
            ("oracle D", series["D"][:n], "#d62728", "6,4")],
           n, "minute", "vehicles")}
{svg_chart("Queue profile Q(t)",
           [("sim queue", sim["Q"][:n], "#9467bd", ""),
            ("oracle Q", series["Q"][:n], "#2ca02c", "6,4")],
           n, "minute", "vehicles")}
{svg_chart("Flow rates — arrivals vs discharge vs mu",
           [("sim inflow (dCA/dt)", lam_sim, "#1f77b4", ""),
            ("sim outflow (dCD/dt)", out_rate, "#d62728", ""),
            ("oracle lambda", series["lambda_vph"][:n], "#7f7f7f", "6,4"),
            ("mu", [summary["mu_vph"]] * n, "#000000", "2,4")],
           n, "minute", "veh/h")}
{speed_strip(sim, n)}
</body></html>"""

    rdir = os.path.join(ROOT, "reports")
    os.makedirs(rdir, exist_ok=True)
    with open(os.path.join(rdir, f"{case_id}.html"), "w", encoding="utf-8") as f:
        f.write(html)


def main():
    args = sys.argv[1:]
    exe = DEFAULT_EXE
    if args and args[-1].lower().endswith(".exe"):
        exe = args.pop()

    if args and args[0] == "--all":
        case_ids = sorted(d for d in os.listdir(os.path.join(ROOT, "cases"))
                          if d.startswith("ST02"))
    else:
        case_ids = args[:1]

    if not case_ids:
        print(__doc__)
        return 2

    all_ok = True
    index_rows = []
    for cid in case_ids:
        try:
            ok, checks = validate(cid, exe)
        except Exception as e:
            ok, checks = False, [("engine run", False, str(e)[:300])]
            print(f"{cid}: ERROR {e}")

        all_ok &= ok
        n_ok = sum(1 for _, o, _ in checks if o)
        print(f"{cid}: {'PASS' if ok else 'FAIL'} ({n_ok}/{len(checks)} checks)")
        index_rows.append(
            f"<tr class='{ 'ok' if ok else 'bad'}'><td>{'PASS' if ok else 'FAIL'}</td>"
            f"<td><a href='{cid}.html'>{cid}</a></td><td>{n_ok}/{len(checks)}</td></tr>")

    if len(case_ids) > 1:
        with open(os.path.join(ROOT, "reports", "index.html"), "w", encoding="utf-8") as f:
            f.write("<!doctype html><html><head><meta charset='utf-8'>"
                    "<title>OpenDTA analytical self-test index</title><style>"
                    "body{font-family:Segoe UI,Arial;margin:24px} table{border-collapse:collapse}"
                    "td,th{border:1px solid #ccc;padding:4px 12px}"
                    "tr.ok td:first-child{background:#2e8b57;color:#fff}"
                    "tr.bad td:first-child{background:#c0392b;color:#fff}</style></head><body>"
                    "<h1>OpenDTA analytical self-test — case index</h1>"
                    "<table><tr><th>result</th><th>case</th><th>checks</th></tr>"
                    + "".join(index_rows) + "</table></body></html>")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())

"""LDN034_BD (I-395 corridor subarea) PM smoke pilot -- the MVP acceptance
chain on real agency data:

  wide Cube shapefile + OMX  ->  TAPLite GMNS (PM period resolve)
  ->  TAPLite UE (column_output=2)  ->  DTAC v2  ->  dtac2opendta
  ->  OpenDTA fixed-path DNL  ->  vehicle results + HTML panel

SMOKE MODE: uniform departure profile (no profile source), constant mu from
PM hourly capacities, vehicle classes collapsed to auto (disclosed) --
validation_eligible = false by construction. Agency data stays outside the
repo: every path comes from the command line.

Decoded dataset facts (see TAPLite4MPO/private_docs/NVTA_DATA_AUDIT_*.md):
- OMX zone index = TAZ - 1 (0-based); PM OD universe = internal TAZ
  {2400,2401,2402} + boundary external stations {3723,3724,3725,3726};
- centroid/zone nodes are exactly those 7 ids (all < 38112 = first through
  node); FTYPE=0 rows are centroid connectors (code 0);
- PM supply: PMLANE lanes, IPMHRLNCAP veh/h/lane; VDF code FTYPE*100+ATYPE
  -> link_bpr.csv period-3 (PM) alpha/beta;
- lengths in miles (DISTANCE), speeds in mph (I4PMFFSPD).

Usage:
  python ldn034_pilot.py --data-dir <LDN034_BD> --work-dir <scratch>
      [--taplite-exe <DTALite_exe.exe>] [--opendta-exe <OpenDTA.exe>]
"""
import argparse
import base64
import csv
import io
import json
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))

ZONES = [2400, 2401, 2402, 3723, 3724, 3725, 3726]
FIRST_THROUGH = 38112
PM_START, PM_END = 15, 19       # 4 h assignment period
CLEAR_HOURS = 1                 # DNL drain buffer


def build_taplite_case(data_dir, case_dir):
    import openmatrix as omx
    import pyogrio

    gdf = pyogrio.read_dataframe(os.path.join(data_dir, "SubArea_NTWK_LDN034_LL.shp"))
    bpr = {}
    with open(os.path.join(data_dir, "link_bpr.csv"), newline="",
              encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                code = int(row["VDF_code"])
            except ValueError:
                continue

            bpr[code] = (float(row["VDF_alpha3"]), float(row["VDF_beta3"]))

    os.makedirs(case_dir, exist_ok=True)
    nodes = {}
    for _, r in gdf.iterrows():
        for n, pt in ((int(r.A), r.geometry.coords[0]),
                      (int(r.B), r.geometry.coords[-1])):
            nodes.setdefault(n, pt)

    with open(os.path.join(case_dir, "node.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["node_id", "x_coord", "y_coord", "zone_id"])
        for n in sorted(nodes):
            x, y = nodes[n]
            w.writerow([n, f"{x:.6f}", f"{y:.6f}", n if n in ZONES else 0])

    links = []
    with open(os.path.join(case_dir, "link.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["link_id", "from_node_id", "to_node_id", "length", "lanes",
                    "free_speed", "capacity", "link_type", "VDF_alpha", "VDF_beta"])
        for _, r in gdf.iterrows():
            code = 0 if r.FTYPE == 0 else int(r.FTYPE) * 100 + int(r.ATYPE)
            alpha, beta = bpr.get(code, (0.15, 4.0))
            ffs = int(r.I4PMFFSPD) if r.FTYPE != 0 else 60
            w.writerow([int(r.ID), int(r.A), int(r.B), f"{r.DISTANCE:.4f}",
                        int(r.PMLANE), ffs, int(r.IPMHRLNCAP), int(r.FTYPE),
                        alpha, beta])
            links.append((int(r.ID), float(r.DISTANCE)))

    with omx.open_file(os.path.join(data_dir, "PM_SubArea.OMX")) as f:
        tot = None
        for n in f.list_matrices():
            a = np.array(f[n])
            tot = a if tot is None else tot + a

    idx = [z - 1 for z in ZONES]   # 0-based index = TAZ - 1 (audited)
    total = 0.0
    with open(os.path.join(case_dir, "demand.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["o_zone_id", "d_zone_id", "volume"])
        for i, oz in enumerate(ZONES):
            for j, dz in enumerate(ZONES):
                v = float(tot[idx[i], idx[j]])
                if oz != dz and v > 0:
                    w.writerow([oz, dz, f"{v:.4f}"])
                    total += v

    with open(os.path.join(case_dir, "settings.csv"), "w", newline="") as f:
        f.write("number_of_iterations,number_of_processors,demand_period_starting_hours,"
                "demand_period_ending_hours,first_through_node_id,base_demand_mode,"
                "route_output,vehicle_output,log_file,odme_mode,odme_vmt,column_output\n"
                f"30,4,{PM_START},{PM_END},{FIRST_THROUGH},0,0,0,0,0,0,2\n")

    with open(os.path.join(case_dir, "mode_type.csv"), "w", newline="") as f:
        f.write("mode_type,vot,pce,occ,operating_cost,demand_file,dedicated_shortest_path\n"
                "auto,10,1,1,0,demand.csv,1\n")

    return total, links


def build_opendta_case(taplite_case, case_dir):
    os.makedirs(case_dir, exist_ok=True)
    for name in ("node.csv",):
        rows = list(csv.DictReader(open(os.path.join(taplite_case, name))))

    with open(os.path.join(case_dir, "node.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["node_id", "name", "x_coord", "y_coord", "node_type",
                    "ctrl_type", "zone_id", "geometry"])
        for r in rows:
            z = r["zone_id"] if r["zone_id"] != "0" else ""
            w.writerow([r["node_id"], "", r["x_coord"], r["y_coord"], "", "",
                        z, f"POINT ({r['x_coord']} {r['y_coord']})"])

    with open(os.path.join(case_dir, "link.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["link_id", "name", "from_node_id", "to_node_id",
                    "facility_type", "link_type", "dir_flag", "length", "lanes",
                    "free_speed", "capacity", "geometry"])
        for r in csv.DictReader(open(os.path.join(taplite_case, "link.csv"))):
            w.writerow([r["link_id"], "", r["from_node_id"], r["to_node_id"],
                        "", r["link_type"], 1, r["length"], r["lanes"],
                        r["free_speed"], r["capacity"], ""])

    # demand files exist for the period declaration; load_columns skips them
    for name, vol in (("demand.csv", ""), ("demand_zero.csv", "0")):
        with open(os.path.join(case_dir, name), "w", newline="") as f:
            f.write("o_zone_id,d_zone_id,volume\n")
            if vol:
                f.write(f"{ZONES[0]},{ZONES[1]},{vol}\n")

    clear_end = PM_END + CLEAR_HOURS
    with open(os.path.join(case_dir, "settings.yml"), "w", newline="\n") as f:
        f.write(f"""---
# LDN034_BD PM smoke (generated by ldn034_pilot.py -- agency-derived, do
# not commit). Frozen TAPLite paths, uniform departure profile (SMOKE),
# point queue at 6 s.
user_equilibrium:
  load_columns: true
  column_gen_num: 0
  column_opd_num: 0

simulation:
  enable: true
  resolution: 6
  traffic_flow_model: point_queue

agent_type:
  - type: a
    name: auto
    flow_type: 0
    pce: 1
    vot: 10
    free_speed: 60
    use_link_ffs: true

demand_period:
  - period: PM
    period_id: 1
    time_period: {PM_START:02d}00-{PM_END:02d}00
    demand:
      - file_name: demand.csv
        agent_type: auto
  - period: CLEAR
    period_id: 2
    time_period: {PM_END:02d}00-{clear_end:02d}00
    demand:
      - file_name: demand_zero.csv
        agent_type: auto
""")


def parse_hms(s):
    h, m, sec = (list(map(int, s.split(":"))) + [0])[:3]
    return h * 60 + m + sec / 60.0


def render_report(out_dir, work, total_demand, links):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # departures (5-min bins) + completion from trajectories
    deps, tts, completed = [], [], 0
    with open(os.path.join(out_dir, "trajectories.csv"), newline="") as f:
        for row in csv.DictReader(f):
            deps.append(parse_hms(row["dep_time"]))
            tts.append(float(row["travel_time"]))
            completed += row["trip_completed"] == "c"

    n = len(deps)

    # link time series
    series = {}
    with open(os.path.join(out_dir, "link_performance_dta.csv"), newline="") as f:
        rd = csv.reader(f)
        next(rd)
        for row in rd:
            s = series.setdefault(row[0], {"Q": [], "CA": [], "CD": [], "TT": []})
            s["Q"].append(float(row[11]))
            s["CA"].append(float(row[8]))
            s["CD"].append(float(row[9]))
            s["TT"].append(float(row[5]))

    real_ids = [str(i) for i, _ in links]
    qmat = np.array([series[i]["Q"] for i in real_ids if i in series])
    worst = max(series, key=lambda i: max(series[i]["Q"]))

    figs = []

    fig, ax = plt.subplots(figsize=(8, 2.8))
    ax.hist([d / 60 for d in deps], bins=np.arange(PM_START, PM_END + CLEAR_HOURS + 0.001, 5 / 60))
    ax.set(title=f"Departures (uniform SMOKE profile), n={n}",
           xlabel="hour of day", ylabel="veh / 5 min")
    figs.append(fig)

    fig, ax = plt.subplots(figsize=(8, 3.2))
    t = np.arange(qmat.shape[1]) / 60 + PM_START
    im = ax.imshow(qmat, aspect="auto", cmap="inferno",
                   extent=[t[0], t[-1], qmat.shape[0] - 0.5, -0.5])
    ax.set(title="Queue heatmap (veh), links x time", xlabel="hour of day",
           ylabel="link row")
    fig.colorbar(im, ax=ax, label="queue (veh)")
    figs.append(fig)

    fig, ax = plt.subplots(figsize=(8, 3.0))
    s = series[worst]
    ax.plot(t, s["CA"], label="cumulative arrivals")
    ax.plot(t, s["CD"], label="cumulative departures")
    ax2 = ax.twinx()
    ax2.plot(t, s["Q"], color="tab:red", alpha=0.6, label="queue")
    ax.set(title=f"Worst link {worst}: A/D curves and queue",
           xlabel="hour of day", ylabel="cumulative veh")
    ax2.set_ylabel("queue (veh)")
    ax.legend(loc="upper left")
    figs.append(fig)

    imgs = []
    for fig in figs:
        buf = io.BytesIO()
        fig.tight_layout()
        fig.savefig(buf, format="png", dpi=110)
        plt.close(fig)
        imgs.append(base64.b64encode(buf.getvalue()).decode())

    entered = sum(series[i]["CA"][-1] for i in series
                  if i in {r for r, _ in [(str(l), d) for l, d in links]}) if False else None
    remaining = int(round(sum(s["CA"][-1] - s["CD"][-1] for s in series.values())))
    vmt = sum((series[str(l)]["CD"][-1]) * d for l, d in links if str(l) in series)
    vht = sum(tts) / 60.0

    summary = {
        "mode": "SMOKE", "validation_eligible": False,
        "used_default_profile": True, "used_default_mu": True,
        "total_demand": total_demand, "vehicles_generated": n,
        "trips_completed": completed, "n_remaining_on_network": remaining,
        "VMT_link_based": round(vmt, 1), "VHT_trajectory_based": round(vht, 1),
        "mean_TT_min": round(float(np.mean(tts)), 2),
        "p95_TT_min": round(float(np.percentile(tts, 95)), 2),
    }
    with open(os.path.join(work, "run_summary.json"), "w") as f:
        json.dump(summary, f, indent=1)

    rows = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in summary.items())
    html = ("<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<title>LDN034_BD PM smoke - OpenDTA DNL</title>"
            "<style>body{font-family:Segoe UI,Arial;margin:24px;max-width:900px}"
            "table{border-collapse:collapse}td{border:1px solid #ccc;padding:3px 10px}"
            "img{max-width:100%}</style></head><body>"
            "<h1>LDN034_BD (I-395) PM smoke &mdash; TAPLite &rarr; OpenDTA DNL</h1>"
            "<p><b>SMOKE MODE</b>: uniform departure profile, constant &mu; from "
            "PM hourly capacities, classes collapsed to auto. "
            "<i>validation_eligible = false.</i></p>"
            f"<table>{rows}</table>"
            + "".join(f"<p><img src='data:image/png;base64,{b}'></p>" for b in imgs)
            + "</body></html>")
    path = os.path.join(work, "pilot_report.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    return summary, path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--work-dir", required=True)
    ap.add_argument("--taplite-exe", default=os.path.join(
        REPO, "..", "TAPLite4MPO", "kernel", "build", "Release", "DTALite_exe.exe"))
    ap.add_argument("--opendta-exe", default=os.path.join(
        REPO, "build", "Release", "OpenDTA.exe"))
    args = ap.parse_args()

    work = os.path.abspath(args.work_dir)
    tap_case = os.path.join(work, "taplite")
    oda_case = os.path.join(work, "opendta")
    out_dir = os.path.join(work, "output")

    print("[1/5] building TAPLite GMNS case (PM resolve)")
    total, links = build_taplite_case(args.data_dir, tap_case)
    print(f"      demand total {total:.1f} veh over {PM_END - PM_START} h")

    print("[2/5] TAPLite UE -> DTAC v2")
    r = subprocess.run([os.path.abspath(args.taplite_exe)], cwd=tap_case,
                       capture_output=True, text=True, timeout=1800)
    tail = [l for l in r.stdout.splitlines() if "column_output" in l or "iter No = 29" in l]
    print("      " + "\n      ".join(tail[-2:]))
    if r.returncode != 0:
        print(r.stdout[-2000:])
        return 1

    print("[3/5] dtac2opendta (PT-1 boundary gate)")
    build_opendta_case(tap_case, oda_case)
    r = subprocess.run([sys.executable, os.path.join(HERE, "dtac2opendta.py"),
                        "--taplite-dir", tap_case, "--out-dir", oda_case,
                        "--period", "PM"], capture_output=True, text=True)
    print("      " + r.stdout.strip())
    if r.returncode != 0:
        return 1

    print("[4/5] OpenDTA fixed-path DNL")
    os.makedirs(out_dir, exist_ok=True)
    r = subprocess.run([os.path.abspath(args.opendta_exe), oda_case + os.sep,
                        out_dir + os.sep], capture_output=True, text=True,
                       timeout=1800)
    if r.returncode != 0:
        print(r.stdout[-1500:], r.stderr[-500:])
        return 1

    print("[5/5] report")
    summary, path = render_report(out_dir, work, total, links)
    for k, v in summary.items():
        print(f"      {k}: {v}")

    print(f"      report: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

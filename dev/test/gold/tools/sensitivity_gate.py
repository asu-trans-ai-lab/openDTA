"""Demand-scaling sensitivity gate: run the fluid gold solver at scaled demand
(default 0.8x / 1.0x / 1.2x) and check physics monotonicity - no analytical
values required, only ordering:
  * total system delay non-decreasing in the scale factor
  * peak queue non-decreasing
  * completed throughput non-decreasing (nothing lost as demand grows)
  * congested-duration non-decreasing
Usage: python tools/sensitivity_gate.py cases/<case> [scales...]
"""
import csv, json, shutil, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from gold_solver import GoldSolver

def run_scaled(case, scale):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / 'case'
        shutil.copytree(Path(case) / 'input', root / 'input')
        p = root / 'input' / 'columns.csv'
        rows = list(csv.DictReader(open(p)))
        for r in rows:
            r['volume_veh'] = str(float(r['volume_veh']) * scale)
        with open(p, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
        s = GoldSolver(str(root), strict=False)
        mins, _out = s.run()
        delay = sum(max(0.0, float(r['instantaneous_travel_time_sec']) - float(r['fftt_sec']))
                    for r in mins) / 60.0
        peak = max(float(r['exit_queue_pce']) for r in mins)
        cong = sum(1 for r in mins if float(r['exit_queue_pce']) > 1e-6)
        links = {r['link_id'] for r in mins}
        # completed = final CD on terminal links (no downstream successor)
        succ = {a for seq in s.routes.values() for a in seq[:-1]}
        term = [l for l in links if l not in succ]
        done = sum(max(float(r['CD_pce']) for r in mins if r['link_id'] == l) for l in term)
        done -= 0.0
        return {'scale': scale, 'leftover_pce': round(s.leftover_pce, 2), 'delay_veh_min_proxy': round(delay, 2), 'peak_queue_pce': round(peak, 2),
                'congested_rows': cong, 'completed_pce': round(done, 2)}

def main(case, scales):
    res = [run_scaled(case, s) for s in scales]
    ok = True
    for a, b in zip(res, res[1:]):
        for k, sense in (('delay_veh_min_proxy', '<='), ('peak_queue_pce', '<='),
                         ('congested_rows', '<='), ('completed_pce', '<=')):
            if not a[k] <= b[k] + 1e-6:
                ok = False
                print(f"MONOTONICITY FAIL {k}: {a['scale']}x -> {a[k]}  vs  {b['scale']}x -> {b[k]}")
    for r in res:
        print(r)
    print('sensitivity gate:', 'PASS' if ok else 'FAIL')
    return 0 if ok else 2

if __name__ == '__main__':
    case = sys.argv[1]
    scales = [float(x) for x in sys.argv[2:]] or [0.8, 1.0, 1.2]
    sys.exit(main(case, scales))

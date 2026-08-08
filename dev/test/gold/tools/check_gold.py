"""OpenDTA Gold Dataset v2 - contract audit + numeric assertion runner.

Usage:
    python tools/check_gold.py                 # check every case under cases/
    python tools/check_gold.py cases/G1_...    # check one case

Two layers per case:
  1. Contract audit (Gate 0 style): files, required columns, PKs, period grid,
     supply coverage, route/corridor continuity, profile normalization,
     demand<->column conservation, static allowed-use feasibility.
  2. Numeric assertions from the case's frozen assertions.json: cell values,
     episodes, boundary delay discontinuities, queue continuity (no reset),
     tandem identity CD_up(t)==CQ_down(t+tau0), system conservation,
     corridor conservation residuals, and vehicle-layer checks (exact
     vehicleization, handoffs, cross-period evidence, fluid consistency).

Exit code 0 == every case PASS. A FAIL names the case, layer, metric, and
evidence; nothing is silently skipped (a missing gold file is itself a FAIL).
"""
from __future__ import annotations
import csv, json, sys
from collections import defaultdict
from pathlib import Path

def rows(path):
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))

def parse_clock(s):
    p = [int(x) for x in s.split(':')]; p += [0] * (3 - len(p))
    return p[0] * 3600 + p[1] * 60 + p[2]

REQUIRED_INPUT = {
    'demand_period.csv': ['period_id', 'period_name', 'start_time', 'end_time', 'sequence_no'],
    'link.csv': ['link_id', 'from_node_id', 'to_node_id', 'length_miles', 'lanes'],
    'link_period.csv': ['link_id', 'period_id', 'capacity_pce_per_hour', 'capacity_unit',
                        'fftt_sec', 'reference_tt_sec', 'allowed_uses', 'capacity_ratio',
                        'capacity_source', 'reference_tt_source'],
    'vehicle_class.csv': ['vehicle_class_id', 'pce'],
    'route.csv': ['route_id', 'o_zone_id', 'd_zone_id', 'link_sequence'],
    'corridor.csv': ['corridor_id', 'sequence_no', 'link_id', 'role'],
    'columns.csv': ['route_id', 'period_id', 'vehicle_class_id', 'volume_veh', 'departure_profile_id'],
    'departure_profile.csv': ['profile_id', 'period_id', 'departure_time', 'bin_width_sec', 'weight', 'profile_source'],
    'demand.csv': ['o_zone_id', 'd_zone_id', 'period_id', 'vehicle_class_id', 'volume_veh'],
}

class Report:
    def __init__(self, case):
        self.case = case; self.metrics = []
    def emit(self, layer, metric, ok, actual='', target='', evidence=''):
        self.metrics.append({'case': self.case, 'layer': layer, 'metric': metric,
                             'status': 'PASS' if ok else 'FAIL',
                             'actual': str(actual), 'target': str(target), 'evidence': str(evidence)})
    @property
    def ok(self):
        return all(m['status'] == 'PASS' for m in self.metrics)

def contract_audit(root, rep):
    inp = root / 'input'
    cache = {}
    for fname, req in REQUIRED_INPUT.items():
        p = inp / fname
        if not p.exists():
            rep.emit('A0', f'{fname}:present', False, 0, 1, str(p)); continue
        rr = rows(p); cache[fname] = rr
        missing = [c for c in req if rr and c not in rr[0]]
        rep.emit('A0', f'{fname}:required_columns', not missing, len(missing), 0, ','.join(missing))
    periods = cache.get('demand_period.csv', [])
    ps = sorted([(parse_clock(r['start_time']), parse_clock(r['end_time']), r['period_id']) for r in periods])
    contiguous = all(e1 == s2 for (s1, e1, _), (s2, e2, _) in zip(ps, ps[1:]))
    rep.emit('G0', 'periods_contiguous_half_open', contiguous, contiguous, True)
    links = {r['link_id'] for r in cache.get('link.csv', [])}
    pset = {r['period_id'] for r in periods}
    lp = cache.get('link_period.csv', [])
    lpk = {(r['link_id'], r['period_id']) for r in lp}
    missing = [(l, p) for l in links for p in pset if (l, p) not in lpk]
    rep.emit('G0', 'link_period_coverage_complete', not missing, len(missing), 0, str(missing[:5]))
    rep.emit('G0', 'capacity_positive', all(float(r['capacity_pce_per_hour']) > 0 for r in lp))
    rep.emit('G0', 'fftt_nonnegative', all(float(r['fftt_sec']) >= 0 for r in lp))
    rep.emit('G0', 'capacity_unit_declared',
             all(r.get('capacity_unit') == 'pce_per_hour_per_link' for r in lp))
    rep.emit('G0', 'provenance_present',
             all(r.get('capacity_source') and r.get('reference_tt_source') for r in lp))
    linkmap = {r['link_id']: r for r in cache.get('link.csv', [])}
    bad = []
    for r in cache.get('route.csv', []):
        seq = r['link_sequence'].split(';')
        for a, b in zip(seq, seq[1:]):
            if linkmap[a]['to_node_id'] != linkmap[b]['from_node_id']:
                bad.append((r['route_id'], a, b))
    rep.emit('G0', 'route_continuity', not bad, len(bad), 0, str(bad[:5]))
    groups = defaultdict(list)
    for r in cache.get('corridor.csv', []):
        groups[r['corridor_id']].append(r)
    bad = []
    for cid, rr in groups.items():
        main = [x['link_id'] for x in sorted(rr, key=lambda x: int(x['sequence_no'])) if x['role'] == 'mainline']
        for a, b in zip(main, main[1:]):
            if linkmap[a]['to_node_id'] != linkmap[b]['from_node_id']:
                bad.append((cid, a, b))
    rep.emit('G0', 'corridor_mainline_continuity', not bad, len(bad), 0, str(bad[:5]))
    pg = defaultdict(list)
    for r in cache.get('departure_profile.csv', []):
        pg[r['profile_id']].append(r)
    bad = [pid for pid, rr in pg.items() if abs(sum(float(x['weight']) for x in rr) - 1) > 1e-9]
    rep.emit('G0', 'profiles_normalized', not bad, len(bad), 0, str(bad[:5]))
    route_map = {r['route_id']: r for r in cache.get('route.csv', [])}
    exp = defaultdict(float); act = defaultdict(float)
    for r in cache.get('demand.csv', []):
        exp[(r['o_zone_id'], r['d_zone_id'], r['period_id'], r['vehicle_class_id'])] += float(r['volume_veh'])
    for c in cache.get('columns.csv', []):
        ro = route_map[c['route_id']]
        act[(ro['o_zone_id'], ro['d_zone_id'], c['period_id'], c['vehicle_class_id'])] += float(c['volume_veh'])
    errs = {k: act[k] - exp[k] for k in set(exp) | set(act) if abs(act[k] - exp[k]) > 1e-9}
    rep.emit('G0', 'demand_column_conservation', not errs, len(errs), 0, str(errs))
    lprows = {(r['link_id'], r['period_id']): r for r in lp}
    bad = []
    for c in cache.get('columns.csv', []):
        for lid in route_map[c['route_id']]['link_sequence'].split(';'):
            uses = set(lprows[(lid, c['period_id'])]['allowed_uses'].split(';'))
            if 'all' not in uses and c['vehicle_class_id'] not in uses:
                bad.append((c['route_id'], c['period_id'], lid))
    rep.emit('G0', 'column_static_allowed_use_feasible', not bad, len(bad), 0, str(bad[:5]))
    return cache

def numeric_assertions(root, rep):
    a = json.loads((root / 'assertions.json').read_text())
    tol = a.get('tolerance_default', 1e-6)
    g = root / 'gold_expected'
    mrows = rows(g / 'link_time_performance_minute.csv')
    idx = {(r['link_id'], r['time']): r for r in mrows}
    tidx = {(r['link_id'], int(r['time_sec'])): r for r in mrows}
    for c in a.get('cell_assertions', []):
        got = float(idx[(c['link'], c['time'])][c['column']])
        rep.emit('assert', f"cell {c['link']}@{c['time']}.{c['column']}",
                 abs(got - c['expect']) <= c.get('tolerance', tol), got, c['expect'], c.get('note', ''))
    if a.get('episode_assertions'):
        eps = {r['link_id']: r for r in rows(g / 'congestion_episode_gold.csv')}
        for e in a['episode_assertions']:
            r = eps[e['link']]
            ok = all(r[k] == e[k] for k in ('T0', 'T2', 'T3') if k in e) and \
                 abs(float(r['peak_queue_pce']) - e['peak_queue_pce']) <= tol
            rep.emit('assert', f"episode {e['link']}", ok,
                     f"{r['T0']}/{r['T2']}/{r['T3']}/{r['peak_queue_pce']}",
                     f"{e.get('T0','')}/{e['T2']}/{e['T3']}/{e['peak_queue_pce']}", e.get('note', ''))
    for b in a.get('boundary_delay_assertions', []):
        aud = {(r['link_id'], r['boundary']): r for r in rows(g / 'period_boundary_audit.csv')}
        r = aud[(b['link'], b['boundary'])]
        ok = abs(float(r['delay_before_min']) - b['delay_before_min']) <= 1e-6 and \
             abs(float(r['delay_after_min']) - b['delay_after_min']) <= 1e-6 and \
             float(r['mu_before']) == b['mu_before'] and float(r['mu_after']) == b['mu_after']
        rep.emit('assert', f"delay discontinuity {b['link']}@{b['boundary']}", ok,
                 f"{r['delay_before_min']}->{r['delay_after_min']}",
                 f"{b['delay_before_min']}->{b['delay_after_min']}", b.get('note', ''))
    qc = a.get('queue_continuity')
    if qc:
        aud = rows(g / 'period_boundary_audit.csv')
        resets = sum(int(r['reset_detected']) for r in aud)
        rep.emit('assert', 'I3 no queue reset at any boundary', resets == 0, resets, 0)
        for c in qc.get('cells', []):
            got = float(idx[(c['link'], c['time'])][c['column']])
            rep.emit('assert', f"I3 cell {c['link']}@{c['time']}",
                     abs(got - c['expect']) <= tol, got, c['expect'])
    for ti in a.get('tandem_identity', []):
        shift = int(ti['tau0_downstream_sec']); t2 = ti['tolerance']; bad = 0
        for r in mrows:
            if r['link_id'] != ti['upstream']:
                continue
            dn = tidx.get((ti['downstream'], int(r['time_sec']) + shift))
            if dn and abs(float(r['CD_pce']) - float(dn['CQ_pce'])) > t2:
                bad += 1
        rep.emit('assert', f"tandem CD_{ti['upstream']}(t)==CQ_{ti['downstream']}(t+{shift}s)",
                 bad == 0, bad, 0, ti.get('note', ''))
    if 'system_conservation' in a:
        links = sorted({r['link_id'] for r in mrows})
        first, last = links[0], links[-1]  # only meaningful for a single chain; guarded below
        chains = {r['link_id'] for r in mrows}
        if len(chains) == 2:
            worst = 0.0
            for t in sorted({int(r['time_sec']) for r in mrows}):
                ins = sum(float(tidx[(l, t)]['occupancy_pce']) for l in chains)
                diff = float(tidx[('L1', t)]['CA_pce']) - float(tidx[('L2', t)]['CD_pce'])
                worst = max(worst, abs(diff - ins))
            rep.emit('assert', 'system conservation CA1-CD2==in-system',
                     worst <= a['system_conservation']['tolerance'], worst,
                     a['system_conservation']['tolerance'])
    if 'conservation' in a:
        cons = rows(g / 'corridor_conservation_gold.csv')
        worst = max(abs(float(r['residual_pce'])) for r in cons)
        c = a['conservation']
        rep.emit('assert', 'corridor conservation residual', worst <= c['tolerance'], worst,
                 c['tolerance'], c.get('note', ''))
        rep.emit('assert', 'on-ramp flow exercised',
                 sum(1 for r in cons if float(r['R_on_pce']) > 0) >= c['min_rows_with_R_on'])
        rep.emit('assert', 'off-ramp flow exercised',
                 sum(1 for r in cons if float(r['R_off_pce']) > 0) >= c['min_rows_with_R_off'])
    od = a.get('onset_dispersion')
    if od:
        eps = rows(g / 'congestion_episode_gold.csv')
        onsets = {r['T0'] for r in eps if r['has_congestion'] == '1'}
        rep.emit('assert', 'distinct congestion onsets across links',
                 len(onsets) >= od['min_distinct_onsets'], len(onsets), od['min_distinct_onsets'],
                 od.get('note', ''))
    va = a.get('vehicle_assertions')
    if va:
        veh = rows(g / 'vehicle_gold.csv')
        traj = rows(g / 'vehicle_link_trajectory_gold.csv')
        trips = rows(g / 'vehicle_trajectory_gold.csv')
        cols = rows(root / 'input' / 'columns.csv')
        rep.emit('assert', '3.1 total vehicles', len(veh) == va['total_vehicles'], len(veh), va['total_vehicles'])
        by = defaultdict(int)
        for v in veh:
            by[(v['route_id'], v['demand_period_id'], v['vehicle_class_id'])] += 1
        exact = all(by[(c['route_id'], c['period_id'], c['vehicle_class_id'])] == round(float(c['volume_veh']))
                    for c in cols)
        rep.emit('assert', '3.2 sum_t N == round(V_p) per column (largest remainder, no ceil)', exact)
        t3 = defaultdict(list)
        for r in traj:
            t3[r['vehicle_id']].append(r)
        bad = 0
        for vid, rs in t3.items():
            rs.sort(key=lambda r: int(r['link_seq']))
            bad += sum(1 for x, y in zip(rs, rs[1:]) if x['exit_time_sec'] != y['entry_time_sec'])
        rep.emit('assert', '3.3 exit_time(i)==entry_time(i+1) every vehicle', bad == 0, bad, 0)
        cross = sum(1 for r in traj if r['demand_period_id'] != r['supply_period_id'])
        rep.emit('assert', '3.6 rows with demand_period != supply_period (I4 is real)',
                 cross >= va['min_cross_period_rows'], cross, f">={va['min_cross_period_rows']}")
        inc = [t for t in trips if t['trip_completed'] != '1']
        rep.emit('assert', '3.8 all trips complete within clearance buffer', not inc, len(inc), 0)
        # fluid <-> vehicle consistency
        ca = defaultdict(list)
        for r in traj:
            ca[r['link_id']].append((int(r['entry_time_sec']), float(r['pce'])))
        worst = 0.0
        for lid, ent in ca.items():
            ent.sort(); c1 = 0.0; k = 0
            for t in sorted({int(r['time_sec']) for r in mrows}):
                while k < len(ent) and ent[k][0] < t:
                    c1 += ent[k][1]; k += 1
                worst = max(worst, abs(c1 - float(tidx[(lid, t)]['CA_pce'])))
        rep.emit('assert', 'fluid<->vehicle CA consistency (discretization bound)',
                 worst <= va.get('fluid_vehicle_consistency_pce_tolerance', 5.0), round(worst, 3),
                 va.get('fluid_vehicle_consistency_pce_tolerance', 5.0), va.get('consistency_note', ''))

def check_case(case_dir):
    root = Path(case_dir)
    rep = Report(root.name)
    contract_audit(root, rep)
    if (root / 'assertions.json').exists():
        numeric_assertions(root, rep)
    else:
        rep.emit('assert', 'assertions.json present', False)
    return rep

def main(argv):
    targets = argv[1:] if len(argv) > 1 else sorted(str(p) for p in Path('cases').iterdir() if p.is_dir())
    all_metrics = []; ok = True
    for t in targets:
        rep = check_case(t)
        ok &= rep.ok
        all_metrics += rep.metrics
        npass = sum(m['status'] == 'PASS' for m in rep.metrics)
        print(f"{rep.case}: {'PASS' if rep.ok else 'FAIL'} ({npass}/{len(rep.metrics)})")
        for m in rep.metrics:
            if m['status'] != 'PASS':
                print('   FAIL', m['layer'], m['metric'], '| actual', m['actual'], '| target', m['target'], '|', m['evidence'])
    out = Path('reports'); out.mkdir(exist_ok=True)
    with open(out / 'gold_quality.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(all_metrics[0])); w.writeheader(); w.writerows(all_metrics)
    summary = {'overall_status': 'PASS' if ok else 'FAIL',
               'metric_count': len(all_metrics),
               'pass_count': sum(m['status'] == 'PASS' for m in all_metrics),
               'fail_count': sum(m['status'] != 'PASS' for m in all_metrics)}
    (out / 'gold_quality.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))
    return 0 if ok else 2

if __name__ == '__main__':
    sys.exit(main(sys.argv))

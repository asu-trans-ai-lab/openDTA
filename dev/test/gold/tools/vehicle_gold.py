"""Vehicle-level gold layer for OpenDTA Gold Dataset v2.

Two deterministic stages, both RNG-free (invariant I9):

1) VehicleGenerator: (column volume x departure profile) -> vehicles.
   Bin counts by LARGEST-REMAINDER apportionment so sum_t N_{p,t} == round(V_p)
   exactly (gate-reference 3.1/3.2 - no ceil inflation). Within a bin, vehicles
   are spaced evenly: dep = bin_start + floor(j * width / N_bin). Ordering is
   the stable sort (route_id, period_id, vehicle_class_id, bin_time, j), and
   vehicle_id is assigned in that order -> byte-identical reruns.

2) VehicleLoader: deterministic FIFO tandem point-queue at vehicle resolution.
   Per link, a fractional service-credit accumulator (mu * dt / 3600 PCE per
   tick, deterministic - not a stochastic draw) discharges whole vehicles in
   FIFO order once their free-flow arrival time has passed. Supply (mu and
   allowed_uses) is resolved by the clock time the vehicle REACHES each link
   (invariant I4); every trajectory row carries BOTH demand_period_id and
   supply_period_id so the rows where they differ are visible evidence that
   I4 is real rather than documented.

Outputs (gold_expected/):
   vehicle_gold.csv                the generated VehiclePool
   vehicle_link_trajectory_gold.csv  the audit trail, one row per (vehicle, link)
   vehicle_trajectory_gold.csv     trip level, with trip_completed
   reconciliation_gold.csv         tap volume -> vehicleized -> entered -> completed
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

def fmt(sec):
    h, r = divmod(int(round(sec)), 3600); m, s = divmod(r, 60)
    return f'{h:02d}:{m:02d}:{s:02d}'

def write_csv(path, data):
    data = list(data); path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(data[0])); w.writeheader(); w.writerows(data)

def largest_remainder(total, weights):
    """Apportion integer `total` across bins proportionally to weights.
    Deterministic tie-break: larger remainder first, then earlier index."""
    s = sum(weights)
    quotas = [total * w / s for w in weights]
    base = [int(q) for q in quotas]
    rem = total - sum(base)
    order = sorted(range(len(weights)), key=lambda i: (-(quotas[i] - base[i]), i))
    for i in order[:rem]:
        base[i] += 1
    return base

def generate_vehicles(root):
    inp = root / 'input'
    columns = rows(inp / 'columns.csv')
    profiles = defaultdict(list)
    for r in rows(inp / 'departure_profile.csv'):
        profiles[r['profile_id']].append(r)
    vehicles = []
    columns = sorted(columns, key=lambda c: (c['route_id'], c['period_id'], c['vehicle_class_id']))
    for c in columns:
        vol = int(round(float(c['volume_veh'])))
        prof = sorted(profiles[c['departure_profile_id']], key=lambda x: parse_clock(x['departure_time']))
        counts = largest_remainder(vol, [float(x['weight']) for x in prof])
        for pr, n in zip(prof, counts):
            st = parse_clock(pr['departure_time']); width = int(pr['bin_width_sec'])
            for j in range(n):
                vehicles.append({
                    'route_id': c['route_id'], 'demand_period_id': c['period_id'],
                    'vehicle_class_id': c['vehicle_class_id'],
                    'departure_profile_id': c['departure_profile_id'],
                    'departure_time_sec': st + (j * width) // n,
                })
    vehicles.sort(key=lambda v: (v['departure_time_sec'], v['route_id'], v['vehicle_class_id']))
    for i, v in enumerate(vehicles, 1):
        v['vehicle_id'] = f'V{i:06d}'
        v['departure_time'] = fmt(v['departure_time_sec'])
    cols = ['vehicle_id', 'route_id', 'vehicle_class_id', 'demand_period_id',
            'departure_profile_id', 'departure_time', 'departure_time_sec']
    return [{k: v[k] for k in cols} for v in vehicles]

class PeriodManager:
    def __init__(self, period_rows):
        self.periods = sorted(
            [(parse_clock(r['start_time']), parse_clock(r['end_time']), r['period_id']) for r in period_rows])
    def at(self, t):
        for s, e, pid in self.periods:
            if s <= t < e:
                return pid
        raise KeyError(fmt(t))

def load_vehicles(root, vehicles):
    inp = root / 'input'
    cfg = json.load(open(inp / 'config.json', encoding='utf-8'))
    dt = int(cfg['simulation_dt_sec'])
    start = parse_clock(cfg['simulation_start']); end = parse_clock(cfg['simulation_end'])
    pm = PeriodManager(rows(inp / 'demand_period.csv'))
    classes = {r['vehicle_class_id']: float(r['pce']) for r in rows(inp / 'vehicle_class.csv')}
    routes = {r['route_id']: r['link_sequence'].split(';') for r in rows(inp / 'route.csv')}
    route_corr = {r['route_id']: r.get('corridor_id', '') for r in rows(inp / 'route.csv')}
    supply = {(r['link_id'], r['period_id']): r for r in rows(inp / 'link_period.csv')}
    links = {r['link_id'] for r in rows(inp / 'link.csv')}

    pending = defaultdict(list)     # departure tick -> vehicle dicts
    for v in vehicles:
        tick = start + ((v['departure_time_sec'] - start) // dt) * dt
        pending[tick].append(v)
    queues = {lid: [] for lid in links}   # FIFO list of live vehicle states
    credit = defaultdict(float)
    traj = []; trips = {}

    def enter(v, lid, t):
        pid = pm.at(t)
        sp = supply[(lid, pid)]
        uses = set(sp['allowed_uses'].split(';'))
        if 'all' not in uses and v['vehicle_class_id'] not in uses:
            trips[v['vehicle_id']]['trip_completed'] = 0
            trips[v['vehicle_id']]['incomplete_reason'] = 'route_infeasible_allowed_uses'
            trips[v['vehicle_id']]['blocked_link'] = lid
            return
        qlen = sum(s['pce'] for s in queues[lid] if s['ready'] < t)
        queues[lid].append({
            'v': v, 'lid': lid, 'pce': classes[v['vehicle_class_id']],
            'entry': t, 'ready': t + int(round(float(sp['fftt_sec']))),
            'entry_supply_period': pid, 'entry_queue_pce': qlen,
            'mu_at_entry': float(sp['capacity_pce_per_hour'])})

    # upstream-first order so a discharge can chain into the next link this
    # tick; the (position, link_id) key makes tie-breaks deterministic across
    # processes (I9 - plain set ordering is hash-seed dependent).
    order = sorted(links, key=lambda l: (max(
        (seq.index(l) for seq in routes.values() if l in seq), default=0), l))
    for t in range(start, end, dt):
        for v in pending.get(t, []):
            trips[v['vehicle_id']] = {'trip_completed': 1, 'incomplete_reason': '', 'blocked_link': '',
                                      'dep': v['departure_time_sec'], 'arr': None}
            enter(v, routes[v['route_id']][0], t)
        for lid in order:
            pid = pm.at(t)
            mu = float(supply[(lid, pid)]['capacity_pce_per_hour'])
            credit[lid] += mu * dt / 3600.0
            while queues[lid] and queues[lid][0]['ready'] <= t and credit[lid] >= queues[lid][0]['pce'] - 1e-12:
                s = queues[lid].pop(0)
                credit[lid] -= s['pce']
                v = s['v']; exit_t = t  # discharged during [t, t+dt), lumped at t like the fluid gold
                fftt = s['ready'] - s['entry']
                seq = routes[v['route_id']]
                traj.append({
                    'vehicle_id': v['vehicle_id'], 'route_id': v['route_id'],
                    'corridor_id': route_corr.get(v['route_id'], ''),
                    'vehicle_class_id': v['vehicle_class_id'], 'pce': s['pce'],
                    'demand_period_id': v['demand_period_id'],
                    'link_id': lid, 'link_seq': seq.index(lid) + 1,
                    'supply_period_id': s['entry_supply_period'],
                    'entry_time': fmt(s['entry']), 'entry_time_sec': s['entry'],
                    'exit_time': fmt(exit_t), 'exit_time_sec': exit_t,
                    'free_flow_time_sec': fftt,
                    'queue_delay_sec': exit_t - s['entry'] - fftt,
                    'travel_time_sec': exit_t - s['entry'],
                    'entry_queue_pce': s['entry_queue_pce'],
                    'mu_at_entry_pceph': s['mu_at_entry'],
                })
                idx = seq.index(lid)
                if idx + 1 < len(seq):
                    enter(v, seq[idx + 1], exit_t)
                else:
                    trips[v['vehicle_id']]['arr'] = exit_t
            # service credit is work-conserving only: it accumulates while a
            # ready vehicle is waiting and resets when the server idles, so an
            # idle link cannot bank capacity (mirrors the fluid server).
            if not (queues[lid] and queues[lid][0]['ready'] <= t):
                credit[lid] = 0.0
    for lid in links:
        for s in queues[lid]:
            vid = s['v']['vehicle_id']
            if trips[vid]['trip_completed'] == 1:
                trips[vid]['trip_completed'] = 0
                trips[vid]['incomplete_reason'] = ('horizon_end_in_queue' if s['ready'] <= end - dt
                                                  else 'horizon_end_in_transit')
                trips[vid]['blocked_link'] = lid
    traj.sort(key=lambda r: (r['vehicle_id'], r['link_seq']))
    trip_rows = []
    for v in vehicles:
        tr = trips[v['vehicle_id']]
        trip_rows.append({
            'vehicle_id': v['vehicle_id'], 'route_id': v['route_id'],
            'vehicle_class_id': v['vehicle_class_id'], 'demand_period_id': v['demand_period_id'],
            'departure_time': fmt(tr['dep']), 'arrival_time': fmt(tr['arr']) if tr['arr'] else '',
            'travel_time_sec': (tr['arr'] - tr['dep']) if tr['arr'] else '',
            'trip_completed': tr['trip_completed'], 'incomplete_reason': tr['incomplete_reason'],
            'blocked_link': tr['blocked_link']})
    return traj, trip_rows

def reconcile(root, vehicles, trip_rows):
    inp = root / 'input'
    out = []
    tap = defaultdict(float)
    for c in rows(inp / 'columns.csv'):
        tap[(c['route_id'], c['period_id'], c['vehicle_class_id'])] += float(c['volume_veh'])
    gen = defaultdict(int); done = defaultdict(int); ent = defaultdict(int)
    for v in vehicles:
        gen[(v['route_id'], v['demand_period_id'], v['vehicle_class_id'])] += 1
    for t in trip_rows:
        k = (t['route_id'], t['demand_period_id'], t['vehicle_class_id'])
        ent[k] += 1
        if t['trip_completed'] == 1:
            done[k] += 1
    for k in sorted(tap):
        out.append({'route_id': k[0], 'demand_period_id': k[1], 'vehicle_class_id': k[2],
                    'tap_volume_veh': tap[k], 'vehicleized_volume': gen[k],
                    'dnl_entered_volume': ent[k], 'dnl_completed_volume': done[k],
                    'vehicleization_exact': int(gen[k] == round(tap[k]))})
    return out

def main(case_dir):
    root = Path(case_dir); g = root / 'gold_expected'
    vehicles = generate_vehicles(root)
    write_csv(g / 'vehicle_gold.csv', vehicles)
    traj, trips = load_vehicles(root, vehicles)
    write_csv(g / 'vehicle_link_trajectory_gold.csv', traj)
    write_csv(g / 'vehicle_trajectory_gold.csv', trips)
    write_csv(g / 'reconciliation_gold.csv', reconcile(root, vehicles, trips))
    ncross = sum(1 for r in traj if r['demand_period_id'] != r['supply_period_id'])
    ncomplete = sum(1 for t in trips if t['trip_completed'] == 1)
    print(f'{root.name}: {len(vehicles)} vehicles, {len(traj)} vehicle-link rows, '
          f'{ncomplete}/{len(trips)} complete, {ncross} rows with demand_period != supply_period')

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '.')

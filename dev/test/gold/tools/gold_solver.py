"""OpenDTA Gold Dataset v2 - deterministic fluid point/tandem-queue reference solver.

Independent of OpenDTA. One case directory in, frozen gold out.

Semantics (documented so the numbers can be hand-checked):
  * State is RECORDED at each tick t BEFORE injecting/serving that tick, so a
    recorded row at clock t equals the continuous-time value at t. Gate-1 gold
    therefore matches the hand table verbatim (CA(08:00)=1200, Q(08:00)=266.67...).
  * Periods are half-open [s,e). The row at a boundary t_r reports the NEW
    period's mu (t_r+ view); the checker also asserts the t_r- delay using the
    previous period's mu. Queue state itself is continuous across boundaries (I3).
  * Supply for service during tick [t,t+dt) is resolved by clock t (I4):
    a queue standing at 09:00 discharges at the P3 rate, not the P2 rate.
  * mu is PCE/hour/link (I7). Demand is converted to PCE at link entry.
  * CA   = cumulative arrivals at link ENTRANCE (== upstream CD at a 1:1 node).
  * CQ   = cumulative arrivals at the EXIT QUEUE = CA shifted by fftt.
           The tandem identity CD_up(t) == CQ_down(t + fftt_down) is asserted
           on these columns (gate-reference Gate 2 assertion 1).
  * exit_time = t + TT_inst(t), stored not derived (I10).
  * experienced_tt per output bin = flow-weighted travel time of fluid that
    DEPARTED the link in that bin (vs instantaneous_tt, the snapshot). Both are
    emitted, clearly labelled, per the output specification.
"""
from __future__ import annotations
import csv, json, math, sys
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

EPS = 1e-12

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
        if not data:
            f.write(''); return
        w = csv.DictWriter(f, fieldnames=list(data[0])); w.writeheader(); w.writerows(data)

@dataclass
class Cohort:
    commodity: tuple   # (route_id, class_id, demand_period_id)
    pce: float
    pce_per_veh: float
    ready: int         # clock second the cohort reaches the exit queue
    entry: int         # clock second the cohort entered the link

class PeriodManager:
    """I1: the only authority resolving clock -> period_id."""
    def __init__(self, period_rows):
        self.periods = sorted(
            [(parse_clock(r['start_time']), parse_clock(r['end_time']), r['period_id']) for r in period_rows])
        for (s1, e1, _), (s2, e2, _) in zip(self.periods, self.periods[1:]):
            assert e1 == s2, 'periods must be contiguous'
    def at(self, t):
        for s, e, pid in self.periods:
            if s <= t < e:
                return pid
        raise KeyError(fmt(t))
    def boundaries(self):
        return [s for s, _, _ in self.periods[1:]]

class GoldSolver:
    def __init__(self, case_dir, strict=True):
        # strict=True (gold generation): the horizon must clear - a gold case
        # ending with fluid in the system is malformed. strict=False
        # (sensitivity scaling): overload is the point; leftover is measured.
        self.strict = strict
        self.root = Path(case_dir); inp = self.root / 'input'
        self.cfg = json.load(open(inp / 'config.json', encoding='utf-8'))
        self.dt = int(self.cfg['simulation_dt_sec'])
        self.outdt = int(self.cfg['output_dt_sec'])
        # I11: simulation resolution and output resolution are independent.
        # State rows are recorded on the record grid (default 60 s), while the
        # queue engine may step much finer (e.g. 6 s) so that fftt values such
        # as 66 s or 72 s land exactly on ticks instead of waiting a phantom tick.
        self.recdt = int(self.cfg.get('record_dt_sec', 60))
        assert self.outdt % self.recdt == 0 and self.recdt % self.dt == 0
        self.start = parse_clock(self.cfg['simulation_start'])
        self.end = parse_clock(self.cfg['simulation_end'])
        self.pm = PeriodManager(rows(inp / 'demand_period.csv'))
        self.links = {r['link_id']: r for r in rows(inp / 'link.csv')}
        self.classes = {r['vehicle_class_id']: float(r['pce']) for r in rows(inp / 'vehicle_class.csv')}
        self.routes = {r['route_id']: r['link_sequence'].split(';') for r in rows(inp / 'route.csv')}
        self.supply = {(r['link_id'], r['period_id']): r for r in rows(inp / 'link_period.csv')}
        for lid in self.links:
            for _, _, pid in self.pm.periods:
                assert (lid, pid) in self.supply, f'missing supply {lid} {pid}'
        self.columns = rows(inp / 'columns.csv')
        self.profiles = defaultdict(list)
        for r in rows(inp / 'departure_profile.csv'):
            self.profiles[r['profile_id']].append(r)
        self.corridor = rows(inp / 'corridor.csv') if (inp / 'corridor.csv').exists() else []
        # topological order of links along routes (upstream first)
        order, seen = [], set()
        for seq in self.routes.values():
            for lid in seq:
                if lid not in seen:
                    seen.add(lid); order.append(lid)
        # ensure upstream-before-downstream by (route position) stable pass
        self.link_order = sorted(order, key=lambda l: (max(seq.index(l) for seq in self.routes.values() if l in seq), l))

    def sp(self, lid, t):
        return self.supply[(lid, self.pm.at(t))]

    def external_rates(self):
        """t -> commodity -> veh/sec entering the FIRST link of the route at t."""
        ext = defaultdict(lambda: defaultdict(float))
        for c in self.columns:
            vol = float(c['volume_veh']); rid = c['route_id']
            key = (rid, c['vehicle_class_id'], c['period_id'])
            prof = self.profiles[c['departure_profile_id']]
            total = sum(float(x['weight']) for x in prof)
            for pr in prof:
                st = parse_clock(pr['departure_time']); width = int(pr['bin_width_sec'])
                veh = vol * float(pr['weight']) / total
                rate = veh / width
                for t in range(st, st + width, self.dt):
                    ext[t][key] += rate
        return ext

    def run(self):
        q = {lid: deque() for lid in self.links}
        ca_veh = defaultdict(float); cd_veh = defaultdict(float)
        ca_pce = defaultdict(float); cd_pce = defaultdict(float)
        ca_events = defaultdict(list)      # (t_entry, pce) for CQ shifting
        exp_tt = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))  # lid -> outbin -> [tt*veh, veh]
        minute = []
        ext = self.external_rates()

        def enter(lid, commodity, veh, t):
            if veh <= EPS:
                return
            pce_per_veh = self.classes[commodity[1]]
            sp = self.sp(lid, t)
            uses = set(sp['allowed_uses'].split(';'))
            if 'all' not in uses and commodity[1] not in uses:
                raise RuntimeError(
                    f'route_infeasible_allowed_uses: class {commodity[1]} on {lid} at {fmt(t)} '
                    f'(supply period {self.pm.at(t)})')
            pce = veh * pce_per_veh
            fftt = float(sp['fftt_sec'])
            ready = t + int(round(fftt))
            q[lid].append(Cohort(commodity, pce, pce_per_veh, ready, t))
            ca_veh[lid] += veh; ca_pce[lid] += pce
            ca_events[lid].append((t, pce, veh))

        def record(t):
            for lid in self.links:
                t_supply = min(t, self.end - 1)
                pid = self.pm.at(t_supply)
                sp = self.supply[(lid, pid)]
                # NOTE recording semantics: a cohort with ready == t reaches the
                # exit queue *during* [t, t+dt) in continuous time, so it is NOT
                # part of Q(t). Service during tick t still uses ready <= t
                # (fluid arriving within the interval is served concurrently).
                queue_pce = occ_pce = occ_veh = 0.0
                for c in q[lid]:
                    occ_pce += c.pce; occ_veh += c.pce / c.pce_per_veh
                    if c.ready < t:
                        queue_pce += c.pce
                cap = float(sp['capacity_pce_per_hour']); fftt = float(sp['fftt_sec'])
                wait = queue_pce / (cap / 3600.0) if cap > 0 else math.inf
                inst_tt = fftt + wait
                length = float(self.links[lid]['length_miles'])
                speed = length / (inst_tt / 3600.0) if inst_tt > 0 else float(self.links[lid].get('free_speed_mph', 60))
                cq_pce = sum(p for (te, p, v) in ca_events[lid] if te + int(round(fftt)) < t)
                cq_veh = sum(v for (te, p, v) in ca_events[lid] if te + int(round(fftt)) < t)
                minute.append({
                    'time_sec': t, 'time': fmt(t), 'period_id': pid, 'link_id': lid,
                    'CA_veh': round(ca_veh[lid], 9), 'CD_veh': round(cd_veh[lid], 9),
                    'CA_pce': round(ca_pce[lid], 9), 'CD_pce': round(cd_pce[lid], 9),
                    'CQ_veh': round(cq_veh, 9), 'CQ_pce': round(cq_pce, 9),
                    'occupancy_veh': round(occ_veh, 9), 'occupancy_pce': round(occ_pce, 9),
                    'exit_queue_pce': round(queue_pce, 9),
                    'capacity_pce_per_hour': cap, 'fftt_sec': fftt,
                    'instantaneous_travel_time_sec': round(inst_tt, 9),
                    'exit_time': fmt(t + inst_tt),
                    'exit_time_sec': round(t + inst_tt, 9),
                    'speed_mph': round(speed, 9),
                    'capacity_source': sp.get('capacity_source', ''),
                    'reference_tt_source': sp.get('reference_tt_source', sp.get('fftt_source', '')),
                })

        for t in range(self.start, self.end + self.dt, self.dt):
            if (t - self.start) % self.recdt == 0:
                record(t)                  # state BEFORE this tick == continuous value at t
            if t >= self.end:
                break
            for commodity, rate in ext.get(t, {}).items():
                enter(self.routes[commodity[0]][0], commodity, rate * self.dt, t)
            for lid in self.link_order:
                sp = self.sp(lid, t)       # I4: service supply resolved at clock t
                service = float(sp['capacity_pce_per_hour']) * self.dt / 3600.0
                while service > EPS and q[lid] and q[lid][0].ready <= t:
                    c = q[lid][0]
                    take = min(service, c.pce); veh = take / c.pce_per_veh
                    service -= take; c.pce -= take
                    cd_pce[lid] += take; cd_veh[lid] += veh
                    outbin = self.start + ((t - self.start) // self.outdt) * self.outdt
                    acc = exp_tt[lid][outbin]; acc[0] += (t - c.entry) * veh; acc[1] += veh
                    rid = c.commodity[0]; path = self.routes[rid]; idx = path.index(lid)
                    if idx + 1 < len(path):
                        enter(path[idx + 1], c.commodity, veh, t)
                    if c.pce <= EPS:
                        q[lid].popleft()
        leftover = {lid: sum(c.pce for c in q[lid]) for lid in self.links if q[lid]}
        if self.strict:
            assert not any(v > 1e-6 for v in leftover.values()), f'fluid left in system at horizon end: {leftover}'
        self.leftover_pce = sum(leftover.values())
        out = [dict(r) for r in minute if (int(r['time_sec']) - self.start) % self.outdt == 0]
        for r in out:
            acc = exp_tt[r['link_id']].get(int(r['time_sec']))
            r['experienced_tt_sec'] = round(acc[0] / acc[1], 9) if acc and acc[1] > EPS else ''
        return minute, out

def derive_episodes(minute, links):
    by = defaultdict(list)
    for r in minute:
        by[r['link_id']].append(r)
    out = []
    for lid in links:
        rs = by[lid]
        pos = [i for i, r in enumerate(rs) if float(r['exit_queue_pce']) > 1e-8]
        if not pos:
            out.append({'link_id': lid, 'has_congestion': 0, 'T0': '', 'T2': '', 'T3': '',
                        'P_min': 0, 'peak_queue_pce': 0, 'v_t2_mph': '', 'mu_at_t2_pceph': ''})
            continue
        i0 = min(pos); i2 = max(pos, key=lambda i: float(rs[i]['exit_queue_pce']))
        i3 = next((j for j in range(max(pos) + 1, len(rs)) if float(rs[j]['exit_queue_pce']) <= 1e-8), len(rs) - 1)
        t0, t2, t3 = (int(rs[i]['time_sec']) for i in (i0, i2, i3))
        out.append({'link_id': lid, 'has_congestion': 1, 'T0': fmt(t0), 'T2': fmt(t2), 'T3': fmt(t3),
                    'P_min': round((t3 - t0) / 60, 3), 'peak_queue_pce': rs[i2]['exit_queue_pce'],
                    'v_t2_mph': rs[i2]['speed_mph'], 'mu_at_t2_pceph': rs[i2]['capacity_pce_per_hour']})
    return out

def derive_period(minute, pm, links):
    by = defaultdict(list)
    for r in minute:
        by[(r['link_id'], r['period_id'])].append(r)
    out = []
    for lid in links:
        for s, e, pid in pm.periods:
            rs = by.get((lid, pid))
            if not rs:
                continue
            dur = (e - s) / 3600.0
            arrivals = max(float(x['CA_pce']) for x in rs) - min(float(x['CA_pce']) for x in rs)
            cap = float(rs[0]['capacity_pce_per_hour'])
            dc = arrivals / (cap * dur) if cap > 0 and dur > 0 else 0
            step = (int(rs[1]['time_sec']) - int(rs[0]['time_sec'])) / 60 if len(rs) > 1 else 0
            qmins = sum(1 for x in rs if float(x['exit_queue_pce']) > 1e-8) * step
            out.append({'link_id': lid, 'period_id': pid,
                        'arrival_pce_approx': round(arrivals, 6), 'capacity_pce_per_hour': cap,
                        'D_over_C': round(dc, 6), 'queue_duration_min': round(qmins, 3),
                        'min_speed_mph': round(min(float(x['speed_mph']) for x in rs), 6),
                        'max_queue_pce': round(max(float(x['exit_queue_pce']) for x in rs), 6)})
    return out

def derive_boundary_audit(minute, pm, links, dt):
    """I3 evidence: queue value in the ticks straddling every period boundary."""
    idx = {(r['link_id'], int(r['time_sec'])): r for r in minute}
    out = []
    for b in pm.boundaries():
        for lid in links:
            before = idx.get((lid, b - dt)); at = idx.get((lid, b))
            if not before or not at:
                continue
            q0, q1 = float(before['exit_queue_pce']), float(at['exit_queue_pce'])
            lam_max = 1e9  # continuity here means |dQ| bounded by one tick of flow, never a reset to 0
            out.append({'boundary': fmt(b), 'link_id': lid,
                        'Q_before_pce': round(q0, 9), 'Q_at_boundary_pce': round(q1, 9),
                        'mu_before': before['capacity_pce_per_hour'], 'mu_after': at['capacity_pce_per_hour'],
                        'delay_before_min': round(q1 / float(before['capacity_pce_per_hour']) * 60, 9)
                            if float(before['capacity_pce_per_hour']) > 0 else '',
                        'delay_after_min': round(q1 / float(at['capacity_pce_per_hour']) * 60, 9)
                            if float(at['capacity_pce_per_hour']) > 0 else '',
                        # a genuine reset drains MORE than one tick of capacity
                        # could physically discharge; a queue that legitimately
                        # clears at the boundary (G1: exactly 09:00) is not a reset
                        'reset_detected': int(q0 - q1 > float(before['capacity_pce_per_hour']) * dt / 3600.0 + 1e-6)})
    return out

def derive_corridor(minute, out_rows, solver):
    """corridor_time_performance + node-level conservation with declared ramps."""
    if not solver.corridor:
        return [], []
    groups = defaultdict(list)
    for r in solver.corridor:
        groups[r['corridor_id']].append(r)
    idx = defaultdict(dict)
    for r in minute:
        idx[r['link_id']][int(r['time_sec'])] = r
    times = sorted({int(r['time_sec']) for r in out_rows})
    corridor_perf, conservation = [], []
    for cid, rr in groups.items():
        rr = sorted(rr, key=lambda x: int(x['sequence_no']))
        mainline = [x for x in rr if x['role'] == 'mainline']
        ramps_on = defaultdict(list); ramps_off = defaultdict(list)
        for x in rr:
            if x['role'] == 'on_ramp':
                ramps_on[x['merge_node_id']].append(x['link_id'])
            if x['role'] == 'off_ramp':
                ramps_off[x['diverge_node_id']].append(x['link_id'])
        for t in times:
            inst = 0.0; exp_ok = True; texp = float(t); slowest, vmin = '', 1e18
            for x in mainline:
                row = idx[x['link_id']].get(t)
                if not row:
                    exp_ok = False; continue
                inst += float(row['instantaneous_travel_time_sec'])
                if float(row['speed_mph']) < vmin:
                    vmin = float(row['speed_mph']); slowest = x['link_id']
            # experienced: compose through E_a(t) on the minute grid
            for x in mainline:
                tt_row = idx[x['link_id']].get(int(round(texp / solver.dt)) * solver.dt)
                if tt_row is None:
                    exp_ok = False; break
                texp = texp + float(tt_row['instantaneous_travel_time_sec'])
            corridor_perf.append({
                'corridor_id': cid, 'time_sec': t, 'time': fmt(t),
                'model_travel_time_instantaneous_sec': round(inst, 6),
                'model_travel_time_sec': round(texp - t, 6) if exp_ok else '',
                'slowest_link': slowest, 'min_speed_mph': round(vmin, 6)})
        for up, dn in zip(mainline, mainline[1:]):
            node = solver.links[up['link_id']]['to_node_id']
            for t in times:
                ru = idx[up['link_id']].get(t); rd = idx[dn['link_id']].get(t)
                if not ru or not rd:
                    continue
                r_on = sum(float(idx[l][t]['CD_pce']) for l in ramps_on.get(node, []))
                r_off = sum(float(idx[l][t]['CA_pce']) for l in ramps_off.get(node, []))
                lhs = float(rd['CA_pce']); rhs = float(ru['CD_pce']) + r_on - r_off
                conservation.append({
                    'corridor_id': cid, 'node_id': node,
                    'upstream_link': up['link_id'], 'downstream_link': dn['link_id'],
                    'time_sec': t, 'time': fmt(t),
                    'CD_upstream_pce': round(float(ru['CD_pce']), 9),
                    'R_on_pce': round(r_on, 9), 'R_off_pce': round(r_off, 9),
                    'CA_downstream_pce': round(lhs, 9),
                    'residual_pce': round(lhs - rhs, 9)})
    return corridor_perf, conservation

def main(case_dir):
    solver = GoldSolver(case_dir)
    minute, out = solver.run()
    root = Path(case_dir); g = root / 'gold_expected'
    write_csv(g / 'link_time_performance_minute.csv', minute)
    write_csv(g / 'link_time_performance.csv', out)
    write_csv(g / 'congestion_episode_gold.csv', derive_episodes(minute, list(solver.links)))
    write_csv(g / 'period_performance_gold.csv', derive_period(minute, solver.pm, list(solver.links)))
    write_csv(g / 'period_boundary_audit.csv', derive_boundary_audit(minute, solver.pm, list(solver.links), solver.dt))
    cp, cons = derive_corridor(minute, out, solver)
    if cp:
        write_csv(g / 'corridor_time_performance_gold.csv', cp)
    if cons:
        write_csv(g / 'corridor_conservation_gold.csv', cons)
    print(f'{root.name}: {len(minute)} minute rows, {len(out)} output rows')

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '.')

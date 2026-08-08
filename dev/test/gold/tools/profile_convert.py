"""Convert wide-format departure profiles (Chicago Sketch settings.yml style:
one row per purpose, 15-min columns 5h00..4h00 wrapping midnight) into the
long-format departure_profile.csv contract, with an explicit audit + repair
policy. Never silently normalizes: the audit is emitted first, the repaired
file records both raw and normalized weights, and the normalization factor is
stored per profile so the correction is reversible and reviewable.

Usage: python tools/profile_convert.py wide.tsv out_dir/
Wide format: first token = profile label, remaining = weights; time axis is
reconstructed as 15-min slots from 05:00, wrapping to 28:00 clock.
"""
import csv, sys
from pathlib import Path

def slots(n, start_h=5, step_min=15):
    out = []
    t = start_h * 60
    for _ in range(n):
        out.append(t)                      # minutes from midnight, may exceed 1440 after wrap
        t += step_min
        if t >= 24 * 60 and out[0] > 0:    # wrap onto the 24-31h clock so time stays monotone
            pass
    # monotone I/O clock: once we pass midnight, keep counting (24:00 -> 28:00)
    mono, seen_wrap = [], False
    prev = None
    for m in out:
        mm = m % (24 * 60)
        if prev is not None and mm < prev:
            seen_wrap = True
        prev = mm
        mono.append(mm + (24 * 60 if seen_wrap else 0))
    return mono

def fmt(m):
    return f"{m // 60:02d}:{m % 60:02d}:00"

def main(src, outdir):
    outdir = Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    rows = [l.split('\t') for l in Path(src).read_text().strip().split('\n')]
    n = len(rows[0]) - 1
    grid = slots(n)
    expected = 24 * 4
    audit, long_rows = [], []
    for r in rows:
        pid, vals = r[0], [float(x) for x in r[1:]]
        s = sum(vals)
        audit.append({'profile_id': pid, 'n_bins': len(vals), 'expected_bins': expected,
                      'missing_bins': expected - len(vals), 'raw_sum': round(s, 6),
                      'gap_to_1': round(1 - s, 6), 'normalization_factor': round(1 / s, 9),
                      'status': 'PASS' if abs(s - 1) <= 1e-6 and len(vals) == expected else 'REPAIRED'})
        for m, w in zip(grid, vals):
            long_rows.append({'profile_id': pid, 'scope_type': 'agent_type', 'scope_id': pid,
                              'departure_time': fmt(m), 'bin_width_sec': 900,
                              'weight_raw': w, 'weight': w / s,
                              'profile_source': 'chicago_sketch_settings_yml'})
    with open(outdir / 'departure_profile_long.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(long_rows[0])); w.writeheader(); w.writerows(long_rows)
    with open(outdir / 'profile_audit.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(audit[0])); w.writeheader(); w.writerows(audit)
    for a in audit:
        print(a)

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])

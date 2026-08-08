"""F03b Time Contract Audit prototype — design artifact, NOT engine code.

Reads the proposed three-layer schema (demand period registry, 24-hour
departure profile library, period x agent x profile binding) and prints the
per-period audit for human review. No vehicles are generated. Deterministic.

Layer-4 math (the frozen contract):
    S_r        = sum of raw 24h weights whose bin start lies in [start, end)
    p~_{r,k}   = p_k / S_r                    (conditional, sums to 1)
    D_{r,k}    = D_r * p~_{r,k}               (allocated demand, sums to D_r)
"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
# 24h profile library: the FHWA Alexandria TRANSIMS set (raw weights)
PROFILE_LIB = os.path.join(
    HERE, "..", "..", "..", "..",
    "consensus_datasets", "sample_departure_profiles_long.csv")
S_R_FLOOR = 1e-3
PERIOD_DEMAND = 1000.0  # illustrative D_r for every (period, agent)


def to_min(hhmm):
    parts = hhmm.split(":")
    return int(parts[0]) * 60 + int(parts[1]) + (int(parts[2]) / 60 if len(parts) > 2 else 0)


def fmt_clock(minutes):
    return f"{int(minutes) // 60:02d}:{int(minutes) % 60:02d}"


# Layer 1: registry
periods = []
with open(os.path.join(HERE, "demand_period.csv"), newline="") as f:
    for row in csv.DictReader(f):
        periods.append({
            "id": row["period_id"], "label": row["label"],
            "start": to_min(row["start_time"]), "end": to_min(row["end_time"]),
            "active": row["active"].strip() == "1",
        })

# Layer 2: 24h library (raw weights; full-day sum audited, never per-window)
profiles = {}
with open(PROFILE_LIB, newline="") as f:
    for row in csv.DictReader(f):
        profiles.setdefault(row["profile_id"], []).append(
            (to_min(row["departure_time"]), float(row["bin_width_sec"]) / 60,
             float(row["weight_raw"])))
for pid in profiles:
    profiles[pid].sort()

# Layer 3: binding
bindings = []
with open(os.path.join(HERE, "departure_profile_binding.csv"), newline="") as f:
    bindings = list(csv.DictReader(f))

print("=" * 72)
print("F03b TIME CONTRACT AUDIT  (human review; becomes G5 only after sign-off)")
print("=" * 72)

for pid, bins in sorted(profiles.items()):
    total = sum(w for _, _, w in bins)
    covered = 0.0
    for start, _, w in bins:
        clock = start % 1440  # fold the monotone clock back to time of day
        if any(p["start"] <= clock < p["end"] for p in periods):
            covered += w
    print(f"profile {pid:12s}  full-day sum = {total:.6f}   "
          f"uncovered mass (outside all periods) = {total - covered:.6f}")

for p in periods:
    print()
    print(f"Period: {p['id']} / {p['label']:3s}   "
          f"Window: {fmt_clock(p['start'])}-{fmt_clock(p['end'])}   "
          f"active: {'yes' if p['active'] else 'no'}")
    for b in bindings:
        if b["period_id"] != p["id"]:
            continue
        bins = profiles[b["profile_id"]]
        # clip: bin start (folded to time of day) inside the half-open window
        window = [(s, wd, w) for s, wd, w in bins if p["start"] <= s % 1440 < p["end"]]
        s_r = sum(w for _, _, w in window)
        status = "OK" if s_r >= S_R_FLOOR else "FAIL (below S_r floor)"
        print(f"  Agent: {b['agent_type']:6s} Profile: {b['profile_id']}")
        print(f"    Raw profile mass in window   S_r = {s_r:.6f}   [{status}]")
        if s_r < S_R_FLOOR:
            continue
        cond = [(s, wd, w / s_r) for s, wd, w in window]
        cond_sum = sum(w for _, _, w in cond)
        alloc = sum(PERIOD_DEMAND * w for _, _, w in cond)
        earliest = min(s % 1440 for s, _, _ in cond)
        latest = max(s % 1440 for s, _, _ in cond)
        print(f"    Conditional weight sum           = {cond_sum:.6f}")
        print(f"    Period demand                    = {PERIOD_DEMAND:.0f}")
        print(f"    Allocated demand                 = {alloc:.6f}")
        print(f"    Earliest departure bin           = {fmt_clock(earliest)}")
        print(f"    Latest departure bin start       = {fmt_clock(latest)}  (< {fmt_clock(p['end'])}: "
              f"{'yes' if latest < p['end'] else 'NO - VIOLATION'})")

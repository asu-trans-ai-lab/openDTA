# F03b — Time Contract Freeze (design only, no source-code modification)

**Status: DESIGN FOR REVIEW. No engine code changes until this contract is
approved.** `setup_agents()`, vehicle generation, `simulation.cpp`, and the DNL
are untouched. F04 is blocked behind this review.

## Why F03 as implemented is too narrow

F03 passes its gates, but its contract couples two orthogonal concepts:

- it requires `period_id` on every row of `departure_profile.csv`, and
- it requires the weights **inside each period** to sum to 1.

That makes a profile a per-period object. The consequence: switching AM→PM, or
swapping profiles on the same period, forces regenerating CSV rows instead of
flipping a binding. The frozen principle going forward:

```
Demand Period  ≠  Departure-Time Profile
```

## The four-layer time structure

### Layer 1 — Demand Period Registry (from TAPLite/CBI2)

The assignment-side demand definition. Stable names, loaded in full, with an
explicit per-run **active** switch.

```csv
# demand_period.csv
period_id,label,start_time,end_time,active
P1,AM,06:00,10:00,1
P2,MD,10:00,15:00,0
P3,PM,15:00,19:00,0
P4,NT,19:00,24:00,0
```

- `period_id`: canonical integer with accepted `P<int>` alias (F02 rule).
- Labels AM/MD/PM/NT are stable vocabulary — never renamed per case.
- TAPLite/CBI2 demand is `D_od^r` keyed by these `r` only.
- A run loads **all** period definitions and activates a subset
  (`active` column, overridable by `active_periods:` in settings.yml).

### Layer 2 — Departure Profile Library (24-hour, period-free)

A profile is a full-day temporal distribution, reusable across every period.
**No `period_id` column.**

```csv
# departure_profile.csv
profile_id,departure_time,bin_width_sec,weight
HBW_SOV_PA,05:00:00,900,0.00733
HBW_SOV_PA,05:15:00,900,0.011439
...
Trucks,28:45:00,900,0.00014
```

- Monotone clock (24:00–28:45 for past-midnight bins), 05:00 horizon start.
- The G5 three-tier sum tolerance (|Σ−1| ≤ 1e-4 PASS / ≤ 2e-2 REPAIRED with
  recorded factor / else FAIL) applies to the **full-day sum only** — never to
  the mass inside any single period window.
- Reference library: the 7 FHWA Alexandria TRANSIMS profiles
  (`consensus_datasets/sample_departure_profiles_long.csv`, provenance frozen
  from `sample_departure_time_profiles.xlsx` sheet 5.References). These files
  and the Chicago audit files are the contract-freeze evidence base.

### Layer 3 — Binding / switch

The only place the two worlds meet:

```csv
# departure_profile_binding.csv
period_id,agent_type,profile_id
P1,car,HBW_SOV_PA
P1,truck,Trucks
P3,car,PM_peak_01
```

Lookup: `(period, agent_type)` → `(period, *)` → uniform fallback.
Swapping a profile or activating a different period changes **one line here**
— demand `D^r`, the profile library, and the code all stay fixed.

### Layer 4 — What the DNL actually consumes: conditional distributions

Given full-day weights `p_k` (Σ_k p_k = 1) and period window `W_r`:

```
S_r        = Σ_{k ∈ W_r} p_k          (raw profile mass inside the window)
p̃_{r,k}   = p_k / S_r                 (conditional distribution, Σ = 1)
D_{od,r,k} = D_od^r · p̃_{r,k}         (period demand allocated to bins)
```

Invariants:

- Σ_{k∈W_r} p̃_{r,k} = 1 **by construction** — renormalization inside the
  window, never a requirement on the raw profile;
- Σ_{k∈W_r} D_{od,r,k} = D_od^r exactly (demand conservation);
- cumulative loading F_r(t) = Σ_{τ≤t} p̃_{r,τ} rises 0→1 inside the window;
  A_r(t) = D_r · F_r(t) is the cumulative arrival the DNL sees.

Guard: S_r below a floor (proposed 1e-3) is a hard error — binding a profile
to a window where it has essentially no mass is a modeling mistake, and
renormalizing noise would silently manufacture a fake distribution.

Bin/window overlap rule: a bin belongs to `W_r` if its **start time** lies in
`[start, end)` (half-open, consistent with I-half-open elsewhere). Partial-bin
splitting is explicitly out of scope for the freeze — bins are 15 min and
period boundaries in the registry fall on bin edges; the audit checks this
alignment and errors on misalignment rather than silently splitting.

Full pipeline this freezes:

```
D_od^r → profile_id (binding) → p(t) [24h] → clip to W_r → p̃_r → F_r(t) → A_r(t) → vehicles → DNL
```

## The audit that must be eyeballed before it becomes G5

One plain **Time Contract Audit** per (active or not) period — printed for
human review first; only after AM, MD, PM, NT have each been read and
understood does this become the automated G5. Format:

```
Period: P1 / AM        Window: 06:00–10:00     active: yes
  Agent: car           Profile: HBW_SOV_PA
  Raw profile mass inside window  S_r = 0.XXXXXX
  Conditional weight sum              = 1.000000
  Period demand                       = 1000
  Allocated demand                    = 1000.000000
  Earliest departure bin              = 06:00
  Latest departure bin start          < 10:00
```

Plus one global line per profile: `uncovered mass` — the raw weight falling in
no registered period (e.g. 00:00–06:00) — printed, never silently dropped.

## Sanity gates after the contract stabilizes (in this order, all human-checked)

1. Demand allocation only (no vehicles): the audit above, four periods.
2. Single-link loading: same D=1000, same μ(t), three different profiles —
   total loaded must stay exactly 1000; loading curve / peak queue / onset /
   clearance / delay **must differ**. Identical cumulative curves across
   different profiles ⇒ wrong. Total ≠ 1000 ⇒ wrong. AM vehicles appearing
   in PM ⇒ wrong.
3. Single-link queue → two-link tandem → two-corridor → Chicago Sketch.
   Never the reverse: Chicago running proves nothing about loading.

## Migration notes (for the later, separately-approved implementation change)

- The engine's F03 reader currently enforces per-window Σ=1 and requires
  `period_id` in the CSV. That format becomes **transitional**: the final
  reader consumes the Layer-2 library + Layer-3 binding and computes Layer-4
  conditionals. Whether the transitional format stays accepted for one release
  is a review decision, not an implementer default.
- `dev/test/f03/` fixtures remain valid as parser tests; the g1_cross and
  transims fixtures will be re-expressed against the new contract when the
  reader changes.
- Gold cases keep their own `departure_profile.csv` + binding files; the gold
  tools already implement the fallback hierarchy — reconcile the C++ reader to
  THAT, not the other way around.

## Explicitly frozen decisions

1. Demand periods and departure profiles are separate registries joined only
   by the binding table.
2. Full-day profiles sum to 1 over 24h; per-period conditionals are derived by
   clip + renormalize. **Never require per-window raw sums of 1.**
3. Period vocabulary (P1/AM … P4/NT) is stable; runs select active periods,
   they do not redefine periods.
4. Uncovered profile mass is reported, never silently dropped or silently
   reallocated.
5. No vehicle is generated until the four-period audit has been human-reviewed.
